from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)
    # Lightweight migration: add 'evidence_name' if missing
    try:
        insp = inspect(engine)
        cols = [c['name'] for c in insp.get_columns('evidence')]
        if 'evidence_name' not in cols:
            with engine.begin() as conn:
                # SQLite supports adding nullable columns without default
                conn.execute(text("ALTER TABLE evidence ADD COLUMN evidence_name VARCHAR(200)"))
    except Exception:
        # Avoid breaking startup if introspection fails
        pass
