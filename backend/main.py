from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
import asyncio
import sys
import os

# Allow Python to find the main SkyGuard files
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anomaly_detector import SkyGuardDetector, FEATURES
from maintenance_predictor import compute_degradation_trend
from fleet_intelligence import systemic_vs_isolated, anomaly_archetypes

app = FastAPI(
    title="SkyGuard AI API",
    description="Real-time, explainable, fleet-aware AWS anomaly detection backend",
    version="2.0"
)

# Allow frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Load data + run the full pipeline once at startup
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "aws_dataset.csv")
RESULTS_PATH = os.path.join(BASE_DIR, "data", "detection_results.csv")

df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])

detector = SkyGuardDetector()
detector.fit(df)

results = detector.detect(df)
results.to_csv(RESULTS_PATH, index=False)

maintenance_df = compute_degradation_trend(RESULTS_PATH)
systemic_df = systemic_vs_isolated(RESULTS_PATH)
archetype_df, _ = anomaly_archetypes(RESULTS_PATH)


def trust_score(confidence):
    """Continuous 0-100 data-trust score, derived from the fused confidence
    score - lets downstream forecasting systems soft-weight a reading
    instead of only getting a binary anomaly/normal flag."""
    if pd.isna(confidence):
        return None
    return round(float(max(0.0, min(1.0, 1 - confidence))) * 100, 1)


# ---------------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------------
@app.get("/")
def home():
    return {"message": "SkyGuard AI API is running", "status": "online", "version": "2.0"}


@app.get("/health")
def health():
    return {"status": "healthy", "service": "SkyGuard AI"}


STATION_METADATA = {
    "AWS_001": {"location": "New Delhi (NCR)", "lat": 28.6139, "lon": 77.2090, "elevation": "216m"},
    "AWS_002": {"location": "Mumbai (Maharashtra)", "lat": 19.0760, "lon": 72.8777, "elevation": "14m"},
    "AWS_003": {"location": "Chennai (Tamil Nadu)", "lat": 13.0827, "lon": 80.2707, "elevation": "6m"},
    "AWS_004": {"location": "Kolkata (West Bengal)", "lat": 22.5726, "lon": 88.3639, "elevation": "9m"},
    "AWS_005": {"location": "Bengaluru (Karnataka)", "lat": 12.9716, "lon": 77.5946, "elevation": "920m"},
}


@app.get("/stations")
def get_stations():
    latest = results.sort_values("timestamp").groupby("station_id").tail(1)
    stations = []
    for _, row in latest.iterrows():
        sid = row["station_id"]
        meta = STATION_METADATA.get(sid, {"location": sid, "lat": 20.5937, "lon": 78.9629, "elevation": "100m"})
        stations.append({
            "station_id": sid,
            "location": meta["location"],
            "lat": meta["lat"],
            "lon": meta["lon"],
            "elevation": meta["elevation"],
            "temperature": None if pd.isna(row["temperature"]) else round(float(row["temperature"]), 2),
            "pressure": None if pd.isna(row["pressure"]) else round(float(row["pressure"]), 2),
            "humidity": None if pd.isna(row["humidity"]) else round(float(row["humidity"]), 2),
            "confidence_score": round(float(row["confidence_score"]), 3),
            "trust_score": trust_score(row["confidence_score"]),
            "predicted_anomaly": int(row["predicted_anomaly"]),
            "root_cause": row["predicted_root_cause"],
        })
    return stations


@app.get("/alerts")
def get_alerts():
    alerts = results[results["predicted_anomaly"] == 1].sort_values("timestamp", ascending=False).head(20)
    output = []
    for _, row in alerts.iterrows():
        output.append({
            "timestamp": str(row["timestamp"]),
            "station_id": row["station_id"],
            "confidence_score": round(float(row["confidence_score"]), 3),
            "trust_score": trust_score(row["confidence_score"]),
            "root_cause": row["predicted_root_cause"] if row["predicted_root_cause"] != "normal" else "anomaly_detected",
            "temperature": None if pd.isna(row["temperature"]) else round(float(row["temperature"]), 2),
            "pressure": None if pd.isna(row["pressure"]) else round(float(row["pressure"]), 2),
            "humidity": None if pd.isna(row["humidity"]) else round(float(row["humidity"]), 2),
        })
    return output


@app.get("/summary")
def get_summary():
    total = len(results)
    anomalies = int(results["predicted_anomaly"].sum())
    normal = total - anomalies
    return {
        "total_readings": total,
        "anomalies": anomalies,
        "normal": normal,
        "anomaly_rate": round(anomalies / total * 100, 2),
    }


@app.get("/history/{station_id}")
def get_history(station_id: str):
    station_data = results[results["station_id"] == station_id].sort_values("timestamp").tail(50)
    history = []
    for _, row in station_data.iterrows():
        history.append({
            "timestamp": str(row["timestamp"]),
            "temperature": None if pd.isna(row["temperature"]) else round(float(row["temperature"]), 2),
            "humidity": None if pd.isna(row["humidity"]) else round(float(row["humidity"]), 2),
            "pressure": None if pd.isna(row["pressure"]) else round(float(row["pressure"]), 2),
            "confidence_score": round(float(row["confidence_score"]), 3),
            "predicted_anomaly": int(row["predicted_anomaly"]),
            "root_cause": row["predicted_root_cause"],
        })
    return history


# ---------------------------------------------------------------------------
# NEW: Digital Twin — actual vs. climatologically-expected reading
# ---------------------------------------------------------------------------
@app.get("/digital-twin/{station_id}")
def digital_twin(station_id: str, points: int = 50):
    station_data = results[results["station_id"] == station_id].sort_values("timestamp").tail(points)
    out = {"station_id": station_id, "timestamps": station_data["timestamp"].astype(str).tolist()}
    for col in FEATURES:
        out[col] = [None if pd.isna(x) else round(float(x), 2) for x in station_data[col]]
        out[f"{col}_expected"] = [None if pd.isna(x) else round(float(x), 2) for x in station_data[f"{col}_expected"]]
    return out


# ---------------------------------------------------------------------------
# NEW: SHAP-based explainability for a specific alert
# ---------------------------------------------------------------------------
@app.get("/explain/{station_id}")
def explain(station_id: str, timestamp: str = None):
    station_alerts = results[
        (results["station_id"] == station_id) & (results["predicted_anomaly"] == 1)
    ].sort_values("timestamp", ascending=False)

    if station_alerts.empty:
        return {"station_id": station_id, "message": "No anomalies found for this station."}

    if timestamp:
        match = station_alerts[station_alerts["timestamp"].astype(str) == timestamp]
        row = match.iloc[0] if not match.empty else station_alerts.iloc[0]
    else:
        row = station_alerts.iloc[0]

    contribs = detector.explain_row(row)
    return {
        "station_id": station_id,
        "timestamp": str(row["timestamp"]),
        "root_cause": row["predicted_root_cause"],
        "confidence_score": round(float(row["confidence_score"]), 3),
        "trust_score": trust_score(row["confidence_score"]),
        "shap_contributions": {k: round(float(v), 4) for k, v in contribs.items()},
        "suggested_corrected_values": {
            col: None if pd.isna(row[f"{col}_corrected"]) else round(float(row[f"{col}_corrected"]), 2)
            for col in FEATURES
        },
    }


# ---------------------------------------------------------------------------
# NEW: Predictive maintenance
# ---------------------------------------------------------------------------
@app.get("/maintenance")
def get_maintenance():
    return maintenance_df.replace({np.nan: None}).to_dict(orient="records")


# ---------------------------------------------------------------------------
# NEW: Fleet intelligence — systemic vs isolated + anomaly archetypes
# ---------------------------------------------------------------------------
@app.get("/fleet/systemic")
def get_systemic_events():
    significant = systemic_df[systemic_df["classification"] == "SYSTEMIC_EVENT"].copy()
    significant["date"] = significant["date"].astype(str)
    return significant.to_dict(orient="records")


@app.get("/fleet/archetypes")
def get_archetypes():
    if archetype_df.empty:
        return []
    return archetype_df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# NEW: Live streaming simulation over WebSocket
# ---------------------------------------------------------------------------
@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """
    Streams one simulated 'live' reading at a time, cycling through the
    historical dataset, to demonstrate real-time ingestion without needing
    real hardware connected. Each tick simulates the next AWS reading
    arriving, complete with its anomaly verdict and trust score - this is
    what makes a live demo feel like a genuinely real-time monitoring
    system instead of a static report.
    """
    await websocket.accept()
    ordered = results.sort_values("timestamp").reset_index(drop=True)
    i = 0
    n = len(ordered)
    try:
        while True:
            row = ordered.iloc[i % n]
            payload = {
                "timestamp": str(row["timestamp"]),
                "station_id": row["station_id"],
                "temperature": None if pd.isna(row["temperature"]) else round(float(row["temperature"]), 2),
                "pressure": None if pd.isna(row["pressure"]) else round(float(row["pressure"]), 2),
                "humidity": None if pd.isna(row["humidity"]) else round(float(row["humidity"]), 2),
                "predicted_anomaly": int(row["predicted_anomaly"]),
                "root_cause": row["predicted_root_cause"],
                "confidence_score": round(float(row["confidence_score"]), 3),
                "trust_score": trust_score(row["confidence_score"]),
            }
            await websocket.send_json(payload)
            i += 1
            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# NEW: What-If Sensor Simulator Analysis Endpoint
# ---------------------------------------------------------------------------
from pydantic import BaseModel

class TelemetryInput(BaseModel):
    temperature: float
    pressure: float
    humidity: float

@app.post("/analyze")
def analyze_telemetry(payload: TelemetryInput):
    t = payload.temperature
    p = payload.pressure
    h = payload.humidity

    # 1. Layer 1 Rule-based bounds check
    range_violation = bool(t < -20 or t > 55 or p < 850 or p > 1085 or h < 0 or h > 100)

    # 2. Layer 3 Multivariate Isolation Forest check
    sample_df = pd.DataFrame([{"temperature": t, "pressure": p, "humidity": h}])
    raw_mv_score = -detector.iso_forest.score_samples(sample_df[FEATURES])[0]
    mv_pred = bool(detector.iso_forest.predict(sample_df[FEATURES])[0] == -1)

    # 3. Layer 5 Physics-based Magnus-Tetens dew point check
    b, c = 17.62, 243.12
    rh_c = max(0.1, min(100.0, h))
    alpha = np.log(rh_c / 100.0) + (b * t) / (c + t)
    dew_point = (c * alpha) / (b - alpha)
    physics_violation = bool(dew_point > t + 0.1 or (t > 38 and h > 85))

    # Calculate fused confidence score & trust score
    mv_norm = max(0.0, min(1.0, (raw_mv_score - 0.35) / 0.30))
    rule_score = 1.0 if range_violation else 0.0
    phys_score = 1.0 if physics_violation else 0.0

    confidence = round(float(0.45 * mv_norm + 0.35 * rule_score + 0.20 * phys_score), 3)
    is_anomaly = int(range_violation or mv_pred or physics_violation or confidence > 0.40)
    t_score = trust_score(confidence)

    # Root Cause Classification & Recommended Action
    if range_violation:
        cause = "sensor_spike_fault"
        action = "Out-of-range value detected. Dispatch field technician to test transducer."
    elif physics_violation:
        cause = "physics_inconsistent_reading"
        action = "Thermodynamically implausible T/RH coupling. Re-calibrate humidity probe."
    elif mv_pred:
        cause = "calibration_drift_or_inconsistency"
        action = "Multivariate isolation anomaly. Schedule sensor calibration test."
    else:
        cause = "normal"
        action = "Reading is within healthy expected meteorological operational limits."

    return {
        "temperature": t,
        "pressure": p,
        "humidity": h,
        "predicted_anomaly": is_anomaly,
        "confidence_score": confidence,
        "trust_score": t_score,
        "predicted_root_cause": cause,
        "dew_point": round(float(dew_point), 2),
        "layer_signals": {
            "range_violation": range_violation,
            "multivariate_ml": mv_pred,
            "physics_violation": physics_violation
        },
        "recommended_action": action
    }

