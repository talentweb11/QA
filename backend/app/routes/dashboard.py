from __future__ import annotations

from flask import Blueprint, g, jsonify

from app.middleware.auth import require_auth, require_role
from app.services.analytics import full_analytics

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')

# FR-08: GET /api/dashboard
#   Three SQL-aggregated datasets for the current user (category spend, 6-month
#   trend, top merchants). Amounts are stored unencrypted (decision D-03)
#   specifically so SUM can run in the database — nothing here decrypts anything.
#
# NOTE — refactored: this route previously re-implemented the aggregation +
# date helpers inline, duplicating services/analytics.py (the coordinated dedup
# flagged in analytics.py and devplan FR-15). It now delegates to
# analytics.full_analytics(), the single source of truth shared with the
# household summary (FR-15) and advisor analytics (FR-16). The JSON response is
# unchanged. If the dashboard later needs owner-only fields (e.g. total balance),
# add them on top of this shared payload rather than re-forking the aggregation.


# ---------------------------------------------------------------------------
# GET /api/dashboard — spending analytics for the current user
# ---------------------------------------------------------------------------

@dashboard_bp.get('')
@require_auth
@require_role('INDIVIDUAL')
def get_dashboard():
    return jsonify(full_analytics(g.current_user.id)), 200
