"""Have the local worker review a diff it did not write, in a fresh context.

The distinction this rests on: self-review by the model that wrote the code is
the same failure as self-written tests -- it verifies that the code agrees with
the author's intent. A fresh instance reviewing a branch it has never seen has
no memory of the reasoning and no investment in the design. That is peer review.

Runs in a dedicated git worktree so a review can never disturb the main checkout
or a concurrent run, and so the reviewer gets a real repository to read and run
tests in rather than a patch file.

Usage:
    python scripts/run_review.py --branch worker/f01-pi --spec evaluation/tasks/f01-...md --id rv-f01-pi
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from run_task import (
    RUNS_DIR,
    TaskError,
    find_little_coder,
    find_pi,
    git,
    parse_task,
    prompt_delivery,
    summarise_events,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "prompts"
REVIEW_PROMPT = PROMPTS_DIR / "review-diff.md"


# Windows caps a command line at 32767 characters, and the prompt is passed as
# one argument. A feature-sized diff inlined into it blows that limit and the
# failure surfaces as "FileNotFoundError: [WinError 206] The filename or
# extension is too long", which names neither the prompt nor the diff.
MAX_PROMPT_CHARS = 30000


def build_prompt(spec_body: str, base: str, branch: str, diff_path: Path,
                 prompt_file: Path = REVIEW_PROMPT) -> str:
    """Assemble the reviewer's prompt.

    The diff is passed by *path*, not inlined. Inlining it is tempting -- a
    reviewer that has to find its own subject spends turns on navigation -- but
    a feature-sized diff exceeds the command-line limit. The reviewer has the
    repository checked out and is told the exact command, so nothing is lost
    except the shortcut.
    """
    instructions = prompt_file.read_text(encoding="utf-8")
    return (
        f"{instructions}\n\n"
        f"---\n\n"
        f"## The change under review\n\n"
        f"Branch `{branch}`, based on `{base}`. The repository is checked out at the branch tip,\n"
        f"so every file is readable and the test suite is runnable.\n\n"
        f"Get the diff with either:\n\n"
        f"- `git diff {base}...HEAD` — run it yourself, or\n"
        f"- read the file `{diff_path}`, which holds the same diff.\n\n"
        f"---\n\n"
        f"## The task specification the change was meant to satisfy\n\n"
        f"{spec_body}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", required=True, help="branch whose diff is reviewed")
    parser.add_argument("--spec", type=Path, required=True, help="task file the change answers")
    parser.add_argument("--id", required=True, help="names the run directory")
    parser.add_argument("--repo", type=Path, default=Path(r"C:\Dev\homelab"))
    parser.add_argument("--model", default="local-worker/local-worker")
    parser.add_argument("--harness", choices=("pi", "little-coder"), default="pi")
    parser.add_argument(
        "--prompt",
        default="review-diff",
        help="which review prompt in prompts/ to use, without the .md. The broad 'review-diff' "
             "covers every axis at once; the narrow 'review-focus-*' prompts each hunt one class "
             "of defect, restoring by separate runs the context isolation the original skill got "
             "from parallel subagents.",
    )
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()

    run_dir = RUNS_DIR / args.id
    if run_dir.exists():
        print(f"ERROR: {run_dir} already exists; use a new id.", file=sys.stderr)
        return 2

    repo = args.repo.resolve()
    meta, spec_body = parse_task(args.spec)
    base = meta.get("base", "experiment/74-local-llm-worker")

    diff = git(repo, "diff", f"{base}...{args.branch}")
    if not diff.strip():
        print(f"ERROR: {base}...{args.branch} is an empty diff; nothing to review.", file=sys.stderr)
        return 2

    # A throwaway worktree at the branch tip. The reviewer needs a real
    # repository -- it is told to run the tests -- but must not be able to
    # touch the main checkout.
    worktree = repo.parent / "homelab-worktrees" / f"review-{args.id}"
    if worktree.exists():
        print(f"ERROR: {worktree} already exists.", file=sys.stderr)
        return 2

    run_dir.mkdir(parents=True)
    git(repo, "worktree", "add", "--detach", str(worktree), args.branch)
    print(f"review  : {args.id}")
    print(f"branch  : {args.branch} (base {base})")
    print(f"worktree: {worktree}")
    print(f"harness : {args.harness}")
    print()

    try:
        diff_path = (run_dir / "under-review.patch").resolve()
        diff_path.write_text(diff, encoding="utf-8")

        prompt_file = PROMPTS_DIR / f"{args.prompt}.md"
        if not prompt_file.is_file():
            print(f"ERROR: no prompt at {prompt_file}", file=sys.stderr)
            return 2
        prompt = build_prompt(spec_body, base, args.branch, diff_path, prompt_file)
        (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

        if len(prompt) > MAX_PROMPT_CHARS:
            print(f"ERROR: prompt is {len(prompt)} characters, over the {MAX_PROMPT_CHARS} "
                  "limit for a command-line argument on Windows.", file=sys.stderr)
            print("       Shorten the review instructions or the task specification.",
                  file=sys.stderr)
            return 2

        env = None
        if args.harness == "little-coder":
            prefix, extra = find_little_coder()
            import os

            env = dict(os.environ)
            env.update(extra)
        else:
            prefix = find_pi()

        cmd = [
            *prefix,
            "-a",
            "--no-session",
            "--exclude-tools", "ask_question",
            "--mode", "json",
            "--model", args.model,
            "-p", prompt,
        ]

        print("reviewing...")
        started = time.monotonic()
        events_path = run_dir / "events.jsonl"
        with events_path.open("w", encoding="utf-8") as events:
            process = subprocess.Popen(
                cmd, cwd=worktree, stdout=events, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", env=env,
            )
            try:
                _, stderr = process.communicate(timeout=args.timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr = process.communicate()
                timed_out = True
        elapsed = round(time.monotonic() - started, 1)

        events = summarise_events(events_path)
        delivery = prompt_delivery(events_path, prompt)
        print(f"  {elapsed}s, {events['turns']} turns, {events['tool_calls']} tool calls")
        if events["errored_turns"]:
            print(f"  WARNING: {events['errored_turns']} turn(s) ended in an API error.")
        if not delivery["verified"]:
            print(f"  WARNING: prompt delivery unverified -- {delivery['reason']}")

        # The review IS the final assistant text; there is no diff to inspect.
        findings = extract_final_text(events_path)
        (run_dir / "review.md").write_text(findings or "(no text output)", encoding="utf-8")

        # The worktree must come back unchanged. A reviewer that edited the code
        # under review has stopped being a reviewer.
        dirty = git(worktree, "status", "--porcelain").strip()
        if dirty:
            print("  WARNING: the reviewer modified the worktree:")
            print("    " + dirty.replace("\n", "\n    "))
            (run_dir / "reviewer-changes.patch").write_text(
                git(worktree, "diff"), encoding="utf-8")

        record = {
            "review_id": args.id,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "branch": args.branch,
            "base": base,
            "spec": str(args.spec),
            "harness": args.harness,
            "model": args.model,
            "elapsed_seconds": elapsed,
            "timed_out": timed_out,
            "exit_code": process.returncode,
            "events": events,
            "prompt_delivery": delivery,
            "reviewer_modified_worktree": bool(dirty),
            "stderr_tail": (stderr or "").strip()[-2000:],
        }
        (run_dir / "review.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    finally:
        git(repo, "worktree", "remove", "--force", str(worktree), check=False)
        git(repo, "worktree", "prune", check=False)

    print()
    print(f"recorded: {run_dir}")
    print("Score the findings against the known defect list before trusting any of them.")
    return 0


def extract_final_text(events_path: Path) -> str | None:
    final = None
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
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            parts = message.get("content")
            if not isinstance(parts, list):
                continue
            text = "".join(
                p.get("text", "") for p in parts
                if isinstance(p, dict) and p.get("type") == "text"
            )
            if text.strip():
                final = text
    return final


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TaskError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
