#!/usr/bin/env python3
"""Summarize DFTracer traces into flat figure-of-merit lines for ramble.

Runs `dftracer_stats --report detailed --json` over a run's trace/*.pfw.gz, once grouped by
category and once by operation name, and aggregates the per-file results across all ranks/workers
(rank parsed from the `<...>-<rank>-of-<n>-<hash>...pfw.gz` filename). dftracer_stats reports, per
file: `grouped_duration[<group>]` (event count + total duration us for every category/op) and
`grouped_io[<group>]` (real read/write transfer `duration`, `size` bytes and `bandwidth`).

We emit one row per category, per operation name, and per rank, so the FOM set scales to whatever
categories/ops a workload actually produces -- ramble's figure_of_merit_context turns each row into
its own context, no enumeration needed. Format (line-start keys, regex/`re.match`-friendly; the
field tokens are deliberately non-overlapping so each maps to one modifier regex):

  dftracer_events_total <n>
  dftracer_trace_files <n>
  dftracer_cat <name> count=<n> dur_s=<s> iops=<n> io_s=<s> bytes=<b> mibps=<bw>
  dftracer_op  <name> count=<n> dur_s=<s> iops=<n> io_s=<s> bytes=<b> mibps=<bw>
  dftracer_rank <r>   io_s=<s> bytes=<b>

(iops/io_s/bytes/mibps are the transfer-I/O subset; 0 for non-I/O groups.)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from glob import glob

_RANK_RE = re.compile(r"-(\d+)-of-(\d+)-")
_MIB = 1024.0 * 1024.0


def _stats_json(stats_bin, files, index_dir, group_by):
    """Run dftracer_stats and parse its per-file JSON objects (concatenated, comma-separated)."""
    cmd = [
        stats_bin,
        "--report",
        "detailed",
        "--group-by",
        group_by,
        "--json",
        "--index-dir",
        index_dir,
        "--files",
        *files,
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
    except OSError:
        return  # analyzer missing/unresolved (e.g. DFTRACER_STATS_BIN -> a bad path); no stats
    for line in out.splitlines():
        line = line.strip().rstrip(",")
        if line.startswith("{") and line.endswith("}"):
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                pass


def _new_group():
    return {"count": 0, "time_us": 0.0, "ops": 0, "io_us": 0.0, "bytes": 0.0}


def _accumulate(objs, groups, per_rank=None):
    """Fold per-file detailed reports into {group_name: totals} (and optionally per-rank I/O)."""
    events = files = 0
    wall = 0.0
    for obj in objs:
        files += 1
        detailed = obj.get("detailed") or {}
        events += int(detailed.get("events_scanned", 0))
        gd = detailed.get("grouped_duration") or {}
        gio = detailed.get("grouped_io") or {}
        for name, v in gd.items():
            g = groups.setdefault(name, _new_group())
            g["count"] += int(v.get("count", 0))
            g["time_us"] += float(v.get("sum", 0.0))
        rank_io = 0.0
        rank_bytes = 0.0
        for name, v in gio.items():
            g = groups.setdefault(name, _new_group())
            dur = v.get("duration", {})
            size = v.get("size", {})
            g["ops"] += int(dur.get("count", 0))
            g["io_us"] += float(dur.get("sum", 0.0))
            g["bytes"] += float(size.get("sum", 0.0))
            rank_io += float(dur.get("sum", 0.0))
            rank_bytes += float(size.get("sum", 0.0))
        if per_rank is not None:
            m = _RANK_RE.search(os.path.basename(obj.get("file_path", "")))
            r = per_rank.setdefault(m.group(1) if m else "?", {"io_us": 0.0, "bytes": 0.0})
            r["io_us"] += rank_io
            r["bytes"] += rank_bytes
    return events, files, wall


def _row(prefix, name, g):
    # Non-overlapping field tokens (count/dur_s/iops/io_s/bytes/mibps): one regex each in modifier.
    io_s = g["io_us"] / 1e6
    bw = (g["bytes"] / _MIB / io_s) if io_s else 0.0
    return (
        f"{prefix} {name} count={g['count']} dur_s={round(g['time_us'] / 1e6, 6)} "
        f"iops={g['ops']} io_s={round(io_s, 6)} bytes={int(g['bytes'])} "
        f"mibps={round(bw, 3)}"
    )


def summarize(trace_dir, stats_bin, index_dir):
    files = sorted(
        glob(os.path.join(trace_dir, "*.pfw.gz")) + glob(os.path.join(trace_dir, "*.pfw"))
    )
    if not files:  # nothing to analyze -> minimal summary (avoids calling stats with no --files)
        return "dftracer_events_total 0\ndftracer_trace_files 0\n"
    cats, ops, per_rank = {}, {}, {}
    events, nfiles, _ = _accumulate(_stats_json(stats_bin, files, index_dir, "cat"), cats, per_rank)
    _accumulate(_stats_json(stats_bin, files, index_dir, "name"), ops)

    lines = [
        f"dftracer_events_total {events}",
        f"dftracer_trace_files {nfiles}",
    ]
    for name in sorted(cats, key=lambda n: -cats[n]["time_us"]):
        lines.append(_row("dftracer_cat", name, cats[name]))
    for name in sorted(ops, key=lambda n: -ops[n]["time_us"]):
        lines.append(_row("dftracer_op", name, ops[name]))
    for r in sorted(per_rank, key=lambda x: (len(x), x)):
        v = per_rank[r]
        lines.append(f"dftracer_rank {r} io_s={round(v['io_us'] / 1e6, 6)} bytes={int(v['bytes'])}")
    return "\n".join(lines) + "\n"


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("trace_dir")
    ap.add_argument("--stats-bin", default=os.environ.get("DFTRACER_STATS_BIN", "dftracer_stats"))
    ap.add_argument("--index-dir", default=os.environ.get("TMPDIR", "/tmp"))
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    text = summarize(args.trace_dir, args.stats_bin, args.index_dir)
    sys.stdout.write(text)
    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
