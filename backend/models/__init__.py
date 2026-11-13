from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.database.session import Base


class AuditLog(Base):
    """Append-only record of security- and trading-relevant actions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


def record_audit(session: Session, actor: str, action: str, **detail) -> None:
    session.add(AuditLog(actor=actor, action=action, detail=detail))
    session.commit()


from backend.models.insider import (  # noqa: E402,F401  registers the tables
    InsiderFiling,
    InsiderIssuer,
    InsiderTransaction,
)
