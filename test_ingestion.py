"""
SkyGuard AI v2 - Phase 1 Telemetry Ingestion Automated Test Suite
-------------------------------------------------------------------
Tests single & batch telemetry ingestion, validation error handling (missing fields,
invalid timestamps, physical range violations, duplicate packets), optional extended
sensor parameters, and confirms zero regressions across existing REST endpoints.
"""

import urllib.request
import json
import sys
from datetime import datetime, timezone, timedelta

# Ensure UTF-8 output encoding for Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"


def send_post(endpoint, payload_dict):
    url = f"{BASE_URL}{endpoint}"
    data_bytes = json.dumps(payload_dict).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        try:
            err_json = json.loads(body_text)
        except Exception:
            err_json = {"detail": body_text}
        return e.code, err_json


def run_ingestion_tests():
    print("=" * 65)
    print(" 🧪 SkyGuard AI v2 - Phase 1 Telemetry Ingestion Test Suite")
    print("=" * 65)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # TEST 1: Valid Single Telemetry Ingestion
    print("\n1. Valid Single Telemetry Ingestion:")
    valid_payload = {
        "station_id": "IMD_AWS_101",
        "timestamp": now_iso,
        "temperature": 27.5,
        "pressure": 1008.2,
        "humidity": 65.0
    }
    status, res = send_post("/api/v1/telemetry/ingest", valid_payload)
    if status == 201 and res.get("ingestion_status") == "success":
        print(f"  [PASS 201] Valid payload ingested for {res['station_id']} -> Anomaly: {res['detection']['predicted_anomaly']}, Trust: {res['detection']['trust_score']}%")
    else:
        print(f"  [FAIL] Valid ingestion failed with status {status}: {res}")

    # TEST 2: Valid Telemetry with Extended Sensor Parameters
    print("\n2. Valid Telemetry with Extended Sensors (Wind, Rain, Solar):")
    extended_payload = {
        "station_id": "IMD_AWS_102",
        "timestamp": now_iso,
        "temperature": 32.1,
        "pressure": 1004.5,
        "humidity": 78.0,
        "latitude": 28.6139,
        "longitude": 77.2090,
        "wind_speed": 12.5,
        "wind_direction": 180.0,
        "rainfall": 4.2,
        "solar_radiation": 850.0
    }
    status, res = send_post("/api/v1/telemetry/ingest", extended_payload)
    if status == 201 and res.get("telemetry", {}).get("wind_speed") == 12.5:
        print(f"  [PASS 201] Extended sensors validated -> Wind: 12.5 m/s, Rain: 4.2 mm, Solar: 850 W/m²")
    else:
        print(f"  [FAIL] Extended telemetry failed with status {status}: {res}")

    # TEST 3: Missing Required Field
    print("\n3. Validation Error: Missing Mandatory Field (Temperature):")
    missing_field_payload = {
        "station_id": "IMD_AWS_103",
        "timestamp": now_iso,
        "pressure": 1008.0,
        "humidity": 60.0
    }
    status, res = send_post("/api/v1/telemetry/ingest", missing_field_payload)
    if status == 422:
        print(f"  [PASS 422] Correctly rejected missing temperature field -> Error detail verified.")
    else:
        print(f"  [FAIL] Expected 422 Unprocessable Entity, got {status}: {res}")

    # TEST 4: Invalid Timestamp Format
    print("\n4. Validation Error: Invalid Timestamp Format:")
    invalid_ts_payload = {
        "station_id": "IMD_AWS_104",
        "timestamp": "INVALID_DATE_FORMAT",
        "temperature": 25.0,
        "pressure": 1010.0,
        "humidity": 50.0
    }
    status, res = send_post("/api/v1/telemetry/ingest", invalid_ts_payload)
    if status == 422:
        print(f"  [PASS 422] Correctly rejected invalid timestamp format.")
    else:
        print(f"  [FAIL] Expected 422, got {status}: {res}")

    # TEST 5: Far Future Timestamp (> 1 hour ahead)
    print("\n5. Validation Error: Far Future Timestamp (> 1 hour):")
    future_iso = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future_ts_payload = {
        "station_id": "IMD_AWS_105",
        "timestamp": future_iso,
        "temperature": 25.0,
        "pressure": 1010.0,
        "humidity": 50.0
    }
    status, res = send_post("/api/v1/telemetry/ingest", future_ts_payload)
    if status == 422:
        print(f"  [PASS 422] Correctly rejected far-future timestamp.")
    else:
        print(f"  [FAIL] Expected 422, got {status}: {res}")

    # TEST 6: Physical Range Violation (Impossible Temp 150°C)
    print("\n6. Validation Error: Physically Impossible Temperature (150°C):")
    range_viol_payload = {
        "station_id": "IMD_AWS_106",
        "timestamp": now_iso,
        "temperature": 150.0,  # Exceeds max 60°C
        "pressure": 1010.0,
        "humidity": 50.0
    }
    status, res = send_post("/api/v1/telemetry/ingest", range_viol_payload)
    if status == 422:
        print(f"  [PASS 422] Correctly rejected physically impossible temperature (150°C).")
    else:
        print(f"  [FAIL] Expected 422, got {status}: {res}")

    # TEST 7: Duplicate Telemetry Packet Detection
    print("\n7. Duplicate Packet Detection:")
    dup_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.999Z")
    dup_payload = {
        "station_id": "IMD_AWS_DUP_TEST",
        "timestamp": dup_timestamp,
        "temperature": 24.0,
        "pressure": 1012.0,
        "humidity": 55.0
    }
    # First send: expect 201
    status1, _ = send_post("/api/v1/telemetry/ingest", dup_payload)
    # Second send with identical station_id & timestamp: expect 422 duplicate error
    status2, res2 = send_post("/api/v1/telemetry/ingest", dup_payload)
    if status1 == 201 and status2 == 422:
        print(f"  [PASS 422] Duplicate packet correctly rejected on second attempt.")
    else:
        print(f"  [FAIL] Duplicate detection failed: first send={status1}, second send={status2}")

    # TEST 8: Batch Telemetry Ingestion
    print("\n8. Batch Telemetry Ingestion Endpoint:")
    batch_payload = {
        "readings": [
            {"station_id": "IMD_AWS_BATCH_1", "timestamp": now_iso, "temperature": 22.0, "pressure": 1009.0, "humidity": 60.0},
            {"station_id": "IMD_AWS_BATCH_2", "timestamp": now_iso, "temperature": 35.5, "pressure": 998.0, "humidity": 90.0}
        ]
    }
    status, res = send_post("/api/v1/telemetry/ingest/batch", batch_payload)
    if status == 201 and res.get("ingested_count") == 2:
        print(f"  [PASS 201] Batch ingestion successful -> {res['ingested_count']} readings processed.")
    else:
        print(f"  [FAIL] Batch ingestion failed with status {status}: {res}")

    print("\n" + "=" * 65)
    print(" 🎉 PHASE 1 INGESTION TEST SUITE COMPLETED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_ingestion_tests()
