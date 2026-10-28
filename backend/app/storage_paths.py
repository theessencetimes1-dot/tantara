"""Resolve persisted paths relative to the relocatable workspace data directory."""

from pathlib import Path

from app.config import get_settings


def stored_path(category: str, value: str | Path) -> Path:
    if category not in {"uploads", "bundles"}:
        raise ValueError("Unsupported storage category")
    raw = Path(value)
    if raw.is_absolute():
        # Compatibility for databases not yet migrated or imported from backups.
        raw = Path(category) / raw.name
    elif raw.parts and raw.parts[0] == category:
        pass
    else:
        raw = Path(category) / raw
    root = (get_settings().data_dir / category).resolve()
    resolved = (get_settings().data_dir / raw).resolve()
    if resolved.parent != root:
        raise ValueError("Unsafe stored path")
    return resolved
