"""Unit tests for the DFTracer trace summarizer and its coupling to the modifier's FOM regexes.

These run without any HPC/GPU/spack: they feed synthetic `dftracer_stats` JSON into the
summarizer and check both the aggregation and that the modifier's figure_of_merit regexes still
match the summary format (the coupling that silently broke would drop every I/O FOM).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_MOD_DIR = _REPO / "repo" / "modifiers" / "dftracer"


def _load_summary_module():
    spec = importlib.util.spec_from_file_location(
        "dftracer_summary", _MOD_DIR / "dftracer_summary.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


summary = _load_summary_module()


def _detailed(grouped_duration=None, grouped_io=None, events=0):
    """Build a per-file `detailed` object shaped like dftracer_stats --json output."""
    return {
        "detailed": {
            "events_scanned": events,
            "grouped_duration": grouped_duration or {},
            "grouped_io": grouped_io or {},
        }
    }


def test_accumulate_sums_counts_durations_and_io():
    objs = [
        {
            "file_path": "run-0-of-2-abcd-.pfw.gz",
            **_detailed(
                grouped_duration={"POSIX": {"count": 100, "sum": 2_000_000.0}},
                grouped_io={
                    "POSIX": {
                        "duration": {"count": 10, "sum": 1_500_000.0},
                        "size": {"sum": 1_048_576.0 * 300},
                    }
                },
                events=100,
            ),
        },
        {
            "file_path": "run-1-of-2-efgh-.pfw.gz",
            **_detailed(
                grouped_duration={"POSIX": {"count": 50, "sum": 1_000_000.0}},
                grouped_io={
                    "POSIX": {
                        "duration": {"count": 5, "sum": 500_000.0},
                        "size": {"sum": 1_048_576.0 * 100},
                    }
                },
                events=50,
            ),
        },
    ]
    groups, per_rank = {}, {}
    events, nfiles, _ = summary._accumulate(iter(objs), groups, per_rank)

    assert events == 150
    assert nfiles == 2
    p = groups["POSIX"]
    assert p["count"] == 150  # 100 + 50 events in the group
    assert p["ops"] == 15  # 10 + 5 transfer ops
    assert p["io_us"] == 2_000_000.0  # 1.5M + 0.5M us
    assert p["bytes"] == 1_048_576.0 * 400
    # ranks parsed from the filename
    assert set(per_rank) == {"0", "1"}
    assert per_rank["0"]["io_us"] == 1_500_000.0


def test_row_format_tokens_are_nonoverlapping():
    g = {"count": 7, "time_us": 3_000_000.0, "ops": 4, "io_us": 2_000_000.0, "bytes": 2_097_152}
    row = summary._row("dftracer_cat", "POSIX", g)
    assert row.startswith("dftracer_cat POSIX ")
    for token in ("count=", "dur_s=", "iops=", "io_s=", "bytes=", "mibps="):
        assert token in row
    # bandwidth = bytes / MiB / io_s = 2MiB / 2s = 1.0 MiB/s
    assert "mibps=1.0" in row


def _modifier_metric_tokens():
    """Extract the metric field tokens the modifier's regexes capture (count, dur_s, iops, ...),
    so the test breaks if the summary format and the modifier drift apart."""
    src = (_MOD_DIR / "modifier.py").read_text()
    tokens = sorted(set(re.findall(r'"(\w+)=\(\?P<v>', src)))
    assert tokens, "no metric tokens found in modifier.py -- did the format change?"
    return tokens


def test_modifier_regexes_match_summary_rows():
    g = {
        "count": 100538,
        "time_us": 158_092_388.0,
        "ops": 6938,
        "io_us": 147_637_732.0,
        "bytes": 24_400_549_360,
        "mibps": 0,
    }
    row = summary._row("dftracer_cat", "POSIX", g)

    # context regex (as declared in the modifier) picks the category off the same line
    ctx = re.compile(r"dftracer_cat (?P<cat>\S+)")
    assert ctx.match(row).group("cat") == "POSIX"

    # every metric token must extract via re.match with the modifier's anchored prefix
    for token in _modifier_metric_tokens():
        pat = re.compile(rf"dftracer_cat \S+ .*{token}=(?P<v>[0-9.]+)")
        m = pat.match(row)  # re.match == ramble's anchored matching
        assert m is not None, f"token failed to match row: {token}"
        assert m.group("v")


def test_summarize_end_to_end(monkeypatch, tmp_path):
    """summarize() with dftracer_stats mocked -- exercises the whole flat-summary shape."""

    def fake_stats(stats_bin, files, index_dir, group_by):
        if group_by == "cat":
            yield {
                "file_path": "run-0-of-1-x-.pfw.gz",
                **_detailed(
                    grouped_duration={"POSIX": {"count": 10, "sum": 1_000_000.0}},
                    grouped_io={
                        "POSIX": {
                            "duration": {"count": 3, "sum": 900_000.0},
                            "size": {"sum": 1_048_576.0 * 90},
                        }
                    },
                    events=10,
                ),
            }
        else:  # name
            yield {
                "file_path": "run-0-of-1-x-.pfw.gz",
                **_detailed(
                    grouped_duration={"read": {"count": 3, "sum": 900_000.0}},
                    grouped_io={
                        "read": {
                            "duration": {"count": 3, "sum": 900_000.0},
                            "size": {"sum": 1_048_576.0 * 90},
                        }
                    },
                ),
            }

    monkeypatch.setattr(summary, "_stats_json", fake_stats)
    (tmp_path / "run-0-of-1-x-.pfw.gz").write_bytes(b"")
    text = summary.summarize(str(tmp_path), "dftracer_stats", str(tmp_path))

    assert "dftracer_events_total 10" in text
    assert "dftracer_trace_files 1" in text
    assert any(line.startswith("dftracer_cat POSIX ") for line in text.splitlines())
    assert any(line.startswith("dftracer_op read ") for line in text.splitlines())
    assert any(line.startswith("dftracer_rank 0 ") for line in text.splitlines())
