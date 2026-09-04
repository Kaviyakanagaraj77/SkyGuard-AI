"""
SkyGuard AI - Live Dashboard (Streamlit)
-------------------------------------------
Run with:  streamlit run dashboard.py

Shows:
  - Per-station time series (temperature/pressure/humidity) with anomalies
    highlighted and corrected values overlaid
  - A station health grid (green/yellow/red)
  - An alert feed with confidence score + root-cause classification
  - A SHAP explanation panel for any selected alert ("why was this flagged?")
  - A simple real-time simulation slider to mimic a live AWS data stream
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from anomaly_detector import SkyGuardDetector, FEATURES
from maintenance_predictor import compute_degradation_trend
from fleet_intelligence import systemic_vs_isolated, anomaly_archetypes

st.set_page_config(page_title="SkyGuard AI - AWS Anomaly Monitor", layout="wide")


@st.cache_data
def load_and_detect():
    df = pd.read_csv("data/aws_dataset.csv", parse_dates=["timestamp"])
    detector = SkyGuardDetector().fit(df)
    result = detector.detect(df)
    result.to_csv("data/detection_results.csv", index=False)
    maintenance = compute_degradation_trend()
    systemic = systemic_vs_isolated()
    archetypes, _ = anomaly_archetypes()
    return result, detector, maintenance, systemic, archetypes


result, detector, maintenance, systemic, archetypes = load_and_detect()
stations = sorted(result["station_id"].unique())

st.title("🌩️ SkyGuard AI — Real-Time AWS Anomaly Detection")
st.caption("AI/ML-based intelligent anomaly detection for Automatic Weather Stations "
           "(Temperature, Pressure, Humidity) · SIH 2026 · Problem Statement 26073")

# ---------------- Sidebar controls ----------------
st.sidebar.header("Controls")
station = st.sidebar.selectbox("Select AWS Station", stations)
max_idx = result[result["station_id"] == station].shape[0] - 1
sim_hour = st.sidebar.slider("Simulated live stream position (hour)", 24, max_idx, max_idx,
                              help="Drag to replay the stream up to this point in time — mimics live ingestion.")

station_df = result[result["station_id"] == station].reset_index(drop=True)
visible_df = station_df.iloc[:sim_hour + 1]

# ---------------- Station health grid ----------------
st.subheader("Network Health Overview")
status_icons = {
    "MAINTENANCE_REQUIRED_NOW": "🔴",
    "MAINTENANCE_PREDICTED_SOON": "🟠",
    "DEGRADING_SLOWLY": "🟡",
    "HEALTHY": "🟢",
}
cols = st.columns(len(stations))
maint_by_station = maintenance.set_index("station_id").to_dict("index")
for i, s in enumerate(stations):
    m = maint_by_station.get(s, {})
    status = m.get("status", "UNKNOWN")
    icon = status_icons.get(status, "⚪")
    eta = m.get("estimated_days_to_maintenance")
    eta_txt = f"{eta} days to maintenance" if eta is not None else "no rising trend"
    with cols[i]:
        st.metric(label=f"{icon} {s}", value=status.replace("_", " ").title(), delta=eta_txt)

st.divider()

# ---------------- Predictive maintenance detail ----------------
with st.expander("🔧 Predictive Maintenance — full trend report"):
    st.caption("Rolling 7-day anomaly rate per station, trended forward to estimate when "
               "a station will cross the maintenance threshold — answers the problem "
               "statement's objective to 'predict possible sensor degradation and "
               "maintenance requirements' before a sensor fails outright.")
    st.dataframe(maintenance, use_container_width=True, hide_index=True)

st.divider()

# ---------------- Fleet intelligence ----------------
st.subheader("🌐 Fleet Intelligence — Network-Wide Pattern Detection")
st.caption("Most anomaly detectors reason about one station at a time. This looks across "
           "the whole network to tell IMD whether a spike in faults is a coincidence, "
           "or a shared cause (firmware bug, power-grid event, regional weather system) "
           "worth investigating fleet-wide — a distinction that matters at national scale.")

fc1, fc2 = st.columns(2)
with fc1:
    st.markdown("**Statistically significant systemic events**")
    st.caption("Flagged only when the number of stations affected on one day is "
               "unlikely to happen by chance (binomial test, p < 0.05) — not just a raw count.")
    systemic_events = systemic[systemic["classification"] == "SYSTEMIC_EVENT"]
    st.dataframe(
        systemic_events[["date", "predicted_root_cause", "stations_affected", "p_value_vs_chance"]],
        use_container_width=True, hide_index=True, height=280
    )
with fc2:
    st.markdown("**Recurring anomaly archetypes**")
    st.caption("Anomalies clustered by signature (which layers fired, magnitude, time of day). "
               "An archetype spanning many stations may indicate a shared hardware/firmware pattern.")
    if not archetypes.empty:
        st.dataframe(
            archetypes[["archetype", "occurrences", "stations_affected",
                        "dominant_root_cause", "avg_hour"]],
            use_container_width=True, hide_index=True, height=280
        )

st.divider()

# ---------------- Time series with anomalies ----------------
st.subheader(f"Sensor Streams — {station}")
tabs = st.tabs(["Temperature (°C)", "Pressure (hPa)", "Humidity (%)"])

for tab, col in zip(tabs, FEATURES):
    with tab:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=visible_df["timestamp"], y=visible_df[col],
            mode="lines", name=col, line=dict(color="#4C8BF5")
        ))
        anomalies = visible_df[visible_df["predicted_anomaly"] == 1]
        fig.add_trace(go.Scatter(
            x=anomalies["timestamp"], y=anomalies[col],
            mode="markers", name="Detected anomaly",
            marker=dict(color="red", size=9, symbol="x")
        ))
        fig.add_trace(go.Scatter(
            x=anomalies["timestamp"], y=anomalies[f"{col}_corrected"],
            mode="markers", name="Suggested corrected value",
            marker=dict(color="green", size=8, symbol="circle-open")
        ))
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10),
                           legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------- Alert feed ----------------
st.subheader("Live Alert Feed")
alerts = visible_df[visible_df["predicted_anomaly"] == 1].sort_values("timestamp", ascending=False)

if alerts.empty:
    st.info("No anomalies detected in the current window.")
else:
    display_cols = ["timestamp", "temperature", "pressure", "humidity", "dew_point",
                     "confidence_score", "predicted_root_cause"]
    st.dataframe(alerts[display_cols].head(30), use_container_width=True, hide_index=True)

    st.markdown("**Explain an alert (SHAP-based reasoning):**")
    alert_options = alerts.head(30)["timestamp"].astype(str).tolist()
    chosen_ts = st.selectbox("Pick an alert timestamp", alert_options)
    row = alerts[alerts["timestamp"].astype(str) == chosen_ts].iloc[0]

    contribs = detector.explain_row(row)
    c1, c2 = st.columns([2, 1])
    with c1:
        fig = go.Figure(go.Bar(
            x=list(contribs.values()), y=list(contribs.keys()), orientation="h",
            marker_color=["#E64848" if v > 0 else "#4C8BF5" for v in contribs.values()]
        ))
        fig.update_layout(title="SHAP contribution to anomaly score", height=250,
                           margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown(f"**Root cause:** `{row['predicted_root_cause']}`")
        st.markdown(f"**Confidence:** {row['confidence_score']:.2f}")
        st.markdown(f"**Suggested correction:**")
        for f in FEATURES:
            st.markdown(f"- {f}: {row[f]:.2f} → **{row[f'{f}_corrected']:.2f}**")

st.divider()
st.caption("Grand Challenge framing: this pipeline fuses rule-based, temporal, multivariate, "
           "and spatial-consensus signals into one confidence score — moving AWS networks "
           "toward a self-aware, self-healing observation system.")
