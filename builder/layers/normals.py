"""Layer `normals`: USGS day-of-year flow percentiles for every Colorado stream gage (L2, D13,
findings S0.2).

Statistics API (BETA), `observationNormals`, state_code=US:08, streams, discharge 00060,
percentiles only, one query per day, following `next` tokens (2 pages a day in S0.2).
Rows for today and tomorrow (America/Denver), so a late daily run still covers midnight.
Percentiles are the API's values as sent (cfs; Weibull); "nan" -> empty. n = sample_count
(years of record for that day). Site = USGS number without the "USGS-" prefix.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from snapfile import cell

ID = "normals"
CADENCE = 86400
URL = "https://api.waterdata.usgs.gov/statistics/v0/observationNormals"
PCTS = ["5", "10", "25", "50", "75", "90", "95"]
COLUMNS = ["site", "day", "n", "p5", "p10", "p25", "p50", "p75", "p90", "p95"]
MAX_PAGES = 6
# Offline: the S0.2 fixture is one day (11-09) in two pages.
OFFLINE_DAY = "11-09"
OFFLINE_PAGES = ["usgs/s02_stats_co_pct.json", "usgs/s02_stats_co_pct_p2.json"]

skipped_extra_series = 0  # sites with more than one flow series (S0.2: 0); first one kept


def _days(now: int, offline: bool) -> list[str]:
    if offline:
        return [OFFLINE_DAY]
    try:
        tz = ZoneInfo("America/Denver")
    except Exception:  # Windows without the tzdata package; the Action runs on Linux
        tz = timezone(timedelta(hours=-7))
    t = datetime.fromtimestamp(now, tz)
    return [t.strftime("%m-%d"), (t + timedelta(days=1)).strftime("%m-%d")]


def _rows(features: list, day: str, seen: set) -> list[list[str]]:
    global skipped_extra_series
    out = []
    for f in features:
        p = f.get("properties") or {}
        site = (p.get("monitoring_location_id") or "").removeprefix("USGS-")
        for series in p.get("data") or []:
            if series.get("parameter_code") != "00060":
                continue
            for v in series.get("values") or []:
                if v.get("computation") != "percentile" or v.get("time_of_year") != day:
                    continue
                if (site, day) in seen:
                    skipped_extra_series += 1
                    continue
                seen.add((site, day))
                by = dict(zip(v.get("percentiles") or [], v.get("values") or []))
                out.append([cell(site), day, cell(v.get("sample_count"))]
                           + [cell(by.get(k)) for k in PCTS])
    return out


def build(net, now: int) -> list[list[str]]:
    offline = net.offline is not None
    out, seen = [], set()
    for day in _days(now, offline):
        token = None
        for page in range(MAX_PAGES):
            params = [("state_code", "US:08"), ("site_type_code", "ST"), ("parameter_code", "00060"),
                      ("start_date", day), ("end_date", day), ("computation_type", "percentile")]
            if token:
                params.append(("next_token", token))
            fixture = OFFLINE_PAGES[page] if offline and page < len(OFFLINE_PAGES) else None
            d = net.get_json(URL, params, fixture)
            out += _rows(d.get("features") or [], day, seen)
            token = d.get("next")
            if not token:
                break
            if offline and page + 1 >= len(OFFLINE_PAGES):
                break
        else:
            raise ValueError(f"normals: more than {MAX_PAGES} pages for {day}")
    if not out:
        raise ValueError("normals: no rows")
    return out
