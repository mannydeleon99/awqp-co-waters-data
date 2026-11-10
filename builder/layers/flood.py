"""Layer `flood`: NOAA NWPS gauges in Colorado, flood category and latest obs/forecast (S2,
findings S0.6).

One request (bounding-box list). Stage in ft, flow in cfs (NWPS sends kcfs: x1000). Values
the API marks as missing (<= -999) are left empty. Flood stage thresholds and the USGS ID
crosswalk are only in the per-gauge detail (290 requests): not in v1 of this layer; a weekly
crosswalk job needs Manny's OK first (Sprint 0 rule, > 50 requests to one host).
"""
from __future__ import annotations

from snapfile import cell

ID = "flood"
CADENCE = 3600
URL = "https://api.water.noaa.gov/nwps/v1/gauges"
PARAMS = {"bbox.xmin": "-109.06", "bbox.ymin": "36.99", "bbox.xmax": "-102.04",
          "bbox.ymax": "41.0", "srid": "EPSG_4326"}
FIXTURE = "nwps/s04_gauges_co.json"
COLUMNS = ["lid", "name", "lat", "lon", "rfc", "wfo",
           "obsCat", "obsStageFt", "obsFlowCfs", "obsTime",
           "fcstCat", "fcstStageFt", "fcstFlowCfs", "fcstTime"]


def _val(v, unit: str | None):
    if v is None or v <= -999:
        return None
    u = (unit or "").lower()
    if u == "kcfs":
        return v * 1000.0
    if u in ("ft", "cfs"):
        return float(v)
    return None  # other units (e.g. none given): leave empty rather than guess


def _pair(s: dict) -> tuple:
    """(stage ft, flow cfs) from an NWPS status block, whichever of primary/secondary is which."""
    stage = flow = None
    for k in ("primary", "secondary"):
        unit = (s.get(f"{k}Unit") or "").lower()
        v = _val(s.get(k), unit)
        if unit == "ft":
            stage = v
        elif unit in ("kcfs", "cfs"):
            flow = v
    return stage, flow


def build(net, now: int) -> list[list[str]]:
    from layers import clip, unix

    d = net.get_json(URL, PARAMS, FIXTURE)
    out = []
    for g in d["gauges"]:
        if (g.get("state") or {}).get("abbreviation") != "CO":
            continue
        st = g.get("status") or {}
        o, f = st.get("observed") or {}, st.get("forecast") or {}
        os_, of = _pair(o)
        fs, ff = _pair(f)
        out.append([cell(x) for x in (
            g.get("lid"), clip(g.get("name"), 80), g.get("latitude"), g.get("longitude"),
            (g.get("rfc") or {}).get("abbreviation"), (g.get("wfo") or {}).get("abbreviation"),
            o.get("floodCategory"), os_, of, unix(o.get("validTime")),
            f.get("floodCategory"), fs, ff, unix(f.get("validTime")))])
    if not out:
        raise ValueError("flood: no Colorado gauges in the response")
    return out
