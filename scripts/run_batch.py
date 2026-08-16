"""Run a batch of atomic tasks through the local worker on one branch.

The delegation shape this implements: Claude plans N atomic tasks up front,
the worker executes them in sequence with a fresh context each time, and Claude
reviews once at the end. One planning pass and one review pass amortised over N
executions, which is where the frontier-token saving comes from.

The one thing added to that shape is a circuit breaker. Reviewing only at the
end is fine; *continuing* after a step has broken is not, because every later
step then builds on a broken base and the final review becomes an untangling
exercise instead of a review. Each task carries its own acceptance command, and
the batch halts the moment one fails. That gate costs no frontier tokens -- it
is the worker's own test run.

Steps share one branch and commit individually, so later steps build on earlier
ones and the final review can read the change either per-step or as a whole.

Usage:
    python scripts/run_batch.py --id refactor-01 evaluation/tasks/a.md evaluation/tasks/b.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from run_task import (
    RUNS_DIR,
    TaskError,
    diff_stats,
    existing_untracked,
    git,
    parse_task,
    prompt_delivery,
    require_clean_tracked_tree,
    run_worker,
    stage_worker_changes,
    summarise_events,
    verify,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", nargs="+", type=Path, help="task files, in execution order")
    parser.add_argument("--id", required=True, help="batch id; names the branch and run directory")
    parser.add_argument("--model", default="local-worker/local-worker")
    parser.add_argument("--timeout", type=int, default=3600, help="per-step worker timeout")
    parser.add_argument("--verify-timeout", type=int, default=900)
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="do not halt on a failed step. Off by default: later steps would build on a broken "
             "base, which makes the final review harder than reviewing each step would have been.",
    )
    args = parser.parse_args()

    parsed = []
    for path in args.tasks:
        try:
            parsed.append((path, *parse_task(path)))
        except TaskError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2

    repos = {meta["repo"] for _, meta, _ in parsed}
    if len(repos) != 1:
        print(f"ERROR: every task in a batch must target one repository, found: {sorted(repos)}",
              file=sys.stderr)
        return 2

    repo = Path(repos.pop()).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"ERROR: {repo} is not a Git repository", file=sys.stderr)
        return 2

    batch_dir = RUNS_DIR / args.id
    if batch_dir.exists():
        print(f"ERROR: {batch_dir} already exists. Runs are immutable evidence; use a new batch id.",
              file=sys.stderr)
        return 2

    try:
        require_clean_tracked_tree(repo)
    except TaskError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    branch = f"batch/{args.id}"
    base_commit = git(repo, "rev-parse", "HEAD").strip()
    batch_dir.mkdir(parents=True)

    print(f"batch  : {args.id}  ({len(parsed)} steps)")
    print(f"repo   : {repo}")
    print(f"branch : {branch}")
    print()

    git(repo, "checkout", "-q", "-b", branch)

    steps = []
    halted_at = None

    for index, (path, meta, prompt) in enumerate(parsed, start=1):
        task_id = meta["id"]
        step_dir = batch_dir / f"step-{index:02d}-{task_id}"
        step_dir.mkdir()

        print(f"[{index}/{len(parsed)}] {task_id} ({meta['category']})")

        preexisting = existing_untracked(repo)
        worker = run_worker(repo, prompt, args.model, step_dir / "events.jsonl", args.timeout)
        events = summarise_events(step_dir / "events.jsonl")
        delivery = prompt_delivery(step_dir / "events.jsonl", prompt)

        print(f"        {worker['elapsed_seconds']}s, {events['turns']} turns, "
              f"{events['tool_calls']} tool calls")
        if not delivery["verified"]:
            print(f"        WARNING: prompt delivery unverified -- {delivery['reason']}")
            print("        Score as a HARNESS FAILURE, not a model result.")

        created = stage_worker_changes(repo, preexisting)
        (step_dir / "diff.patch").write_text(git(repo, "diff", "--cached"), encoding="utf-8")
        stats = diff_stats(repo, created)
        print(f"        {stats['files_changed']} files, "
              f"+{stats['lines_added']}/-{stats['lines_removed']}")

        step_commit = None
        if stats["files_changed"]:
            git(repo, "-c", "user.name=local-worker", "-c", "user.email=worker@localhost",
                "commit", "-q", "-m", f"worker: {task_id}")
            step_commit = git(repo, "rev-parse", "HEAD").strip()

        try:
            checks = verify(repo, meta.get("verify", ""), args.verify_timeout)
        except Exception as error:  # a verify command that will not even run
            checks = {"command": meta.get("verify"), "passed": False, "output_tail": str(error)}

        if checks.get("command"):
            print(f"        verify: {'PASSED' if checks.get('passed') else 'FAILED'}")
        else:
            print("        verify: skipped (no command)")

        steps.append({
            "index": index,
            "task_id": task_id,
            "task_file": str(path),
            "category": meta["category"],
            "worker": worker,
            "prompt_delivery": delivery,
            "events": events,
            "diff": stats,
            "commit": step_commit,
            "verify": checks,
        })

        # The circuit breaker. A step that produced nothing is also a failure --
        # it means the next step builds on an assumption that was never met.
        broken = not checks.get("passed", True) or stats["files_changed"] == 0
        if broken and not args.keep_going:
            halted_at = index
            reason = "verify failed" if not checks.get("passed", True) else "no changes produced"
            print()
            print(f"HALTED at step {index} ({task_id}): {reason}.")
            print("Later steps would build on a broken base. Fix and rerun from here.")
            break

    record = {
        "batch_id": args.id,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": str(repo),
        "branch": branch,
        "base_commit": base_commit,
        "model": args.model,
        "steps_planned": len(parsed),
        "steps_run": len(steps),
        "halted_at_step": halted_at,
        "steps": steps,
    }
    (batch_dir / "batch.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    git(repo, "checkout", "-q", "-")

    completed = sum(1 for step in steps if step["verify"].get("passed", False))
    print()
    print(f"recorded: {batch_dir}")
    print(f"{completed}/{len(parsed)} steps passed their acceptance command.")
    print("Review the whole branch, then score each step in evaluation/results.md:")
    print(f"  git -C {repo} log --oneline {base_commit}..{branch}")
    print(f"  git -C {repo} diff {base_commit}..{branch}")
    return 0 if halted_at is None else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TaskError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
