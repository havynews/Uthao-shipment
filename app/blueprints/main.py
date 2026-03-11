from flask import Blueprint, render_template, jsonify, request, abort, current_app
from models import Shipment, ShipmentEvent
from extensions import db
from datetime import datetime
import traceback


main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/process')
def process():
    return render_template('process.html')

@main_bp.route('/tracking')
def tracking_page():
    return render_template('tracking.html')


# NEW: Detailed tracking page route
# routes.py


main_bp = Blueprint('main', __name__)

# Progress mapping based on status
STATUS_PROGRESS = {
    'Booking Created': 5,
    'Pending': 10,
    'Picked Up': 25,
    'In Transit': 50,
    'At Port': 75,
    'Customs Hold': 60,
    'Out for Delivery': 90,
    'Delivered': 100
}

def get_progress_from_status(status):
    """Calculate progress percentage from shipment status."""
    if not status:
        return 0
    return STATUS_PROGRESS.get(status, 0)

def _format_time_ago(timestamp):
    """Format timestamp as 'X hours/days ago'."""
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

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/process')
def process():
    return render_template('process.html')

@main_bp.route('/tracking')
def tracking_page():
    return render_template('tracking.html')


@main_bp.route('/tracking/details/<tracking_number>')
def tracking_details(tracking_number):
    """Detailed tracking page for a specific shipment."""
    try:
        tracking_number = tracking_number.strip().upper()
        
        shipment = Shipment.query.filter_by(tracking_number=tracking_number).first_or_404()
        
        # Calculate progress dynamically
        progress = get_progress_from_status(shipment.status)
        
        return render_template('tracking_details.html', shipment=shipment, progress_percent=progress)
        
    except Exception as e:
        current_app.logger.error(f"Error in tracking_details: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        abort(500)


@main_bp.route('/api/track/<tracking_number>')
def track_shipment(tracking_number):

    # Normalize tracking number
    tracking_number = tracking_number.strip().upper()

    s = Shipment.query.filter_by(tracking_number=tracking_number).first()

    if not s:
        return jsonify({
            "success": False,
            "error": "Shipment not found",
            "message": "Tracking ID not found. Please check and try again."
        }), 404

    # Get latest event for update info
    latest_event = s.events[0] if hasattr(s, 'events') and s.events else None

    # Calculate progress if not set
    progress = s.progress_percent if hasattr(s, 'progress_percent') and s.progress_percent else 0

    # Format ETA
    eta = None
    if hasattr(s, 'estimated_delivery') and s.estimated_delivery:
        eta = s.estimated_delivery.isoformat() if hasattr(s.estimated_delivery, 'isoformat') else str(s.estimated_delivery)

    return jsonify({
        "success": True,
        "data": {
            "trackingId": s.tracking_number,
            "status": s.status if hasattr(s, 'status') else 'Pending',
            "origin": s.origin if hasattr(s, 'origin') else 'Unknown',
            "destination": s.destination if hasattr(s, 'destination') else 'Unknown',
            "eta": eta,
            "progress": progress,
            "latestUpdate": latest_event.description if latest_event else (s.description if hasattr(s, 'description') else 'Shipment created'),
            "updateTime": _format_time_ago(latest_event.timestamp) if latest_event else 'Just now',
            "vessel": s.vessel_name if hasattr(s, 'vessel_name') else None,
            "containerNumber": s.container_number if hasattr(s, 'container_number') else None,
            "recipient": {
                "name": s.receiver_name if hasattr(s, 'receiver_name') else '',
                "company": s.receiver_company if hasattr(s, 'receiver_company') else ''
            },
            "events": [
                {
                    "status": e.status,
                    "location": e.location if hasattr(e, 'location') else '',
                    "description": e.description,
                    "timestamp": e.timestamp.isoformat() if hasattr(e.timestamp, 'isoformat') else str(e.timestamp)
                } for e in (s.events if hasattr(s, 'events') else [])
            ]
        }
    })

def _format_time_ago(timestamp):
    """Format timestamp as 'X hours/days ago'."""
    from datetime import datetime
    now = datetime.utcnow()
    if hasattr(timestamp, 'replace'):
        # Ensure both are naive or both are aware
        if timestamp.tzinfo:
            now = datetime.now(timestamp.tzinfo)
    diff = now - timestamp
    
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    hours = diff.seconds // 3600
    if hours > 0:
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    minutes = diff.seconds // 60
    return f"{minutes} minute{'s' if minutes > 1 else ''} ago"