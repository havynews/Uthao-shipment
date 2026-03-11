from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.models import db, Notification, User

logger = logging.getLogger(__name__)

VALID_TYPES = {
    'system', 'billing', 'shipment', 'shipment_delivered', 'shipment_transit',
    'payment_success', 'payment_failed', 'plan_change', 'support',
    'ticket_reply', 'promotional', 'security',
}

VALID_PRIORITIES = {'low', 'normal', 'high', 'urgent'}

# ─────────────────────────────────────────────
# Core helper
# ─────────────────────────────────────────────

def create_notification(user_id: int, title: str, message: str, notification_type: str = 'system', *, related_shipment_id: Optional[int] = None, related_ticket_id: Optional[int] = None, link: Optional[str] = None, priority: str = 'normal', commit: bool = True):
    """
    Create and persist a Notification for a user.

    Parameters
    ----------
    user_id              : ID of the recipient user (required).
    title                : Short heading shown in the notification bell (max 200 chars).
    message              : Body text of the notification (max 1000 chars).
    notification_type    : Category string. Must be one of VALID_TYPES;
                           falls back to 'system' if unknown.
    related_shipment_id  : Optional FK to Shipment — used for deep-linking.
    related_ticket_id    : Optional FK to SupportTicket.
    link                 : URL the user is taken to when they click the notification.
    priority             : 'low' | 'normal' | 'high' | 'urgent'
    commit               : If True (default) the session is committed immediately.
                           Pass False when you are batching multiple DB writes and
                           will commit yourself.

    Returns
    -------
    The saved Notification instance, or None if creation failed.

    Raises
    ------
    Does NOT raise — errors are logged and None is returned so callers
    never crash just because a notification failed to send.
    """

    # ── Input guards ──────────────────────────────────────────────────────────
    if not user_id:
        logger.warning('create_notification called with no user_id — skipped.')
        return None

    if not title or not title.strip():
        logger.warning('create_notification called with empty title — skipped.')
        return None

    if not message or not message.strip():
        logger.warning('create_notification called with empty message — skipped.')
        return None

    # Sanitise / clamp values
    title   = title.strip()[:200]
    message = message.strip()[:1000]

    if notification_type not in VALID_TYPES:
        logger.warning(
            "Unknown notification_type '%s' — falling back to 'system'.",
            notification_type,
        )
        notification_type = 'system'

    if priority not in VALID_PRIORITIES:
        logger.warning(
            "Unknown priority '%s' — falling back to 'normal'.", priority
        )
        priority = 'normal'

    # ── Check user exists ─────────────────────────────────────────────────────
    user = User.query.get(user_id)
    if not user:
        logger.error(
            'create_notification: user %s not found — notification dropped.', user_id
        )
        return None

    if not user.is_active:
        logger.info(
            'create_notification: user %s is inactive — notification still created.',
            user_id,
        )
        # We still create it; if the account is reactivated they'll see it.

    # ── Build the record ──────────────────────────────────────────────────────
    try:
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            related_shipment_id=related_shipment_id,
            related_ticket_id=related_ticket_id,
            link=link,
            priority=priority,
            is_read=False,
            is_archived=False,
            created_at=datetime.utcnow(),
        )

        db.session.add(notification)

        if commit:
            db.session.commit()
            logger.info(
                'Notification #%s created for user %s [%s / %s]: "%s"',
                notification.id,
                user_id,
                notification_type,
                priority,
                title,
            )

        return notification

    except Exception as exc:
        db.session.rollback()
        logger.error(
            'Failed to create notification for user %s: %s',
            user_id,
            exc,
            exc_info=True,
        )
        return None


# ─────────────────────────────────────────────
# Convenience wrappers
# ─────────────────────────────────────────────

def notify_shipment_update(shipment, new_status: str) -> Optional[Notification]:
    """
    Notify a user that their shipment status has changed.

    Usage
    -----
        from notifications import notify_shipment_update
        notify_shipment_update(shipment, 'Out for Delivery')
    """
    from flask import url_for

    status_lower = new_status.lower().replace(' ', '_')
    notif_type   = f'shipment_{status_lower}'
    if notif_type not in VALID_TYPES:
        notif_type = 'shipment'

    priority = 'high' if new_status.lower() in ('delivered', 'out for delivery') else 'normal'

    try:
        link = url_for('user.tracking', q=shipment.tracking_number)
    except RuntimeError:
        # Outside of request context (e.g. background task)
        link = f'/tracking?q={shipment.tracking_number}'

    return create_notification(
        user_id=shipment.user_id,
        title=f'Shipment {new_status}',
        message=(
            f'Your shipment {shipment.tracking_number} is now '
            f'{new_status}.'
        ),
        notification_type=notif_type,
        related_shipment_id=shipment.id,
        link=link,
        priority=priority,
    )


def notify_ticket_reply(ticket, reply) -> Optional[Notification]:
    """
    Notify the ticket owner that a staff member replied.

    Usage
    -----
        from notifications import notify_ticket_reply
        notify_ticket_reply(ticket, reply)
    """
    if not reply.is_staff:
        # Only notify the user on staff replies; staff notifs handled elsewhere.
        return None

    from flask import url_for

    try:
        link = url_for('user.view_ticket', ticket_id=ticket.id)
    except RuntimeError:
        link = f'/help/ticket/{ticket.id}'

    return create_notification(
        user_id=ticket.user_id,
        title='New Reply on Your Support Ticket',
        message=f'Support has responded to: {ticket.subject}',
        notification_type='ticket_reply',
        related_ticket_id=ticket.id,
        link=link,
        priority='normal',
    )


def notify_plan_change(user, old_plan_id: str, new_plan_id: str) -> Optional[Notification]:
    """
    Notify a user that their subscription plan has been changed.

    Usage
    -----
        from notifications import notify_plan_change
        notify_plan_change(user, 'starter', 'professional')
    """
    from models import PLANS

    old_name = PLANS.get(old_plan_id, {}).get('name', old_plan_id.title())
    new_name = PLANS.get(new_plan_id, {}).get('name', new_plan_id.title())

    is_upgrade = True  # Simple heuristic; refine if needed.
    plan_prices = {p: (PLANS[p].get('price_usd') or 0) for p in PLANS}
    if plan_prices.get(new_plan_id, 0) < plan_prices.get(old_plan_id, 0):
        is_upgrade = False

    try:
        from flask import url_for
        link = url_for('user.settings', tab='billing')
    except RuntimeError:
        link = '/settings?tab=billing'

    return create_notification(
        user_id=user.id,
        title=f'Plan {"Upgraded" if is_upgrade else "Changed"}: {new_name}',
        message=(
            f'Your subscription has been {"upgraded" if is_upgrade else "updated"} '
            f'from {old_name} to {new_name}. '
            f'{"Enjoy your new features!" if is_upgrade else "Changes take effect immediately."}'
        ),
        notification_type='plan_change',
        link=link,
        priority='high' if is_upgrade else 'normal',
    )


def notify_payment_approved(user, payment_request) -> Optional[Notification]:
    """
    Notify a user that their payment has been approved and plan activated.
    """
    try:
        from flask import url_for
        link = url_for('user.settings', tab='billing')
    except RuntimeError:
        link = '/settings?tab=billing'

    return create_notification(
        user_id=user.id,
        title='Payment Approved — Plan Activated',
        message=(
            f'Your payment of {payment_request.amount_display} for the '
            f'{payment_request.requested_plan_name} plan has been approved. '
            f'Your account has been upgraded.'
        ),
        notification_type='payment_success',
        link=link,
        priority='high',
    )


def notify_payment_rejected(user, payment_request, reason: str = '') -> Optional[Notification]:
    """
    Notify a user that their payment has been rejected.
    """
    try:
        from flask import url_for
        link = url_for('user.settings', tab='billing')
    except RuntimeError:
        link = '/settings?tab=billing'

    message = (
        f'Your payment of {payment_request.amount_display} for the '
        f'{payment_request.requested_plan_name} plan could not be verified.'
    )
    if reason:
        message += f' Reason: {reason}'
    message += ' Please contact support if you believe this is an error.'

    return create_notification(
        user_id=user.id,
        title='Payment Could Not Be Verified',
        message=message,
        notification_type='payment_failed',
        link=link,
        priority='high',
    )


def notify_bulk(
    user_ids: list[int],
    title: str,
    message: str,
    notification_type: str = 'system',
    *,
    link: Optional[str] = None,
    priority: str = 'normal',
) -> tuple[int, int]:
    """
    Send the same notification to multiple users in one go.
    Commits once at the end for efficiency.

    Returns (success_count, failure_count).

    Usage
    -----
        from notifications import notify_bulk
        ok, fail = notify_bulk(
            user_ids=[1, 2, 3],
            title='Scheduled Maintenance',
            message='We will be down for maintenance on Sunday 02:00–04:00 UTC.',
            notification_type='system',
            priority='high',
        )
    """
    success = 0
    failure = 0

    for uid in user_ids:
        result = create_notification(
            user_id=uid,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link,
            priority=priority,
            commit=False,   # batch — we commit once below
        )
        if result:
            success += 1
        else:
            failure += 1

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error('notify_bulk: commit failed: %s', exc, exc_info=True)
        return 0, len(user_ids)

    logger.info(
        'notify_bulk: sent %s notifications (%s failed) — "%s"',
        success, failure, title,
    )
    return success, failure