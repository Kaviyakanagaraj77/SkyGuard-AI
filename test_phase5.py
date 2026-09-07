"""
SkyGuard AI v2 - Phase 5 Production Hardening & Readiness Test Suite
----------------------------------------------------------------------
Tests centralized configuration management, /health & /ready operational probes,
database connection health checks, secret masking in logs, rate limiting, IMD boundary
adapters, exception masking, and CORS environment configuration.
"""

import sys
import os
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Ensure UTF-8 output encoding for Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"

from config import settings
from logger import SecretMaskingFormatter, logger
from rate_limiter import RateLimiter
from database import check_db_health
from imd_adapter import SyntheticDemoAdapter, IMDPilotAdapterBoundary
from telemetry_validator import TelemetryPayload
from telemetry_ingestor import TelemetryIngestor


def run_phase5_tests():
    print("=" * 70)
    print(" 🧪 SkyGuard AI v2 - Phase 5 Production Hardening & Readiness Tests")
    print("=" * 70)

    # TEST 1: Centralized Configuration Management Test
    print("\n1. Centralized Configuration Management Test:")
    assert settings.APP_NAME == "SkyGuard AI"
    assert settings.APP_VERSION == "2.0"
    assert isinstance(settings.CORS_ORIGINS, list)
    warnings = settings.validate_production_config()
    print(f"  [PASS] Config loaded -> Env: {settings.APP_ENV}, CORS Origins: {len(settings.CORS_ORIGINS)}, Config Warnings: {len(warnings)}.")

    # TEST 2: Operational Health Check Test (/health)
    print("\n2. Operational Health Probe Test (GET /health):")
    req = urllib.request.Request(f"{BASE_URL}/health")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["status"] == "healthy"
        print(f"  [PASS 200] GET /health -> Status: {data['status']}, Service: {data['service']}")

    # TEST 3: Operational Readiness Probe Test (/ready)
    print("\n3. Operational Readiness Probe Test (GET /ready):")
    req = urllib.request.Request(f"{BASE_URL}/ready")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert "status" in data
        assert "database_connected" in data
        print(f"  [PASS 200] GET /ready -> Status: {data['status']}, DB Connected: {data['database_connected']}")

    # TEST 4: Secret Masking Formatter Test
    print("\n4. Log Secret Masking Formatter Test:")
    formatter = SecretMaskingFormatter("[%(levelname)s] %(message)s")
    record1 = logging.LogRecord("test", logging.INFO, "", 0, "User logged in with Bearer eyJhbGciOiJIUzI1NiJ9.test.token", (), None)
    record2 = logging.LogRecord("test", logging.INFO, "", 0, 'Payload contains "password": "MySuperSecretPassword123!"', (), None)
    masked1 = formatter.format(record1)
    masked2 = formatter.format(record2)

    assert "eyJhbGci" not in masked1
    assert "[MASKED_TOKEN]" in masked1
    assert "MySuperSecretPassword123!" not in masked2
    assert "[MASKED_PASSWORD]" in masked2
    print("  [PASS] Secret masking formatter successfully redacted JWT tokens and plain passwords from logs.")

    # TEST 5: Rate Limiting & Abuse Protection Test
    print("\n5. Sliding Window Rate Limiter Test:")
    test_limiter = RateLimiter(max_requests=3, window_seconds=60)
    user_key = "test_ip_127.0.0.1"
    assert test_limiter.is_allowed(user_key) is True
    assert test_limiter.is_allowed(user_key) is True
    assert test_limiter.is_allowed(user_key) is True
    assert test_limiter.is_allowed(user_key) is False  # 4th request exceeds max 3 limit
    print("  [PASS] Rate limiter correctly blocked excess requests beyond limit (Max: 3/min).")

    # TEST 6: Database Connection Health Probe Test
    print("\n6. Database Connection Health Probe Test:")
    db_status = check_db_health()
    print(f"  [PASS] Database health check probe executed -> Connection status: {db_status}.")

    # TEST 7: IMD Integration Boundary Adapter Test
    print("\n7. IMD Integration Boundary Adapter Test:")
    pilot_adapter = IMDPilotAdapterBoundary()
    status_info = pilot_adapter.fetch_latest_telemetry("AWS_001")
    assert status_info["status"] == "unauthorized"
    assert "PILOT_READINESS_BOUNDARY" in status_info["mode"]

    syn_adapter = SyntheticDemoAdapter()
    parsed = syn_adapter.parse_raw_packet({"station_id": "IMD_TEST", "temperature": 27.5, "pressure": 1008.0, "humidity": 65.0})
    assert parsed["station_id"] == "IMD_TEST"
    print("  [PASS] IMD Integration Boundary adapter interface verified cleanly.")

    # TEST 8: Telemetry Packet Deduplication & Idempotency Test
    print("\n8. Telemetry Ingestion Duplicate Packet Idempotency Test:")
    ingestor = TelemetryIngestor()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = TelemetryPayload(station_id="AWS_P5_DEDUP", timestamp=now_iso, temperature=25.0, pressure=1010.0, humidity=60.0)

    res1 = ingestor.process_payload(payload)
    assert res1["ingestion_status"] == "success"

    try:
        ingestor.process_payload(payload)
        assert False, "Expected ValueError on duplicate packet"
    except ValueError as ve:
        assert "Duplicate telemetry packet detected" in str(ve)
        print("  [PASS] Duplicate packet correctly rejected on second attempt.")

    # TEST 9: CORS Environment Configuration Test
    print("\n9. CORS Origin Environment Configuration Test:")
    assert "https://sky-guard-ai-seven.vercel.app" in settings.CORS_ORIGINS
    print(f"  [PASS] CORS origins verified ({len(settings.CORS_ORIGINS)} allowed origin targets configured).")

    print("\n" + "=" * 70)
    print(" 🎉 PHASE 5 PRODUCTION HARDENING & READINESS TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_phase5_tests()
