import re
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@auth_bp.before_app_request
def load_current_user():
    """Runs on every request and sets g.user (or None)."""
    g.user = None
    user_id = session.get("user_id")
    if user_id is None:
        return
    user = db.session.get(User, user_id)
    if user and user.is_active:
        g.user = user
    else:
        session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    """Use below @login_required, e.g. @role_required("admin")."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("auth.login"))
            if g.user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if not name or len(name) > 120:
            error = "Please enter your name."
        elif not EMAIL_PATTERN.match(email):
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif User.query.filter_by(email=email).first():
            error = "An account with that email already exists."

        if error:
            flash(error, "error")
            return render_template("register.html", name=name, email=email), 400

        # Role is never taken from the form. Public sign-ups are employees.
        user = User(name=name, email=email, role="employee")
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("An account with that email already exists.", "error")
            return render_template("register.html", name=name, email=email), 400

        session.clear()
        session["user_id"] = user.id
        session.permanent = True
        flash("Welcome to Auraflow!", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        # Same message for unknown email and wrong password on purpose
        if not user or not user.is_active or not user.check_password(password):
            flash("Incorrect email or password.", "error")
            return render_template("login.html", email=email), 401

        session.clear()
        session["user_id"] = user.id
        session.permanent = True
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))