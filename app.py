from flask import Flask, jsonify, render_template
from sqlalchemy import text

from config import Config
from extensions import db

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