"""Snapshot layers. Each module defines:

  ID        layer id in the file (docs/SNAPSHOT.md)
  CADENCE   seconds between fetches
  COLUMNS   column header, fixed for schema v1 (add at the end only)
  build(net, now) -> list of rows (lists of str, len == len(COLUMNS)); raises on failure
"""
from __future__ import annotations

from datetime import datetime

from . import alerts, calls, drought, flood, normals

ALL = [calls, flood, alerts, normals, drought]


def unix(iso: str | None) -> int | None:
    """ISO 8601 with offset or Z -> Unix seconds; None if empty."""
    if not iso:
        return None
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def clip(s, n: int) -> str:
    s = "" if s is None else " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 3].rstrip() + "..."
