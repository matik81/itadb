"""Small typed helpers for bounded DuckDB operations."""

from typing import Any

import duckdb


def row(result: duckdb.DuckDBPyConnection) -> tuple[Any, ...]:
    value = result.fetchone()
    if value is None:
        raise ValueError("Expected one database result")
    return value
