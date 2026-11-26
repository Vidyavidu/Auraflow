from sqlalchemy import text

from app import app
from extensions import db

with app.app_context():
    db.session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS specialties TEXT"))
    db.session.commit()
    print("Done: the users.specialties column is ready.")