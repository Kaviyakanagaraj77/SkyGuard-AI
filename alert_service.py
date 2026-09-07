"""
SkyGuard AI v2 - Early Warning Alert Service (Phase 3)
-------------------------------------------------------
Manages early warning alert generation, duplicate alert suppression windowing,
lifecycle transitions (ACTIVE -> ACKNOWLEDGED -> RESOLVED), and ORM database persistence.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field
import uuid

from risk_engine import RiskAssessment
from database import db_enabled, SessionLocal


class EarlyWarningAlert(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    station_id: str
    timestamp: str
    severity: str = Field(..., description="NORMAL, WARNING, or CRITICAL")
    affected_parameters: List[str] = Field(default_factory=list)
    current_values: Dict[str, float] = Field(default_factory=dict)
    risk_score: float
    message: str
    status: str = Field("ACTIVE", description="ACTIVE, ACKNOWLEDGED, or RESOLVED")


class AlertService:
    def __init__(self, suppression_window_minutes: int = 15):
        self.suppression_window_minutes = suppression_window_minutes
        self.in_memory_alerts: List[EarlyWarningAlert] = []
        self._recent_alert_cache: Dict[str, datetime] = {}  # key: f"{station_id}_{param}_{severity}"

    def should_trigger_alert(self, risk_assessment: RiskAssessment) -> bool:
        """
        Determines whether an early warning alert should be triggered based on:
        - Critical threshold crossed
        - Multiple warning conditions
        - Risk score reaches HIGH (>= 71.0)
        """
        if risk_assessment.risk_score >= 71.0:
            return True
        if "CRITICAL" in risk_assessment.severities.values():
            return True
        warning_count = sum(1 for s in risk_assessment.severities.values() if s == "WARNING")
        if warning_count >= 2:
            return True
        return False

    def is_duplicate(self, station_id: str, affected_params: List[str], severity: str) -> bool:
        """
        Checks whether a matching alert for the same station and parameters was triggered
        within the suppression window.
        """
        now = datetime.now(timezone.utc)
        cache_key = f"{station_id}_{'_'.join(sorted(affected_params))}_{severity}"
        if cache_key in self._recent_alert_cache:
            last_time = self._recent_alert_cache[cache_key]
            if now - last_time < timedelta(minutes=self.suppression_window_minutes):
                return True
        return False

    def generate_alert(
        self,
        risk_assessment: RiskAssessment,
        current_values: Dict[str, float],
        custom_message: Optional[str] = None
    ) -> Optional[EarlyWarningAlert]:
        """
        Generates and stores an EarlyWarningAlert if conditions are met and not suppressed as duplicate.
        """
        if not self.should_trigger_alert(risk_assessment):
            return None

        severities = risk_assessment.severities
        has_critical = "CRITICAL" in severities.values()
        overall_severity = "CRITICAL" if (has_critical or risk_assessment.risk_level == "HIGH") else "WARNING"

        affected = risk_assessment.contributing_parameters or ["general_telemetry"]

        # Duplicate alert suppression check
        if self.is_duplicate(risk_assessment.station_id, affected, overall_severity):
            return None

        msg = custom_message or (
            f"EARLY WARNING [{overall_severity}]: Station {risk_assessment.station_id} "
            f"reported elevated risk score {risk_assessment.risk_score} ({risk_assessment.risk_level}). "
            f"Affected parameters: {', '.join(affected)}."
        )

        alert = EarlyWarningAlert(
            station_id=risk_assessment.station_id,
            timestamp=risk_assessment.timestamp,
            severity=overall_severity,
            affected_parameters=affected,
            current_values=current_values,
            risk_score=risk_assessment.risk_score,
            message=msg,
            status="ACTIVE"
        )

        # Store in memory
        self.in_memory_alerts.insert(0, alert)
        
        # Update duplicate suppression cache
        now = datetime.now(timezone.utc)
        cache_key = f"{risk_assessment.station_id}_{'_'.join(sorted(affected))}_{overall_severity}"
        self._recent_alert_cache[cache_key] = now

        # Persist to database if DB is enabled
        self._persist_alert_to_db(alert)

        return alert

    def _persist_alert_to_db(self, alert: EarlyWarningAlert):
        """Persists Phase 3 alert to SQLAlchemy database if enabled."""
        if not db_enabled or not SessionLocal:
            return
        try:
            from models import AlertModel
            session = SessionLocal()
            ts_clean = alert.timestamp.replace("Z", "+00:00")
            try:
                ts_dt = datetime.fromisoformat(ts_clean)
            except Exception:
                ts_dt = datetime.utcnow()

            db_alert = AlertModel(
                station_id=alert.station_id,
                timestamp=ts_dt,
                confidence_score=round(alert.risk_score / 100.0, 3),
                trust_score=round(max(0.0, 100.0 - alert.risk_score), 1),
                root_cause=", ".join(alert.affected_parameters),
                temperature=alert.current_values.get("temperature"),
                pressure=alert.current_values.get("pressure"),
                humidity=alert.current_values.get("humidity"),
                status=alert.status,
                severity=alert.severity,
                risk_score=alert.risk_score,
                message=alert.message,
                affected_parameters=", ".join(alert.affected_parameters)
            )
            session.add(db_alert)
            session.commit()
            session.close()
        except Exception:
            pass

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Transitions an alert status to ACKNOWLEDGED."""
        updated = False
        for a in self.in_memory_alerts:
            if a.alert_id == alert_id:
                a.status = "ACKNOWLEDGED"
                updated = True
                break

        if db_enabled and SessionLocal:
            try:
                from models import AlertModel
                session = SessionLocal()
                # Check by string ID or numeric ID matching
                row = session.query(AlertModel).filter(AlertModel.id == alert_id).first()
                if row:
                    row.status = "ACKNOWLEDGED"
                    session.commit()
                    updated = True
                session.close()
            except Exception:
                pass
        return updated

    def resolve_alert(self, alert_id: str) -> bool:
        """Transitions an alert status to RESOLVED."""
        updated = False
        for a in self.in_memory_alerts:
            if a.alert_id == alert_id:
                a.status = "RESOLVED"
                updated = True
                break

        if db_enabled and SessionLocal:
            try:
                from models import AlertModel
                session = SessionLocal()
                row = session.query(AlertModel).filter(AlertModel.id == alert_id).first()
                if row:
                    row.status = "RESOLVED"
                    session.commit()
                    updated = True
                session.close()
            except Exception:
                pass
        return updated

    def get_active_alerts(self, station_id: Optional[str] = None) -> List[EarlyWarningAlert]:
        """Returns all ACTIVE early warning alerts."""
        alerts = [a for a in self.in_memory_alerts if a.status == "ACTIVE"]
        if station_id:
            alerts = [a for a in alerts if a.station_id == station_id]
        return alerts

    def get_alert_history(self, station_id: Optional[str] = None, severity: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns alert history with optional station and severity filtering."""
        res = []
        for a in self.in_memory_alerts:
            if station_id and a.station_id != station_id:
                continue
            if severity and a.severity != severity:
                continue
            res.append(a.model_dump())
            if len(res) >= limit:
                break
        return res
