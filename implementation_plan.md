# SkyGuard AI v2 — Final Production Quality Fix & SIH 2026 Readiness Plan

This implementation plan outlines the targeted fixes, UI polish, backend health monitoring, and page-by-page verification required to ensure **SkyGuard AI v2** is 100% production-stable and presentation-ready for the SIH 2026 evaluation.

---

## 🔒 Safety & Non-Negotiable Rules

> [!IMPORTANT]
> The core system architecture and Phase 1–5 implementations must remain intact:
> - **`dashboard.py`**: **100% UNTOUCHED**
> - **`anomaly_detector.py`**: **100% UNTOUCHED**
> - **Render Backend URL**: `https://skyguard-ai-d2jb.onrender.com`
> - **Vercel Frontend URL**: `https://sky-guard-ai-seven.vercel.app/`
> - **API Contracts**: All 65 automated regression tests must pass without breaking existing request/response schemas.

---

## 🎯 Target Improvements & Fix Summary

### 1. Render Backend Production Reliability & Readiness Probe
- Add explicit `@app.get("/ready")` and `@app.get("/api/v1/ready")` readiness probes in `backend/main.py` for cloud load balancer health checks.

### 2. Truthful Frontend Backend Status & Cold-Start Recovery
- Add live health polling (`checkBackendHealth()`) every 10 seconds checking `API_BASE + "/health"`.
- Update status badge dynamically (🟢 Backend Online, 🟡 Connecting / Re-waking, 🔴 Backend Offline with Retry button).

### 3. Digital Twin Verification
- Line graphs for Temperature, Pressure, and Humidity render real backend data cleanly across all stations (`AWS_001` through `AWS_005`).

---

## 🛠️ Proposed File Changes

### Backend Component
- Modify `backend/main.py` to add `/ready` probes and router endpoints.

### Frontend Component
- Modify `frontend/index.html` to add backend health indicator, KPI label update, 5-layer XAI, simulator presets, printable incident report.
