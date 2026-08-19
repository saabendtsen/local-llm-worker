"""Turn aggregated review findings into bounded fix tasks, using a frontier model.

This is the pipeline's triage step. The findings come from `aggregate_findings.py`;
the output is one task file per accepted finding under evaluation/tasks/, in the
shape the local worker already executes. The frontier model reads the repository
(verifying each finding against the source -- a finding's `problem` is a claim,
not a fact), classifies defect versus test gap, merges findings that are one
issue, and orders the work. This script owns the prompt, invokes the model by
CLI, validates the output strictly, retries with the errors fed back, and
refuses to proceed on anything half-parsed.

The frontier model is pluggable (`--frontier claude|codex|cmd:<template>`). The
prompt is always delivered on stdin -- Windows caps a command line at 32767
characters and a findings list plus a diff is larger than that. The model runs
in a throwaway, detached worktree of the target repository and is expected to
leave it untouched; any modification is a hard failure.

Built-in frontier commands:
    claude  claude -p --output-format text --tools Read,Grep,Glob
                   --permission-mode dontAsk --no-session-persistence [--model M]
            (checked against `claude --help` for 2.1.x; read-only tool set)
    codex   codex exec --sandbox read-only -C <worktree> [-m M] -
            (best effort: flags taken from `codex exec --help`, read-only sandbox,
            `-` reads the prompt from stdin; not exercised as thoroughly as claude)
    cmd:T   T is run through the shell with the prompt on stdin, cwd = worktree.
            `{worktree}` and `{model}` in T are substituted.

Usage:
    python scripts/run_triage.py --findings evaluation/runs/<rv>/findings.json \\
        --spec evaluation/tasks/f02-wayfinder-history.md \\
        --branch worker/f02-wayfinder-history --id tr-f02 --frontier claude
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from run_task import RUNS_DIR, TaskError, git, parse_task, pipeline_of, write_started

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "prompts"
TASKS_DIR = REPO_ROOT / "evaluation" / "tasks"
TRIAGE_PROMPT = PROMPTS_DIR / "triage.md"

# Above this the diff is passed by path rather than inlined. The limit is about
# keeping the prompt readable for the model, not the command line -- the prompt
# goes over stdin, so the 32767-character argv cap does not apply here.
MAX_INLINE_PROMPT_CHARS = 60000

DISPOSITIONS = ("fix", "fix-test-only", "defer", "drop")
TASK_DISPOSITIONS = ("fix", "fix-test-only")
CATEGORIES = ("bugfix", "tests")
COMPLEXITIES = ("small", "medium")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
JSON_BLOCK_RE = re.compile(r"```json[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL)
# The leading path in a finding's `file` field, which may be followed by
# ":line", ", symbol" or prose.
FILE_PATH_RE = re.compile(r"^\s*`?([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)")


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def format_findings(findings: list[dict]) -> str:
    """Pretty JSON, each finding carrying its 1-based index.

    The index is what the model refers to in its dispositions, so it must be
    unambiguous and visible rather than implied by list position.
    """
    numbered = [{"index": i, **f} for i, f in enumerate(findings, start=1)]
    return json.dumps(numbered, indent=2, ensure_ascii=False)


def build_prompt(instructions: str, spec_body: str, findings: list[dict], base: str,
                 branch: str, diff: str, diff_path: Path,
                 max_inline: int = MAX_INLINE_PROMPT_CHARS, findings_only: bool = False) -> str:
    """Assemble the triage prompt.

    With `findings_only` the diff is withheld entirely: the model gets the
    specification, the findings and read access to the branch, and must open
    the cited files itself. That is the cheaper configuration -- the diff is
    most of the prompt -- and whether triage quality survives it is the
    question the flag exists to answer.
    """
    head = (
        f"{instructions}\n\n"
        f"---\n\n"
        f"## The branch under triage\n\n"
        f"Branch `{branch}`, based on `{base}`. The repository is checked out read-only at the\n"
        f"branch tip, so every cited file and line is readable. Do not modify anything.\n\n"
        f"---\n\n"
        f"## The task specification the branch was meant to satisfy\n\n"
        f"{spec_body}\n\n"
        f"---\n\n"
        f"## The findings ({len(findings)} total, 1-based `index`)\n\n"
        f"```json\n{format_findings(findings)}\n```\n\n"
        f"---\n\n"
    )
    if findings_only:
        return head + (
            "## No diff is provided\n\n"
            "Verify each finding by reading the cited files in the repository. Every file and\n"
            "line the findings name is there at the branch tip.\n"
        )
    head += "## The diff of the branch against its base\n\n"
    inline = f"```diff\n{diff}\n```\n"
    if len(head) + len(inline) <= max_inline:
        return head + inline
    return head + (
        f"The diff is {len(diff)} characters, too large to inline. Read it from\n"
        f"`{diff_path}` or run `git diff {base}...HEAD` in the repository.\n"
    )


def rejection_suffix(raw_output: str, errors: list[str], max_echo: int = 20000) -> str:
    """What gets appended to the prompt on a retry.

    The model has no memory between invocations, so the rejected output is
    echoed back with the errors; otherwise "emit the corrected JSON" has nothing
    to correct.
    """
    echoed = raw_output if len(raw_output) <= max_echo else raw_output[-max_echo:]
    bullet = "\n".join(f"- {e}" for e in errors)
    return (
        f"\n\n---\n\n"
        f"## Your previous output was rejected\n\n"
        f"The validator found these problems:\n\n{bullet}\n\n"
        f"Your previous output was:\n\n"
        f"````\n{echoed}\n````\n\n"
        f"Emit the corrected JSON block only. Every rule in the output contract applies.\n"
    )


# ---------------------------------------------------------------------------
# Output parsing and validation
# ---------------------------------------------------------------------------

class TriageOutputError(ValueError):
    """The frontier's reply does not satisfy the contract."""


def extract_json_block(text: str) -> str:
    blocks = JSON_BLOCK_RE.findall(text or "")
    if not blocks:
        raise TriageOutputError("no ```json fenced block found in the output")
    if len(blocks) > 1:
        raise TriageOutputError(
            f"expected exactly one ```json fenced block, found {len(blocks)}")
    return blocks[0]


def parse_triage_output(text: str) -> dict:
    """Extract and parse the JSON block. Raises TriageOutputError on any failure."""
    block = extract_json_block(text)
    try:
        obj = json.loads(block)
    except json.JSONDecodeError as error:
        raise TriageOutputError(f"the json block does not parse: {error}") from error
    if not isinstance(obj, dict):
        raise TriageOutputError("the json block must be a single object")
    return obj


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _str_list(value: object, nonempty: bool) -> bool:
    if not isinstance(value, list):
        return False
    if nonempty and not value:
        return False
    return all(_nonempty_str(v) for v in value)


def validate_task(task: object, where: str, disposition: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(task, dict):
        return [f"{where}: task must be an object"]

    slug = task.get("slug")
    if not (_nonempty_str(slug) and SLUG_RE.match(slug)):
        errors.append(f"{where}: task.slug must be kebab-case ([a-z0-9]+(-[a-z0-9]+)*)")
    if not _nonempty_str(task.get("title")):
        errors.append(f"{where}: task.title must be a non-empty string")
    if task.get("category") not in CATEGORIES:
        errors.append(f"{where}: task.category must be one of {list(CATEGORIES)}")
    if task.get("complexity") not in COMPLEXITIES:
        errors.append(f"{where}: task.complexity must be one of {list(COMPLEXITIES)}")
    if not _str_list(task.get("files_allowed"), nonempty=True):
        errors.append(f"{where}: task.files_allowed must be a non-empty list of paths")
    for key in ("current_behavior", "desired_behavior"):
        if not _nonempty_str(task.get(key)):
            errors.append(f"{where}: task.{key} must be a non-empty string")
    for key in ("out_of_scope", "acceptance"):
        if not _str_list(task.get(key), nonempty=True):
            errors.append(f"{where}: task.{key} must be a non-empty list of strings")
    if not _str_list(task.get("notes", []), nonempty=False):
        errors.append(f"{where}: task.notes must be a list of strings")

    cases = task.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append(f"{where}: task.cases must be a non-empty list")
    else:
        for j, case in enumerate(cases):
            if not (isinstance(case, dict)
                    and _nonempty_str(case.get("case"))
                    and _nonempty_str(case.get("source_of_truth"))):
                errors.append(
                    f"{where}: task.cases[{j}] must be {{\"case\": str, \"source_of_truth\": str}}"
                    " with non-empty strings")

    mutation = task.get("mutation_check")
    if disposition == "fix-test-only":
        if not _nonempty_str(mutation):
            errors.append(f"{where}: task.mutation_check must be a non-empty string "
                          "for a fix-test-only disposition")
    elif mutation is not None and not _nonempty_str(mutation):
        errors.append(f"{where}: task.mutation_check must be a string or null")

    return errors


def validate_triage(obj: object, finding_count: int) -> list[str]:
    """Every rule the prompt's output contract states, checked by hand.

    Returns a list of human-readable errors; empty means valid. The errors are
    fed back to the model verbatim on retry, so they name the exact field.
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["top level must be a JSON object"]

    dispositions = obj.get("dispositions")
    if not isinstance(dispositions, list) or not dispositions:
        errors.append("dispositions must be a non-empty list")
        dispositions = []

    seen: dict[int, int] = {}
    task_indexes: list[int] = []
    for i, item in enumerate(dispositions):
        where = f"dispositions[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: must be an object")
            continue

        findings = item.get("findings")
        if not isinstance(findings, list) or not findings:
            errors.append(f"{where}: findings must be a non-empty list of integers")
        else:
            for f in findings:
                if not isinstance(f, int) or isinstance(f, bool):
                    errors.append(f"{where}: findings contains a non-integer {f!r}")
                elif not 1 <= f <= finding_count:
                    errors.append(f"{where}: finding index {f} is out of range 1..{finding_count}")
                elif f in seen:
                    errors.append(f"{where}: finding {f} already appears in "
                                  f"dispositions[{seen[f]}]; each finding exactly once")
                else:
                    seen[f] = i

        disposition = item.get("disposition")
        if disposition not in DISPOSITIONS:
            errors.append(f"{where}: disposition must be one of {list(DISPOSITIONS)}")
        if not _nonempty_str(item.get("verified")):
            errors.append(f"{where}: verified must be a non-empty string saying what you read")
        if not _nonempty_str(item.get("rationale")):
            errors.append(f"{where}: rationale must be a non-empty string")

        has_task = "task" in item and item["task"] is not None
        if disposition in TASK_DISPOSITIONS:
            task_indexes.append(i)
            if not has_task:
                errors.append(f"{where}: disposition {disposition!r} requires a task")
            else:
                errors.extend(validate_task(item["task"], where, disposition))
        elif has_task:
            errors.append(f"{where}: disposition {disposition!r} must not carry a task")

    missing = sorted(set(range(1, finding_count + 1)) - set(seen))
    if missing:
        errors.append(f"findings {missing} appear in no disposition; every input finding "
                      "must be disposed of exactly once")

    order = obj.get("order")
    if not isinstance(order, list) or not all(
            isinstance(o, int) and not isinstance(o, bool) for o in order):
        errors.append("order must be a list of integers (0-based indexes into dispositions)")
    else:
        if sorted(order) != sorted(task_indexes):
            errors.append(
                f"order must list every fix/fix-test-only disposition index exactly once: "
                f"expected a permutation of {task_indexes}, got {order}")

    if not _nonempty_str(obj.get("summary")):
        errors.append("summary must be a non-empty string")

    # Slugs name files; two equal slugs would collide.
    slugs = [dispositions[i]["task"]["slug"] for i in task_indexes
             if isinstance(dispositions[i], dict) and isinstance(dispositions[i].get("task"), dict)
             and _nonempty_str(dispositions[i]["task"].get("slug"))]
    dupes = sorted({s for s in slugs if slugs.count(s) > 1})
    if dupes:
        errors.append(f"task slugs must be unique; duplicated: {dupes}")

    return errors


# ---------------------------------------------------------------------------
# Task rendering
# ---------------------------------------------------------------------------

def finding_paths(findings: list[dict], indexes: list[int]) -> list[str]:
    """The repository paths a set of findings cite, deduplicated, in order."""
    paths: list[str] = []
    for i in indexes:
        if not 1 <= i <= len(findings):
            continue
        match = FILE_PATH_RE.match(str(findings[i - 1].get("file", "")))
        if match:
            path = match.group(1).replace("\\", "/")
            if path not in paths:
                paths.append(path)
    return paths


def _code_list(items: list[str]) -> str:
    quoted = [f"`{p}`" for p in items]
    if len(quoted) <= 1:
        return "".join(quoted)
    return ", ".join(quoted[:-1]) + f" and {quoted[-1]}"


def _bullets(items: list[str], marker: str = "-") -> str:
    return "\n".join(f"{marker} {item.strip()}" for item in items if item.strip())


def render_task(task: dict, *, disposition: str, task_id: str, repo: str, verify: str,
                base: str, branch: str, findings_cited: list[int],
                implementation_files: list[str], baseline: str | None = None) -> str:
    """Render one task in the evaluation/task-template.md shape.

    Deliberately close to the hand-written f02-fix-* tasks: the bounded opening
    line, the scope sentence, the cases table with a source of truth, and for a
    test-only task the mutation self-check and the "do not modify the
    implementation" line -- the things E8 showed the worker obeys when told and
    never infers when not told.
    """
    test_only = disposition == "fix-test-only"
    files = list(task["files_allowed"])
    verify_line = f"`{verify}` passes" if verify else "the test suite passes"
    baseline_text = (
        f"Baseline on this branch is **{baseline}**, so any other failure is a regression."
        if baseline else
        f"The suite is green on `{base}`, so any failure you see is one you introduced."
    )

    lines = [
        "---",
        f"id: {task_id}",
        f"repo: {repo}",
        f"category: {task['category']}",
        f"complexity: {task['complexity']}",
    ]
    if verify:
        lines.append(f"verify: {verify}")
    lines += [
        f"base: {base}",
        f"branch: {branch}",
        "---",
        "",
        f"# Task: {task['title'].strip()}",
        "",
    ]
    if len(files) == 1:
        lines.append(f"**Edit {_code_list(files)} only.**")
    else:
        lines.append(f"**Edit {_code_list(files)}. Nothing else.**")
    lines.append("")
    if test_only:
        lines.append("**The implementation is already correct. Do not change it.** This task adds "
                     "the test that holds that true.")
    else:
        lines.append("This is a single, bounded fix. Do not refactor, do not improve anything the "
                     "task does not name, and do not address any other review finding.")
    lines += [
        "",
        "## Current behavior",
        "",
        task["current_behavior"].strip(),
        "",
        "## Desired behavior",
        "",
        task["desired_behavior"].strip(),
        "",
        "## Out of scope",
        "",
    ]
    out_of_scope = list(task["out_of_scope"])
    if test_only:
        # The guard below says this already; drop the model's own phrasing of it
        # so the section does not say the same thing twice.
        out_of_scope = [
            item for item in out_of_scope
            if not (item.lower().lstrip("* ").startswith("do not")
                    and any(path in item for path in implementation_files))
        ]
        named = (_code_list(implementation_files) if implementation_files
                 else "any file other than those named above")
        guard = (f"**Do not modify {named} at all.** If you believe the implementation needs "
                 "changing, you have misread the task -- the fix here is a test.")
        out_of_scope.insert(0, guard)
    if not any("other review finding" in item or "other finding" in item for item in out_of_scope):
        out_of_scope.append("Do not address any other review finding, however tempting.")
    lines.append(_bullets(out_of_scope))
    lines += [
        "",
        "## Cases the tests must cover",
        "",
        "| Case | Source of truth for the assertion |",
        "| --- | --- |",
    ]
    for case in task["cases"]:
        c = " ".join(case["case"].split()).replace("|", "\\|")
        s = " ".join(case["source_of_truth"].split()).replace("|", "\\|")
        lines.append(f"| {c} | {s} |")
    lines += ["", "## Acceptance criteria", ""]

    acceptance = [a for a in task["acceptance"] if a.strip()]
    if test_only:
        mutation = task["mutation_check"].strip()
        acceptance.append(
            f"The new test **fails** if you {mutation}. Verify this yourself: make that change, "
            "watch the test fail, then restore the source exactly. Say in your summary that you "
            "did, and quote the failure.")
        if implementation_files:
            acceptance.append(
                f"`git status` shows {_code_list(implementation_files)} unmodified when you finish.")
    if not verify or not any(verify in a for a in acceptance):
        acceptance.append(f"{verify_line} -- the whole suite, not only the new tests. {baseline_text}")
    else:
        acceptance.append(baseline_text)
    acceptance.append("Return a concise summary of what was modified and anything left unresolved.")
    lines.append(_bullets(acceptance, marker="- [ ]"))

    notes = [n for n in task.get("notes", []) if n.strip()]
    notes.append("Generated by triage from review finding(s) "
                 + ", ".join(str(i) for i in findings_cited) + ".")
    lines += ["", "## Notes", "", _bullets(notes), ""]
    return "\n".join(lines)


def plan_tasks(triage: dict, *, findings: list[dict], prefix: str, spec_meta: dict[str, str],
               reviewed_branch: str, baseline: str | None = None) -> list[dict]:
    """Chain the accepted dispositions into task files, in `order`.

    fix-01 is based on the reviewed branch; fix-02 on fix-01's branch; and so
    on. Each task therefore sees the previous fix's tests, and the last branch
    carries every fix.
    """
    planned: list[dict] = []
    base = reviewed_branch
    for n, disp_index in enumerate(triage["order"], start=1):
        item = triage["dispositions"][disp_index]
        task = item["task"]
        number = f"{n:02d}"
        task_id = f"{prefix}-fix-{number}-{task['slug']}"
        branch = f"worker/{prefix}-fix-{number}"
        cited = list(item["findings"])
        impl = [p for p in finding_paths(findings, cited) if p not in task["files_allowed"]]
        content = render_task(
            task, disposition=item["disposition"], task_id=task_id,
            repo=spec_meta.get("repo", ""), verify=spec_meta.get("verify", ""),
            base=base, branch=branch, findings_cited=cited,
            implementation_files=impl,
            # Only the first task inherits the measured baseline; every later one
            # starts from whatever the previous fix left green.
            baseline=baseline if n == 1 else None,
        )
        planned.append({
            "path": TASKS_DIR / f"{task_id}.md",
            "id": task_id,
            "branch": branch,
            "base": base,
            "disposition": item["disposition"],
            "findings": cited,
            "content": content,
        })
        base = branch
    return planned


def render_triage_table(triage: dict, planned: list[dict]) -> str:
    """A human-readable summary of the dispositions, for triage.md."""
    task_for_index = {}
    for n, disp_index in enumerate(triage["order"], start=1):
        task_for_index[disp_index] = planned[n - 1]["id"] if n - 1 < len(planned) else f"task {n}"

    def cell(text: str) -> str:
        return " ".join(str(text).split()).replace("|", "\\|")

    lines = [
        "# Triage",
        "",
        cell(triage.get("summary", "")),
        "",
        "| # | Findings | Disposition | Task | Verified | Rationale |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for i, item in enumerate(triage["dispositions"]):
        findings = "+".join(str(f) for f in item["findings"])
        task = task_for_index.get(i, "")
        lines.append(
            f"| {i} | {findings} | **{item['disposition']}** | {task} | "
            f"{cell(item['verified'])} | {cell(item['rationale'])} |")
    lines += ["", "## Execution order", ""]
    for n, p in enumerate(planned, start=1):
        lines.append(f"{n}. `{p['path'].name}` -- base `{p['base']}`, branch `{p['branch']}` "
                     f"({p['disposition']}, findings {'+'.join(map(str, p['findings']))})")
    dropped = [(i, d) for i, d in enumerate(triage["dispositions"])
               if d["disposition"] in ("drop", "defer")]
    if dropped:
        lines += ["", "## Not converted", ""]
        for i, d in dropped:
            lines.append(f"- findings {'+'.join(map(str, d['findings']))}: **{d['disposition']}** "
                         f"-- {cell(d['rationale'])}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Frontier invocation
# ---------------------------------------------------------------------------

def _resolve(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise TaskError(f"'{name}' not found on PATH")
    return found


def frontier_command(frontier: str, worktree: Path, model: str | None,
                     extra_dirs: list[Path] | None = None) -> tuple[list[str] | str, bool]:
    """Return (command, use_shell) for the chosen frontier.

    The prompt is never part of the command: it is written to stdin by the
    caller. `--tools Read,Grep,Glob` restricts claude to reading; `--sandbox
    read-only` does the same for codex. A `cmd:` template is trusted as given.
    """
    if frontier == "claude":
        cmd = [
            _resolve("claude"), "-p",
            "--output-format", "text",
            "--tools", "Read,Grep,Glob",
            "--permission-mode", "dontAsk",
            "--no-session-persistence",
        ]
        for extra in extra_dirs or []:
            cmd += ["--add-dir", str(extra)]
        if model:
            cmd += ["--model", model]
        return cmd, False
    if frontier == "codex":
        cmd = [_resolve("codex"), "exec", "--sandbox", "read-only", "-C", str(worktree)]
        if model:
            cmd += ["-m", model]
        cmd.append("-")
        return cmd, False
    if frontier.startswith("cmd:"):
        template = frontier[len("cmd:"):].strip()
        if not template:
            raise TaskError("cmd: frontier needs a command template after the colon")
        rendered = template.replace("{worktree}", str(worktree)).replace("{model}", model or "")
        return rendered, True
    raise TaskError(f"unknown frontier {frontier!r}")


def invoke_frontier(cmd: list[str] | str, use_shell: bool, prompt: str, cwd: Path,
                    timeout: int) -> dict:
    """Run the frontier once with the prompt on stdin; capture its stdout."""
    env = dict(os.environ)
    # A nested Claude Code launch inherits the parent's session markers and may
    # refuse to start or attach itself to the parent's session. Strip them.
    for key in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT"):
        env.pop(key, None)

    started = time.monotonic()
    timed_out = False
    process = subprocess.Popen(
        cmd, cwd=cwd, shell=use_shell,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", env=env,
    )
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        timed_out = True
    return {
        "stdout": stdout or "",
        "stderr_tail": (stderr or "").strip()[-4000:],
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }


def command_for_record(cmd: list[str] | str) -> str:
    if isinstance(cmd, str):
        return cmd
    return " ".join(shlex.quote(c) for c in cmd)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--findings", type=Path, required=True,
                        help="findings.json written by aggregate_findings.py")
    parser.add_argument("--spec", type=Path, required=True,
                        help="the task file the reviewed branch answered")
    parser.add_argument("--branch", required=True, help="the reviewed branch")
    parser.add_argument("--base", default=None,
                        help="diff base; defaults to the spec frontmatter. Needed once the branch "
                             "has been merged and the spec base no longer differs from it")
    parser.add_argument("--id", required=True, help="names the run directory")
    parser.add_argument("--frontier", required=True,
                        help="claude | codex | cmd:<shell template, prompt on stdin>")
    parser.add_argument("--repo", type=Path, default=Path(r"C:\Dev\homelab"))
    parser.add_argument("--model", default=None, help="passed through to the frontier CLI")
    parser.add_argument("--timeout", type=int, default=1800, help="per attempt, seconds")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--task-prefix", default=None,
                        help="prefix for generated task ids/files; defaults to the spec's id")
    parser.add_argument("--baseline", default=None,
                        help="the suite's current result on the reviewed branch, e.g. "
                             "'172 passed, ruff clean'; rendered into every task")
    parser.add_argument("--findings-only", action="store_true",
                        help="withhold the diff; the model verifies findings by reading the branch")
    parser.add_argument("--force", action="store_true",
                        help="overwrite existing task files with the same names")
    args = parser.parse_args()

    run_dir = RUNS_DIR / args.id
    if run_dir.exists():
        print(f"ERROR: {run_dir} already exists; use a new id.", file=sys.stderr)
        return 2
    if args.max_attempts < 1:
        print("ERROR: --max-attempts must be at least 1", file=sys.stderr)
        return 2

    repo = args.repo.resolve()
    meta, spec_body = parse_task(args.spec)
    base = args.base or meta.get("base", "experiment/74-local-llm-worker")
    prefix = args.task_prefix or meta["id"]

    payload = json.loads(args.findings.read_text(encoding="utf-8-sig"))
    findings = payload.get("findings") if isinstance(payload, dict) else payload
    if not isinstance(findings, list) or not findings:
        print(f"ERROR: {args.findings} holds no findings.", file=sys.stderr)
        return 2

    if not TRIAGE_PROMPT.is_file():
        print(f"ERROR: no prompt at {TRIAGE_PROMPT}", file=sys.stderr)
        return 2

    # Refuse early rather than after a multi-minute frontier run.
    existing = sorted(TASKS_DIR.glob(f"{prefix}-fix-[0-9][0-9]-*.md"))
    if existing and not args.force:
        print(f"ERROR: task files with prefix {prefix!r} already exist; pass --task-prefix "
              f"or --force:", file=sys.stderr)
        for path in existing:
            print(f"  {path}", file=sys.stderr)
        return 2

    diff = git(repo, "diff", f"{base}...{args.branch}")
    if not diff.strip():
        print(f"ERROR: {base}...{args.branch} is an empty diff; nothing to triage.",
              file=sys.stderr)
        return 2

    worktree = repo.parent / "homelab-worktrees" / f"triage-{args.id}"
    if worktree.exists():
        print(f"ERROR: {worktree} already exists.", file=sys.stderr)
        return 2

    run_dir.mkdir(parents=True)
    write_started(run_dir, "triage", args.id, f"Triage of {args.branch} ({args.frontier})",
                  pipeline=pipeline_of(meta["id"]), branch=args.branch, frontier=args.frontier)
    diff_path = (run_dir / "under-triage.patch").resolve()
    diff_path.write_text(diff, encoding="utf-8")

    instructions = TRIAGE_PROMPT.read_text(encoding="utf-8")
    prompt = build_prompt(instructions, spec_body, findings, base, args.branch, diff, diff_path,
                          findings_only=args.findings_only)
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    git(repo, "worktree", "add", "--detach", str(worktree), args.branch)
    print(f"triage  : {args.id}")
    print(f"branch  : {args.branch} (base {base})")
    print(f"worktree: {worktree}")
    print(f"frontier: {args.frontier}" + (f" ({args.model})" if args.model else ""))
    print(f"findings: {len(findings)}")
    print(f"prompt  : {len(prompt)} chars")
    print()

    cmd, use_shell = frontier_command(args.frontier, worktree, args.model,
                                      extra_dirs=[run_dir.resolve()])
    record: dict = {
        "triage_id": args.id,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "branch": args.branch,
        "base": base,
        "spec": str(args.spec),
        "findings_file": str(args.findings),
        "findings_count": len(findings),
        "findings_only": args.findings_only,
        "frontier": args.frontier,
        "model": args.model,
        "command": command_for_record(cmd),
        "task_prefix": prefix,
        "attempts": [],
        "valid": False,
    }
    triage = None
    current_prompt = prompt
    started = time.monotonic()
    try:
        for attempt in range(1, args.max_attempts + 1):
            print(f"attempt {attempt}/{args.max_attempts}...")
            result = invoke_frontier(cmd, use_shell, current_prompt, worktree, args.timeout)
            raw_path = run_dir / f"raw-attempt-{attempt}.txt"
            raw_path.write_text(result["stdout"], encoding="utf-8")
            print(f"  {result['elapsed_seconds']}s, exit {result['exit_code']}"
                  + (", TIMED OUT" if result["timed_out"] else ""))

            errors: list[str]
            try:
                candidate = parse_triage_output(result["stdout"])
                errors = validate_triage(candidate, len(findings))
            except TriageOutputError as error:
                candidate = None
                errors = [str(error)]
            if result["stderr_tail"] and not result["stdout"].strip():
                errors.append(f"frontier wrote nothing to stdout; stderr: {result['stderr_tail']}")

            record["attempts"].append({
                "attempt": attempt,
                "elapsed_seconds": result["elapsed_seconds"],
                "exit_code": result["exit_code"],
                "timed_out": result["timed_out"],
                "raw_output": raw_path.name,
                "errors": errors,
                "stderr_tail": result["stderr_tail"],
            })
            if not errors:
                triage = candidate
                break
            print(f"  rejected ({len(errors)} problem(s)):")
            for e in errors:
                print(f"    - {e}")
            if attempt < args.max_attempts:
                current_prompt = prompt + rejection_suffix(result["stdout"], errors)
                (run_dir / f"prompt-attempt-{attempt + 1}.txt").write_text(
                    current_prompt, encoding="utf-8")

        record["elapsed_seconds"] = round(time.monotonic() - started, 1)
        # Stamped when the triage *ends*, like every other runner; the status
        # page computes finished durations as recorded_at - started_at, and the
        # first f03 triage showed as 0:01 because this was set at the start.
        record["recorded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # The frontier was told not to touch anything, and its tool set should
        # have made that impossible. Check anyway: a triage that edited the
        # code under triage has contaminated the evidence.
        dirty = git(worktree, "status", "--porcelain").strip()
        record["frontier_modified_worktree"] = bool(dirty)
        if dirty:
            (run_dir / "frontier-changes.patch").write_text(git(worktree, "diff"),
                                                             encoding="utf-8")
            record["worktree_status"] = dirty
            (run_dir / "triage.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            print("ERROR: the frontier modified the worktree:", file=sys.stderr)
            print("  " + dirty.replace("\n", "\n  "), file=sys.stderr)
            return 3
    finally:
        git(repo, "worktree", "remove", "--force", str(worktree), check=False)
        git(repo, "worktree", "prune", check=False)

    if triage is None:
        (run_dir / "triage.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"\nERROR: no valid triage after {args.max_attempts} attempt(s); "
              f"nothing written to {TASKS_DIR}.", file=sys.stderr)
        print(f"recorded: {run_dir}", file=sys.stderr)
        return 1

    planned = plan_tasks(triage, findings=findings, prefix=prefix, spec_meta=meta,
                         reviewed_branch=args.branch, baseline=args.baseline)
    collisions = [p["path"] for p in planned if p["path"].exists()]
    if collisions and not args.force:
        record["collisions"] = [str(c) for c in collisions]
        (run_dir / "triage.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print("ERROR: refusing to overwrite existing task files (pass --force):", file=sys.stderr)
        for c in collisions:
            print(f"  {c}", file=sys.stderr)
        return 2

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    for p in planned:
        p["path"].write_text(p["content"], encoding="utf-8")

    record["valid"] = True
    record["triage"] = triage
    record["tasks"] = [
        {"id": p["id"], "file": str(p["path"]), "base": p["base"], "branch": p["branch"],
         "disposition": p["disposition"], "findings": p["findings"]}
        for p in planned
    ]
    (run_dir / "triage.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    table = render_triage_table(triage, planned)
    (run_dir / "triage.md").write_text(table, encoding="utf-8")

    print()
    print(f"valid after {len(record['attempts'])} attempt(s); {len(planned)} task(s):")
    for n, p in enumerate(planned, start=1):
        print(f"  {n}. {p['path'].relative_to(REPO_ROOT)}  [{p['disposition']}, "
              f"findings {'+'.join(map(str, p['findings']))}]  {p['base']} -> {p['branch']}")
    not_converted = [d for d in triage["dispositions"] if d["disposition"] in ("drop", "defer")]
    if not_converted:
        print("not converted:")
        for d in not_converted:
            print(f"  {d['disposition']:5} findings {'+'.join(map(str, d['findings']))}: "
                  f"{' '.join(d['rationale'].split())}")
    print()
    print(f"recorded: {run_dir}")
    print("Read the generated tasks before running any of them; triage is a model's judgement.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TaskError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
