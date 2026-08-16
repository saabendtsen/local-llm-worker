"""Reduce a raw agent event stream to the events worth keeping.

Both harnesses emit `message_update` once per generated token, and each one
carries the *entire accumulated message* rather than just the delta. A single
feature build produced a 189 MB log that way -- past GitHub's 100 MB file limit
-- while containing only a few hundred events that mean anything.

This drops the streaming deltas and keeps every event the evaluation actually
reads: turn boundaries, tool executions with their arguments and results,
completed messages with their content and token usage, and stop reasons. The
distilled stream is what gets committed; the raw one stays local.

Usage:
    python scripts/distill_events.py                 # every run under evaluation/runs
    python scripts/distill_events.py path/to/run     # one run directory
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "evaluation" / "runs"

# Everything except the per-token streaming deltas. Keeping the set explicit
# rather than filtering only `message_update` means a new event type from a
# harness upgrade is kept by default -- losing evidence is worse than keeping
# a little noise.
DROPPED_TYPES = {"message_update"}

# A tool result can be an entire file. Keep enough to see what came back
# without storing the repository twice.
MAX_RESULT_CHARS = 4000


def distil_line(line: str) -> str | None:
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        # Keep unparseable lines: a malformed stream is itself evidence, and
        # the runner counts these.
        return line

    if event.get("type") in DROPPED_TYPES:
        return None

    result = event.get("result")
    if isinstance(result, str) and len(result) > MAX_RESULT_CHARS:
        event["result"] = result[:MAX_RESULT_CHARS] + f"... [{len(result)} chars truncated]"

    return json.dumps(event, separators=(",", ":"))


def distil_run(run_dir: Path) -> tuple[int, int] | None:
    raw = run_dir / "events.jsonl"
    if not raw.is_file():
        return None

    out = run_dir / "events-distilled.jsonl"
    kept = 0
    with raw.open(encoding="utf-8", errors="replace") as source, \
            out.open("w", encoding="utf-8") as target:
        for line in source:
            distilled = distil_line(line)
            if distilled is not None:
                target.write(distilled + "\n")
                kept += 1

    return raw.stat().st_size, out.stat().st_size


def main() -> int:
    targets = [Path(a) for a in sys.argv[1:]] or sorted(
        d for d in RUNS_DIR.iterdir() if d.is_dir()
    )

    total_raw = total_out = 0
    for target in targets:
        # Batch runs nest their steps one level down.
        run_dirs = [target] if (target / "events.jsonl").is_file() else sorted(
            d for d in target.iterdir() if d.is_dir()
        ) if target.is_dir() else []

        for run_dir in run_dirs:
            sizes = distil_run(run_dir)
            if sizes is None:
                continue
            raw_size, out_size = sizes
            total_raw += raw_size
            total_out += out_size
            print(f"{run_dir.name:<45} {raw_size / 1e6:8.1f} MB -> {out_size / 1e6:6.2f} MB")

    if total_raw:
        print(f"\ntotal {total_raw / 1e6:.1f} MB -> {total_out / 1e6:.1f} MB "
              f"({100 * total_out / total_raw:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
