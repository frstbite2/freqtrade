"""One lock for all SEC ingestion, shared by every process.

SEC asks clients to stay under 10 requests a second. Each process spaces its own requests (8 a
second, `backend/core/http.py`), but two processes together would double that. So every process
that contacts SEC (the worker, and the ingest and verify commands) first takes this lock: only one
process talks to SEC at a time, and the combined rate never exceeds one process's. The same lock
stops two workers from running jobs at the same time. `EdgarClient` refuses to send a real request
unless this process holds the lock.

- PostgreSQL: a session advisory lock on a connection of its own. The server drops the lock the
  moment that connection ends, so a crashed or killed process frees it at once. If a process's
  host vanishes without closing the connection, TCP keepalives (client side in `make_engine`,
  server side in docker-compose.platform.yml) end it within about a minute.
- SQLite, for local development: an operating-system lock on `<database file>.ingest-lock`, which
  the OS releases when the process ends. It only coordinates processes on the same machine using
  the same database file, and network file systems (NFS, SMB) may not honour it. An in-memory
  database uses a lock file in the system's temporary directory.
"""

import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from sqlalchemy import Connection, Engine, text


_held = 0  # locks this process holds now
_held_guard = threading.Lock()


def held() -> bool:
    """Whether this process holds the SEC ingestion lock."""
    return _held > 0


class LockLost(Exception):
    """The lock's database connection ended, so another process may now take the lock."""


class IngestionLock:
    KEY = 7_203_146  # any constant; must differ from the migration lock in migrations/env.py

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._connection: Connection | None = None
        self._file: IO[bytes] | None = None

    def acquire(
        self,
        wait: bool = True,
        poll: float = 1.0,
        on_wait: Callable[[], object] | None = None,
        stop: threading.Event | None = None,
    ) -> bool:
        """Take the lock. With `wait`, try every `poll` seconds until it is free (calling
        `on_wait` once, so the caller can say why it is waiting) or `stop` is set."""
        told = False
        while not self._try():
            if not wait or (stop is not None and stop.is_set()):
                return False
            if on_wait is not None and not told:
                on_wait()
                told = True
            time.sleep(poll)
        global _held
        with _held_guard:
            _held += 1
        return True

    def check(self) -> None:
        """Raise LockLost if the lock is no longer held (its database connection ended)."""
        if self._connection is None:
            return  # a file lock lasts as long as this process
        try:
            still = self._connection.execute(
                text(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted "
                    "AND pid = pg_backend_pid() AND classid = 0 AND objid = :key"
                ),
                {"key": self.KEY},
            ).scalar()
        except Exception as exc:
            raise LockLost(f"database connection ended: {type(exc).__name__}") from exc
        if not still:
            raise LockLost("the database no longer holds the lock for this connection")

    def release(self) -> None:
        global _held
        if self._connection is None and self._file is None:
            return
        try:
            if self._connection is not None:
                self._connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self.KEY})
        except Exception:  # noqa: S110  the connection is gone, and with it the lock
            pass
        finally:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            if self._file is not None:
                self._file.close()  # closing the file releases the OS lock
                self._file = None
            with _held_guard:
                _held = max(0, _held - 1)

    @staticmethod
    def holder_exists(engine: Engine) -> bool | None:
        """Whether some process holds the lock now; None where that cannot be read (SQLite)."""
        if engine.dialect.name != "postgresql":
            return None
        with engine.connect() as conn:
            return bool(
                conn.execute(
                    text(
                        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted "
                        "AND classid = 0 AND objid = :key"
                    ),
                    {"key": IngestionLock.KEY},
                ).scalar()
            )

    # --- implementations ---

    def _try(self) -> bool:
        if self._engine.dialect.name == "postgresql":
            return self._try_advisory()
        if self._engine.dialect.name == "sqlite":
            return self._try_file()
        raise RuntimeError(f"no SEC ingestion lock for {self._engine.dialect.name} databases")

    def _try_advisory(self) -> bool:
        conn = self._engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        if conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": self.KEY}).scalar():
            self._connection = conn
            return True
        conn.close()
        return False

    def _lock_path(self) -> Path:
        database = self._engine.url.database
        if not database or database == ":memory:":
            return Path(tempfile.gettempdir()) / "platform-memory.ingest-lock"
        return Path(database).with_name(Path(database).name + ".ingest-lock")

    def _try_file(self) -> bool:
        path = self._lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
        try:
            _lock_file(handle)
        except OSError:
            handle.close()
            return False
        self._file = handle
        return True


def _lock_file(handle: IO[bytes]) -> None:
    """Take an exclusive OS lock without waiting; OSError if another process has it."""
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextmanager
def sec_ingestion(engine: Engine, wait: bool = True) -> Iterator[IngestionLock]:
    """For command-line tools: hold the lock while the block runs.

    By default waits for another process to finish, saying so once; with `wait=False` (the
    `--no-wait` option) exits instead.
    """
    lock = IngestionLock(engine)

    def say_waiting() -> None:
        print(
            "Another process is ingesting from SEC; waiting for it to finish "
            "(use --no-wait to exit instead).",
            file=sys.stderr,
            flush=True,
        )

    if not lock.acquire(wait=wait, on_wait=say_waiting):
        raise SystemExit("Not started: another process is ingesting from SEC (--no-wait).")
    try:
        yield lock
    finally:
        lock.release()


def add_wait_option(parser) -> None:
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="exit at once if another process is ingesting from SEC, instead of waiting",
    )
