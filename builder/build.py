"""Build the AWQP CO Waters snapshot (schema v1, docs/SNAPSHOT.md). Standard library only.

Run by the GitHub Action every 15 min (D3). Each run:
  1. reads the previous snapshot (--prev), if any;
  2. fetches only the layers that are due (cadence elapsed since their last attempt);
  3. a layer that fails keeps its previous rows and asOf, with ok=0 (never dropped);
  4. writes snapshot.csv, status.json (this run) and appends one line to runs.csv (S1.4 log).

  python snapshot/build.py --out site --prev site_prev/snapshot.csv     (online)
  python snapshot/build.py --offline                                     (from Sprint 0 fixtures)

--offline writes test/fixtures/snapshot/built_v1.csv + .counts for the host test.
Exit code: 0 if the file was written (even with failed layers), 2 if nothing could be written.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import layers  # noqa: E402
import snapfile  # noqa: E402
from net import Net  # noqa: E402

ROOT = HERE.parent
FIXTURES = ROOT / "test" / "fixtures"
OFFLINE_NOW = 1794294000  # 2026-11-10T07:00:00Z, about when the Sprint 0 fixtures were taken
SLACK_S = 300             # a layer is due this much early, so a 15-min schedule hits an hourly cadence
RUNS_KEEP = 5000          # lines kept in runs.csv (~52 days at 15 min)


def due(prev: snapfile.Block | None, cadence: int, now: int, force: bool) -> bool:
    return force or prev is None or now - prev.tried >= cadence - SLACK_S


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, help="output folder (default: site/, or the fixture folder offline)")
    ap.add_argument("--prev", type=Path, help="previous snapshot.csv (runs.csv is looked for next to it)")
    ap.add_argument("--offline", nargs="?", const=str(FIXTURES), help="read Sprint 0 fixtures instead of the network")
    ap.add_argument("--force", action="store_true", help="fetch every layer, due or not")
    ap.add_argument("--only", action="append", help="fetch only this layer (repeatable); others carried over")
    ap.add_argument("--fail", action="append", default=[], help="pretend this layer failed (testing)")
    ap.add_argument("--now", type=int, help="Unix time to use (testing)")
    ap.add_argument("--save-alerts", type=Path, help="if alerts are non-empty and this file does not exist yet, save the raw response here")
    a = ap.parse_args(argv)

    offline = Path(a.offline) if a.offline else None
    now = a.now or (OFFLINE_NOW if offline else int(time.time()))
    out = a.out or (FIXTURES / "snapshot" if offline else ROOT / "site")
    out.mkdir(parents=True, exist_ok=True)
    net = Net(offline)
    t0 = time.time()

    prev: dict[str, snapfile.Block] = {}
    prev_note = "none"
    if a.prev and a.prev.exists():
        try:
            _, prev = snapfile.read(a.prev.read_text(encoding="utf-8"))
            prev_note = f"{len(prev)} layers"
        except (ValueError, IndexError) as e:
            prev_note = f"unreadable: {e}"  # start fresh rather than fail the run
    print(f"previous snapshot: {prev_note}")

    blocks, status = [], {}
    for mod in layers.ALL:
        p = prev.get(mod.ID)
        b = snapfile.Block(mod.ID, list(mod.COLUMNS), cadence=mod.CADENCE)
        if p is not None and p.columns == b.columns:
            b.rows, b.ok, b.as_of, b.tried = p.rows, p.ok, p.as_of, p.tried
        elif p is not None:
            print(f"{mod.ID}: columns changed since the previous file; old rows dropped")
        wanted = not a.only or mod.ID in a.only
        st = {"due": False, "ok": b.ok, "rows": len(b.rows), "seconds": 0.0, "error": None}
        if wanted and due(p, mod.CADENCE, now, a.force or offline is not None):
            st["due"] = True
            t = time.time()
            b.tried = now
            try:
                if mod.ID in a.fail:
                    raise RuntimeError("forced failure (--fail)")
                rows = mod.build(net, now)
                b.rows, b.ok, b.as_of = rows, True, now
                st["ok"] = True
            except Exception as e:  # one layer's failure must not stop the others
                b.ok = False
                st["ok"] = False
                st["error"] = f"{type(e).__name__}: {e}"[:300]
                traceback.print_exc()
            st["seconds"] = round(time.time() - t, 2)
            st["rows"] = len(b.rows)
        age = "never" if not b.as_of else f"{(now - b.as_of) // 60} min old"
        print(f"{mod.ID:8s} {'fetched' if st['due'] else 'carried'} ok={int(b.ok)} rows={len(b.rows)} {age}"
              + (f"  ERROR {st['error']}" if st["error"] else ""))
        status[mod.ID] = st
        blocks.append(b)

    try:
        text = snapfile.write(blocks, now)
    except ValueError as e:
        print(f"cannot write snapshot: {e}")
        return 2
    snapfile.read(text)  # the file must read back
    (out / "snapshot.csv").write_bytes(text.encode("utf-8"))  # LF line ends on every OS
    size = len(text.encode("utf-8"))
    built = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run = {"built": built, "builtUnix": now, "seconds": round(time.time() - t0, 1), "bytes": size,
           "downloaded": net.bytes, "requests": net.count, "layers": status}
    print(f"snapshot.csv: {size:,} bytes, {run['seconds']} s, downloaded {net.bytes:,} bytes")

    if offline:
        (out / "built_v1.csv").write_bytes(text.encode("utf-8"))
        (out / "snapshot.csv").unlink()
        (out / "built_v1.counts").write_text("".join(f"{b.id} {len(b.rows)}\n" for b in blocks), newline="\n")
        return 0

    (out / "status.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    append_run(out, a.prev, run)
    # Keep the first non-empty response only (the workflow carries it from the previous site).
    if (a.save_alerts and not a.save_alerts.exists() and layers.alerts.last_raw
            and layers.alerts.last_raw.get("features")):
        a.save_alerts.parent.mkdir(parents=True, exist_ok=True)
        a.save_alerts.write_text(json.dumps(layers.alerts.last_raw, indent=1), encoding="utf-8")
        print(f"non-empty alerts saved to {a.save_alerts}")
    return 0


RUN_COLS = ["built", "seconds", "bytes"] + [f"{m.ID}_{k}" for m in layers.ALL for k in ("due", "ok", "rows")] + ["errors"]


def append_run(out: Path, prev: Path | None, run: dict) -> None:
    """runs.csv: one line per run, carried from the previous site (S1.4 reliability log)."""
    lines: list[str] = []
    old = prev.parent / "runs.csv" if prev else None
    if old and old.exists():
        lines = old.read_text(encoding="utf-8").splitlines()[1:]
    row = [run["built"], str(run["seconds"]), str(run["bytes"])]
    errs = []
    for m in layers.ALL:
        s = run["layers"][m.ID]
        row += [str(int(s["due"])), str(int(s["ok"])), str(s["rows"])]
        if s["error"]:
            errs.append(f"{m.ID}: {s['error']}")
    row.append(" | ".join(errs))
    from io import StringIO
    buf = StringIO()
    csv.writer(buf, lineterminator="\n").writerow(row)
    lines = (lines + [buf.getvalue().rstrip("\n")])[-RUNS_KEEP:]
    hdr = ",".join(RUN_COLS)
    (out / "runs.csv").write_text(hdr + "\n" + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.exit(main())
