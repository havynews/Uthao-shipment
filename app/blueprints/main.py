from flask import Blueprint, render_template, jsonify, request, abort, current_app
from models import Shipment, ShipmentEvent
from extensions import db
from datetime import datetime
import traceback


main_bp = Blueprint('main', __name__)

# ── Progress mapping ──────────────────────────────────────────────────────────
STATUS_PROGRESS = {
    'Booking Created':   5,
    'Pending':          10,
    'Picked Up':        25,
    'In Transit':       50,
    'At Port':          75,
    'Customs Hold':     60,
    'Out for Delivery': 90,
    'Delivered':       100,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_tracking(raw: str) -> str:
    """Strip whitespace and uppercase — makes lookup case-insensitive."""
    return raw.strip().upper() if raw else ''


def _get_progress(shipment) -> int:
    """Return progress % from shipment.progress_percent or derive from status."""
    if hasattr(shipment, 'progress_percent') and shipment.progress_percent is not None:
        return int(shipment.progress_percent)
    return STATUS_PROGRESS.get(shipment.status, 0)


def _format_time_ago(timestamp) -> str:
    """Return a human-friendly '2 hours ago' string from a datetime."""
    if not timestamp:
        return 'Unknown'
    try:
        now = datetime.utcnow()
        if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo:
            now = datetime.now(timestamp.tzinfo)
        diff = now - timestamp
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    except Exception:
        return 'Unknown'


def _safe_iso(value) -> str | None:
    """Return ISO string from a datetime/date, or None."""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


# ── Page routes ───────────────────────────────────────────────────────────────

@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/process')
def process():
    return render_template('process.html')


@main_bp.route('/tracking')
def tracking_page():
    return render_template('tracking.html')


@main_bp.route('/tracking/details/<path:tracking_number>')
def tracking_details(tracking_number):
    try:
        tn = _normalize_tracking(tracking_number)
        if not tn:
            return render_template('tracking_details.html', shipment=None, error="Please provide a valid tracking number.")

        shipment = (
            Shipment.query
            .filter(Shipment.tracking_number.ilike(tn))
            .first()
        )

        if not shipment:
            return render_template(
                'tracking_details.html',
                shipment=None,
                error=f"No shipment found for tracking number <strong>{tn}</strong>. Please check and try again.",
                tracking_number=tn
            )

        progress = _get_progress(shipment)
        return render_template(
            'tracking_details.html',
            shipment=shipment,
            progress_percent=progress,
        )

    except Exception as e:
        current_app.logger.error(f"tracking_details error: {e}")
        current_app.logger.error(traceback.format_exc())
        return render_template(
            'tracking_details.html',
            shipment=None,
            error="Something went wrong. Please try again later."
        )


# ── API ───────────────────────────────────────────────────────────────────────

@main_bp.route('/api/track/<path:tracking_number>')
def track_shipment(tracking_number):
    """
    JSON tracking endpoint.
    Accepts any casing — UTH-123, uth-123, Uth-123 all resolve to the same shipment.
    """
    tn = _normalize_tracking(tracking_number)

    if not tn:
        return jsonify({
            'success': False,
            'message': 'Please provide a tracking ID.',
        }), 400

    # Case-insensitive lookup (works on PostgreSQL and SQLite)
    shipment = (
        Shipment.query
        .filter(Shipment.tracking_number.ilike(tn))
        .first()
    )

    if not shipment:
        return jsonify({
            'success': False,
            'error': 'Shipment not found',
            'message': 'Tracking ID not found. Please check and try again.',
        }), 404

    # Latest event
    events = getattr(shipment, 'events', []) or []
    latest_event = events[0] if events else None

    return jsonify({
        'success': True,
        'data': {
            'trackingId':       shipment.tracking_number,
            'status':           getattr(shipment, 'status', 'Pending'),
            'origin':           getattr(shipment, 'origin', 'Unknown'),
            'destination':      getattr(shipment, 'destination', 'Unknown'),
            'eta':              _safe_iso(getattr(shipment, 'estimated_delivery', None)),
            'progress':         _get_progress(shipment),
            'latestUpdate':     (
                                    latest_event.description
                                    if latest_event
                                    else getattr(shipment, 'description', 'Shipment created')
                                ),
            'updateTime':       (
                                    _format_time_ago(latest_event.timestamp)
                                    if latest_event
                                    else 'Just now'
                                ),
            'vessel':           getattr(shipment, 'vessel_name', None),
            'containerNumber':  getattr(shipment, 'container_number', None),
            'recipient': {
                'name':    getattr(shipment, 'receiver_name', ''),
                'company': getattr(shipment, 'receiver_company', ''),
            },
            'events': [
                {
                    'status':      e.status,
                    'location':    getattr(e, 'location', ''),
                    'description': e.description,
                    'timestamp':   _safe_iso(e.timestamp),
                }
                for e in events
            ],
        },
    })