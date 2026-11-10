"""Layer `calls`: DWR CDSS active administrative (river) calls (S1, findings S0.4).

One row per active call, drawn as a point at the calling structure (DECISIONS Nov 10 2026);
the bounding structure, when present, is for the detail page. Times are Unix s; priorityDate
is the appropriation date (YYYY-MM-DD, can be before 1970). Comments are left out (long,
free text); the board links to DWR's page by callNumber.
"""
from __future__ import annotations

from snapfile import cell

ID = "calls"
CADENCE = 3600
URL = "https://dwr.state.co.us/Rest/GET/api/v2/administrativecalls/active/"
FIXTURE = "dwr/s04_calls_active.json"
COLUMNS = ["callNumber", "type", "set", "released", "source", "wdid", "streamMile", "name",
           "priorityWdid", "priorityName", "adminNo", "priorityDate", "division", "lat", "lon",
           "boundWdid", "boundName", "boundLat", "boundLon", "modified"]


def build(net, now: int) -> list[list[str]]:
    from layers import clip, unix

    d = net.get_json(URL, {"format": "json"}, FIXTURE)
    if d.get("PageCount", 1) != 1:
        raise ValueError(f"calls: {d.get('PageCount')} pages, only 1 read")
    out = []
    for c in d["ResultList"]:
        out.append([cell(x) for x in (
            c.get("callNumber"), c.get("callType"), unix(c.get("dateTimeSet")),
            unix(c.get("dateTimeReleased")), clip(c.get("waterSourceName"), 60),
            c.get("locationWdid"), c.get("locationWdidStreammile"),
            clip(c.get("locationStructureName"), 60), c.get("priorityWdid"),
            clip(c.get("priorityStructureName"), 60), c.get("priorityAdminNumber"),
            (c.get("priorityDate") or "")[:10], c.get("division"),
            c.get("locationStructureLatitude"), c.get("locationStructureLongitude"),
            c.get("boundingWdid"), clip(c.get("boundingStructureName"), 60),
            c.get("boundingStructureLatitude"), c.get("boundingStructureLongitude"),
            unix(c.get("modified")))])
    if len(out) != d.get("ResultCount", len(out)):
        raise ValueError(f"calls: {len(out)} rows, ResultCount {d.get('ResultCount')}")
    return out
