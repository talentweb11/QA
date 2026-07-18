from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_

from app.models import Consent


def get_valid_consent(grantor_id, grantee_id) -> Consent | None:
    """Return the ACTIVE, unexpired Consent from grantor to grantee, or None.

    Used by household and advisor endpoints to gate access to another user's
    financial data before returning or aggregating it.
    """
    return (
        Consent.query
        .filter(
            Consent.grantor_id == grantor_id,
            Consent.grantee_id == grantee_id,
            Consent.status == 'ACTIVE',
            or_(Consent.expires_at.is_(None), Consent.expires_at > datetime.utcnow()),
        )
        .first()
    )
