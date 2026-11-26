from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload

from auth import login_required, role_required
from extensions import db
from models import Ticket, TicketUpdate, User, utcnow
import sla
from tickets import OPEN_STATES, can_view, describe_pick, pick_technician

workflow_bp = Blueprint("workflow", __name__)

STAFF = ("l1", "l2")  # admins manage, they do not work tickets
MAX_NOTE = 1000


# ---------- helpers ----------
def _get_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        abort(404)
    if not can_view(ticket):
        abort(403)
    return ticket


def _can_work(ticket):
    """L2 can work any ticket. L1 only their own assigned ones."""
    if g.user.role == "l2":
        return True
    return g.user.role == "l1" and ticket.assignee_id == g.user.id


def _log(ticket, kind, note):
    ticket.updates.append(TicketUpdate(author_id=g.user.id, kind=kind, note=note))


def _back(ticket):
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


def _clean_note(field, minimum=0):
    text = request.form.get(field, "").strip()
    if len(text) > MAX_NOTE:
        return None
    if len(text) < minimum:
        return None
    return text


def ticket_actions(ticket):
    """What the current user may do with this ticket. Used by templates and routes."""
    user = g.user
    actions = {
        key: False
        for key in (
            "can_start", "can_resolve", "can_escalate",
            "can_reassign", "can_rate", "can_reopen",
        )
    }
    actions["technicians"] = []
    if user is None:
        return actions

    is_open = ticket.status in OPEN_STATES
    can_work = user.role in STAFF and _can_work(ticket)
    is_requester = user.id == ticket.requester_id

    actions["can_start"] = can_work and ticket.status in ("open", "escalated")
    actions["can_resolve"] = can_work and is_open
    actions["can_escalate"] = (
        can_work and user.role == "l1" and ticket.level == 1 and is_open
    )
    actions["can_reassign"] = user.role in ("l2", "admin") and is_open
    actions["can_rate"] = (
        is_requester and ticket.status in ("resolved", "closed") and ticket.rating is None
    )
    actions["can_reopen"] = (
        is_requester and ticket.status == "resolved" and ticket.rating is None
    )

    if actions["can_reassign"]:
        actions["technicians"] = (
            User.query.filter(User.role.in_(("l1", "l2")), User.is_active.is_(True))
            .order_by(User.role, User.name)
            .all()
        )
    return actions


@workflow_bp.app_context_processor
def inject_helpers():
    return {"ticket_actions": ticket_actions}


def _guard(ticket_id, key):
    """Returns (ticket, allowed). Flashes a message when not allowed."""
    ticket = _get_ticket(ticket_id)
    if not ticket_actions(ticket)[key]:
        flash("That action is not available for this ticket right now.", "error")
        return ticket, False
    return ticket, True


def queue_counts(user):
    open_filter = Ticket.status.in_(OPEN_STATES)
    mine = Ticket.query.filter(open_filter, Ticket.assignee_id == user.id).count()
    overdue = Ticket.query.filter(
        open_filter, Ticket.assignee_id == user.id, Ticket.sla_due_at < utcnow()
    ).count()

    waiting = Ticket.query.filter(open_filter, Ticket.assignee_id.is_(None))
    if user.role == "l1":
        waiting = waiting.filter(Ticket.level == 1)
    elif user.role == "l2":
        waiting = waiting.filter(Ticket.level == 2)
    return {"mine": mine, "unassigned": waiting.count(), "overdue": overdue}


# ---------- queue ----------
@workflow_bp.route("/queue")
@role_required("l1", "l2")
def queue():
    user = g.user
    base = Ticket.query.options(
        joinedload(Ticket.requester), joinedload(Ticket.assignee)
    ).filter(Ticket.status.in_(OPEN_STATES))

    mine = (
        base.filter(Ticket.assignee_id == user.id)
        .order_by(Ticket.sla_due_at.asc())
        .all()
    )

    waiting = base.filter(Ticket.assignee_id.is_(None))
    if user.role == "l1":
        waiting = waiting.filter(Ticket.level == 1)
    else:
        waiting = waiting.filter(Ticket.level == 2)
    unassigned = waiting.order_by(Ticket.sla_due_at.asc()).all()

    others = []
    if user.role == "l2":
        others = (
            base.filter(Ticket.assignee_id.isnot(None), Ticket.assignee_id != user.id)
            .order_by(Ticket.sla_due_at.asc())
            .limit(50)
            .all()
        )

    def with_sla(items):
        return [(t, sla.sla_state(t)) for t in items]

    return render_template(
        "queue.html",
        mine=with_sla(mine),
        unassigned=with_sla(unassigned),
        others=with_sla(others),
    )


# ---------- actions ----------
@workflow_bp.route("/tickets/<int:ticket_id>/claim", methods=["POST"])
@role_required("l1", "l2")
def claim(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        abort(404)

    role = g.user.role
    level_ok = (role == "l1" and ticket.level == 1) or (role == "l2" and ticket.level == 2)
    if not level_ok or ticket.status not in OPEN_STATES:
        flash("You cannot claim that ticket.", "error")
        return redirect(url_for("workflow.queue"))

    # Atomic: only succeeds if nobody has taken it in the meantime
    taken = Ticket.query.filter(
        Ticket.id == ticket_id, Ticket.assignee_id.is_(None)
    ).update({"assignee_id": g.user.id}, synchronize_session=False)

    if not taken:
        db.session.rollback()
        flash("Someone else already took that ticket.", "info")
        return redirect(url_for("workflow.queue"))

    db.session.add(
        TicketUpdate(
            ticket_id=ticket_id,
            author_id=g.user.id,
            kind="claimed",
            note=f"{g.user.name} claimed this ticket from the queue.",
        )
    )
    db.session.commit()
    flash(f"You claimed {ticket.number}.", "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket_id))


@workflow_bp.route("/tickets/<int:ticket_id>/comment", methods=["POST"])
@login_required
def comment(ticket_id):
    ticket = _get_ticket(ticket_id)
    text = _clean_note("note", minimum=1)
    if text is None:
        flash(f"Please write a comment (up to {MAX_NOTE} characters).", "error")
        return _back(ticket)
    _log(ticket, "comment", text)
    db.session.commit()
    flash("Comment added.", "success")
    return _back(ticket)


@workflow_bp.route("/tickets/<int:ticket_id>/start", methods=["POST"])
@login_required
def start(ticket_id):
    ticket, ok = _guard(ticket_id, "can_start")
    if not ok:
        return _back(ticket)
    if ticket.assignee_id is None:
        ticket.assignee_id = g.user.id
    ticket.status = "in_progress"
    _log(ticket, "started", f"{g.user.name} started working on this ticket.")
    db.session.commit()
    flash("Marked as in progress.", "success")
    return _back(ticket)


@workflow_bp.route("/tickets/<int:ticket_id>/resolve", methods=["POST"])
@login_required
def resolve(ticket_id):
    ticket, ok = _guard(ticket_id, "can_resolve")
    if not ok:
        return _back(ticket)
    note = _clean_note("note", minimum=5)
    if note is None:
        flash(f"Please describe the fix (5 to {MAX_NOTE} characters).", "error")
        return _back(ticket)
    if ticket.assignee_id is None:
        ticket.assignee_id = g.user.id
    ticket.status = "resolved"
    ticket.resolved_at = utcnow()
    _log(ticket, "resolved", f"Resolved by {g.user.name}: {note}")
    db.session.commit()
    flash(f"{ticket.number} resolved.", "success")
    return _back(ticket)


@workflow_bp.route("/tickets/<int:ticket_id>/escalate", methods=["POST"])
@login_required
def escalate(ticket_id):
    ticket, ok = _guard(ticket_id, "can_escalate")
    if not ok:
        return _back(ticket)
    reason = _clean_note("note", minimum=5)
    if reason is None:
        flash(f"Please explain why (5 to {MAX_NOTE} characters).", "error")
        return _back(ticket)

    target, how = pick_technician("l2", ticket.category)
    ticket.level = 2
    ticket.status = "escalated"
    ticket.assignee_id = target.id if target else None

    where = (
        describe_pick(target, how, "L2", ticket.category)
        if target
        else "No L2 technician is available, so it is waiting in the L2 queue."
    )
    _log(ticket, "escalated", f"Escalated to L2 by {g.user.name}. Reason: {reason} {where}")
    db.session.commit()
    flash(f"{ticket.number} escalated to L2.", "success")

    # An L1 can no longer open the ticket once it is assigned to L2
    return redirect(url_for("workflow.queue"))


@workflow_bp.route("/tickets/<int:ticket_id>/reassign", methods=["POST"])
@login_required
def reassign(ticket_id):
    ticket, ok = _guard(ticket_id, "can_reassign")
    if not ok:
        return _back(ticket)

    try:
        target_id = int(request.form.get("assignee_id", ""))
    except ValueError:
        flash("Please choose a technician.", "error")
        return _back(ticket)

    target = db.session.get(User, target_id)
    if target is None or not target.is_active or target.role not in ("l1", "l2"):
        flash("Please choose an active L1 or L2 technician.", "error")
        return _back(ticket)
    if target.id == ticket.assignee_id:
        flash("That technician already has this ticket.", "info")
        return _back(ticket)

    note = _clean_note("note")
    if note is None:
        flash(f"The note is too long (maximum {MAX_NOTE} characters).", "error")
        return _back(ticket)

    ticket.assignee_id = target.id
    ticket.level = 2 if target.role == "l2" else 1
    ticket.status = "escalated" if ticket.level == 2 else "open"

    text = f"Reassigned to {target.name} ({target.role.upper()}) by {g.user.name}."
    if note:
        text += f" Note: {note}"
    _log(ticket, "reassigned", text)
    db.session.commit()
    flash(f"{ticket.number} reassigned to {target.name}.", "success")
    return _back(ticket)


@workflow_bp.route("/tickets/<int:ticket_id>/rate", methods=["POST"])
@login_required
def rate(ticket_id):
    ticket, ok = _guard(ticket_id, "can_rate")
    if not ok:
        return _back(ticket)
    try:
        stars = int(request.form.get("rating", ""))
    except ValueError:
        stars = 0
    if stars < 1 or stars > 5:
        flash("Please choose a rating from 1 to 5.", "error")
        return _back(ticket)
    comment_text = (request.form.get("note", "").strip())[:500]

    ticket.rating = stars
    ticket.rating_comment = comment_text or None
    text = f"{g.user.name} rated the support {stars}/5."
    if comment_text:
        text += f" Comment: {comment_text}"
    _log(ticket, "rated", text)
    db.session.commit()
    flash("Thank you for your feedback!", "success")
    return _back(ticket)


@workflow_bp.route("/tickets/<int:ticket_id>/reopen", methods=["POST"])
@login_required
def reopen(ticket_id):
    ticket, ok = _guard(ticket_id, "can_reopen")
    if not ok:
        return _back(ticket)
    reason = _clean_note("note", minimum=5)
    if reason is None:
        flash(f"Please say what is still wrong (5 to {MAX_NOTE} characters).", "error")
        return _back(ticket)

    ticket.status = "escalated" if ticket.level == 2 else "open"
    ticket.resolved_at = None
    _log(ticket, "reopened", f"Reopened by {g.user.name}. Reason: {reason}")
    db.session.commit()
    flash(f"{ticket.number} reopened.", "success")
    return _back(ticket)