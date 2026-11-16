"""Scheduled job runs: history, failure reports, and the lock that prevents overlapping runs."""

from datetime import datetime

from sqlalchemy import JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base, UTCDateTime


class JobRun(Base):
    __tablename__ = "job_run"
    # `active` is True while a run is in progress and NULL afterwards. NULLs never collide in a
    # unique constraint, so the database itself allows only one running row per job.
    __table_args__ = (UniqueConstraint("job", "active"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(32), index=True)
    active: Mapped[bool | None]
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # running | succeeded | partial | failed | interrupted (shut down between targets)
    status: Mapped[str] = mapped_column(String(12))
    detail: Mapped[dict] = mapped_column(JSON)  # per-target results
    error: Mapped[str | None] = mapped_column(Text)
