from flask import Flask, g, jsonify, redirect, render_template, url_for
from sqlalchemy import text

from auth import auth_bp, login_required, role_required
from config import Config
from extensions import db

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
app.register_blueprint(auth_bp)

ROLE_LABELS = {
    "employee": "Employee",
    "l1": "L1 Technician",
    "l2": "L2 Technician",
    "admin": "Administrator",
}


@app.route("/")
def home():
    if g.user:
        return redirect(url_for("dashboard"))
    return redirect(url_for("auth.login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html", role_label=ROLE_LABELS.get(g.user.role, g.user.role)
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