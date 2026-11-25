import os

from dotenv import load_dotenv

# Reads the local .env file. On Vercel there is no .env file,
# so the values come from Vercel's environment variables instead.
load_dotenv()

ON_VERCEL = bool(os.environ.get("VERCEL"))


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


def get_secret_key():
    key = os.environ.get("SECRET_KEY", "").strip()

    if not key:
        if ON_VERCEL:
            raise RuntimeError(
                "SECRET_KEY is not set. Add it under Settings > "
                "Environment Variables (Production) and redeploy."
            )
        # Local development only
        return "dev-only-change-me"

    return key


class Config:
    SECRET_KEY = get_secret_key()
    SQLALCHEMY_DATABASE_URI = get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Keeps connections healthy on serverless platforms
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # Login cookie safety
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = ON_VERCEL  # HTTPS only on the live site
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12  # 12 hours