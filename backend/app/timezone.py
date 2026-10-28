"""Workspace-local datetime parsing and API serialization."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def workspace_zone() -> ZoneInfo:
    return ZoneInfo(get_settings().workspace_time_zone)


def workspace_now() -> datetime:
    return datetime.now(workspace_zone())


def to_workspace_naive(value: datetime) -> datetime:
    """Store wall time in the configured workspace zone in legacy naive columns."""
    if value.tzinfo is None:
        return value
    return value.astimezone(workspace_zone()).replace(tzinfo=None)


def to_workspace_iso(value: datetime) -> str:
    """Emit stored naive wall time with its configured workspace UTC offset."""
    zoned = value.replace(tzinfo=workspace_zone()) if value.tzinfo is None else value.astimezone(workspace_zone())
    return zoned.isoformat()


def to_utc_iso(value: datetime) -> str:
    """Serialize audit and system timestamps, which are stored as UTC-naive."""
    zoned = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return zoned.isoformat()
