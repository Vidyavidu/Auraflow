from app import app
from extensions import db
import models  # noqa: F401  (registers all tables)

with app.app_context():
    db.create_all()
    print("Tables created:")
    for name in sorted(db.metadata.tables):
        print(" -", name)