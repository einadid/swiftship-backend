"""Database configuration (SQLite via SQLAlchemy).

For production you can switch to PostgreSQL by changing DATABASE_URL,
e.g. postgresql+psycopg://user:pass@host/swiftship
or using DATABASE_URL env var.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Resolve BASE_DIR as the backend/ folder regardless of cwd
# backend/app/database.py -> backend/app -> backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Default to SQLite file in backend/data/app.db
# For Postgres: DATABASE_URL=postgresql://user:pass@host/db
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(DATA_DIR, 'app.db')}")

# SQLite needs check_same_thread=False for FastAPI's threaded workers
# and a generous timeout to avoid "database is locked" on concurrent writes
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}
    # Ensure sqlite path is absolute and handles spaces
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
        echo=False,
    )
else:
    # Postgres or other DB
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
