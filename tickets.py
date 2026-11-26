import uuid
from datetime import timedelta

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from auth import login_required
from extensions import db
from models import Article, ChatMessage, Ticket, TicketUpdate, User, utcnow
import sla
import urgency

tickets_bp = Blueprint("tickets", __name__)

OPEN_STATES = ("open", "in_progress", "escalated")
MAX_TITLE = 200
MAX_DESCRIPTION = 2000


def pick_l1_technician():
    """Active L1 technician with the fewest open tickets (ties: lowest id)."""
    return (
        db.session.query(User)
        .outerjoin(
            Ticket,
            (Ticket.assignee_id == User.id) & Ticket.status.in_(OPEN_STATES),
        )
        .filter(User.role == "l1", User.is_active.is_(True))
        .group_by(User.id)
        .order_by(func.count(Ticket.id).asc(), User.id.asc())
        .first()
    )


def create_ticket(requester, title, description, category="General",
                  article=None, source_note=None, signal_text=None):
    """Returns (ticket, created). created is False for a quick duplicate."""
    title = title.strip()[:MAX_TITLE]

    # Guard against double clicks: same user and title within 2 minutes
    recent = utcnow() - timedelta(minutes=2)
    existing = Ticket.query.filter(
        Ticket.requester_id == requester.id,
        Ticket.title == title,
        Ticket.created_at >= recent,
    ).first()
    if existing:
        return existing, False

    base = article.default_urgency if article else "medium"
    level, reasons = urgency.detect_urgency(signal_text or description, base)

    now = utcnow()
    ticket = Ticket(
        number="TMP-" + uuid.uuid4().hex[:12],  # replaced right after the flush
        title=title,
        description=description,
        category=category,
        urgency=level,
        status="open",
        level=1,
        requester_id=requester.id,
        article_id=article.id if article else None,
        sla_due_at=sla.due_at(level, now),
        created_at=now,
    )

    assignee = pick_l1_technician()
    if assignee:
        ticket.assignee_id = assignee.id

    db.session.add(ticket)
    db.session.flush()
    ticket.number = f"INC{ticket.id:07d}"

    hours = sla.SLA_HOURS[level]
    note = (source_note + " " if source_note else "") + (
        f"Urgency set to {level.upper()} ({'; '.join(reasons)}). "
        f"SLA target: {sla.hours_text(hours)}."
    )
    ticket.updates.append(
        TicketUpdate(author_id=requester.id, kind="created", note=note)
    )

    if assignee:
        assign_note = f"Auto-assigned to {assignee.name} (L1)."
    else:
        assign_note = "No L1 technician is available. Ticket is waiting in the unassigned queue."
    ticket.updates.append(TicketUpdate(author_id=None, kind="assigned", note=assign_note))

    db.session.commit()
    return ticket, True


def can_view(ticket):
    user = g.user
    if user.role in ("admin", "l2"):
        return True
    return user.id in (ticket.requester_id, ticket.assignee_id)


def _categories():
    rows = (
        db.session.query(Article.category)
        .filter(Article.is_published.is_(True))
        .distinct()
        .all()
    )
    names = {r[0] for r in rows}
    names.discard("General")
    return sorted(names) + ["General"]


# ---------- Chat uses this endpoint ----------
@tickets_bp.route("/api/tickets", methods=["POST"])
@login_required
def api_create_ticket():
    data = request.get_json(silent=True) or {}
    description = str(data.get("description", "")).strip()

    if not description:
        return jsonify(error="Please describe the problem first."), 400
    if len(description) > MAX_DESCRIPTION:
        return jsonify(error="The description is too long."), 400

    article = None
    raw_id = data.get("article_id")
    if isinstance(raw_id, int) and not isinstance(raw_id, bool):
        article = db.session.get(Article, raw_id)

    if article:
        title = article.title
        category = article.category
        source_note = f'Raised from chat after the suggested fix "{article.title}" did not work.'
    else:
        title = " ".join(description.split())[:80]
        category = "General"
        source_note = "Raised from chat. The assistant could not find a matching fix."

    ticket, created = create_ticket(
        g.user, title, description, category, article, source_note
    )

    assignee = ticket.assignee
    hours = sla.SLA_HOURS.get(ticket.urgency, 8)

    if created:
        who = (
            f"It has been assigned to {assignee.name}."
            if assignee
            else "It is waiting in the queue for a technician."
        )
        message = (
            f"Ticket {ticket.number} raised. Urgency: {ticket.urgency.upper()}. "
            f"{who} Target resolution: within {sla.hours_text(hours)}."
        )
        db.session.add(
            ChatMessage(user_id=g.user.id, sender="bot", message=message)
        )
        db.session.commit()
    else:
        message = f"You already raised ticket {ticket.number} a moment ago, so I did not create another one."

    return (
        jsonify(
            id=ticket.id,
            number=ticket.number,
            urgency=ticket.urgency,
            assignee=assignee.name if assignee else None,
            sla_hours=hours,
            message=message,
            url=url_for("tickets.ticket_detail", ticket_id=ticket.id),
            existing=not created,
        ),
        201 if created else 200,
    )


# ---------- Pages ----------
@tickets_bp.route("/tickets")
@login_required
def ticket_list():
    query = Ticket.query.options(
        joinedload(Ticket.requester), joinedload(Ticket.assignee)
    )

    if g.user.role in ("l2", "admin"):
        scope = "All tickets"
    else:
        query = query.filter(
            or_(Ticket.requester_id == g.user.id, Ticket.assignee_id == g.user.id)
        )
        scope = "My tickets" if g.user.role == "employee" else "Assigned to me or raised by me"

    tickets = query.order_by(Ticket.id.desc()).limit(100).all()
    rows = [(t, sla.sla_state(t)) for t in tickets]
    return render_template("tickets.html", rows=rows, scope=scope)


@tickets_bp.route("/tickets/new", methods=["GET", "POST"])
@login_required
def ticket_new():
    categories = _categories()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "General")
        if category not in categories:
            category = "General"

        error = None
        if len(title) < 3 or len(title) > MAX_TITLE:
            error = "Please enter a short title (3 to 200 characters)."
        elif len(description) < 10:
            error = "Please describe the problem in at least 10 characters."
        elif len(description) > MAX_DESCRIPTION:
            error = "The description is too long (2000 characters maximum)."

        if error:
            flash(error, "error")
            return render_template(
                "ticket_new.html",
                categories=categories,
                title=title,
                description=description,
                category=category,
            ), 400

        ticket, created = create_ticket(
            g.user,
            title,
            description,
            category,
            source_note="Raised from the ticket form.",
            signal_text=f"{title}. {description}",
        )
        if created:
            flash(f"Ticket {ticket.number} created.", "success")
        else:
            flash(f"You already raised {ticket.number} a moment ago.", "info")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    return render_template(
        "ticket_new.html", categories=categories, title="", description="", category="General"
    )


@tickets_bp.route("/tickets/<int:ticket_id>")
@login_required
def ticket_detail(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        abort(404)
    if not can_view(ticket):
        abort(403)
    return render_template(
        "ticket_detail.html", ticket=ticket, sla=sla.sla_state(ticket)
    )