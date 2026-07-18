from __future__ import annotations

from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models import AuditLog


def log_event(
    event_type: str,
    outcome: str,
    ip_address: str,
    *,
    user_id=None,
    resource_id=None,
    user_agent: str | None = None,
) -> None:
    """Append an immutable audit log entry. Never raises — failures are logged to app logger only."""
    try:
        entry = AuditLog(
            user_id=user_id,
            event_type=event_type,
            resource_id=resource_id,
            outcome=outcome,
            ip_address=ip_address or '0.0.0.0',  # nosec B104
            user_agent=(user_agent or '')[:500],
            timestamp=datetime.utcnow(),
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        current_app.logger.exception('audit log write failed: %s %s', event_type, outcome)
        db.session.rollback()
