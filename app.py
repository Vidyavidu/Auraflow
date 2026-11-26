from datetime import timedelta, timezone

from flask import Flask, Response, g, jsonify, redirect, render_template, url_for
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from admin import admin_bp
from auth import auth_bp, login_required, role_required
from chat import chat_bp
from config import Config
from extensions import db
from kb import kb_bp
from models import Ticket, utcnow
import sla
from tickets import OPEN_STATES, scoped_query, tickets_bp
from workflow import queue_counts, workflow_bp

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(workflow_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(kb_bp)

ROLE_LABELS = {
    "employee": "Employee",
    "l1": "L1 Technician",
    "l2": "L2 Technician",
    "admin": "Administrator",
}

# Times are stored in UTC and shown in Indian Standard Time (UTC+5:30)
DISPLAY_TZ = timezone(timedelta(hours=5, minutes=30))


@app.template_filter("local_time")
def local_time(value):
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(DISPLAY_TZ).strftime("%d %b %Y, %I:%M %p") + " IST"


@app.route("/favicon.svg")
def favicon():
    return Response(render_template("_logo.html"), mimetype="image/svg+xml")


@app.route("/favicon.ico")
def favicon_ico():
    return redirect(url_for("favicon"))


@app.route("/")
def home():
    if g.user:
        return redirect(url_for("dashboard"))
    return redirect(url_for("auth.login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = g.user
    open_filter = Ticket.status.in_(OPEN_STATES)

    if user.role in ("l1", "l2"):
        c = queue_counts(user)
        tiles = [
            {"label": "In my queue", "value": c["mine"], "tone": ""},
            {"label": "Waiting for a technician", "value": c["unassigned"],
             "tone": "warn" if c["unassigned"] else ""},
            {"label": "Overdue", "value": c["overdue"],
             "tone": "bad" if c["overdue"] else ""},
        ]
    elif user.role == "admin":
        open_n = Ticket.query.filter(open_filter).count()
        unassigned = Ticket.query.filter(open_filter, Ticket.assignee_id.is_(None)).count()
        overdue = Ticket.query.filter(open_filter, Ticket.sla_due_at < utcnow()).count()
        tiles = [
            {"label": "Open tickets", "value": open_n, "tone": ""},
            {"label": "Unassigned", "value": unassigned,
             "tone": "warn" if unassigned else ""},
            {"label": "Overdue", "value": overdue, "tone": "bad" if overdue else ""},
        ]
    else:
        mine = Ticket.query.filter(Ticket.requester_id == user.id)
        total = mine.count()
        open_n = mine.filter(open_filter).count()
        tiles = [
            {"label": "My open tickets", "value": open_n, "tone": ""},
            {"label": "Resolved", "value": total - open_n, "tone": ""},
            {"label": "Total raised", "value": total, "tone": ""},
        ]

    recent = (
        scoped_query()
        .options(joinedload(Ticket.requester), joinedload(Ticket.assignee))
        .order_by(Ticket.id.desc())
        .limit(5)
        .all()
    )
    rows = [(t, sla.sla_state(t)) for t in recent]

    return render_template(
        "dashboard.html",
        role_label=ROLE_LABELS.get(user.role, user.role),
        tiles=tiles,
        rows=rows,
    )


@app.route("/admin-check")
@role_required("admin")
def admin_check():
    """Temporary route to prove role protection works."""
    return jsonify(status="ok", message="You are an admin.")


@app.errorhandler(403)
def forbidden(_error):
    return render_template(
        "message.html",
        title="Access denied",
        text="Your role does not have permission to open this page.",
    ), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template(
        "message.html", title="Page not found", text="That page does not exist."
    ), 404


@app.route("/health")
def health():
    return jsonify(status="ok", app="Auraflow")


@app.route("/db-test")
def db_test():
    """Temporary route: checks that the app can reach Neon."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify(
            status="ok",
            database=db.engine.dialect.name,
            message="Connected to Neon",
        )
    except Exception as error:
        db.session.rollback()
        return jsonify(status="error", message=str(error)), 500


if __name__ == "__main__":
    app.run(debug=True)