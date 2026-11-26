import re
from getpass import getpass

from app import app
from extensions import db
from models import ROLES, User
from tickets import category_names

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


def ask_specialties(role):
    if role not in ("l1", "l2"):
        return []

    names = category_names(published_only=False, include_general=False)
    lookup = {n.lower(): n for n in names}
    print("Categories:", ", ".join(names))
    print("Type the categories this technician handles, separated by commas.")
    print("Leave blank for a generalist who can take any category.")

    while True:
        raw = input("Specialties: ").strip()
        if not raw:
            return []
        chosen, unknown = [], []
        for part in raw.split(","):
            key = part.strip().lower()
            if not key:
                continue
            if key in lookup:
                if lookup[key] not in chosen:
                    chosen.append(lookup[key])
            else:
                unknown.append(part.strip())
        if unknown:
            print("Not a known category:", ", ".join(unknown), "- try again.")
            continue
        return chosen


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
    specialties = ask_specialties(role)
    password = ask_password()

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    user.set_specialties(specialties)
    db.session.add(user)
    db.session.commit()

    extra = ""
    if role in ("l1", "l2"):
        extra = f" Specialties: {', '.join(specialties) if specialties else 'generalist'}."
    print(f"Created {role} account for {email} (id {user.id}).{extra}")


if __name__ == "__main__":
    with app.app_context():
        while True:
            run()
            again = input("\nCreate another user? (y/n): ").strip().lower()
            if again != "y":
                break