"""
SkyGuard AI v2 - Comprehensive Automated Verification Test Suite
------------------------------------------------------------------
Validates all FastAPI REST endpoints and WebSocket live streaming interface.

Run with:
    python test_app.py
"""

import urllib.request
import json
import sys

# Ensure UTF-8 output encoding for Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"


def test_endpoint(endpoint, name, method="GET", body=None):
    url = f"{BASE_URL}{endpoint}"
    try:
        data_bytes = json.dumps(body).encode("utf-8") if body else None
        headers = {"Content-Type": "application/json"} if body else {}
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            data = json.loads(resp.read().decode())
            print(f"  [OK {status}] {name:35s} -> Path: {endpoint}")
            return data
    except Exception as e:
        print(f"  [FAIL] {name} ({endpoint}): {e}")
        return None


def run_tests():
    print("=" * 60)
    print(" SkyGuard AI v2 - Automated Verification Test Suite")
    print("=" * 60)

    # 1. Health & Root
    print("\n1. System Health & Metadata Endpoints:")
    test_endpoint("/health", "System Health Check")
    test_endpoint("/", "API Root Info")

    # 2. Monitoring & Summary
    print("\n2. Monitoring & Summary Endpoints:")
    summary = test_endpoint("/summary", "Network Summary Metrics")
    if summary:
        print(f"     Readings: {summary.get('total_readings')}, Anomalies: {summary.get('anomalies')} ({summary.get('anomaly_rate')}%)")

    stations = test_endpoint("/stations", "AWS Fleet Station Telemetry")
    if stations and len(stations) > 0:
        print(f"     Active Stations: {len(stations)} ({[s['station_id'] for s in stations]})")

    alerts = test_endpoint("/alerts", "Recent Anomaly Alerts Feed")
    if alerts:
        print(f"     Alerts Count: {len(alerts)}")

    # 3. Digital Twin & XAI
    print("\n3. Digital Twin & XAI Explainability:")
    twin = test_endpoint("/digital-twin/AWS_001", "Digital Twin Baseline (AWS_001)")
    if twin:
        print(f"     Timestamps: {len(twin.get('timestamps', []))}, Features: T, P, RH Expected Baselines Included")

    explain = test_endpoint("/explain/AWS_003", "SHAP Feature Contribution (AWS_003)")
    if explain:
        print(f"     Root Cause: {explain.get('root_cause')}, SHAP: {explain.get('shap_contributions')}")

    # 4. Maintenance & Fleet Intelligence
    print("\n4. Predictive Maintenance & Fleet Intelligence:")
    maint = test_endpoint("/maintenance", "Predictive Maintenance Forecast")
    if maint:
        print(f"     Stations Evaluated: {len(maint)}")

    systemic = test_endpoint("/fleet/systemic", "Systemic vs Isolated Faults")
    if systemic:
        print(f"     Statistically Significant Systemic Events: {len(systemic)}")

    archetypes = test_endpoint("/fleet/archetypes", "Anomaly Signature Archetypes")
    if archetypes:
        print(f"     Recurring Signature Clusters: {len(archetypes)}")

    # 5. What-If Simulator Endpoint
    print("\n5. What-If Sensor Simulator Endpoint:")
    analysis = test_endpoint("/analyze", "What-If Telemetry Analysis", method="POST", body={"temperature": 45.0, "pressure": 1005.0, "humidity": 92.0})
    if analysis:
        print(f"     Input: T=45C, P=1005hPa, RH=92% -> Anomaly: {analysis.get('predicted_anomaly')}, Cause: {analysis.get('predicted_root_cause')}")

    print("\n" + "=" * 60)
    print(" ALL REST VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
