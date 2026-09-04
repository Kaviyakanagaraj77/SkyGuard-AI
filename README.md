# SkyGuard AI
### Intelligent Real-Time Anomaly Detection for Automatic Weather Stations
**SIH 2026 · Problem Statement 26073 · Ministry of Earth Sciences (MoES) / IMD**

---

## 1. Problem
Automatic Weather Stations (AWS) report Temperature, Pressure, and Humidity, but
sensor faults, communication failures, calibration drift, and power issues
regularly corrupt this data. Simple threshold-based QC cannot catch complex or
hidden anomalies — and can't tell a *faulty reading* apart from a *genuine
extreme weather event*.

## 2. Our Approach — Layered, Explainable, Multivariate Detection
Rather than a single model, SkyGuard AI fuses four independent detection
layers, because each anomaly type has a different statistical signature:

| Layer | Purpose | Method |
|---|---|---|
| 1. Rule-based | Frozen sensors, physically impossible ranges, rate-of-change spikes, dropout/comms failure | Rolling variance, hard bounds, first-difference thresholds |
| 2. Temporal | Deviation from the station's own expected diurnal/seasonal pattern | Per-hour z-score residuals |
| 3. Multivariate ML | Values individually normal but jointly inconsistent (e.g. high temp + high humidity + wrong pressure trend) | Isolation Forest over (temp, pressure, humidity) |
| 4. Spatial | One station diverging while neighbors report normally — directly matches the problem statement's example use case | Robust (MAD-based) z-score against simultaneous neighbor readings |
| 5. Physics-based | Temperature and humidity rising *together* with no pressure drop — thermodynamically inconsistent, since RH normally falls as T rises unless a real front (which drops pressure) is moving in | Rate-of-change rule grounded in atmospheric physics, not statistics |

These are fused into a single **confidence score**, and combined with rule
outputs to produce a **root-cause classification**: `sensor_stuck_fault`,
`communication_failure`, `sensor_spike_fault`, `localized_sensor_fault`,
`calibration_drift_or_inconsistency`, or `possible_genuine_weather_event`.

**Explainability**: Layer 3's Isolation Forest is wrapped with SHAP, so every
flagged alert shows which parameter (temperature/pressure/humidity) drove the
anomaly score — satisfying the explainability evaluation criterion, not just
bolting XAI on as an afterthought.

**Suggested correction**: for any flagged point, we output a rolling-median
imputed value from the same station as a proposed corrected reading.

## 3. Why Synthetic Data + Injected Anomalies
Bulk IMD/AWS station data isn't freely downloadable (access is
request/paid-based). The evaluation criteria itself states results will be
"evaluated on anomaly injected data" — so `data_generator.py` builds
realistic multi-station series (diurnal + seasonal patterns, spatial
correlation between neighbors) and injects **labeled** anomalies (spike,
frozen, drift, dropout, multivariate-inconsistent) so we can report real
Precision/Recall/F1 numbers instead of unverifiable claims.

## 4. Results (on synthetic labeled data — see `evaluate.py`)
- Overall: Precision 0.50 / Recall 0.71 / F1 0.59
- Spike, dropout, and multivariate-inconsistency anomalies: **100% recall**
- The physics layer independently catches 21/46 (46%) of thermodynamically
  inconsistent readings on its own; combined with the other layers, 31/46
  (67%) are caught overall — verified directly against ground truth, not
  estimated.
- Drift and frozen-sensor anomalies are harder (~61–64% recall) — an honest,
  presentable limitation with a clear improvement path (LSTM-autoencoder
  for slow drift, described below).

## 4b. Predictive Maintenance (`maintenance_predictor.py`)
Directly answers the objective "predict possible sensor degradation and
maintenance requirements." Tracks each station's rolling 7-day anomaly rate,
fits a linear trend, and extrapolates to estimate days-until-maintenance.
Output statuses: `HEALTHY`, `DEGRADING_SLOWLY`, `MAINTENANCE_PREDICTED_SOON`,
`MAINTENANCE_REQUIRED_NOW`. The threshold (25%) is calibrated *above* the
detector's own baseline false-positive rate (~13–14%) so normal detector
noise doesn't trigger false maintenance flags — in a real deployment this
threshold should be set from a burn-in period on known-healthy stations
rather than hardcoded.

## 4c. Fleet Intelligence (`fleet_intelligence.py`) — the key differentiator
Every layer above reasons about **one station at a time**. At ministry scale
(hundreds of AWS stations), the operationally critical question is
different: *is this one broken sensor, or a shared cause affecting many
stations at once* (firmware bug rolled to a batch, a power-grid event, or a
genuine large-scale weather system)? Getting this wrong means IMD either
dispatches a technician for a problem that will recur across the fleet, or
ignores a systemic issue as "just noise."

- **Systemic vs. Isolated classification**: uses a one-sided binomial
  significance test (not a raw fraction threshold) — flags a date/root-cause
  combination as `SYSTEMIC_EVENT` only when the number of stations affected
  is statistically unlikely to occur by chance given that root cause's own
  baseline rate (p < 0.05). Verified result: 21 statistically significant
  systemic events identified out of 393 date/root-cause combinations, with
  `localized_sensor_fault` (station-specific by design) correctly classified
  as isolated almost everywhere — confirming the test isn't just flagging
  the most common cause.
- **Anomaly archetypes**: clusters every detected anomaly by its multi-layer
  signature (KMeans over layer magnitudes + time-of-day) to surface
  recurring patterns across stations — a fleet-wide firmware or hardware
  batch defect looks like a repeated archetype cluster, not independent noise.

## 4d. Live Web App (`backend/` + `frontend/`) — Digital Twin, Trust Score, Live Mode
On top of the analysis pipeline above, the project includes a full working
web application:

- **FastAPI backend** (`backend/main.py`): serves stations, alerts,
  maintenance, fleet intelligence, and a new **Digital Twin** endpoint that
  returns each station's actual reading alongside its climatologically
  *expected* reading — so the dashboard can show "what a healthy station
  should look like right now" next to what it's actually reporting.
- **Trust Score**: every reading gets a continuous 0–100 trust score
  (derived from the fused confidence score) instead of only a binary
  anomaly flag — letting a downstream forecasting system soft-weight a
  reading rather than discard it outright.
- **SHAP explainability on click**: clicking any alert in the dashboard
  calls `/explain/{station_id}` and shows exactly which parameter drove
  the anomaly score, plus the suggested corrected value.
- **Live Mode (WebSocket)**: `/ws/live` streams simulated real-time AWS
  readings one at a time, so the dashboard can demonstrate genuine
  real-time ingestion in a demo without needing physical hardware connected.
- Chart.js is bundled locally (`frontend/vendor_chart.js`) rather than
  loaded from a CDN, so the demo still works if hackathon venue wifi is
  unreliable.
- **Verified end-to-end**: all 8 REST endpoints and the WebSocket stream
  were tested over real HTTP/WS calls, and the full production dashboard was tested
  in a real browser — zero console errors, all sections
  (station grid, Digital Twin charts, Predictive Maintenance, Fleet
  Intelligence, alerts, SHAP explain panel, Live Mode) confirmed rendering
  with live backend data.

**Quick 1-Click Launch:**
```bash
python start_app.py
```
This automatically starts the FastAPI backend (Port 8000), launches the production web application (Port 8080), and opens the dashboard in your default browser.

**Manual Launch:**
```bash
# Terminal 1: Start FastAPI backend
cd backend && python -m uvicorn main:app --reload --port 8000

# Terminal 2: Start Web Frontend
cd frontend && python -m http.server 8080
# Open http://127.0.0.1:8080 in your browser
```

## 5. Project Structure
```
skyguard/
├── start_app.py          # unified 1-click launcher for backend & web application
├── test_app.py           # automated verification test suite for all endpoints
├── data_generator.py     # synthetic multi-station AWS data + labeled anomaly injection
├── anomaly_detector.py   # 5-layer detection engine + SHAP explainability
├── evaluate.py           # precision/recall/F1 evaluation against ground truth
├── maintenance_predictor.py  # per-station degradation trend + maintenance forecast
├── fleet_intelligence.py # network-wide systemic-vs-isolated detection + anomaly archetypes
├── dashboard.py          # Streamlit live monitoring dashboard (untouched backup)
├── backend/
│   └── main.py           # FastAPI REST & WebSocket streaming server
├── frontend/
│   ├── index.html        # Production SIH 2026 Single Page Application (SPA)
│   └── vendor_chart.js   # Bundled local Chart.js library (offline hackathon resilience)
└── data/
    ├── aws_dataset.csv          # generated dataset (ground truth labels included)
    ├── detection_results.csv    # detector output
    ├── maintenance_report.csv   # per-station maintenance forecast
    ├── systemic_report.csv      # fleet-wide systemic vs isolated classification
    └── archetype_report.csv     # recurring anomaly signature clusters
```

## 6. How to Run & Verify
```bash
# Run automated verification test suite
python test_app.py

# Launch production web application
python start_app.py

# Optional: run legacy Streamlit backup dashboard
streamlit run dashboard.py
```

## 7. Roadmap / What We'd Add Next
- **Temporal deep learning**: LSTM-Autoencoder to improve recall on slow
  calibration drift (currently handled only by per-hour z-score residuals).
- **Edge AI deployment**: distill/quantize the Isolation Forest or a small
  autoencoder to TensorFlow Lite Micro for on-device inference on ESP32,
  directly addressing the "Energy Efficiency" and "Deployability" criteria.
- **Real IMD/NOAA ISD data** integration once a data-sharing agreement or API
  key is available, replacing/augmenting the synthetic backbone.
- **Automated maintenance prediction**: trend the confidence score per
  station over weeks to flag sensors likely to need servicing before they
  fail outright.

## 8. Grand Challenge Alignment
> "Can AI build a self-aware and self-healing weather observation network
> capable of delivering trustworthy atmospheric data under all environmental
> conditions?"

SkyGuard AI's spatial-consensus layer (Layer 4) is the "self-aware" piece —
each station is cross-validated against its neighbors in real time — and the
corrected-value suggestion is the first step toward "self-healing":
proposing a trustworthy estimate rather than just discarding bad data.
