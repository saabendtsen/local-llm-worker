"""Run one delegated task through the local worker and record what happened.

Claude writes the task file and reviews the result; this script only executes the
run and gathers evidence. It deliberately makes no judgement about quality --
that is the reviewer's job, and a runner that scored its own output would defeat
the point of the evaluation.

Usage:
    python scripts/run_task.py evaluation/tasks/0001-example.md
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "evaluation" / "runs"

# Pi emits one JSON object per line in --mode json. These are the events we count.
EVENT_TURN = "turn_end"
EVENT_TOOL = "tool_execution_end"


class TaskError(RuntimeError):
    """A problem with the task definition or the repository it targets."""


def parse_task(path: Path) -> tuple[dict[str, str], str]:
    """Split a task file into its frontmatter fields and its prompt body.

    Frontmatter is a leading '---' delimited block of 'key: value' lines. It is
    parsed by hand rather than with PyYAML so the harness stays dependency-free.
    """
    # utf-8-sig, not utf-8: PowerShell's Set-Content and Notepad both write a BOM,
    # which would otherwise sit in front of the '---' and fail the check below.
    text = path.read_text(encoding="utf-8-sig").lstrip()
    if not text.startswith("---"):
        raise TaskError(f"{path.name}: missing '---' frontmatter block")

    _, raw_meta, body = text.split("---", 2)

    meta: dict[str, str] = {}
    for line in raw_meta.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise TaskError(f"{path.name}: frontmatter line is not 'key: value': {line!r}")
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()

    for required in ("id", "repo", "category"):
        if required not in meta:
            raise TaskError(f"{path.name}: frontmatter is missing '{required}'")

    return meta, body.strip()


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise TaskError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def require_clean_tracked_tree(repo: Path) -> None:
    """Refuse to run when tracked files have uncommitted changes.

    The whole measurement is the diff the worker produced. Pre-existing edits to
    tracked files would be indistinguishable from the worker's work, and worse,
    the worker could overwrite them.

    Untracked files are tolerated: real working copies routinely carry local
    scratch files that have nothing to do with the task. They are snapshotted
    instead (see `existing_untracked`) and subtracted from the result, so the
    run still reports only what the worker actually created.
    """
    if git(repo, "status", "--porcelain", "--untracked-files=no").strip():
        raise TaskError(
            f"{repo} has uncommitted changes to tracked files. Commit or stash them first -- "
            "the run measures the diff the worker creates, so tracked files must start clean."
        )


def existing_untracked(repo: Path) -> set[str]:
    return {
        name
        for name in git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if name
    }


def find_pi() -> str:
    pi = shutil.which("pi")
    if not pi:
        raise TaskError(
            "'pi' not found on PATH. Install it with:\n"
            "  npm install -g --ignore-scripts @earendil-works/pi-coding-agent"
        )
    return pi


def run_worker(repo: Path, prompt: str, model: str, events_path: Path, timeout: int) -> dict:
    """Run Pi headless against the repository, streaming its JSON events to disk."""
    cmd = [
        find_pi(),
        "-a",                            # trust project files; the branch is the safety net
        "--no-session",                  # each run is independent
        "--exclude-tools", "ask_question",  # headless: a question would hang forever
        "--mode", "json",
        "--model", model,
        "-p", prompt,
    ]

    started = time.monotonic()
    timed_out = False

    with events_path.open("w", encoding="utf-8") as events:
        process = subprocess.Popen(
            cmd,
            cwd=repo,
            stdout=events,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            _, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate()
            timed_out = True

    return {
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "stderr_tail": (stderr or "").strip()[-2000:],
    }


def summarise_events(events_path: Path) -> dict:
    """Count turns and tool calls from Pi's event stream.

    'Turns' is the closest available proxy for how many times the worker looped
    before it stopped, which is one of the metrics the evaluation asks for.
    """
    turns = 0
    tool_calls = 0
    tools_used: dict[str, int] = {}
    malformed = 0

    with events_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue

            kind = event.get("type")
            if kind == EVENT_TURN:
                turns += 1
            elif kind == EVENT_TOOL:
                tool_calls += 1
                name = _tool_name(event)
                tools_used[name] = tools_used.get(name, 0) + 1

    return {
        "turns": turns,
        "tool_calls": tool_calls,
        "tools_used": dict(sorted(tools_used.items(), key=lambda kv: -kv[1])),
        "malformed_event_lines": malformed,
    }


def _tool_name(event: dict) -> str:
    """Pi has moved tool names around between versions; try the known shapes."""
    for path in (("toolName",), ("name",), ("tool", "name"), ("execution", "toolName")):
        value: object = event
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, str):
            return value
    return "unknown"


def verify(repo: Path, command: str, timeout: int) -> dict:
    """Run the task's acceptance command and record whether it passed."""
    if not command:
        return {"command": None, "skipped": "no verify command in task frontmatter"}

    result = subprocess.run(
        command,
        cwd=repo,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    output = (result.stdout + result.stderr).strip()
    return {
        "command": command,
        "exit_code": result.returncode,
        "passed": result.returncode == 0,
        "output_tail": output[-4000:],
    }


def diff_stats(repo: Path, preexisting: set[str]) -> dict:
    numstat = git(repo, "diff", "--numstat")
    files = added = removed = 0
    for line in numstat.strip().splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        files += 1
        # '-' appears for binary files; count the file but not its lines.
        if parts[0].isdigit():
            added += int(parts[0])
        if parts[1].isdigit():
            removed += int(parts[1])

    # Only untracked files that appeared during the run are the worker's doing.
    untracked = sorted(existing_untracked(repo) - preexisting)

    return {
        "files_changed": files,
        "lines_added": added,
        "lines_removed": removed,
        "untracked_files": untracked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="path to the task markdown file")
    parser.add_argument("--model", default="local-worker/local-worker")
    parser.add_argument("--timeout", type=int, default=3600, help="worker timeout in seconds")
    parser.add_argument("--verify-timeout", type=int, default=900)
    parser.add_argument(
        "--keep-branch",
        action="store_true",
        help="leave the work branch checked out instead of reporting how to inspect it",
    )
    args = parser.parse_args()

    try:
        meta, prompt = parse_task(args.task)
    except TaskError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    repo = Path(os.path.expandvars(meta["repo"])).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"ERROR: {repo} is not a Git repository", file=sys.stderr)
        return 2

    task_id = meta["id"]
    run_dir = RUNS_DIR / task_id
    if run_dir.exists():
        print(
            f"ERROR: {run_dir} already exists. Runs are immutable evidence; "
            "give the task a new id rather than overwriting a result.",
            file=sys.stderr,
        )
        return 2

    try:
        require_clean_tracked_tree(repo)
    except TaskError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    preexisting = existing_untracked(repo)

    branch = meta.get("branch", f"worker/{task_id}")
    base_commit = git(repo, "rev-parse", "HEAD").strip()

    run_dir.mkdir(parents=True)
    print(f"task   : {task_id} ({meta['category']})")
    print(f"repo   : {repo}")
    print(f"branch : {branch}")
    print(f"model  : {args.model}")
    print()

    git(repo, "checkout", "-q", "-b", branch)

    print("running worker...")
    worker = run_worker(repo, prompt, args.model, run_dir / "events.jsonl", args.timeout)
    print(f"  finished in {worker['elapsed_seconds']}s (exit {worker['exit_code']})")
    if worker["timed_out"]:
        print(f"  TIMED OUT after {args.timeout}s")

    events = summarise_events(run_dir / "events.jsonl")
    print(f"  {events['turns']} turns, {events['tool_calls']} tool calls")

    (run_dir / "diff.patch").write_text(git(repo, "diff"), encoding="utf-8")
    stats = diff_stats(repo, preexisting)
    print(f"  {stats['files_changed']} files changed, "
          f"+{stats['lines_added']}/-{stats['lines_removed']}")
    if stats["untracked_files"]:
        print(f"  plus {len(stats['untracked_files'])} untracked file(s)")

    print("verifying...")
    try:
        checks = verify(repo, meta.get("verify", ""), args.verify_timeout)
    except subprocess.TimeoutExpired:
        checks = {"command": meta.get("verify"), "passed": False, "output_tail": "verify timed out"}
    if checks.get("command"):
        print(f"  {'PASSED' if checks.get('passed') else 'FAILED'}: {checks['command']}")
    else:
        print("  skipped (no verify command)")

    record = {
        "task_id": task_id,
        "category": meta["category"],
        "complexity": meta.get("complexity"),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": str(repo),
        "branch": branch,
        "base_commit": base_commit,
        "model": args.model,
        "worker": worker,
        "events": events,
        "diff": stats,
        "verify": checks,
    }
    (run_dir / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    if not args.keep_branch:
        git(repo, "checkout", "-q", "-")

    print()
    print(f"recorded: {run_dir}")
    print("Review the diff and score the run in evaluation/results.md.")
    print(f"  git -C {repo} diff {base_commit}..{branch}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TaskError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
