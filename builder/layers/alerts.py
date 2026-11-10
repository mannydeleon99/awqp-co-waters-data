"""Layer `alerts`: active NWS flood and hydrologic alerts for Colorado (S3, findings S0.6).

Only events with "Flood" or "Hydrologic" in the name (flood watch/warning/advisory, flash
flood, hydrologic outlook); other weather alerts are not this display's job. `ugc` is the
space-separated list of affected zone/county codes; the board matches gauges to it later.
The first non-empty response is saved by build.py (--save-alerts) as the parser fixture
still missing from Sprint 0.
"""
from __future__ import annotations

from snapfile import cell

ID = "alerts"
CADENCE = 900
URL = "https://api.weather.gov/alerts/active"
FIXTURE = "nws/s04_alerts_co.json"
COLUMNS = ["id", "event", "severity", "urgency", "certainty", "onset", "ends", "expires",
           "ugc", "area", "headline"]

last_raw = None  # the parsed response, for --save-alerts


def build(net, now: int) -> list[list[str]]:
    global last_raw
    from layers import clip, unix

    d = net.get_json(URL, {"area": "CO"}, FIXTURE)
    last_raw = d
    out = []
    for f in d.get("features", []):
        p = f.get("properties") or {}
        ev = p.get("event") or ""
        if "flood" not in ev.lower() and "hydrologic" not in ev.lower():
            continue
        ugc = " ".join((p.get("geocode") or {}).get("UGC") or [])
        out.append([cell(x) for x in (
            clip((p.get("id") or f.get("id") or "").rsplit("/", 1)[-1], 80), clip(ev, 40),
            p.get("severity"), p.get("urgency"), p.get("certainty"),
            unix(p.get("onset") or p.get("effective")), unix(p.get("ends")), unix(p.get("expires")),
            clip(ugc, 120), clip(p.get("areaDesc"), 100), clip(p.get("headline"), 120))])
    return out
