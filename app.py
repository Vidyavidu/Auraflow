from datetime import timedelta, timezone

from flask import Flask, g, jsonify, redirect, render_template, url_for
from sqlalchemy import text

from admin import admin_bp
from auth import auth_bp, login_required, role_required
from chat import chat_bp
from config import Config
from extensions import db
from models import Ticket
from tickets import OPEN_STATES, tickets_bp
from workflow import queue_counts, workflow_bp

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(workflow_bp)
app.register_blueprint(admin_bp)

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


@app.route("/")
def home():
    if g.user:
        return redirect(url_for("dashboard"))
    return redirect(url_for("auth.login"))


@app.route("/dashboard")
@login_required
def dashboard():
    open_count = Ticket.query.filter(
        Ticket.requester_id == g.user.id, Ticket.status.in_(OPEN_STATES)
    ).count()
    counts = queue_counts(g.user) if g.user.role in ("l1", "l2", "admin") else None
    return render_template(
        "dashboard.html",
        role_label=ROLE_LABELS.get(g.user.role, g.user.role),
        open_count=open_count,
        counts=counts,
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