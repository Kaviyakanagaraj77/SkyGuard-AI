"""
SkyGuard AI v2 - IMD Telemetry Integration Boundary Adapter (Phase 5)
-----------------------------------------------------------------------
Defines a clean, decoupled adapter boundary for future authorized IMD AWS telemetry streams
without scraping or hardcoding unapproved credentials.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


class IMDAWSAdapterInterface(ABC):
    """Abstract interface defining standard integration boundary for AWS telemetry ingestors."""

    @abstractmethod
    def parse_raw_packet(self, raw_data: Any) -> Dict[str, Any]:
        """Parses raw telemetry payload into SkyGuard TelemetryPayload schema."""
        pass

    @abstractmethod
    def fetch_latest_telemetry(self, station_id: str) -> Optional[Dict[str, Any]]:
        """Fetches latest observation for a given AWS station identifier."""
        pass


class SyntheticDemoAdapter(IMDAWSAdapterInterface):
    """High-fidelity synthetic physics-backed adapter for demonstration & benchmark mode."""

    def __init__(self, dataset_df=None):
        self.df = dataset_df

    def parse_raw_packet(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "station_id": raw_data.get("station_id", "IMD_AWS_DEMO"),
            "timestamp": raw_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "temperature": float(raw_data.get("temperature", 25.0)),
            "pressure": float(raw_data.get("pressure", 1013.2)),
            "humidity": float(raw_data.get("humidity", 60.0)),
            "wind_speed": float(raw_data.get("wind_speed", 5.0)) if "wind_speed" in raw_data else None,
            "source": "synthetic_demo_adapter"
        }

    def fetch_latest_telemetry(self, station_id: str) -> Optional[Dict[str, Any]]:
        if self.df is not None and not self.df.empty:
            st_df = self.df[self.df["station_id"] == station_id]
            if not st_df.empty:
                latest = st_df.sort_values("timestamp").iloc[-1]
                return {
                    "station_id": station_id,
                    "timestamp": str(latest["timestamp"]),
                    "temperature": float(latest["temperature"]),
                    "pressure": float(latest["pressure"]),
                    "humidity": float(latest["humidity"]),
                    "source": "synthetic_demo_dataset"
                }
        return None


class IMDPilotAdapterBoundary(IMDAWSAdapterInterface):
    """
    Integration boundary adapter prepared for future authorized real IMD AWS telemetry streams.
    Requires formal government data agreement, access credentials, and approved stream endpoints.
    """

    def __init__(self, api_key: Optional[str] = None, endpoint_url: Optional[str] = None):
        self.api_key = api_key
        self.endpoint_url = endpoint_url
        self.authorized = bool(api_key and endpoint_url)

    def parse_raw_packet(self, raw_data: Any) -> Dict[str, Any]:
        if not self.authorized:
            raise PermissionError(
                "Official IMD AWS data ingestion requires formal authorization, access credentials, "
                "and an approved government data sharing agreement. SkyGuard AI currently operates in research mode."
            )
        # Boundary parser stub for future authorized format
        return dict(raw_data)

    def fetch_latest_telemetry(self, station_id: str) -> Optional[Dict[str, Any]]:
        if not self.authorized:
            return {
                "status": "unauthorized",
                "message": "Official IMD stream connection pending formal government authorization and API credentials.",
                "station_id": station_id,
                "mode": "PILOT_READINESS_BOUNDARY"
            }
        return None
