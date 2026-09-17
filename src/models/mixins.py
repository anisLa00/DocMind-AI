"""Shared helpers for model column definitions."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Timezone-aware UTC now.

    Used as the Python-side column default so inserted rows get microsecond
    precision regardless of the database's clock granularity - SQLite's
    CURRENT_TIMESTAMP only resolves to whole seconds, which would make messages
    written in the same second impossible to order.
    """
    return datetime.now(UTC)
