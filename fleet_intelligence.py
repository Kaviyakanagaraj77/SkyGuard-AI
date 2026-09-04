"""
SkyGuard AI - Fleet Intelligence Module
-------------------------------------------
Every other module in this project reasons about ONE station at a time.
This module reasons about the WHOLE NETWORK - which is the actual problem
at ministry scale (hundreds of AWS stations, not five).

Two capabilities:

1. SYSTEMIC vs ISOLATED classification
   If the same root-cause anomaly type shows up across MANY stations on the
   same day, that's not five independent sensor failures - it's much more
   likely a shared cause: a firmware bug pushed to a batch of stations, a
   power-grid event, or a genuine large-scale weather system. Isolated
   single-station faults, by contrast, really are just "replace that
   sensor" issues. Telling these apart changes what IMD actually does in
   response - patch a firmware version vs. dispatch a repair technician -
   and no other layer in this project currently makes that distinction.

2. ANOMALY ARCHETYPES (recurring signature clustering)
   Clusters detected anomalies by their "shape" (which layers fired, at what
   magnitude, what time of day) using KMeans. Recurring archetypes across
   many stations/times point to a systemic hardware/firmware pattern worth
   investigating fleet-wide, rather than being dismissed as noise one alert
   at a time.
"""

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.cluster import KMeans


def systemic_vs_isolated(detection_results_path="data/detection_results.csv",
                          significance_level=0.05, min_stations=2):
    """
    Naive 'fraction of fleet affected' thresholds break down at small station
    counts: with only a handful of stations and a non-trivial baseline
    false-positive rate, two or three stations coincidentally flagging the
    same root cause on the same day happens by CHANCE regularly - that's not
    a systemic event, it's noise. This matters more, not less, as you scale
    to real deployments with hundreds of stations, where you need to be able
    to tell genuine coordinated failures apart from background noise.

    So instead of a raw fraction, we run a one-sided binomial test: given
    each root cause's own baseline per-station-per-day occurrence rate
    (estimated from the whole dataset), what's the probability of seeing
    this many stations affected on one day BY CHANCE ALONE? Only flag
    SYSTEMIC_EVENT when that's statistically unlikely (p < 0.05) - this is
    what actually justifies telling IMD "investigate a shared cause" instead
    of "these are independent hardware faults."
    """
    df = pd.read_csv(detection_results_path, parse_dates=["timestamp"])
    anomalies = df[df["predicted_anomaly"] == 1].copy()
    anomalies["date"] = anomalies["timestamp"].dt.date
    n_stations = df["station_id"].nunique()
    n_days = df["timestamp"].dt.date.nunique()

    # Baseline per-station-per-day occurrence probability, per root cause
    station_day_hits = (
        anomalies.groupby(["predicted_root_cause", "date", "station_id"])
        .size().reset_index(name="hits")
    )
    baseline_p = (
        station_day_hits.groupby("predicted_root_cause")["station_id"].count()
        / (n_stations * n_days)
    ).clip(upper=0.99)

    grouped = (
        anomalies.groupby(["date", "predicted_root_cause"])["station_id"]
        .nunique()
        .reset_index(name="stations_affected")
    )
    grouped["fraction_of_fleet"] = grouped["stations_affected"] / n_stations

    p_values, classifications = [], []
    for _, row in grouped.iterrows():
        p0 = baseline_p.get(row["predicted_root_cause"], 0.05)
        k = int(row["stations_affected"])
        if k < min_stations:
            p_values.append(1.0)
            classifications.append("ISOLATED_FAULT")
            continue
        result = binomtest(k, n_stations, p0, alternative="greater")
        pval = result.pvalue
        p_values.append(round(pval, 4))
        classifications.append("SYSTEMIC_EVENT" if pval < significance_level else "ISOLATED_FAULT")

    grouped["p_value_vs_chance"] = p_values
    grouped["classification"] = classifications
    grouped = grouped.sort_values(["classification", "p_value_vs_chance"],
                                   ascending=[False, True])
    return grouped


def anomaly_archetypes(detection_results_path="data/detection_results.csv", n_clusters=5):
    """
    Clusters every detected anomaly by its multi-layer 'signature':
    how strongly each layer fired, and time-of-day (cyclically encoded).
    Recurring archetypes that show up across many stations point to a
    shared hardware/firmware pattern rather than independent random noise.
    """
    df = pd.read_csv(detection_results_path, parse_dates=["timestamp"])
    anomalies = df[df["predicted_anomaly"] == 1].copy()
    if len(anomalies) < n_clusters:
        return pd.DataFrame(), anomalies

    hour = anomalies["timestamp"].dt.hour
    features = pd.DataFrame({
        "mv_score": anomalies["mv_score"],
        "temporal_z": anomalies["temporal_z"] / 6.0,
        "spatial_z": anomalies["spatial_z"] / 6.0,
        "physics_violation": anomalies["physics_violation"].astype(float),
        "hour_sin": np.sin(2 * np.pi * hour / 24),
        "hour_cos": np.cos(2 * np.pi * hour / 24),
    }).fillna(0)

    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    anomalies["archetype"] = km.fit_predict(features)

    summary = (
        anomalies.groupby("archetype")
        .agg(
            occurrences=("archetype", "size"),
            stations_affected=("station_id", "nunique"),
            dominant_root_cause=("predicted_root_cause",
                                  lambda s: s.value_counts().idxmax()),
            avg_confidence=("confidence_score", "mean"),
            avg_hour=("timestamp", lambda s: s.dt.hour.mean()),
        )
        .reset_index()
        .sort_values("occurrences", ascending=False)
    )
    summary["avg_confidence"] = summary["avg_confidence"].round(3)
    summary["avg_hour"] = summary["avg_hour"].round(1)
    summary["spans_multiple_stations"] = summary["stations_affected"] > 1
    return summary, anomalies


if __name__ == "__main__":
    print("=== Systemic vs Isolated Anomaly Report ===")
    report = systemic_vs_isolated()
    print(report.head(15).to_string(index=False))
    report.to_csv("data/systemic_report.csv", index=False)

    print("\n=== Anomaly Archetypes (recurring signature clusters) ===")
    archetypes, _ = anomaly_archetypes()
    print(archetypes.to_string(index=False))
    archetypes.to_csv("data/archetype_report.csv", index=False)
