"""Combine findings from several focused reviews into one ordered list.

Deliberately mechanical. Every decision here is one a script can make correctly
and a model can only make expensively: deduplication, ordering, and enforcing a
rule the reviewer was already given. Judgement -- which findings become work,
and in what order -- belongs to the triage step that reads this output.

Two rules worth stating, because both were learned the hard way:

**Union, never majority.** E7 ran three reviewers over one identical diff. The
subtlest defect was found by exactly one of them, so a majority vote would have
discarded the best finding in the experiment. Majority voting is right when
false positives are the problem; across eight reviews there were none.

**An empty evidence field demotes a finding.** The review prompts all say a
`verified` claim requires evidence actually obtained. Enforcing that here means
the reviewer's own rule is applied even when the reviewer forgot it.

Usage:
    python scripts/aggregate_findings.py evaluation/runs/rvf-*  --out findings.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
CONFIDENCE_ORDER = {"verified": 0, "suspected": 1}

FIELD = re.compile(r"^(?P<key>[a-z_]+):\s*(?P<value>.*)$")
HEADER = re.compile(r"^###\s+FINDING\b", re.IGNORECASE)


def parse_review(path: Path) -> list[dict]:
    """Pull FINDING blocks out of one review.

    Tolerant on purpose. Reviews have arrived with preamble before the first
    block and without the trailing SUMMARY line, and a parser that rejected
    those would discard real findings over formatting.
    """
    findings: list[dict] = []
    current: dict | None = None
    key: str | None = None

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip().strip("`")

        if HEADER.match(stripped):
            if current:
                findings.append(current)
            current = {"source": path.parent.name}
            key = None
            continue

        if current is None:
            continue

        match = FIELD.match(stripped)
        if match:
            key = match.group("key")
            current[key] = match.group("value").strip()
        elif key and stripped:
            # A field wrapped onto the next line.
            current[key] = (current.get(key, "") + " " + stripped).strip()

    if current:
        findings.append(current)
    return findings


def normalise(finding: dict) -> dict:
    finding.setdefault("axis", "unknown")
    finding.setdefault("file", "")
    finding.setdefault("severity", "low")
    finding.setdefault("confidence", "suspected")

    # The reviewer's own rule: no evidence means not verified. Several prompts
    # word the evidence field differently, so accept any of them.
    evidence = " ".join(
        finding.get(k, "") for k in ("evidence", "proof", "result", "repro")
    ).strip()
    if finding["confidence"] == "verified" and not evidence:
        finding["confidence"] = "suspected"
        finding["demoted"] = "verified claim with no evidence"

    finding["severity"] = finding["severity"].split()[0].lower() if finding["severity"] else "low"
    if finding["severity"] not in SEVERITY_ORDER:
        finding["severity"] = "low"
    return finding


def dedupe_key(finding: dict) -> tuple[str, str]:
    """Group by exact location and axis, not by wording.

    Two reviewers describing one defect will not phrase it identically, so
    matching on text would leave duplicates in.

    The line number has to be part of the key. Keying on the file alone was
    tried and was badly wrong: ten distinct error-path defects -- different bad
    inputs failing at different lines of one module -- collapsed into a single
    finding. Distinct defects in one file are the normal case, not the
    exception.

    The cost of the finer key is that two reviewers citing slightly different
    lines for one defect survive as two entries. That is the right way to be
    wrong here: a duplicate is visible and cheap for triage to merge, whereas a
    silently swallowed defect is neither.
    """
    location = finding.get("file", "").replace("\\", "/").strip().rstrip(".,")
    return (location, finding.get("axis", "unknown"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path, help="review run directories")
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    parser.add_argument(
        "--min-severity",
        choices=("high", "medium", "low"),
        default="low",
        help="drop findings below this. The severity floor exists because some real findings are "
             "not worth acting on -- three error-path findings in E7 were reachable only by "
             "calling private functions with malformed input.",
    )
    parser.add_argument(
        "--verified-only",
        action="store_true",
        help="drop anything not backed by evidence the reviewer actually obtained",
    )
    args = parser.parse_args()

    raw: list[dict] = []
    for run in args.runs:
        review = run / "review.md"
        if not review.is_file():
            print(f"warning: no review.md in {run}", file=sys.stderr)
            continue
        raw.extend(parse_review(review))

    findings = [normalise(f) for f in raw]

    floor = SEVERITY_ORDER[args.min_severity]
    kept = [f for f in findings if SEVERITY_ORDER[f["severity"]] <= floor]
    if args.verified_only:
        kept = [f for f in kept if f["confidence"] == "verified"]

    groups: dict[tuple[str, str], dict] = {}
    for finding in kept:
        key = dedupe_key(finding)
        existing = groups.get(key)
        if existing is None:
            finding["found_by"] = [finding["source"]]
            groups[key] = finding
            continue
        # Keep the better-evidenced version; record that more than one reviewer
        # saw it. Agreement is a display hint, never a filter.
        existing["found_by"].append(finding["source"])
        better = (CONFIDENCE_ORDER[finding["confidence"]], SEVERITY_ORDER[finding["severity"]])
        current = (CONFIDENCE_ORDER[existing["confidence"]], SEVERITY_ORDER[existing["severity"]])
        if better < current:
            found_by = existing["found_by"]
            groups[key] = finding
            groups[key]["found_by"] = found_by

    ordered = sorted(
        groups.values(),
        key=lambda f: (
            SEVERITY_ORDER[f["severity"]],
            CONFIDENCE_ORDER[f["confidence"]],
            -len(f["found_by"]),
            f.get("file", ""),
        ),
    )

    report = {
        "reviews_read": [str(r) for r in args.runs],
        "findings_parsed": len(raw),
        "findings_after_filters": len(kept),
        "findings_after_dedupe": len(ordered),
        "findings": ordered,
    }

    text = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"{len(raw)} parsed -> {len(kept)} kept -> {len(ordered)} after dedupe")
        print(f"written: {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
