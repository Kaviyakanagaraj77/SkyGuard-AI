"""
SkyGuard AI v2 - Database Configuration & Resilience Layer (Phase 2)
----------------------------------------------------------------------
Manages SQLAlchemy database connections, DATABASE_URL environment configuration,
session dependencies, and graceful fallback when PostgreSQL is unconfigured.
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger("skyguard.database")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

engine = None
SessionLocal = None
Base = declarative_base()
db_enabled = False

if DATABASE_URL:
    try:
        # Support postgres:// -> postgresql:// alias if provided by hosting services
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)

        connect_args = {}
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}

        engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,
            pool_size=5 if not url.startswith("sqlite") else None
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db_enabled = True
        logger.info(f"Database engine initialized for target: {url.split('@')[-1] if '@' in url else url}")
    except Exception as e:
        logger.warning(f"Failed to initialize database engine: {e}. Falling back to In-Memory Demo Mode.")
        db_enabled = False
else:
    logger.info("DATABASE_URL not configured. SkyGuard AI running in Demo / In-Memory Mode.")


def init_db():
    """Safely initializes database tables and attempts optional TimescaleDB extension."""
    if not db_enabled or not engine:
        return False

    try:
        from models import StationModel, TelemetryModel, AlertModel, MaintenanceRecordModel  # noqa
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")

        # Attempt optional TimescaleDB hypertable extension if supported by PostgreSQL host
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
                conn.execute(text("SELECT create_hypertable('telemetry', 'timestamp', if_not_exists => TRUE);"))
                conn.commit()
                logger.info("TimescaleDB hypertable initialized for telemetry table.")
        except Exception:
            # Ordinary PostgreSQL / SQLite without TimescaleDB extension continues silently
            pass

        return True
    except Exception as e:
        logger.warning(f"Database initialization error: {e}. Disabling database persistence.")
        return False


def get_db():
    """SQLAlchemy Session dependency with graceful fallback."""
    if not db_enabled or not SessionLocal:
        yield None
        return

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> bool:
    """Checks active database engine connectivity for readiness probes."""
    if not db_enabled or not engine:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
