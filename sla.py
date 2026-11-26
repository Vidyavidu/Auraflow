from datetime import datetime, timedelta, timezone

from models import utcnow

SLA_HOURS = {"critical": 1, "high": 4, "medium": 8, "low": 24}
AT_RISK_FRACTION = 0.25  # "at risk" in the last 25% of the time window


def due_at(urgency, start=None):
    start = start or utcnow()
    return start + timedelta(hours=SLA_HOURS.get(urgency, 8))


def hours_text(hours):
    return "1 hour" if hours == 1 else f"{hours} hours"


def _aware(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _human(delta):
    minutes = int(abs(delta.total_seconds())) // 60
    if minutes < 1:
        return "less than a minute"
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def sla_state(ticket):
    """Returns {"state": ..., "label": ...} for display."""
    if ticket.sla_due_at is None:
        return {"state": "none", "label": "No SLA"}

    due = _aware(ticket.sla_due_at)

    if ticket.status in ("resolved", "closed"):
        done = _aware(ticket.resolved_at)
        if done is None or done <= due:
            return {"state": "met", "label": "SLA met"}
        return {"state": "breached", "label": "Resolved late"}

    now = utcnow()
    if now > due:
        return {"state": "breached", "label": f"Overdue by {_human(now - due)}"}

    total = due - _aware(ticket.created_at)
    remaining = due - now
    state = "at_risk" if remaining <= total * AT_RISK_FRACTION else "on_track"
    return {"state": state, "label": f"Due in {_human(remaining)}"}