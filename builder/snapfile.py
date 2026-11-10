"""Snapshot file format, schema v1 (docs/SNAPSHOT.md). Writer and reader; standard library only.

The board reads the same format with lib/water/snapshot.* (row by row, csv::Reader, lines
up to 512 bytes). Keep both sides in step: a change here is a schema change.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone

SCHEMA = 1
LINE_MAX = 500  # board csv::Reader drops lines over 512 bytes; keep a margin


@dataclass
class Block:
    id: str
    columns: list[str]
    rows: list[list[str]] = field(default_factory=list)
    ok: bool = False
    as_of: int = 0     # Unix s of the data; 0 = never fetched
    tried: int = 0     # Unix s of the last attempt
    cadence: int = 0   # planned seconds between fetches


def _line(fields: list[str]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(fields)
    return buf.getvalue()


def cell(v) -> str:
    """One value as text: None/NaN -> '', floats without noise, no newlines."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        if v != v:  # NaN
            return ""
        return repr(round(v, 6)).removesuffix(".0")  # shortest text that reads back the same
    s = str(v).replace("\r", " ").replace("\n", " ").strip()
    return "" if s.lower() == "nan" else s


def write(blocks: list[Block], built: int) -> str:
    iso = datetime.fromtimestamp(built, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = [_line(["#snapshot", str(SCHEMA), str(built), iso])]
    for b in blocks:
        out.append(_line(["#layer", b.id, "1" if b.ok else "0", str(b.as_of), str(b.tried),
                          str(len(b.rows)), str(b.cadence)]))
        out.append(_line(b.columns))
        for r in b.rows:
            if len(r) != len(b.columns):
                raise ValueError(f"{b.id}: row has {len(r)} fields, header {len(b.columns)}")
            if r and r[0].startswith("#"):
                raise ValueError(f"{b.id}: first field starts with '#': {r[0]!r}")
            line = _line(r)
            if len(line.encode("utf-8")) > LINE_MAX:
                raise ValueError(f"{b.id}: row over {LINE_MAX} bytes: {line[:80]!r}...")
            out.append(line)
    out.append("#end\n")
    return "".join(out)


def read(text: str) -> tuple[int, dict[str, Block]]:
    """Parse a snapshot. Raises ValueError on anything the board would also reject."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or rows[0][:1] != ["#snapshot"] or len(rows[0]) < 3:
        raise ValueError("not a snapshot")
    if int(rows[0][1]) != SCHEMA:
        raise ValueError(f"unknown schema {rows[0][1]}")
    built = int(rows[0][2])
    blocks: dict[str, Block] = {}
    i, ended = 1, False
    while i < len(rows):
        r = rows[i]
        if not r:
            i += 1
            continue
        if r[0] == "#end":
            ended = True
            break
        if r[0] != "#layer":
            if r[0].startswith("#"):
                i += 1
                continue
            raise ValueError(f"row outside a layer at line {i + 1}")
        _, lid, ok, as_of, tried, count, cadence = r[:7]
        n = int(count)
        b = Block(lid, rows[i + 1], [list(x) for x in rows[i + 2:i + 2 + n]], ok == "1",
                  int(as_of), int(tried), int(cadence))
        if len(b.rows) != n or any(x and x[0].startswith("#") for x in b.rows):
            raise ValueError(f"layer {lid}: row count does not match")
        blocks[lid] = b
        i += 2 + n
    if not ended:
        raise ValueError("truncated: no #end")
    return built, blocks
