import os

from dotenv import load_dotenv

# Reads the local .env file. On Vercel there is no .env file,
# so the values come from Vercel's environment variables instead.
load_dotenv()


def get_database_uri():
    uri = os.environ.get("DATABASE_URL", "").strip()

    if not uri:
        raise RuntimeError(
            "DATABASE_URL is not set. Locally, add it to your .env file. "
            "On Vercel, add it under Settings > Environment Variables "
            "(Production) and redeploy."
        )

    # Some providers give "postgres://", SQLAlchemy needs "postgresql://"
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    return uri


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Keeps connections healthy on serverless platforms
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }