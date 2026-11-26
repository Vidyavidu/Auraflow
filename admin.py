from datetime import timedelta, timezone

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func

from auth import role_required
from extensions import db
from models import ROLES, Ticket, TicketUpdate, User, utcnow
import sla
from tickets import OPEN_STATES

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

IST = timezone(timedelta(hours=5, minutes=30))
URGENCY_ORDER = ("critical", "high", "medium", "low")
STATUS_ORDER = ("open", "in_progress", "escalated", "resolved", "closed")
DONE_STATES = ("resolved", "closed")


def _bars(pairs, pretty=True):
    """pairs: [(key, count)]. Returns dicts ready for the bar chart macro."""
    top = max([count for _key, count in pairs] or [0]) or 1
    bars = []
    for key, count in pairs:
        label = str(key)
        if pretty:
            label = label.replace("_", " ").title()
        pct = max(round(count / top * 100), 3) if count else 0
        bars.append({"key": str(key), "label": label, "count": count, "pct": pct})
    return bars


def _ordered(rows, order):
    counts = {key: count for key, count in rows}
    pairs = [(key, counts.get(key, 0)) for key in order]
    pairs += [(k, c) for k, c in counts.items() if k not in order]
    return pairs


def build_stats():
    now = utcnow()
    open_filter = Ticket.status.in_(OPEN_STATES)

    total = Ticket.query.count()
    open_count = Ticket.query.filter(open_filter).count()
    overdue = Ticket.query.filter(open_filter, Ticket.sla_due_at < now).count()
    unassigned = Ticket.query.filter(open_filter, Ticket.assignee_id.is_(None)).count()

    by_urgency = _ordered(
        db.session.query(Ticket.urgency, func.count(Ticket.id))
        .group_by(Ticket.urgency)
        .all(),
        URGENCY_ORDER,
    )
    by_status = _ordered(
        db.session.query(Ticket.status, func.count(Ticket.id))
        .group_by(Ticket.status)
        .all(),
        STATUS_ORDER,
    )
    by_category = sorted(
        db.session.query(Ticket.category, func.count(Ticket.id))
        .group_by(Ticket.category)
        .all(),
        key=lambda row: -row[1],
    )

    # SLA compliance and resolution time (resolved tickets only)
    done = (
        db.session.query(Ticket.created_at, Ticket.resolved_at, Ticket.sla_due_at)
        .filter(Ticket.status.in_(DONE_STATES), Ticket.resolved_at.isnot(None))
        .all()
    )
    met = 0
    hours_total = 0.0
    for created, resolved, due in done:
        created = sla._aware(created)
        resolved = sla._aware(resolved)
        due = sla._aware(due)
        hours_total += (resolved - created).total_seconds() / 3600
        if due is None or resolved <= due:
            met += 1
    sla_compliance = round(met / len(done) * 100) if done else None
    avg_hours = round(hours_total / len(done), 1) if done else None

    # Last 7 days (by IST date)
    today = now.astimezone(IST).date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    per_day = {d: 0 for d in days}
    since = now - timedelta(days=8)
    for (created,) in db.session.query(Ticket.created_at).filter(Ticket.created_at >= since).all():
        day = sla._aware(created).astimezone(IST).date()
        if day in per_day:
            per_day[day] += 1
    last7 = [(d.strftime("%a %d %b"), per_day[d]) for d in days]

    # Ratings
    avg_rating, rated_count = db.session.query(
        func.avg(Ticket.rating), func.count(Ticket.rating)
    ).filter(Ticket.rating.isnot(None)).one()
    avg_rating = round(float(avg_rating), 2) if avg_rating is not None else None
    rating_counts = dict(
        db.session.query(Ticket.rating, func.count(Ticket.id))
        .filter(Ticket.rating.isnot(None))
        .group_by(Ticket.rating)
        .all()
    )
    rating_pairs = [(f"{n} star" + ("" if n == 1 else "s"), rating_counts.get(n, 0)) for n in (5, 4, 3, 2, 1)]

    # Technician table
    techs = (
        User.query.filter(User.role.in_(("l1", "l2")), User.is_active.is_(True))
        .order_by(User.role, User.name)
        .all()
    )
    open_by = dict(
        db.session.query(Ticket.assignee_id, func.count(Ticket.id))
        .filter(open_filter, Ticket.assignee_id.isnot(None))
        .group_by(Ticket.assignee_id)
        .all()
    )
    solved_by = dict(
        db.session.query(Ticket.assignee_id, func.count(Ticket.id))
        .filter(Ticket.status.in_(DONE_STATES), Ticket.assignee_id.isnot(None))
        .group_by(Ticket.assignee_id)
        .all()
    )
    rating_by = {
        uid: (float(avg), cnt)
        for uid, avg, cnt in db.session.query(
            Ticket.assignee_id, func.avg(Ticket.rating), func.count(Ticket.rating)
        )
        .filter(Ticket.rating.isnot(None), Ticket.assignee_id.isnot(None))
        .group_by(Ticket.assignee_id)
        .all()
    }
    tech_rows = []
    for tech in techs:
        avg, cnt = rating_by.get(tech.id, (None, 0))
        tech_rows.append(
            {
                "name": tech.name,
                "role": tech.role.upper(),
                "open": open_by.get(tech.id, 0),
                "solved": solved_by.get(tech.id, 0),
                "rating": round(avg, 2) if avg is not None else None,
                "rated": cnt,
            }
        )

    return {
        "total": total,
        "open": open_count,
        "overdue": overdue,
        "unassigned": unassigned,
        "resolved_total": len(done),
        "sla_compliance": sla_compliance,
        "avg_hours": avg_hours,
        "avg_rating": avg_rating,
        "rated_count": rated_count,
        "by_urgency": _bars(by_urgency),
        "by_status": _bars(by_status),
        "by_category": _bars(by_category, pretty=False),
        "last7": _bars(last7, pretty=False),
        "ratings": _bars(rating_pairs, pretty=False),
        "techs": tech_rows,
    }


@admin_bp.route("")
@role_required("admin")
def analytics():
    return render_template("admin_dashboard.html", s=build_stats())


@admin_bp.route("/users")
@role_required("admin")
def users():
    open_by = dict(
        db.session.query(Ticket.assignee_id, func.count(Ticket.id))
        .filter(Ticket.status.in_(OPEN_STATES), Ticket.assignee_id.isnot(None))
        .group_by(Ticket.assignee_id)
        .all()
    )
    rows = [(u, open_by.get(u.id, 0)) for u in User.query.order_by(User.id).all()]
    return render_template("admin_users.html", rows=rows, roles=ROLES)


@admin_bp.route("/users/<int:user_id>/role", methods=["POST"])
@role_required("admin")
def change_role(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        abort(404)
    if target.id == g.user.id:
        flash("You cannot change your own role.", "error")
        return redirect(url_for("admin.users"))

    new_role = request.form.get("role", "")
    if new_role not in ROLES:
        flash("Please choose a valid role.", "error")
        return redirect(url_for("admin.users"))
    if new_role == target.role:
        flash("That user already has this role.", "info")
        return redirect(url_for("admin.users"))

    open_assigned = Ticket.query.filter(
        Ticket.assignee_id == target.id, Ticket.status.in_(OPEN_STATES)
    ).count()
    if open_assigned:
        flash(
            f"{target.name} has {open_assigned} open ticket(s). "
            "Reassign them first, then change the role.",
            "error",
        )
        return redirect(url_for("admin.users"))

    old_role = target.role
    target.role = new_role
    db.session.commit()
    flash(f"{target.name} changed from {old_role.upper()} to {new_role.upper()}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_active(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        abort(404)
    if target.id == g.user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.users"))

    if target.is_active:
        target.is_active = False
        released = Ticket.query.filter(
            Ticket.assignee_id == target.id, Ticket.status.in_(OPEN_STATES)
        ).all()
        for ticket in released:
            ticket.assignee_id = None
            ticket.updates.append(
                TicketUpdate(
                    author_id=g.user.id,
                    kind="unassigned",
                    note=f"Unassigned because {target.name} was deactivated. Waiting in the queue.",
                )
            )
        db.session.commit()
        extra = f" {len(released)} open ticket(s) returned to the queue." if released else ""
        flash(f"{target.name} deactivated.{extra}", "success")
    else:
        target.is_active = True
        db.session.commit()
        flash(f"{target.name} reactivated.", "success")
    return redirect(url_for("admin.users"))