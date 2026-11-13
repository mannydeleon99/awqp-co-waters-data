"""Layer `drought`: US Drought Monitor, percent of area in drought (S5, findings S0.7).

usdmdataservices.unl.edu, GetDroughtSeverityStatisticsByAreaPercent, statisticsType=1
("traditional" = cumulative: d1 = % of area in D1 or worse). Categorical shares are
differences (findings S0.7: equal within 0.01) and None = 100 - d0, so neither is stored.

Rows (kind, id):
  state  08        53 weekly maps (1 year), for the statewide graph
  county 08001...  64 counties, newest 2 maps (this week and last)
  huc6   101900... 18 HUC6 that reach Colorado, newest 2 maps
  huc8   10180001. 92 HUC8 that reach Colorado, newest 2 maps
Order: state, county, huc6, huc8; by id; newest map first.

USDM's map is dated Tuesday (data valid that morning) and released on Thursday, so the
newest map is 2 to 9 days old. A wrong request answers HTTP 200 with an empty body
(findings S0.7): every answer must have rows, or the layer fails (keeps its last good data).
HUCs can't be asked for by state: one request per HUC2 region, filtered by co_hucs (USGS WBD).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from . import co_hucs

ID = "drought"
CADENCE = 6 * 3600  # weekly data; 6 h picks up Thursday's map the same day
URL = "https://usdmdataservices.unl.edu/api/{area}/GetDroughtSeverityStatisticsByAreaPercent"
COLUMNS = ["kind", "id", "name", "mapDate", "d0", "d1", "d2", "d3", "d4"]
LEVELS = ["D0", "D1", "D2", "D3", "D4"]
REGIONS = ["10", "11", "13", "14"]  # HUC2 regions that reach Colorado (co_hucs)
COUNTIES = 64
STATE_DAYS = 365
UNIT_DAYS = 13      # window for counties and HUCs; it returns 2-3 maps, the newest 2 are kept
KEEP_WEEKS = 2
MAX_AGE_DAYS = 16   # newest statewide map older than this = USDM not updating: fail


def _mdy(t: datetime) -> str:
    return f"{t.month}/{t.day}/{t.year}"


def _rows(net, area: str, params: dict, fixture: str, what: str) -> list[dict]:
    text = net.get_text(URL.format(area=area), params, fixture, accept="text/csv")
    rs = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rs:
        raise ValueError(f"drought: {what}: empty answer")
    return rs


def _date(s: str) -> str:
    return datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d")


def _values(r: dict, what: str) -> list[str]:
    v = [float(r[k]) for k in LEVELS]
    if any(x < 0 or x > 100.001 for x in v) or any(v[i] + 0.011 < v[i + 1] for i in range(4)):
        raise ValueError(f"drought: {what} {r.get('MapDate')}: {v} is not cumulative")
    return [r[k].strip() for k in LEVELS]


def _newest(rs: list[dict], key: str) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    for r in rs:
        by.setdefault(r[key], []).append(r)
    return {k: sorted(v, key=lambda r: r["MapDate"], reverse=True)[:KEEP_WEEKS] for k, v in by.items()}


def build(net, now: int) -> list[list[str]]:
    t = datetime.fromtimestamp(now, timezone(timedelta(hours=-7)))  # Colorado date; MST is close enough
    year = dict(startdate=_mdy(t - timedelta(days=STATE_DAYS)), enddate=_mdy(t), statisticsType="1")
    week = dict(startdate=_mdy(t - timedelta(days=UNIT_DAYS)), enddate=_mdy(t), statisticsType="1")
    out: list[list[str]] = []

    st = _rows(net, "StateStatistics", dict(aoi="08", **year), "usdm/s07_state_trad_1y.csv", "state")
    st.sort(key=lambda r: r["MapDate"], reverse=True)
    newest = datetime.strptime(st[0]["MapDate"], "%Y%m%d").replace(tzinfo=t.tzinfo)
    if (t - newest).days > MAX_AGE_DAYS:
        raise ValueError(f"drought: newest statewide map {st[0]['MapDate']} is over {MAX_AGE_DAYS} days old")
    for r in st:
        out.append(["state", "08", "Colorado", _date(r["MapDate"])] + _values(r, "state"))

    cty = _newest(_rows(net, "CountyStatistics", dict(aoi="CO", **week), "usdm/s07_county_trad_2w.csv",
                        "counties"), "FIPS")
    if len(cty) != COUNTIES:
        raise ValueError(f"drought: {len(cty)} counties, expected {COUNTIES}")
    for fips in sorted(cty):
        for r in cty[fips]:
            out.append(["county", fips, r["County"].strip(), _date(r["MapDate"])] + _values(r, fips))

    for lvl, want in (("6", co_hucs.HUC6), ("8", co_hucs.HUC8)):
        got: list[dict] = []
        for reg in REGIONS:
            got += _rows(net, "HUCStatistics", dict(aoi=reg, hucLevel=lvl, **week),
                         f"usdm/s07_huc{lvl}_r{reg}_trad_2w.csv", f"huc{lvl} region {reg}")
        by = _newest([r for r in got if r["HUCId"] in want], "HUCId")
        missing = sorted(set(want) - set(by))
        if missing:
            raise ValueError(f"drought: huc{lvl} missing {', '.join(missing[:5])} ({len(missing)})")
        for h in sorted(by):
            for r in by[h]:
                out.append([f"huc{lvl}", h, r["HUC"].strip(), _date(r["MapDate"])] + _values(r, h))
    return out
