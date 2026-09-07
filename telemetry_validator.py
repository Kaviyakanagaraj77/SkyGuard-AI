"""
SkyGuard AI v2 - Telemetry Validation Engine (Phase 1)
--------------------------------------------------------
Provides strict data schema, physical range validation, timestamp parsing,
station ID formatting, and duplicate packet detection for AWS telemetry.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import re

# Physical boundary constants for AWS sensors
TEMP_MIN, TEMP_MAX = -40.0, 60.0       # Celsius
PRESS_MIN, PRESS_MAX = 800.0, 1100.0   # hPa
HUM_MIN, HUM_MAX = 0.0, 100.0          # Percent
WIND_SPEED_MAX = 150.0                 # m/s
RAIN_MAX = 500.0                       # mm/hr
SOLAR_MAX = 2000.0                     # W/m²


class TelemetryPayload(BaseModel):
    station_id: str = Field(..., description="Unique AWS station identifier (e.g. AWS_001, IMD_AWS_101)")
    timestamp: str = Field(..., description="ISO 8601 formatted observation timestamp")
    temperature: float = Field(..., description="Air temperature in °C")
    pressure: float = Field(..., description="Atmospheric pressure in hPa")
    humidity: float = Field(..., description="Relative humidity in %")
    latitude: Optional[float] = Field(None, description="Geographic latitude")
    longitude: Optional[float] = Field(None, description="Geographic longitude")
    wind_speed: Optional[float] = Field(None, description="Wind speed in m/s")
    wind_direction: Optional[float] = Field(None, description="Wind direction in degrees (0-360)")
    rainfall: Optional[float] = Field(None, description="Accumulated rainfall in mm")
    solar_radiation: Optional[float] = Field(None, description="Solar radiation intensity in W/m²")

    @field_validator("station_id")
    def validate_station_id(cls, v):
        v_str = str(v).strip()
        if not v_str or len(v_str) < 3:
            raise ValueError("station_id must be at least 3 characters long.")
        if not re.match(r"^[A-Za-z0-9_-]+$", v_str):
            raise ValueError("station_id must contain only alphanumeric characters, hyphens, or underscores.")
        return v_str

    @field_validator("timestamp")
    def validate_timestamp(cls, v):
        v_str = str(v).strip()
        try:
            # Parse ISO timestamp
            dt = datetime.fromisoformat(v_str.replace("Z", "+00:00"))
        except Exception:
            raise ValueError(f"Invalid timestamp format '{v}'. Expected ISO 8601 format (e.g. 2026-09-06T12:00:00).")

        # Sanity check: prevent far-future timestamps (> 1 hour in future)
        now = datetime.now(timezone.utc)
        dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if dt_utc > now + timedelta(hours=1):
            raise ValueError(f"Timestamp '{v}' is in the future beyond acceptable clock drift tolerance.")
        return v_str

    @field_validator("temperature")
    def validate_temperature(cls, v):
        if v < TEMP_MIN or v > TEMP_MAX:
            raise ValueError(f"Temperature {v}°C violates physical boundaries [{TEMP_MIN}°C, {TEMP_MAX}°C].")
        return round(float(v), 2)

    @field_validator("pressure")
    def validate_pressure(cls, v):
        if v < PRESS_MIN or v > PRESS_MAX:
            raise ValueError(f"Atmospheric pressure {v} hPa violates physical boundaries [{PRESS_MIN} hPa, {PRESS_MAX} hPa].")
        return round(float(v), 2)

    @field_validator("humidity")
    def validate_humidity(cls, v):
        if v < HUM_MIN or v > HUM_MAX:
            raise ValueError(f"Relative humidity {v}% violates physical boundaries [{HUM_MIN}%, {HUM_MAX}%].")
        return round(float(v), 2)

    @field_validator("latitude")
    def validate_latitude(cls, v):
        if v is not None and (v < -90.0 or v > 90.0):
            raise ValueError(f"Latitude {v} must be between -90.0 and 90.0 degrees.")
        return round(float(v), 4) if v is not None else None

    @field_validator("longitude")
    def validate_longitude(cls, v):
        if v is not None and (v < -180.0 or v > 180.0):
            raise ValueError(f"Longitude {v} must be between -180.0 and 180.0 degrees.")
        return round(float(v), 4) if v is not None else None

    @field_validator("wind_speed")
    def validate_wind_speed(cls, v):
        if v is not None and (v < 0.0 or v > WIND_SPEED_MAX):
            raise ValueError(f"Wind speed {v} m/s is invalid (must be between 0.0 and {WIND_SPEED_MAX} m/s).")
        return round(float(v), 2) if v is not None else None

    @field_validator("wind_direction")
    def validate_wind_direction(cls, v):
        if v is not None and (v < 0.0 or v > 360.0):
            raise ValueError(f"Wind direction {v}° is invalid (must be between 0.0 and 360.0 degrees).")
        return round(float(v), 1) if v is not None else None

    @field_validator("rainfall")
    def validate_rainfall(cls, v):
        if v is not None and (v < 0.0 or v > RAIN_MAX):
            raise ValueError(f"Rainfall {v} mm is invalid (must be between 0.0 and {RAIN_MAX} mm).")
        return round(float(v), 2) if v is not None else None

    @field_validator("solar_radiation")
    def validate_solar_radiation(cls, v):
        if v is not None and (v < 0.0 or v > SOLAR_MAX):
            raise ValueError(f"Solar radiation {v} W/m² is invalid (must be between 0.0 and {SOLAR_MAX} W/m²).")
        return round(float(v), 2) if v is not None else None


class BatchTelemetryPayload(BaseModel):
    readings: List[TelemetryPayload]


class TelemetryValidator:
    """Manages payload validation and in-memory duplicate packet detection."""
    def __init__(self, max_cache_size: int = 10000):
        self._seen_packets = set()
        self._max_cache_size = max_cache_size

    def is_duplicate(self, station_id: str, timestamp: str) -> bool:
        packet_key = f"{station_id}::{timestamp}"
        if packet_key in self._seen_packets:
            return True
        return False

    def mark_seen(self, station_id: str, timestamp: str):
        packet_key = f"{station_id}::{timestamp}"
        if len(self._seen_packets) >= self._max_cache_size:
            # Clear oldest entries when cache exceeds capacity
            self._seen_packets.clear()
        self._seen_packets.add(packet_key)

    def validate_dict(self, payload_dict: Dict[str, Any]) -> TelemetryPayload:
        """Validates raw dict and checks for duplicates."""
        payload = TelemetryPayload(**payload_dict)
        if self.is_duplicate(payload.station_id, payload.timestamp):
            raise ValueError(f"Duplicate telemetry packet detected for {payload.station_id} at {payload.timestamp}.")
        return payload
