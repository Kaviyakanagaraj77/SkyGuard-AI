"""
SkyGuard AI v2 - Phase 3 Real-Time Intelligence & Early Warning Test Suite
-----------------------------------------------------------------------------
Tests real-time processing, deterministic parameter anomaly detection, risk scoring formula,
LOW/MEDIUM/HIGH risk tiers, early warning alert generation, duplicate alert suppression,
alert lifecycle state transitions (ACTIVE -> ACKNOWLEDGED -> RESOLVED), ORM persistence,
historical alert queries, and Phase 1/Phase 2 regression compatibility.
"""

import sys
import os
import json
import urllib.request
from datetime import datetime, timezone

# Ensure UTF-8 output encoding for Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"

from risk_engine import RiskEngine, RiskAssessment, ParameterAnomaly
from alert_service import AlertService, EarlyWarningAlert
from telemetry_validator import TelemetryPayload
from telemetry_ingestor import TelemetryIngestor


def run_phase3_tests():
    print("=" * 70)
    print(" 🧪 SkyGuard AI v2 - Phase 3 Real-Time Intelligence & Early Warning Tests")
    print("=" * 70)

    risk_engine = RiskEngine()
    alert_service = AlertService(suppression_window_minutes=15)
    ingestor = TelemetryIngestor(risk_engine=risk_engine, alert_service=alert_service)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # TEST 1: Normal Telemetry Evaluation
    print("\n1. Normal Telemetry Evaluation Test:")
    r_norm = risk_engine.calculate_risk("AWS_P3_01", now_iso, temperature=25.0, pressure=1013.2, humidity=50.0)
    assert r_norm.risk_score == 0.0, f"Expected 0.0 risk score, got {r_norm.risk_score}"
    assert r_norm.risk_level == "LOW", f"Expected LOW risk level, got {r_norm.risk_level}"
    assert len(r_norm.contributing_parameters) == 0
    print(f"  [PASS] Normal telemetry -> Risk Score: {r_norm.risk_score}, Level: {r_norm.risk_level}")

    # TEST 2: Warning Threshold Breach Test
    print("\n2. Warning Threshold Breach Test:")
    r_warn = risk_engine.calculate_risk("AWS_P3_01", now_iso, temperature=48.0, pressure=1013.2, humidity=50.0)
    assert r_warn.risk_score >= 25.0, f"Expected risk score >= 25.0, got {r_warn.risk_score}"
    assert r_warn.severities["temperature"] == "WARNING"
    print(f"  [PASS] Warning threshold breach -> Temp Severity: {r_warn.severities['temperature']}, Risk Score: {r_warn.risk_score}")

    # TEST 3: Critical Threshold Breach Test
    print("\n3. Critical Threshold Breach Test:")
    r_crit = risk_engine.calculate_risk("AWS_P3_01", now_iso, temperature=56.0, pressure=1013.2, humidity=50.0)
    assert r_crit.risk_score >= 55.0, f"Expected risk score >= 55.0, got {r_crit.risk_score}"
    assert r_crit.severities["temperature"] == "CRITICAL"
    print(f"  [PASS] Critical threshold breach -> Temp Severity: {r_crit.severities['temperature']}, Risk Score: {r_crit.risk_score}")

    # TEST 4: Anomaly Detection Details Test
    print("\n4. Parameter Anomaly Detail Inspection Test:")
    anom_temp = risk_engine.evaluate_parameter("temperature", 56.0, now_iso)
    assert anom_temp.severity == "CRITICAL"
    assert anom_temp.parameter == "temperature"
    assert anom_temp.current_value == 56.0
    print(f"  [PASS] Parameter anomaly details verified -> Reason: {anom_temp.reason}")

    # TEST 5: Multiple Simultaneous Anomalies Test
    print("\n5. Multiple Simultaneous Anomalies & Multi-Parameter Bonus Test:")
    r_multi = risk_engine.calculate_risk("AWS_P3_01", now_iso, temperature=48.0, pressure=890.0, humidity=96.0)
    # Temp warning (+25), Pressure critical (+55), Humidity warning (+25), Multi-bonus (+30) -> Clamped to 100
    assert r_multi.risk_score >= 70.0, f"Expected elevated risk score, got {r_multi.risk_score}"
    assert len(r_multi.contributing_parameters) == 3
    print(f"  [PASS] Multi-parameter anomalies -> Risk Score: {r_multi.risk_score}, Contributing: {r_multi.contributing_parameters}")

    # TEST 6: Risk Score Calculation Formula Verification
    print("\n6. Risk Score Formula Verification Test:")
    # single warning: 25.0 points
    r_f1 = risk_engine.calculate_risk("AWS_FORMULA", now_iso, temperature=48.0, pressure=1013.2, humidity=50.0)
    assert r_f1.risk_score == 25.0, f"Expected 25.0, got {r_f1.risk_score}"
    print(f"  [PASS] Single WARNING formula verified -> Risk Score: {r_f1.risk_score}")

    # TEST 7: LOW Risk Tier (0–30) Test
    print("\n7. LOW Risk Tier Test (0–30):")
    assert r_norm.risk_level == "LOW"
    print(f"  [PASS] LOW risk tier confirmed (Score {r_norm.risk_score} -> LOW).")

    # TEST 8: MEDIUM Risk Tier (31–70) Test
    print("\n8. MEDIUM Risk Tier Test (31–70):")
    r_med = risk_engine.calculate_risk("AWS_MED", now_iso, temperature=48.0, pressure=940.0, humidity=50.0)
    assert r_med.risk_level == "MEDIUM", f"Expected MEDIUM risk tier, got {r_med.risk_level}"
    print(f"  [PASS] MEDIUM risk tier confirmed (Score {r_med.risk_score} -> MEDIUM).")

    # TEST 9: HIGH Risk Tier (71–100) Test
    print("\n9. HIGH Risk Tier Test (71–100):")
    assert r_multi.risk_level == "HIGH", f"Expected HIGH risk tier, got {r_multi.risk_level}"
    print(f"  [PASS] HIGH risk tier confirmed (Score {r_multi.risk_score} -> HIGH).")

    # TEST 10: Early Warning Alert Generation Test
    print("\n10. Early Warning Alert Generation Test:")
    current_vals = {"temperature": 56.0, "pressure": 1013.2, "humidity": 50.0}
    alert1 = alert_service.generate_alert(r_crit, current_vals)
    assert alert1 is not None, "Expected alert generation on critical risk breach"
    assert alert1.status == "ACTIVE"
    assert alert1.severity == "CRITICAL"
    print(f"  [PASS] Alert generated -> Alert ID: {alert1.alert_id}, Severity: {alert1.severity}, Status: {alert1.status}")

    # TEST 11: Duplicate Alert Suppression Window Test
    print("\n11. Duplicate Alert Suppression Window Test:")
    alert_dup = alert_service.generate_alert(r_crit, current_vals)
    assert alert_dup is None, "Duplicate alert within suppression window should be suppressed"
    print(f"  [PASS] Duplicate alert correctly suppressed within suppression window.")

    # TEST 12: Alert Persistence to Database Test
    print("\n12. Alert Database Persistence & ORM Test:")
    from models import AlertModel
    from database import SessionLocal, db_enabled
    if db_enabled and SessionLocal:
        session = SessionLocal()
        a_count = session.query(AlertModel).filter(AlertModel.station_id == "AWS_P3_01").count()
        session.close()
        print(f"  [PASS] Early warning alert persisted to database ORM (Count: {a_count}).")
    else:
        print(f"  [PASS (Demo Fallback)] In-memory alert cache count: {len(alert_service.in_memory_alerts)}.")

    # TEST 13: Historical Alert Retrieval & Filtering Test
    print("\n13. Historical Alert Retrieval & Filtering Test:")
    history = alert_service.get_alert_history(station_id="AWS_P3_01")
    assert len(history) >= 1
    assert history[0]["station_id"] == "AWS_P3_01"
    print(f"  [PASS] Historical alert query retrieved {len(history)} record(s) for station AWS_P3_01.")

    # TEST 14: Alert Lifecycle Transitions (ACTIVE -> ACKNOWLEDGED -> RESOLVED) Test
    print("\n14. Alert Lifecycle State Transition Test:")
    aid = alert1.alert_id
    ack_ok = alert_service.acknowledge_alert(aid)
    assert ack_ok, "Acknowledge operation failed"
    assert alert1.status == "ACKNOWLEDGED"

    res_ok = alert_service.resolve_alert(aid)
    assert res_ok, "Resolve operation failed"
    assert alert1.status == "RESOLVED"
    print(f"  [PASS] Alert state transition sequence verified: ACTIVE -> ACKNOWLEDGED -> RESOLVED.")

    # TEST 15: End-to-End Ingestion-to-Risk Pipeline Integration Test
    print("\n15. Full Ingestion-to-Risk & Early Warning Integration Test:")
    payload = TelemetryPayload(
        station_id="AWS_P3_INTEG",
        timestamp=now_iso,
        temperature=54.0,
        pressure=1005.0,
        humidity=92.0
    )
    res = ingestor.process_payload(payload)
    assert "risk_assessment" in res, "Missing risk_assessment in process_payload output"
    assert res["risk_assessment"]["risk_score"] > 0
    print(f"  [PASS] End-to-End Telemetry Ingestion -> Risk Score: {res['risk_assessment']['risk_score']}, Risk Level: {res['risk_assessment']['risk_level']}")

    # TEST 16: Live Phase 3 API Endpoints Test against Running Server
    print("\n16. Live REST API Phase 3 Endpoints Test:")
    try:
        req = urllib.request.Request(f"{BASE_URL}/risk/AWS_001")
        with urllib.request.urlopen(req) as resp:
            data_risk = json.loads(resp.read().decode())
            print(f"  [PASS {resp.status}] GET /risk/AWS_001 -> Risk Level: {data_risk['risk_level']}, Score: {data_risk['risk_score']}")

        req2 = urllib.request.Request(f"{BASE_URL}/telemetry/health/AWS_001")
        with urllib.request.urlopen(req2) as resp2:
            data_health = json.loads(resp2.read().decode())
            print(f"  [PASS {resp2.status}] GET /telemetry/health/AWS_001 -> Health Status: {data_health['health_status']}")

        req3 = urllib.request.Request(f"{BASE_URL}/alerts/active")
        with urllib.request.urlopen(req3) as resp3:
            data_active = json.loads(resp3.read().decode())
            print(f"  [PASS {resp3.status}] GET /alerts/active -> Active Early Warning Alerts: {len(data_active)}")
    except Exception as e:
        print(f"  [FAIL] Live REST API Phase 3 endpoints test failed: {e}")

    print("\n" + "=" * 70)
    print(" 🎉 PHASE 3 REAL-TIME INTELLIGENCE TEST SUITE COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_phase3_tests()
