# AWQP CO Waters: data snapshot

Public data file for the **AWQP CO Waters** touchscreen display (Colorado State University,
Agricultural Water Quality Program). A scheduled GitHub Action fetches public agency data
every 15 minutes and publishes it to GitHub Pages:

- `https://mannydeleon99.github.io/awqp-co-waters-data/snapshot.csv`: the snapshot (schema v1)
- `status.json`: the last run, by layer
- `runs.csv`: one line per run (reliability log)

| Layer | Source | Refreshed |
|---|---|---|
| `calls` | Colorado DWR CDSS, active administrative (river) calls | hourly |
| `flood` | NOAA National Water Prediction Service, gauges and flood categories | hourly |
| `alerts` | National Weather Service, active flood and hydrologic alerts for Colorado | 15 min |
| `normals` | USGS Water Data statistics API, day-of-year flow percentiles | daily |

Values are as published by each agency, which remains the authoritative source. Many are
provisional. A layer that fails keeps its last good data and is marked `ok=0` with its age.

`builder/` is copied from the display's main (private) repository; edit it there.
Format: see the header comment in `builder/snapfile.py`.
