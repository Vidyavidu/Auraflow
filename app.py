from flask import Flask, jsonify, render_template

from config import Config
from extensions import db
from models import HealthCheck

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify(status="ok", app="Auraflow")


@app.route("/db-test")
def db_test():
    """Temporary route: writes one row to the database and reads it back."""
    try:
        db.create_all()

        row = HealthCheck(note="Hello from Auraflow")
        db.session.add(row)
        db.session.commit()

        total = HealthCheck.query.count()
        latest = HealthCheck.query.order_by(HealthCheck.id.desc()).first()

        engine_name = db.engine.dialect.name

        return jsonify(
            status="ok",
            database=engine_name,
            rows_saved=total,
            latest_note=latest.note,
        )
    except Exception as error:
        db.session.rollback()
        return jsonify(status="error", message=str(error)), 500


if __name__ == "__main__":
    app.run(debug=True)