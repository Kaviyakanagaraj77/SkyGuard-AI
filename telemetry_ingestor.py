"""
SkyGuard AI v2 - Unified Telemetry Ingestion Pipeline (Phase 1)
------------------------------------------------------------------
Coordinates telemetry ingestion from synthetic CSV, HTTP REST webhooks, and future
authorized IMD AWS stream adapters. Passes validated packets into SkyGuardDetector.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime
from telemetry_validator import TelemetryPayload, TelemetryValidator
from database import db_enabled, SessionLocal


def _persist_to_db(payload: TelemetryPayload, result: Dict[str, Any]):
    """Persists validated telemetry and alerts to SQLAlchemy database if enabled."""
    if not db_enabled or not SessionLocal:
        return
    try:
        from models import StationModel, TelemetryModel, AlertModel
        session = SessionLocal()
        ts_clean = payload.timestamp.replace("Z", "+00:00")
        try:
            ts_dt = datetime.fromisoformat(ts_clean)
        except Exception:
            ts_dt = datetime.utcnow()

        # Ensure Station record exists
        st = session.query(StationModel).filter(StationModel.station_id == payload.station_id).first()
        if not st:
            st = StationModel(
                station_id=payload.station_id,
                location=payload.station_id,
                latitude=payload.latitude,
                longitude=payload.longitude
            )
            session.add(st)
            session.commit()

        # Create Telemetry Record
        det = result["detection"]
        t_model = TelemetryModel(
            station_id=payload.station_id,
            timestamp=ts_dt,
            temperature=payload.temperature,
            pressure=payload.pressure,
            humidity=payload.humidity,
            latitude=payload.latitude,
            longitude=payload.longitude,
            wind_speed=payload.wind_speed,
            wind_direction=payload.wind_direction,
            rainfall=payload.rainfall,
            solar_radiation=payload.solar_radiation,
            predicted_anomaly=det["predicted_anomaly"],
            confidence_score=det["confidence_score"],
            trust_score=det["trust_score"],
            predicted_root_cause=det["predicted_root_cause"],
            dew_point=det["dew_point"]
        )
        session.add(t_model)
        session.commit()

        # Create Alert Record if flagged as anomaly
        if det["predicted_anomaly"] == 1:
            alert = AlertModel(
                telemetry_id=t_model.id,
                station_id=payload.station_id,
                timestamp=ts_dt,
                confidence_score=det["confidence_score"],
                trust_score=det["trust_score"],
                root_cause=det["predicted_root_cause"],
                temperature=payload.temperature,
                pressure=payload.pressure,
                humidity=payload.humidity,
                status="Active"
            )
            session.add(alert)
            session.commit()

        session.close()
    except Exception:
        # Graceful database persistence error handling
        pass


from risk_engine import RiskEngine
from alert_service import AlertService


class TelemetryIngestor:
    def __init__(self, detector=None, validator=None, risk_engine=None, alert_service=None):
        self.validator = validator or TelemetryValidator()
        self.detector = detector
        self.risk_engine = risk_engine or RiskEngine()
        self.alert_service = alert_service or AlertService()

    def set_detector(self, detector):
        self.detector = detector

    def process_payload(self, payload: TelemetryPayload) -> Dict[str, Any]:
        """
        Ingests a single validated TelemetryPayload, runs it through SkyGuardDetector's
        5-layer AI detection engine, and returns a comprehensive ingestion result.
        """
        # Check duplicate packet cache before marking seen
        if self.validator.is_duplicate(payload.station_id, payload.timestamp):
            raise ValueError(f"Duplicate telemetry packet detected for {payload.station_id} at {payload.timestamp}.")
        self.validator.mark_seen(payload.station_id, payload.timestamp)

        t = payload.temperature
        p = payload.pressure
        h = payload.humidity

        # Create single-row DataFrame compatible with SkyGuardDetector
        row_dict = {
            "timestamp": pd.to_datetime(payload.timestamp),
            "station_id": payload.station_id,
            "temperature": t,
            "pressure": p,
            "humidity": h
        }
        df_row = pd.DataFrame([row_dict])

        # Execute 5-Layer AI Detection Engine if fitted detector is available
        if self.detector and hasattr(self.detector, "_fitted") and self.detector._fitted:
            # 1. Rule-based layer
            rule_flags = self.detector._rule_flags(df_row)
            range_viol = bool(rule_flags["range_violation"].iloc[0])
            frozen = bool(rule_flags["frozen"].iloc[0])
            spike = bool(rule_flags["rate_spike"].iloc[0])

            # 2. Multivariate Isolation Forest layer
            sample_df = pd.DataFrame([{"temperature": t, "pressure": p, "humidity": h}])
            raw_mv_score = -self.detector.iso_forest.score_samples(sample_df[["temperature", "pressure", "humidity"]])[0]
            mv_pred = bool(self.detector.iso_forest.predict(sample_df[["temperature", "pressure", "humidity"]])[0] == -1)

            # 3. Physics thermodynamic layer (Magnus-Tetens)
            b, c = 17.62, 243.12
            rh_c = max(0.1, min(100.0, h))
            alpha = np.log(rh_c / 100.0) + (b * t) / (c + t)
            dew_point = (c * alpha) / (b - alpha)
            phys_viol = bool(dew_point > t + 0.1 or (t > 38 and h > 85))

            # Normalize & blend confidence score
            mv_norm = max(0.0, min(1.0, (raw_mv_score - 0.35) / 0.30))
            rule_norm = 1.0 if (range_viol or frozen or spike) else 0.0
            phys_norm = 1.0 if phys_viol else 0.0

            confidence = round(float(0.40 * mv_norm + 0.35 * rule_norm + 0.25 * phys_norm), 3)
            is_anomaly = int(range_viol or frozen or spike or mv_pred or phys_viol or confidence > 0.40)
            trust_score = round(float(max(0.0, min(1.0, 1.0 - confidence))) * 100, 1)

            # Determine root cause diagnosis
            if range_viol or spike:
                root_cause = "sensor_spike_fault"
            elif frozen:
                root_cause = "sensor_stuck_fault"
            elif phys_viol:
                root_cause = "physics_inconsistent_reading"
            elif mv_pred:
                root_cause = "calibration_drift_or_inconsistency"
            else:
                root_cause = "normal"
        else:
            # Fallback bounds check if detector is initializing
            range_viol = bool(t < -20 or t > 55 or p < 850 or p > 1085 or h < 0 or h > 100)
            dew_point = 15.0
            confidence = 0.8 if range_viol else 0.05
            is_anomaly = 1 if range_viol else 0
            trust_score = round(float(1.0 - confidence) * 100, 1)
            root_cause = "sensor_spike_fault" if range_viol else "normal"
            mv_pred, phys_viol = False, False

        result = {
            "station_id": payload.station_id,
            "timestamp": payload.timestamp,
            "telemetry": {
                "temperature": t,
                "pressure": p,
                "humidity": h,
                "latitude": payload.latitude,
                "longitude": payload.longitude,
                "wind_speed": payload.wind_speed,
                "wind_direction": payload.wind_direction,
                "rainfall": payload.rainfall,
                "solar_radiation": payload.solar_radiation
            },
            "detection": {
                "predicted_anomaly": is_anomaly,
                "confidence_score": confidence,
                "trust_score": trust_score,
                "predicted_root_cause": root_cause,
                "dew_point": round(float(dew_point), 2),
                "layer_signals": {
                    "rule_violation": range_viol,
                    "multivariate_ml": mv_pred,
                    "physics_violation": phys_viol
                }
            },
            "ingestion_status": "success",
            "source": "api_v1_telemetry_ingest"
        }

        # Phase 3 Real-Time Risk & Early Warning Assessment
        risk_assessment = self.risk_engine.calculate_risk(
            station_id=payload.station_id,
            timestamp_str=payload.timestamp,
            temperature=t,
            pressure=p,
            humidity=h,
            wind_speed=payload.wind_speed,
            physics_breach=phys_viol
        )

        current_vals = {"temperature": t, "pressure": p, "humidity": h}
        if payload.wind_speed is not None:
            current_vals["wind_speed"] = payload.wind_speed

        early_alert = self.alert_service.generate_alert(
            risk_assessment=risk_assessment,
            current_values=current_vals
        )

        result["risk_assessment"] = risk_assessment.model_dump()
        result["early_warning_alert"] = early_alert.model_dump() if early_alert else None

        # Persist to database if db_enabled is True
        _persist_to_db(payload, result)

        return result

    def process_batch(self, payloads: List[TelemetryPayload]) -> List[Dict[str, Any]]:
        results = []
        for p in payloads:
            results.append(self.process_payload(p))
        return results

