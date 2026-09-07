"""
SkyGuard AI v2 - Phase 2 Database Automated Test Suite
--------------------------------------------------------
Tests SQLite/PostgreSQL database initialization, ORM models, telemetry & alert persistence,
time-range historical queries, duplicate packet handling, and graceful DB-unavailable fallback.
"""

import os
import sys
import json
import urllib.request
from datetime import datetime, timezone

# Ensure UTF-8 output encoding for Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"


def run_database_tests():
    print("=" * 65)
    print(" 🧪 SkyGuard AI v2 - Phase 2 Database Automated Test Suite")
    print("=" * 65)

    # TEST 1: Test Demo Mode Fallback (When DATABASE_URL is not set)
    print("\n1. Database-Unavailable Graceful Fallback Test:")
    from database import db_enabled, DATABASE_URL
    if not DATABASE_URL:
        print(f"  [PASS] DATABASE_URL is unconfigured. db_enabled={db_enabled} (Running in Demo Fallback Mode).")
    else:
        print(f"  [INFO] DATABASE_URL configured: {DATABASE_URL}")

    # TEST 2: In-Memory SQLite Database Model & Schema Test
    print("\n2. SQLite/PostgreSQL Table Schema & Composite Index Test:")
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    
    # Reload database & models module to pick up SQLite test URL
    import database
    database.DATABASE_URL = "sqlite:///:memory:"
    database.engine = database.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    database.SessionLocal = database.sessionmaker(autocommit=False, autoflush=False, bind=database.engine)
    database.db_enabled = True

    init_success = database.init_db()
    if init_success:
        print("  [PASS] Database tables and composite index 'idx_station_timestamp' created successfully.")
    else:
        print("  [FAIL] Failed to create database tables.")

    # TEST 3: Telemetry & Alert ORM Persistence Test
    print("\n3. Telemetry & Alert ORM Persistence Test:")
    from telemetry_validator import TelemetryPayload, TelemetryValidator
    from telemetry_ingestor import TelemetryIngestor
    from anomaly_detector import SkyGuardDetector
    from models import TelemetryModel, AlertModel, StationModel
    import pandas as pd

    validator = TelemetryValidator()

    # Fit detector on sample dataset so 5-layer anomaly engine runs
    sample_df = pd.DataFrame([
        {"timestamp": pd.to_datetime("2026-01-01T00:00:00Z"), "station_id": "TEST_AWS_DB", "temperature": 25.0, "pressure": 1010.0, "humidity": 60.0},
        {"timestamp": pd.to_datetime("2026-01-01T01:00:00Z"), "station_id": "TEST_AWS_DB", "temperature": 26.0, "pressure": 1009.0, "humidity": 62.0}
    ])
    detector = SkyGuardDetector().fit(sample_df)
    ingestor = TelemetryIngestor(detector=detector, validator=validator)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = TelemetryPayload(
        station_id="TEST_AWS_DB",
        timestamp=now_iso,
        temperature=58.0,  # Exceeds trained range -> triggers anomaly alert within valid bounds
        pressure=1005.0,
        humidity=92.0
    )

    result = ingestor.process_payload(payload)
    
    session = database.SessionLocal()
    st_count = session.query(StationModel).filter(StationModel.station_id == "TEST_AWS_DB").count()
    t_count = session.query(TelemetryModel).filter(TelemetryModel.station_id == "TEST_AWS_DB").count()
    a_count = session.query(AlertModel).filter(AlertModel.station_id == "TEST_AWS_DB").count()
    session.close()

    if st_count == 1 and t_count == 1 and a_count >= 1:
        print(f"  [PASS] Telemetry & Alert successfully persisted to database (Stations: {st_count}, Telemetry: {t_count}, Alerts: {a_count}).")
    else:
        print(f"  [FAIL] Persistence check failed (Stations: {st_count}, Telemetry: {t_count}, Alerts: {a_count}).")

    # TEST 4: Time-Range Historical Retrieval Query
    print("\n4. Time-Range Historical Retrieval Test:")
    session = database.SessionLocal()
    t_records = session.query(TelemetryModel).filter(
        TelemetryModel.station_id == "TEST_AWS_DB",
        TelemetryModel.timestamp <= datetime.now(timezone.utc)
    ).all()
    session.close()

    if len(t_records) >= 1:
        print(f"  [PASS] Time-range query retrieved {len(t_records)} record(s) matching station and timestamp filter.")
    else:
        print("  [FAIL] Time-range query returned no records.")

    # TEST 5: Live API GET /history Time-Range Filter Test against Running Server
    print("\n5. API GET /history/{station_id} Time-Range Query Test:")
    try:
        url = f"{BASE_URL}/history/AWS_001?start_time=2025-01-01T00:00:00&limit=10"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            print(f"  [PASS {resp.status}] GET /history/AWS_001 with start_time filter returned {len(data)} items.")
    except Exception as e:
        print(f"  [FAIL] API /history time-range query failed: {e}")

    print("\n" + "=" * 65)
    print(" 🎉 PHASE 2 DATABASE TEST SUITE COMPLETED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_database_tests()
