import os
from pathlib import Path
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("CLIPFORGE_DB_PATH", ROOT / "storage" / "clipforge.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# create_all() never alters existing tables, so new columns are added here.
_NEW_COLUMNS = {
    "videos": {"proxy_path": "VARCHAR(1000)"},
    "clips": {"thumbnail_path": "VARCHAR(1000)"},
    "jobs": {"payload": "TEXT"},
}


def _ensure_columns():
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _NEW_COLUMNS.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def init_db():
    from backend.database import models  # noqa: F401
    Base.metadata.create_all(engine)
    _ensure_columns()
