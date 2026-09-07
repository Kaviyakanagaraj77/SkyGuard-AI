"""
SkyGuard AI v2 - Real-Time Risk Engine & Anomaly Detection (Phase 3)
----------------------------------------------------------------------
Provides deterministic, explainable anomaly detection, parameter deviation tracking,
and normalized risk scoring (0-100 scale: LOW, MEDIUM, HIGH) for AWS telemetry.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ParameterAnomaly(BaseModel):
    parameter: str = Field(..., description="Telemetry parameter name (e.g., temperature, pressure)")
    current_value: float = Field(..., description="Observed sensor reading")
    expected_range: str = Field(..., description="Normal operating bounds string")
    severity: str = Field(..., description="NORMAL, WARNING, or CRITICAL")
    timestamp: str = Field(..., description="ISO 8601 observation timestamp")
    reason: str = Field(..., description="Explanation of threshold or baseline deviation")
    status: str = Field("ACTIVE", description="Anomaly status: ACTIVE, ACKNOWLEDGED, RESOLVED")


class RiskAssessment(BaseModel):
    station_id: str
    timestamp: str
    risk_score: float = Field(..., description="Normalized risk score from 0.0 to 100.0")
    risk_level: str = Field(..., description="Risk tier: LOW (0-30), MEDIUM (31-70), HIGH (71-100)")
    contributing_parameters: List[str] = Field(default_factory=list, description="List of abnormal parameter names")
    explanation: str = Field(..., description="Human-readable summary of risk score factors")
    severities: Dict[str, str] = Field(default_factory=dict, description="Map of parameter to severity level")
    anomalies: List[ParameterAnomaly] = Field(default_factory=list, description="Detailed parameter anomaly breakdowns")


# Default Operational Parameter Bounds for AWS Sensors
DEFAULT_BOUNDS = {
    "temperature": {
        "normal_min": 10.0, "normal_max": 45.0,
        "warning_min": -10.0, "warning_max": 52.0,
        "critical_min": -40.0, "critical_max": 60.0
    },
    "pressure": {
        "normal_min": 950.0, "normal_max": 1050.0,
        "warning_min": 900.0, "warning_max": 1080.0,
        "critical_min": 800.0, "critical_max": 1100.0
    },
    "humidity": {
        "normal_min": 20.0, "normal_max": 90.0,
        "warning_min": 10.0, "warning_max": 95.0,
        "critical_min": 0.0, "critical_max": 100.0
    },
    "wind_speed": {
        "normal_min": 0.0, "normal_max": 25.0,
        "warning_min": 0.0, "warning_max": 40.0,
        "critical_min": 0.0, "critical_max": 150.0
    }
}


class RiskEngine:
    def __init__(self, custom_bounds: Optional[Dict[str, Dict[str, float]]] = None):
        self.bounds = custom_bounds or DEFAULT_BOUNDS

    def evaluate_parameter(self, param: str, val: float, timestamp_str: str) -> ParameterAnomaly:
        """
        Evaluates a single numeric telemetry parameter against deterministic operational limits.
        """
        if param not in self.bounds or val is None:
            return ParameterAnomaly(
                parameter=param,
                current_value=float(val) if val is not None else 0.0,
                expected_range="N/A",
                severity="NORMAL",
                timestamp=timestamp_str,
                reason=f"{param} within expected operating range.",
                status="NORMAL"
            )

        b = self.bounds[param]
        exp_range_str = f"[{b['normal_min']} to {b['normal_max']}]"

        # Check CRITICAL bounds (outside warning limits)
        if val > b["warning_max"] or val < b["warning_min"]:
            severity = "CRITICAL"
            reason = f"{param.capitalize()} value {val} severely breaches operational limit {exp_range_str}."
        # Check WARNING bounds (outside normal limits)
        elif val > b["normal_max"] or val < b["normal_min"]:
            severity = "WARNING"
            reason = f"{param.capitalize()} value {val} deviates from normal operating baseline {exp_range_str}."
        else:
            severity = "NORMAL"
            reason = f"{param.capitalize()} operating within normal parameters."

        return ParameterAnomaly(
            parameter=param,
            current_value=val,
            expected_range=exp_range_str,
            severity=severity,
            timestamp=timestamp_str,
            reason=reason,
            status=severity
        )

    def calculate_risk(
        self,
        station_id: str,
        timestamp_str: str,
        temperature: float,
        pressure: float,
        humidity: float,
        wind_speed: Optional[float] = None,
        physics_breach: bool = False
    ) -> RiskAssessment:
        """
        Calculates a deterministic normalized risk score (0.0 to 100.0) based on parameter severities
        and multi-parameter accumulation logic.

        Scoring Formula:
        - Base Score: 0.0
        - Single WARNING parameter: +25.0 points
        - Single CRITICAL parameter: +55.0 points
        - Multi-Parameter Bonus: +15.0 points per additional non-NORMAL parameter (beyond 1)
        - Physics Inconsistency Breach: +20.0 points
        - Clamped to range [0.0, 100.0]
        - Risk Tiers:
            0.0 <= score <= 30.0 -> LOW
            30.1 <= score <= 70.0 -> MEDIUM
            70.1 <= score <= 100.0 -> HIGH
        """
        params_to_check = {
            "temperature": temperature,
            "pressure": pressure,
            "humidity": humidity
        }
        if wind_speed is not None:
            params_to_check["wind_speed"] = wind_speed

        anomalies: List[ParameterAnomaly] = []
        severities: Dict[str, str] = {}
        contributing: List[str] = []

        warning_count = 0
        critical_count = 0
        raw_score = 0.0

        for p_name, p_val in params_to_check.items():
            anom = self.evaluate_parameter(p_name, p_val, timestamp_str)
            anomalies.append(anom)
            severities[p_name] = anom.severity

            if anom.severity == "WARNING":
                warning_count += 1
                contributing.append(p_name)
                raw_score += 25.0
            elif anom.severity == "CRITICAL":
                critical_count += 1
                contributing.append(p_name)
                raw_score += 55.0

        total_abnormal = warning_count + critical_count
        if total_abnormal > 1:
            raw_score += 15.0 * (total_abnormal - 1)

        if physics_breach:
            raw_score += 20.0
            if "thermodynamics" not in contributing:
                contributing.append("thermodynamics")

        risk_score = round(min(100.0, max(0.0, raw_score)), 1)

        if risk_score <= 30.0:
            risk_level = "LOW"
        elif risk_score <= 70.0:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        if total_abnormal == 0 and not physics_breach:
            explanation = "Station operating normally with zero parameter anomalies detected."
        else:
            explanation = (
                f"Risk score {risk_score} ({risk_level}) driven by {total_abnormal} abnormal parameter(s): "
                f"{', '.join(contributing)}."
            )

        return RiskAssessment(
            station_id=station_id,
            timestamp=timestamp_str,
            risk_score=risk_score,
            risk_level=risk_level,
            contributing_parameters=contributing,
            explanation=explanation,
            severities=severities,
            anomalies=anomalies
        )
