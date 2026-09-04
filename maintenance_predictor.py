"""
SkyGuard AI - Predictive Maintenance Module
-----------------------------------------------
Directly addresses the problem statement's objective: "Predict possible
sensor degradation and maintenance requirements."

Approach: track each station's rolling anomaly rate over time. A healthy
sensor's anomaly rate should be low and flat. A degrading sensor typically
shows a rising trend even before it fails outright (more frequent small
drifts/spikes as components wear). We fit a simple linear trend to the
recent rolling anomaly rate and extrapolate to estimate when a station will
cross a "needs maintenance" threshold - turning detection into prevention.
"""

import numpy as np
import pandas as pd


MAINTENANCE_THRESHOLD = 0.25  # calibrate above the detector's baseline false-positive
                               # rate (~13-14% on this dataset - see evaluate.py) so a
                               # healthy station's normal noise doesn't trigger a false
                               # maintenance flag. In production this threshold should be
                               # set per-deployment from a burn-in period of known-healthy
                               # station data, not hardcoded.


def compute_degradation_trend(detection_results_path="data/detection_results.csv",
                               window_hours=24 * 7, threshold=MAINTENANCE_THRESHOLD):
    df = pd.read_csv(detection_results_path, parse_dates=["timestamp"])
    reports = []

    for station, g in df.groupby("station_id"):
        g = g.sort_values("timestamp").reset_index(drop=True)
        g["rolling_anomaly_rate"] = (
            g["predicted_anomaly"].rolling(window_hours, min_periods=24).mean()
        )
        valid = g.dropna(subset=["rolling_anomaly_rate"])
        if len(valid) < 2:
            continue

        # Fit a simple linear trend over the last ~30 days of rolling rate
        recent = valid.tail(24 * 30)
        x = np.arange(len(recent))
        y = recent["rolling_anomaly_rate"].values
        if len(x) < 2 or np.all(y == y[0]):
            slope, intercept = 0.0, y[-1] if len(y) else 0.0
        else:
            slope, intercept = np.polyfit(x, y, 1)

        current_rate = y[-1] if len(y) else 0.0

        if slope <= 1e-6:
            eta_hours = None  # not degrading (flat or improving)
        elif current_rate >= threshold:
            eta_hours = 0  # already past threshold
        else:
            eta_hours = max(0, (threshold - current_rate) / slope)

        status = "HEALTHY"
        if current_rate >= threshold:
            status = "MAINTENANCE_REQUIRED_NOW"
        elif eta_hours is not None and eta_hours <= 24 * 14:
            status = "MAINTENANCE_PREDICTED_SOON"
        elif slope > 1e-6:
            status = "DEGRADING_SLOWLY"

        reports.append({
            "station_id": station,
            "current_anomaly_rate": round(float(current_rate), 4),
            "trend_slope_per_hour": round(float(slope), 6),
            "estimated_hours_to_maintenance": None if eta_hours is None else round(eta_hours, 1),
            "estimated_days_to_maintenance": None if eta_hours is None else round(eta_hours / 24, 1),
            "status": status,
        })

    return pd.DataFrame(reports).sort_values("current_anomaly_rate", ascending=False)


if __name__ == "__main__":
    report = compute_degradation_trend()
    print("=== Predictive Maintenance Report ===")
    print(report.to_string(index=False))
    report.to_csv("data/maintenance_report.csv", index=False)
