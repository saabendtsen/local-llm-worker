"""Unit tests for scripts/run_triage.py: parsing, validation, task rendering.

No network, no CLI calls, no git. The frontier invocation is not exercised here;
what is tested is everything the script decides on its own -- which is where a
quiet failure would otherwise hide.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_triage  # noqa: E402
from run_triage import (  # noqa: E402
    TriageOutputError,
    build_prompt,
    extract_json_block,
    finding_paths,
    format_findings,
    frontier_command,
    parse_triage_output,
    plan_tasks,
    rejection_suffix,
    render_task,
    render_triage_table,
    validate_triage,
)

FINDINGS = [
    {"source": "rv-errors", "axis": "error-paths", "file": "scripts/x.py:865",
     "severity": "high", "confidence": "verified",
     "problem": "crash on non-dict run.json", "repro": "python scripts/x.py history"},
    {"source": "rv-coverage", "axis": "missing-coverage",
     "file": "scripts/x.py, `list_runs()` read-only behaviour",
     "severity": "high", "confidence": "verified", "gap": "no read-only test"},
    {"source": "rv-tests", "axis": "test-strength", "file": "tests/test_x.py:570-584",
     "severity": "medium", "confidence": "verified", "problem": "limit+state untested"},
    {"source": "rv-consistency", "axis": "consistency", "file": "scripts/x.py:472",
     "severity": "low", "confidence": "suspected", "problem": "json decimal width"},
]

SPEC_META = {
    "id": "f99-thing",
    "repo": r"C:\Dev\homelab",
    "category": "feature-medium",
    "verify": "python -m ruff check scripts tests && python -m pytest -q",
    "base": "experiment/base",
    "branch": "worker/f99-thing",
}


def fix_task(**overrides) -> dict:
    task = {
        "slug": "nondict-runjson",
        "title": "handle a run.json that is not an object",
        "category": "bugfix",
        "complexity": "small",
        "files_allowed": ["scripts/x.py", "tests/test_x.py"],
        "current_behavior": "`list_runs` raises `AttributeError` at scripts/x.py:865.",
        "desired_behavior": "The run is reported as unreadable; exit code 0.",
        "out_of_scope": ["Do not change the sort order."],
        "cases": [
            {"case": "run.json containing `[1, 2, 3]`",
             "source_of_truth": "the sentinel the truncated-JSON test asserts"},
        ],
        "acceptance": ["Every case above passes."],
        "notes": ["Follow the module's conventions."],
        "mutation_check": None,
    }
    task.update(overrides)
    return task


def make_test_only_task(**overrides) -> dict:
    task = fix_task(
        slug="limit-state-ordering-test",
        title="pin the --state before --limit ordering",
        category="tests",
        files_allowed=["tests/test_x.py"],
        current_behavior="scripts/x.py:902-904 filters before slicing; nothing pins it.",
        desired_behavior="A test that fails if the order is swapped.",
        out_of_scope=["Do not change existing tests except to add to the file."],
        cases=[{"case": "--state failed --limit 1 over 2 completed + 2 failed",
                "source_of_truth": "the newest failed run id literal"}],
        acceptance=["The new test passes."],
        notes=[],
        mutation_check="swap the `if states:` block and the `if limit is not None:` slice "
                       "in `list_runs`",
    )
    task.update(overrides)
    return task


def valid_triage() -> dict:
    return {
        "dispositions": [
            {"findings": [1], "disposition": "fix",
             "verified": "scripts/x.py:865 calls .get() after json.loads().",
             "rationale": "Real crash.", "task": fix_task()},
            {"findings": [2, 3], "disposition": "fix-test-only",
             "verified": "scripts/x.py:902-904 filters before slicing.",
             "rationale": "Correct but unpinned.", "task": make_test_only_task()},
            {"findings": [4], "disposition": "drop",
             "verified": "scripts/x.py:472 rounds to 3 places.",
             "rationale": "JSON has no decimal width."},
        ],
        "order": [0, 1],
        "summary": "Two tasks, one drop.",
    }


def fenced(obj: object, tag: str = "json") -> str:
    return f"```{tag}\n{json.dumps(obj, indent=2)}\n```"


class ExtractJsonBlockTests(unittest.TestCase):
    def test_single_block_is_returned(self):
        text = "Some preamble.\n\n```json\n{\"a\": 1}\n```\n\nDone."
        self.assertEqual(extract_json_block(text), '{"a": 1}')

    def test_crlf_fence_is_accepted(self):
        text = "```json\r\n{\"a\": 1}\r\n```\r\n"
        self.assertEqual(extract_json_block(text), '{"a": 1}')

    def test_no_block_raises(self):
        with self.assertRaises(TriageOutputError) as ctx:
            extract_json_block("just prose, no fence")
        self.assertIn("no ```json", str(ctx.exception))

    def test_two_blocks_raise(self):
        text = "```json\n{}\n```\n\n```json\n{}\n```"
        with self.assertRaises(TriageOutputError) as ctx:
            extract_json_block(text)
        self.assertIn("found 2", str(ctx.exception))

    def test_untagged_fence_is_not_a_json_block(self):
        with self.assertRaises(TriageOutputError):
            extract_json_block("```\n{}\n```")

    def test_empty_output_raises(self):
        with self.assertRaises(TriageOutputError):
            extract_json_block("")


class ParseTriageOutputTests(unittest.TestCase):
    def test_parses_object(self):
        obj = parse_triage_output("ok\n" + fenced(valid_triage()))
        self.assertEqual(obj["order"], [0, 1])

    def test_invalid_json_names_the_parse_error(self):
        with self.assertRaises(TriageOutputError) as ctx:
            parse_triage_output("```json\n{\"a\": 1,}\n```")
        self.assertIn("does not parse", str(ctx.exception))

    def test_non_object_is_rejected(self):
        with self.assertRaises(TriageOutputError) as ctx:
            parse_triage_output("```json\n[1, 2]\n```")
        self.assertIn("single object", str(ctx.exception))


class ValidateTriageTests(unittest.TestCase):
    def assertErrors(self, obj, *fragments, count=4):
        errors = validate_triage(obj, count)
        self.assertTrue(errors, "expected validation errors, got none")
        joined = "\n".join(errors)
        for fragment in fragments:
            self.assertIn(fragment, joined)
        return errors

    def test_valid_object_has_no_errors(self):
        self.assertEqual(validate_triage(valid_triage(), 4), [])

    def test_missing_finding_is_reported(self):
        obj = valid_triage()
        obj["dispositions"][2]["findings"] = [4]
        obj["dispositions"][1]["findings"] = [2]  # 3 now disposed of nowhere
        self.assertErrors(obj, "findings [3] appear in no disposition")

    def test_duplicate_finding_is_reported(self):
        obj = valid_triage()
        obj["dispositions"][2]["findings"] = [4, 1]
        self.assertErrors(obj, "finding 1 already appears in dispositions[0]")

    def test_out_of_range_finding_is_reported(self):
        obj = valid_triage()
        obj["dispositions"][2]["findings"] = [4, 9]
        self.assertErrors(obj, "finding index 9 is out of range 1..4")

    def test_non_integer_finding_is_reported(self):
        obj = valid_triage()
        obj["dispositions"][2]["findings"] = ["4"]
        self.assertErrors(obj, "non-integer", "findings [4] appear in no disposition")

    def test_unknown_disposition(self):
        obj = valid_triage()
        obj["dispositions"][2]["disposition"] = "ignore"
        self.assertErrors(obj, "disposition must be one of")

    def test_drop_must_not_carry_task(self):
        obj = valid_triage()
        obj["dispositions"][2]["task"] = fix_task()
        self.assertErrors(obj, "'drop' must not carry a task")

    def test_defer_must_not_carry_task(self):
        obj = valid_triage()
        obj["dispositions"][2]["disposition"] = "defer"
        obj["dispositions"][2]["task"] = fix_task()
        self.assertErrors(obj, "'defer' must not carry a task")

    def test_fix_requires_task(self):
        obj = valid_triage()
        del obj["dispositions"][0]["task"]
        self.assertErrors(obj, "'fix' requires a task")

    def test_fix_with_null_task_is_missing(self):
        obj = valid_triage()
        obj["dispositions"][0]["task"] = None
        self.assertErrors(obj, "'fix' requires a task")

    def test_verified_and_rationale_required(self):
        obj = valid_triage()
        obj["dispositions"][0]["verified"] = "  "
        del obj["dispositions"][1]["rationale"]
        self.assertErrors(obj, "dispositions[0]: verified", "dispositions[1]: rationale")

    def test_test_only_requires_mutation_check(self):
        obj = valid_triage()
        obj["dispositions"][1]["task"]["mutation_check"] = None
        self.assertErrors(obj, "mutation_check must be a non-empty string for a fix-test-only")

    def test_fix_allows_null_or_absent_mutation_check(self):
        obj = valid_triage()
        del obj["dispositions"][0]["task"]["mutation_check"]
        self.assertEqual(validate_triage(obj, 4), [])
        obj["dispositions"][0]["task"]["mutation_check"] = None
        self.assertEqual(validate_triage(obj, 4), [])

    def test_fix_rejects_non_string_mutation_check(self):
        obj = valid_triage()
        obj["dispositions"][0]["task"]["mutation_check"] = 3
        self.assertErrors(obj, "mutation_check must be a string or null")

    def test_slug_must_be_kebab_case(self):
        for bad in ("Has Caps", "under_score", "-leading", "trailing-", "double--dash", ""):
            with self.subTest(slug=bad):
                obj = valid_triage()
                obj["dispositions"][0]["task"]["slug"] = bad
                self.assertErrors(obj, "task.slug must be kebab-case")

    def test_duplicate_slugs_rejected(self):
        obj = valid_triage()
        obj["dispositions"][1]["task"]["slug"] = "nondict-runjson"
        self.assertErrors(obj, "task slugs must be unique")

    def test_category_and_complexity_enums(self):
        obj = valid_triage()
        obj["dispositions"][0]["task"]["category"] = "feature"
        obj["dispositions"][0]["task"]["complexity"] = "large"
        self.assertErrors(obj, "task.category must be one of", "task.complexity must be one of")

    def test_files_allowed_nonempty(self):
        obj = valid_triage()
        obj["dispositions"][0]["task"]["files_allowed"] = []
        self.assertErrors(obj, "files_allowed must be a non-empty list")

    def test_cases_shape(self):
        obj = valid_triage()
        obj["dispositions"][0]["task"]["cases"] = [{"case": "x"}]
        self.assertErrors(obj, "task.cases[0] must be")
        obj["dispositions"][0]["task"]["cases"] = []
        self.assertErrors(obj, "task.cases must be a non-empty list")

    def test_string_lists(self):
        obj = valid_triage()
        obj["dispositions"][0]["task"]["out_of_scope"] = "not a list"
        obj["dispositions"][0]["task"]["acceptance"] = []
        obj["dispositions"][0]["task"]["notes"] = [1]
        self.assertErrors(obj, "task.out_of_scope must be", "task.acceptance must be",
                          "task.notes must be")

    def test_notes_may_be_absent(self):
        obj = valid_triage()
        del obj["dispositions"][0]["task"]["notes"]
        self.assertEqual(validate_triage(obj, 4), [])

    def test_order_must_be_permutation_of_task_indexes(self):
        obj = valid_triage()
        obj["order"] = [0]
        self.assertErrors(obj, "order must list every fix/fix-test-only")
        obj["order"] = [0, 1, 2]
        self.assertErrors(obj, "order must list every fix/fix-test-only")
        obj["order"] = [1, 1]
        self.assertErrors(obj, "order must list every fix/fix-test-only")
        obj["order"] = [1, 0]
        self.assertEqual(validate_triage(obj, 4), [])

    def test_order_must_be_integers(self):
        obj = valid_triage()
        obj["order"] = ["0", "1"]
        self.assertErrors(obj, "order must be a list of integers")

    def test_summary_required(self):
        obj = valid_triage()
        obj["summary"] = ""
        self.assertErrors(obj, "summary must be a non-empty string")

    def test_empty_dispositions(self):
        obj = valid_triage()
        obj["dispositions"] = []
        self.assertErrors(obj, "dispositions must be a non-empty list",
                          "findings [1, 2, 3, 4] appear in no disposition")

    def test_non_dict_top_level(self):
        self.assertEqual(validate_triage([], 4), ["top level must be a JSON object"])

    def test_booleans_are_not_finding_indexes(self):
        obj = valid_triage()
        obj["dispositions"][2]["findings"] = [True, 4]
        self.assertErrors(obj, "non-integer")


class RenderTaskTests(unittest.TestCase):
    def render_fix(self, **kw):
        return render_task(
            fix_task(), disposition="fix", task_id="f99-thing-fix-01-nondict-runjson",
            repo=r"C:\Dev\homelab", verify=SPEC_META["verify"],
            base="worker/f99-thing", branch="worker/f99-thing-fix-01",
            findings_cited=[1], implementation_files=[], **kw)

    def render_test_only(self, **kw):
        return render_task(
            make_test_only_task(), disposition="fix-test-only",
            task_id="f99-thing-fix-02-limit-state-ordering-test",
            repo=r"C:\Dev\homelab", verify=SPEC_META["verify"],
            base="worker/f99-thing-fix-01", branch="worker/f99-thing-fix-02",
            findings_cited=[2, 3], implementation_files=["scripts/x.py"], **kw)

    def test_frontmatter_round_trips_through_parse_task(self):
        from run_task import parse_task
        import tempfile
        content = self.render_fix()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.md"
            path.write_text(content, encoding="utf-8")
            meta, body = parse_task(path)
        self.assertEqual(meta["id"], "f99-thing-fix-01-nondict-runjson")
        self.assertEqual(meta["repo"], r"C:\Dev\homelab")
        self.assertEqual(meta["category"], "bugfix")
        self.assertEqual(meta["complexity"], "small")
        self.assertEqual(meta["verify"], SPEC_META["verify"])
        self.assertEqual(meta["base"], "worker/f99-thing")
        self.assertEqual(meta["branch"], "worker/f99-thing-fix-01")
        self.assertTrue(body.startswith("# Task: handle a run.json that is not an object"))

    def test_fix_task_has_template_sections_in_order(self):
        content = self.render_fix()
        headings = [line for line in content.splitlines() if line.startswith("## ")]
        self.assertEqual(headings, [
            "## Current behavior", "## Desired behavior", "## Out of scope",
            "## Cases the tests must cover", "## Acceptance criteria", "## Notes",
        ])

    def test_fix_task_is_bounded(self):
        content = self.render_fix()
        self.assertIn("**Edit `scripts/x.py` and `tests/test_x.py`. Nothing else.**", content)
        self.assertIn("do not address any other review finding", content)
        self.assertIn("Do not address any other review finding, however tempting.", content)
        self.assertIn("- Do not change the sort order.", content)

    def test_fix_task_cases_table_and_acceptance(self):
        content = self.render_fix()
        self.assertIn("| Case | Source of truth for the assertion |", content)
        self.assertIn("| run.json containing `[1, 2, 3]` | the sentinel the truncated-JSON test "
                      "asserts |", content)
        self.assertIn("- [ ] Every case above passes.", content)
        self.assertIn(f"- [ ] `{SPEC_META['verify']}` passes -- the whole suite", content)
        self.assertIn("- [ ] Return a concise summary", content)
        self.assertNotIn("mutation", content.lower().split("## acceptance criteria")[1]
                         .split("## notes")[0])
        self.assertIn("- Generated by triage from review finding(s) 1.", content)

    def test_baseline_is_rendered_when_given(self):
        content = self.render_fix(baseline="172 passed, ruff clean")
        self.assertIn("Baseline on this branch is **172 passed, ruff clean**", content)
        without = self.render_fix()
        self.assertIn("The suite is green on `worker/f99-thing`", without)

    def test_verify_acceptance_not_duplicated_when_model_already_names_it(self):
        task = fix_task(acceptance=[f"`{SPEC_META['verify']}` passes."])
        content = render_task(
            task, disposition="fix", task_id="x", repo="r", verify=SPEC_META["verify"],
            base="b", branch="w", findings_cited=[1], implementation_files=[])
        self.assertEqual(content.count(SPEC_META["verify"]), 2)  # frontmatter + the one item

    def test_test_only_task_forbids_touching_implementation(self):
        content = self.render_test_only()
        self.assertIn("**Edit `tests/test_x.py` only.**", content)
        self.assertIn("**The implementation is already correct. Do not change it.**", content)
        self.assertIn("**Do not modify `scripts/x.py` at all.**", content)
        self.assertIn("`git status` shows `scripts/x.py` unmodified when you finish.", content)

    def test_test_only_guard_is_not_duplicated_when_model_states_it(self):
        task = make_test_only_task(out_of_scope=["Do not modify scripts/x.py at all.",
                                                 "Do not change existing tests."])
        content = render_task(
            task, disposition="fix-test-only", task_id="x", repo="r", verify="v",
            base="b", branch="w", findings_cited=[2], implementation_files=["scripts/x.py"])
        self.assertEqual(content.count("Do not modify"), 1)
        self.assertIn("- Do not change existing tests.", content)

    def test_test_only_task_renders_mutation_self_check(self):
        content = self.render_test_only()
        self.assertIn("- [ ] The new test **fails** if you swap the `if states:` block and the "
                      "`if limit is not None:` slice in `list_runs`. Verify this yourself",
                      content)
        self.assertIn("quote the failure", content)

    def test_test_only_without_known_implementation_file_still_guards(self):
        content = render_task(
            make_test_only_task(), disposition="fix-test-only", task_id="x", repo="r", verify="v",
            base="b", branch="w", findings_cited=[2], implementation_files=[])
        self.assertIn("**Do not modify any file other than those named above at all.**",
                      content)
        self.assertNotIn("git status", content)

    def test_pipe_in_case_text_is_escaped(self):
        task = fix_task(cases=[{"case": "a | b", "source_of_truth": "c"}])
        content = render_task(
            task, disposition="fix", task_id="x", repo="r", verify="v", base="b", branch="w",
            findings_cited=[1], implementation_files=[])
        self.assertIn("| a \\| b | c |", content)


class PlanTasksTests(unittest.TestCase):
    def test_chain_follows_order_and_bases_each_on_previous(self):
        planned = plan_tasks(valid_triage(), findings=FINDINGS, prefix="f99-auto",
                             spec_meta=SPEC_META, reviewed_branch="worker/f99-thing")
        self.assertEqual([p["id"] for p in planned], [
            "f99-auto-fix-01-nondict-runjson",
            "f99-auto-fix-02-limit-state-ordering-test",
        ])
        self.assertEqual(planned[0]["base"], "worker/f99-thing")
        self.assertEqual(planned[0]["branch"], "worker/f99-auto-fix-01")
        self.assertEqual(planned[1]["base"], "worker/f99-auto-fix-01")
        self.assertEqual(planned[1]["branch"], "worker/f99-auto-fix-02")
        self.assertEqual(planned[0]["path"],
                         run_triage.TASKS_DIR / "f99-auto-fix-01-nondict-runjson.md")
        self.assertIn("base: worker/f99-auto-fix-01\nbranch: worker/f99-auto-fix-02",
                      planned[1]["content"])

    def test_reversed_order_is_honoured(self):
        triage = valid_triage()
        triage["order"] = [1, 0]
        planned = plan_tasks(triage, findings=FINDINGS, prefix="p", spec_meta=SPEC_META,
                             reviewed_branch="worker/f99-thing")
        self.assertEqual(planned[0]["id"], "p-fix-01-limit-state-ordering-test")
        self.assertEqual(planned[1]["id"], "p-fix-02-nondict-runjson")
        self.assertEqual(planned[1]["base"], "worker/p-fix-01")

    def test_implementation_files_derived_from_findings_minus_allowed(self):
        planned = plan_tasks(valid_triage(), findings=FINDINGS, prefix="p", spec_meta=SPEC_META,
                             reviewed_branch="worker/f99-thing")
        # test-only task cites findings 2 (scripts/x.py) and 3 (tests/test_x.py);
        # tests/test_x.py is allowed, so only scripts/x.py is guarded.
        self.assertIn("**Do not modify `scripts/x.py` at all.**", planned[1]["content"])
        self.assertNotIn("Do not modify `tests/test_x.py`", planned[1]["content"])

    def test_verify_copied_from_spec(self):
        planned = plan_tasks(valid_triage(), findings=FINDINGS, prefix="p", spec_meta=SPEC_META,
                             reviewed_branch="worker/f99-thing")
        for p in planned:
            self.assertIn(f"verify: {SPEC_META['verify']}\n", p["content"])
            self.assertIn(f"repo: {SPEC_META['repo']}\n", p["content"])


class FindingPathsTests(unittest.TestCase):
    def test_strips_line_numbers_and_prose(self):
        self.assertEqual(finding_paths(FINDINGS, [1, 2, 3, 4]),
                         ["scripts/x.py", "tests/test_x.py"])

    def test_backticks_and_backslashes(self):
        findings = [{"file": "`scripts\\wayfinder_autopilot.py`:12 something"}]
        self.assertEqual(finding_paths(findings, [1]), ["scripts/wayfinder_autopilot.py"])

    def test_out_of_range_ignored(self):
        self.assertEqual(finding_paths(FINDINGS, [0, 99]), [])


class PromptTests(unittest.TestCase):
    def test_findings_are_numbered_from_one(self):
        numbered = json.loads(format_findings(FINDINGS))
        self.assertEqual([f["index"] for f in numbered], [1, 2, 3, 4])
        self.assertEqual(numbered[0]["file"], "scripts/x.py:865")

    def test_findings_only_withholds_the_diff(self):
        prompt = build_prompt("INSTR", "SPEC", FINDINGS, "base", "br", "+added line",
                              Path("C:/run/under-triage.patch"), findings_only=True)
        self.assertNotIn("+added line", prompt)
        self.assertNotIn("under-triage.patch", prompt)
        self.assertIn("## No diff is provided", prompt)
        self.assertIn('"index": 1', prompt)

    def test_diff_is_inlined_when_small(self):
        prompt = build_prompt("INSTR", "SPEC", FINDINGS, "base", "br", "+added line",
                              Path("C:/run/under-triage.patch"))
        self.assertTrue(prompt.startswith("INSTR"))
        self.assertIn("## The task specification", prompt)
        self.assertIn("SPEC", prompt)
        self.assertIn('"index": 1', prompt)
        self.assertIn("```diff\n+added line\n```", prompt)
        self.assertNotIn("under-triage.patch", prompt)

    def test_diff_is_referenced_when_large(self):
        prompt = build_prompt("INSTR", "SPEC", FINDINGS, "base", "br", "x" * 500,
                              Path("C:/run/under-triage.patch"), max_inline=400)
        self.assertNotIn("```diff", prompt)
        self.assertIn("under-triage.patch", prompt)
        self.assertIn("git diff base...HEAD", prompt)

    def test_rejection_suffix_names_errors_and_echoes_output(self):
        suffix = rejection_suffix("RAW OUTPUT", ["order must be a list", "summary missing"])
        self.assertIn("Your previous output was rejected", suffix)
        self.assertIn("- order must be a list", suffix)
        self.assertIn("- summary missing", suffix)
        self.assertIn("RAW OUTPUT", suffix)
        self.assertIn("Emit the corrected JSON block only.", suffix)

    def test_rejection_suffix_truncates_long_output(self):
        suffix = rejection_suffix("a" * 100 + "TAIL", [], max_echo=10)
        self.assertIn("aaaaaaTAIL", suffix)
        self.assertNotIn("a" * 20, suffix)


class FrontierCommandTests(unittest.TestCase):
    def test_cmd_template_substitutes_and_uses_shell(self):
        cmd, shell = frontier_command("cmd:mytool --cwd {worktree} --m {model}",
                                      Path("C:/wt"), "gpt")
        self.assertTrue(shell)
        self.assertEqual(cmd, "mytool --cwd C:\\wt --m gpt")

    def test_cmd_template_without_model(self):
        cmd, _ = frontier_command("cmd:mytool {model}", Path("C:/wt"), None)
        self.assertEqual(cmd, "mytool ")

    def test_empty_cmd_template_rejected(self):
        from run_task import TaskError
        with self.assertRaises(TaskError):
            frontier_command("cmd:   ", Path("C:/wt"), None)

    def test_unknown_frontier_rejected(self):
        from run_task import TaskError
        with self.assertRaises(TaskError):
            frontier_command("gemini", Path("C:/wt"), None)

    def test_claude_command_is_read_only_and_prompt_free(self):
        original = run_triage.shutil.which
        run_triage.shutil.which = lambda name: f"C:/bin/{name}.cmd"
        try:
            cmd, shell = frontier_command("claude", Path("C:/wt"), "opus",
                                          extra_dirs=[Path("C:/run")])
        finally:
            run_triage.shutil.which = original
        self.assertFalse(shell)
        self.assertEqual(cmd[0], "C:/bin/claude.cmd")
        self.assertIn("-p", cmd)
        self.assertIn("--tools", cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(cmd[cmd.index("--model") + 1], "opus")
        self.assertEqual(cmd[cmd.index("--add-dir") + 1], str(Path("C:/run")))
        for forbidden in ("Edit", "Write", "Bash", "bypassPermissions"):
            self.assertNotIn(forbidden, " ".join(cmd))

    def test_codex_command_is_read_only_and_reads_stdin(self):
        original = run_triage.shutil.which
        run_triage.shutil.which = lambda name: f"C:/bin/{name}.cmd"
        try:
            cmd, shell = frontier_command("codex", Path("C:/wt"), None)
        finally:
            run_triage.shutil.which = original
        self.assertFalse(shell)
        self.assertEqual(cmd[cmd.index("--sandbox") + 1], "read-only")
        self.assertEqual(cmd[cmd.index("-C") + 1], "C:\\wt")
        self.assertEqual(cmd[-1], "-")
        self.assertNotIn("-m", cmd)


class TriageTableTests(unittest.TestCase):
    def test_table_lists_every_disposition_and_the_plan(self):
        triage = valid_triage()
        planned = plan_tasks(triage, findings=FINDINGS, prefix="p", spec_meta=SPEC_META,
                             reviewed_branch="worker/f99-thing")
        table = render_triage_table(triage, planned)
        self.assertIn("| 0 | 1 | **fix** | p-fix-01-nondict-runjson |", table)
        self.assertIn("| 1 | 2+3 | **fix-test-only** | p-fix-02-limit-state-ordering-test |",
                      table)
        self.assertIn("| 2 | 4 | **drop** |  |", table)
        self.assertIn("1. `p-fix-01-nondict-runjson.md` -- base `worker/f99-thing`", table)
        self.assertIn("- findings 4: **drop** -- JSON has no decimal width.", table)

    def test_original_is_not_mutated_by_planning(self):
        triage = valid_triage()
        before = copy.deepcopy(triage)
        plan_tasks(triage, findings=FINDINGS, prefix="p", spec_meta=SPEC_META,
                   reviewed_branch="worker/f99-thing")
        self.assertEqual(triage, before)


if __name__ == "__main__":
    unittest.main()
