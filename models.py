"""
SkyGuard AI v2 - SQLAlchemy Database Models (Phase 2)
------------------------------------------------------
Defines database schemas for stations, telemetry time-series, alerts, and maintenance records.
Includes composite indexes for high-performance station + timestamp filtering.
"""

from sqlalchemy import Column, Integer, BigInteger, Float, String, DateTime, ForeignKey, Index, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class StationModel(Base):
    __tablename__ = "stations"

    station_id = Column(String(50), primary_key=True, index=True)
    location = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    elevation = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    telemetry_records = relationship("TelemetryModel", back_populates="station", cascade="all, delete-orphan")


class TelemetryModel(Base):
    __tablename__ = "telemetry"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    station_id = Column(String(50), ForeignKey("stations.station_id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)

    # Core Meteorological Telemetry
    temperature = Column(Float, nullable=False)
    pressure = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)

    # Optional Extended Meteorological Parameters
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    wind_speed = Column(Float, nullable=True)
    wind_direction = Column(Float, nullable=True)
    rainfall = Column(Float, nullable=True)
    solar_radiation = Column(Float, nullable=True)

    # AI Detection Outputs
    predicted_anomaly = Column(Integer, default=0, nullable=False)
    confidence_score = Column(Float, default=0.0, nullable=False)
    trust_score = Column(Float, default=100.0, nullable=False)
    predicted_root_cause = Column(String(100), default="normal", nullable=False)
    dew_point = Column(Float, nullable=True)

    station = relationship("StationModel", back_populates="telemetry_records")

    # Composite Index for fast time-series queries (station_id + timestamp)
    __table_args__ = (
        Index("idx_station_timestamp", "station_id", "timestamp"),
    )


class AlertModel(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telemetry_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("telemetry.id"), nullable=True)
    station_id = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)

    confidence_score = Column(Float, nullable=False)
    trust_score = Column(Float, nullable=False)
    root_cause = Column(String(100), nullable=False)

    temperature = Column(Float, nullable=True)
    pressure = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    status = Column(String(30), default="Active", nullable=False)  # Active, Acknowledged, Resolved

    # Phase 3 Early Warning Extensions (Nullable for 100% backward compatibility)
    severity = Column(String(30), nullable=True)
    risk_score = Column(Float, nullable=True)
    message = Column(String(255), nullable=True)
    affected_parameters = Column(String(255), nullable=True)


class MaintenanceRecordModel(Base):
    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(String(50), nullable=False, index=True)
    current_anomaly_rate = Column(Float, nullable=False)
    trend_slope_per_hour = Column(Float, nullable=False)
    estimated_days_to_maintenance = Column(Float, nullable=True)
    status = Column(String(50), nullable=False)  # HEALTHY, DEGRADING_SLOWLY, MAINTENANCE_PREDICTED_SOON, MAINTENANCE_REQUIRED_NOW
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default="VIEWER")  # ADMIN, OPERATOR, ANALYST, VIEWER
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
