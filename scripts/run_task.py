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
import re
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


def task_title(body: str, fallback: str) -> str:
    """The task's heading, without the leading '# Task:' -- what a status page shows."""
    for line in body.splitlines():
        if line.startswith("# "):
            return re.sub(r"^#\s*(Task:\s*)?", "", line).strip() or fallback
    return fallback


def write_started(run_dir: Path, kind: str, task_id: str, title: str, **extra: object) -> None:
    """Mark a run as in progress the moment its directory exists.

    Every other file in a run directory is written when the run ends (run.json,
    review.json, triage.json), so without this marker nothing says what is
    running now, or since when. The status page reads it; nothing else does.
    """
    record = {
        "kind": kind,
        "task_id": task_id,
        "title": title,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **extra,
    }
    (run_dir / "started.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


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


def find_little_coder() -> tuple[list[str], dict[str, str]]:
    """Return the command prefix and environment for the sandboxed little-coder.

    Deliberately only the sandbox copy under sandbox/little-coder. little-coder
    depends on Pi ^0.83.0 while the working setup runs 0.84.2, so a global
    install would change which Pi every run uses -- and tool names, which the
    metrics count, moved between those versions.
    """
    sandbox = REPO_ROOT / "sandbox" / "little-coder"
    launcher = sandbox / "node_modules" / "little-coder" / "bin" / "little-coder.mjs"
    if not launcher.is_file():
        raise TaskError(
            f"little-coder is not installed at {launcher}.\n"
            f"Run: cd {sandbox} && npm install"
        )
    node = shutil.which("node")
    if not node:
        raise TaskError("'node' not found on PATH; little-coder needs it.")

    models = sandbox / "models.json"
    if not models.is_file():
        raise TaskError(f"missing {models}")

    return [node, str(launcher)], {"LITTLE_CODER_MODELS_FILE": str(models)}


def find_pi() -> list[str]:
    """Return the command prefix that launches Pi.

    On Windows, `shutil.which('pi')` resolves to `pi.CMD`, and launching a .CMD
    hands the argument list to cmd.exe -- which truncates any argument at its
    first newline. The task prompt is multi-line, so the worker would silently
    receive only its title. That is not a hypothetical: it produced a run that
    looked like a comprehension failure until the event log showed the prompt
    had arrived as a single line.

    So resolve the package's JS entry point and run it under node directly,
    bypassing the shim and cmd.exe entirely. Fall back to the shim only when the
    entry point cannot be found, and warn if that happens.
    """
    node = shutil.which("node")
    if node:
        for root in _npm_global_roots():
            entry = root / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
            if entry.is_file():
                return [node, str(entry)]

    pi = shutil.which("pi")
    if not pi:
        raise TaskError(
            "'pi' not found on PATH. Install it with:\n"
            "  npm install -g --ignore-scripts @earendil-works/pi-coding-agent"
        )
    if os.name == "nt" and pi.lower().endswith((".cmd", ".bat")):
        print(
            f"WARNING: falling back to {pi}. On Windows the shim truncates the prompt at its "
            "first newline, so the worker will not see the whole task.",
            file=sys.stderr,
        )
    return [pi]


def _npm_global_roots() -> list[Path]:
    roots = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "npm" / "node_modules")
    prefix = shutil.which("npm")
    if prefix:
        roots.append(Path(prefix).parent / "node_modules")
    roots.append(Path.home() / "node_modules")
    return roots


# Everything except bash. The worker can read, search, and edit, and cannot
# execute a shell command at all -- so no `rm` can reach anything, inside the
# repository or outside it. Pi's controls are tool-level, so a single command
# cannot be denied; dropping the whole tool is the available boundary.
NO_SHELL_TOOLS = "read,edit,write,grep,find,ls"


def run_worker(repo: Path, prompt: str, model: str, events_path: Path, timeout: int,
               allow_shell: bool = True, harness: str = "pi") -> dict:
    """Run the chosen harness headless, streaming its JSON events to disk.

    Both harnesses take the same flags because little-coder *is* Pi underneath —
    it passes user arguments through to the Pi it bundles. That is what makes a
    like-for-like comparison possible at all.
    """
    env = dict(os.environ)
    if harness == "little-coder":
        prefix, extra_env = find_little_coder()
        env.update(extra_env)
    else:
        prefix = find_pi()

    cmd = [
        *prefix,
        "-a",                            # trust project files; the branch is the safety net
        "--no-session",                  # each run is independent
        "--exclude-tools", "ask_question",  # headless: a question would hang forever
        "--mode", "json",
        "--model", model,
    ]
    if not allow_shell:
        cmd += ["--tools", NO_SHELL_TOOLS]
    cmd += ["-p", prompt]

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
            env=env,
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
    errored_turns = 0

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

            # An assistant turn that ends in `error` produced nothing: the
            # request failed. A whole run of these looks like a model that
            # refused to act, when in fact the server was unreachable or still
            # loading. Count them so the difference is visible in the record.
            message = event.get("message")
            if isinstance(message, dict) and message.get("stopReason") == "error":
                errored_turns += 1

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
        "errored_turns": errored_turns,
    }


def prompt_delivery(events_path: Path, prompt: str) -> dict:
    """Confirm the worker actually received the whole prompt.

    A truncated prompt is indistinguishable from a stupid model when you only
    look at the diff: the worker does something irrelevant, confidently, and the
    run reads as a comprehension failure. This check makes that failure loud, so
    a harness bug can never again be recorded as a capability result.
    """
    received = None
    with events_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = event.get("message")
            if isinstance(message, dict) and message.get("role") == "user":
                parts = message.get("content")
                if isinstance(parts, list):
                    received = "".join(
                        part.get("text", "")
                        for part in parts
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                elif isinstance(parts, str):
                    received = parts
                break

    sent_chars = len(prompt)
    if received is None:
        return {"verified": False, "reason": "no user message found in event stream",
                "sent_chars": sent_chars}

    # Harnesses wrap the prompt in their own scaffolding, so require containment
    # rather than equality, and treat a large shortfall as truncation.
    intact = prompt.strip() in received
    return {
        "verified": intact,
        "sent_chars": sent_chars,
        "received_chars": len(received),
        "reason": None if intact else "prompt was altered or truncated in transit",
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


def stage_worker_changes(repo: Path, preexisting: set[str]) -> list[str]:
    """Stage everything the worker changed, and nothing it did not.

    `git add -A` would sweep in local scratch files that were already lying
    around, so tracked modifications and worker-created files are staged
    separately.
    """
    git(repo, "add", "-u")
    created = sorted(existing_untracked(repo) - preexisting)
    for name in created:
        git(repo, "add", "--", name)
    return created


def diff_stats(repo: Path, created: list[str]) -> dict:
    numstat = git(repo, "diff", "--cached", "--numstat")
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

    return {
        "files_changed": files,
        "lines_added": added,
        "lines_removed": removed,
        "files_created": created,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="path to the task markdown file")
    parser.add_argument("--model", default="local-worker/local-worker")
    parser.add_argument(
        "--harness",
        choices=("pi", "little-coder"),
        default="pi",
        help="which harness drives the model. 'little-coder' uses the sandboxed copy, which "
             "bundles Pi 0.83 and injects its own system prompt -- so its numbers are not "
             "directly comparable to 'pi' unless the same task is run through both.",
    )
    parser.add_argument(
        "--id",
        help="override the task's id. Lets one task file drive several runs -- an A/B across "
             "harnesses, or a repeat to measure variance -- without duplicating the prompt, so "
             "both arms are provably identical.",
    )
    parser.add_argument("--branch", help="override the work branch name")
    parser.add_argument("--timeout", type=int, default=3600, help="worker timeout in seconds")
    parser.add_argument("--verify-timeout", type=int, default=900)
    parser.add_argument(
        "--no-shell",
        action="store_true",
        help="deny the worker the bash tool entirely. It can still read, search and edit, but "
             "cannot run any command -- so a mistaken path cannot destroy anything. Pair with a "
             "pipeline that runs the tests, since the worker can no longer run them itself.",
    )
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

    task_id = args.id or meta["id"]
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

    branch = args.branch or meta.get("branch", f"worker/{task_id}")
    base_commit = git(repo, "rev-parse", "HEAD").strip()

    # Record the starting branch by NAME. Restoring with `git checkout -` looks
    # equivalent and is not: `-` resolves @{-1}, which any other checkout in the
    # repository silently rewrites. A review agent inspecting an older branch
    # once left @{-1} pointing at it, so the next run branched off a previous
    # run's work instead of the base -- and started with the defect already
    # fixed. That run looked plausible and was worthless as a measurement.
    original_branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()

    # Branch from an explicitly named base when the task states one, rather than
    # from whatever happens to be checked out. Without this a run silently
    # inherits an earlier run's work and measures nothing -- it has already
    # happened twice, and both times the record looked entirely plausible:
    # passing suite, sensible diff, reasonable turn count.
    base = meta.get("base")
    if base:
        if not git(repo, "rev-parse", "--verify", "--quiet", base, check=False).strip():
            print(f"ERROR: base {base!r} does not exist in {repo}", file=sys.stderr)
            return 2
        git(repo, "checkout", "-q", base)
        base_commit = git(repo, "rev-parse", "HEAD").strip()
        print(f"base   : {base} ({base_commit[:7]})")

    run_dir.mkdir(parents=True)
    write_started(run_dir, "task", task_id, task_title(prompt, task_id),
                  category=meta["category"], branch=branch, harness=args.harness)
    print(f"task   : {task_id} ({meta['category']})")
    print(f"repo   : {repo}")
    print(f"branch : {branch}")
    print(f"model  : {args.model}")
    print()

    git(repo, "checkout", "-q", "-b", branch)

    allow_shell = not (args.no_shell or meta.get("shell", "").lower() in {"no", "false", "off"})
    print(f"shell  : {'enabled' if allow_shell else 'DENIED (read/edit/write only)'}")
    print()
    print(f"harness: {args.harness}")
    print()
    print("running worker...")
    worker = run_worker(repo, prompt, args.model, run_dir / "events.jsonl", args.timeout,
                        allow_shell=allow_shell, harness=args.harness)

    # Keep the exact prompt beside the evidence. The task file may be edited
    # later; this is what was actually sent, so a run stays reproducible and
    # reviewable without trusting that the task file never moved.
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"  finished in {worker['elapsed_seconds']}s (exit {worker['exit_code']})")
    if worker["timed_out"]:
        print(f"  TIMED OUT after {args.timeout}s")

    events = summarise_events(run_dir / "events.jsonl")
    print(f"  {events['turns']} turns, {events['tool_calls']} tool calls")

    if events["errored_turns"]:
        print(f"  WARNING: {events['errored_turns']} turn(s) ended in an API error.")
        print("           The server was unreachable, still loading, or rejected the request.")
        print("           Score this as a HARNESS FAILURE, not a model result.")

    delivery = prompt_delivery(run_dir / "events.jsonl", prompt)
    if not delivery["verified"]:
        print(f"  WARNING: prompt delivery unverified -- {delivery['reason']}")
        print(f"           sent {delivery['sent_chars']} chars, "
              f"worker saw {delivery.get('received_chars', '?')}")
        print("           Score this as a HARNESS FAILURE, not a model result.")

    created = stage_worker_changes(repo, preexisting)
    (run_dir / "diff.patch").write_text(git(repo, "diff", "--cached"), encoding="utf-8")
    stats = diff_stats(repo, created)
    print(f"  {stats['files_changed']} files changed, "
          f"+{stats['lines_added']}/-{stats['lines_removed']}")
    if created:
        print(f"  {len(created)} new file(s): {', '.join(created)}")

    # Commit on the work branch. Without this the changes stay in the working
    # tree and follow the checkout back to the original branch -- so the branch
    # would be an empty artifact and the original branch would silently inherit
    # the worker's edits.
    work_commit = None
    if stats["files_changed"]:
        git(repo, "-c", "user.name=local-worker", "-c", "user.email=worker@localhost",
            "commit", "-q", "-m", f"worker: {task_id}")
        work_commit = git(repo, "rev-parse", "HEAD").strip()

    print("verifying...")
    try:
        checks = verify(repo, meta.get("verify", ""), args.verify_timeout)
    except subprocess.TimeoutExpired:
        checks = {"command": meta.get("verify"), "passed": False, "output_tail": "verify timed out"}
    if checks.get("command"):
        print(f"  {'PASSED' if checks.get('passed') else 'FAILED'}: {checks['command']}")
    else:
        print("  skipped (no verify command)")

    # A green suite on an empty diff means the worker did nothing, not that the
    # task is done. Observed for real: a 23-minute run that made zero changes
    # recorded verify.passed because the untouched suite still passes. Anything
    # keyed on the acceptance command alone would file that as a success.
    no_op = stats["files_changed"] == 0
    if no_op and checks.get("passed"):
        print("  WARNING: the acceptance command passed but NOTHING CHANGED.")
        print("           A green suite on an empty diff means the worker did no work.")
        print("           This is not a success.")

    record = {
        "task_id": task_id,
        "category": meta["category"],
        "complexity": meta.get("complexity"),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": str(repo),
        "branch": branch,
        "base_commit": base_commit,
        "work_commit": work_commit,
        "model": args.model,
        "harness": args.harness,
        "task_file": str(args.task),
        "shell_allowed": allow_shell,
        "worker": worker,
        "prompt_delivery": delivery,
        "events": events,
        "diff": stats,
        "verify": checks,
        # Derived, so nothing downstream has to rediscover the distinction
        # between "the acceptance command passed" and "work was actually done".
        "produced_no_changes": no_op,
        "meaningful_pass": bool(checks.get("passed")) and not no_op,
    }
    (run_dir / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    if not args.keep_branch:
        git(repo, "checkout", "-q", original_branch)

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
