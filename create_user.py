import re
from getpass import getpass

from app import app
from extensions import db
from models import ROLES, User

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def ask_role():
    print("Roles:", ", ".join(ROLES))
    while True:
        role = input("Role: ").strip().lower()
        if role in ROLES:
            return role
        print("Please type one of:", ", ".join(ROLES))


def ask_password():
    while True:
        password = getpass("Password (hidden, at least 8 characters): ")
        if len(password) < 8:
            print("Too short. Use at least 8 characters.")
            continue
        confirm = getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match. Try again.")
            continue
        return password


def run():
    name = input("Full name: ").strip()
    if not name:
        print("Name cannot be empty.")
        return

    email = input("Email: ").strip().lower()
    if not EMAIL_PATTERN.match(email):
        print("That does not look like a valid email.")
        return

    if User.query.filter_by(email=email).first():
        print("A user with that email already exists. Nothing was changed.")
        return

    role = ask_role()
    password = ask_password()

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Created {role} account for {email} (id {user.id}).")


if __name__ == "__main__":
    with app.app_context():
        run()