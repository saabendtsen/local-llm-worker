# Pipeline design

The shape the evaluation has converged on, and the reasoning behind each step. Nothing here is
built yet beyond the review stage; this records the design so it survives the session that produced
it.

## The stages

```text
  Claude / frontier          local worker                      mechanical
  ─────────────────          ────────────                      ──────────
  write the task      ─────► implement                    ───► verify (tests)
                             ├─ N focused reviews  ◄────────── dedupe + sort
  triage findings     ◄──────┘
  into atomic tasks
        │
        └──────────────────► fix, one finding per cycle  ───► re-verify:
                                                               tests + the
                                                               finding's own
                                                               repro command
```

The division follows what has been measured, not what sounds tidy:

- **Judgement stays with the frontier model** — writing the specification, and triaging findings
  into ordered atomic tasks. E3 and E6 both showed the worker mischaracterises causes and produces
  plans that agree with themselves. A local planning step would emit a plausible-but-wrong plan
  that the implementer would then faithfully execute — two weak steps compounding, with nothing to
  catch it.
- **Volume goes to the worker** — implementing, and reviewing. E7 showed focused local reviewers
  finding defects a frontier generalist missed on the same diff.
- **Anything deterministic is done by neither** — running tests, deduplicating findings, sorting by
  severity, re-verifying a fix. A model should never be asked to decide something a script can
  compute.

## The frontier model is a pluggable component

**The pipeline owns the planning prompt and invokes the frontier model by CLI.** It is not a
Claude Code feature that happens to call some scripts; it is a pipeline that happens to call Claude
Code today, and might call Codex or a hosted DeepSeek tomorrow.

Consequences worth designing for now rather than discovering later:

1. **The planning prompt lives in `prompts/`**, beside the review prompts, versioned with
   everything else. Whatever drives the pipeline reads it from there. Nothing about the plan should
   depend on which agent happened to invoke it.

2. **The frontier model is selected like the harness is.** `run_task.py` already takes
   `--harness pi|little-coder`; the planning step takes an equivalent `--frontier` choice, each
   mapping to a command template. This workspace already has precedent — `scripts/codex-task.cmd`
   and `codex_task_server.py` delegate bounded work to Codex over SSH.

3. **The output contract has to be strict, and this is the hard part.** Different models format
   differently, and unlike the local worker there is no `json_schema` or GBNF grammar to constrain a
   hosted CLI's decoding. So the planning step must:
   - specify the output shape exactly in the prompt;
   - parse and *validate* the result rather than trusting it;
   - reject and retry with the validation error fed back, rather than accepting something
     malformed;
   - fail loudly instead of proceeding on a half-parsed plan.

   This is the same lesson as everything else in this project: a step that cannot fail loudly will
   fail quietly.

4. **Pluggability makes the frontier model measurable.** Once it is a flag, the same A/B that
   compared Pi against little-coder can compare Claude against Codex against DeepSeek on identical
   findings — and E6's lesson applies unchanged: **run a repeat arm**, because within-model variance
   has swamped between-model differences every single time it has been measured.

## Why one finding per cycle

Settled 2026-08-17: the batch size starts at one and opens as the worker earns trust.

Each finding from a focused review already contains a `repro` command — the exact invocation that
demonstrates the defect. **That command is the acceptance test for its own fix, for free.** So an
atomic fix task is:

- **Current behavior** — the finding's `problem` and `evidence`
- **Desired behavior** — what the repro should print instead
- **Verify** — the repro command, plus the full test suite
- **Out of scope** — everything the finding does not name

No judgement is required to build that task; it is a mechanical transformation of a structured
finding. The frontier model's triage decides *which* findings become tasks and in *what order* —
not how each is phrased.

## Two constraints on the fix step

- **A fix may only touch what its finding names.** A fix round with a free hand is another
  implementation round with none of the specification, and it re-opens every risk the review just
  closed.
- **Re-verify mechanically, never with a second full review.** Run the tests and the finding's repro
  command. E7 showed the variance is between *reviewers*, not between versions of the code — a
  second review after a fix re-rolls the dice rather than going deeper, and risks a fresh reviewer
  undoing what the previous fix deliberately introduced.

## Aggregating findings: union, not majority

From E7. Three reviewers over one identical diff produced three different reviews, and the subtlest
defect was found by exactly one of them. **Majority voting would have discarded the best finding in
the experiment.**

Majority voting is right when false positives are the problem. Across five reviews there were none.
So: take the union, and keep the frequency count as a display hint rather than a filter.

Mechanical preprocessing before the frontier model sees anything:

- deduplicate by `(file, line, axis)`;
- sort by severity, then confidence;
- drop `suspected` findings whose `evidence` field is empty — the prompt already says an empty
  evidence field demotes a finding, so this is enforcing a rule the reviewer was given;
- keep the repro command attached to each finding, since it becomes the acceptance test.

## Open questions

- How many focused reviewers, and on which axes? Three were run; error-paths alone found seven
  defects a frontier generalist missed. Adding axes is cheap.
- Do marginal findings need a filter? The error-paths reviewer reported three defects reachable
  only by calling private functions with malformed input. Real, but acting on them would add
  defensive code to helpers nobody misuses. Triage currently handles this by judgement; a severity
  floor might handle it mechanically.
- Does the frontier model need the diff, or only the findings? Findings-only is far cheaper and
  keeps the saving; whether triage quality survives it is untested.

---

# Proposed updates, after E7

## 1. Put a linter in `verify`, not in review

**Measured, not assumed.** Run against the worker's own output on `worker/f01-pi`, `ruff` default
rules instantly report:

```
report-migration-coverage.py:8:8   F401  `glob` imported but unused
test_migration_coverage.py:112:17  F841  Local variable `disp_sum` is assigned to but never used
```

Both were review findings. `disp_sum` was found by two of three generic reviewers and **none** of
the focused ones; `glob` was found by **nobody** — the generic reviewer caught the neighbouring
dead `LEGEND` constant and missed the unused import beside it.

A linter gets both in milliseconds, deterministically, every time. Three reviewers spent 10–18
minutes each and got them inconsistently.

The important part is **where** it goes: in the acceptance command, so the *implementing* worker
must pass it before a review ever runs. That turns a whole finding class into something the worker
fixes itself, and stops reviewers spending attention on lint.

`LEGEND` — an unused module-level constant — is not caught by any default rule, so a residual
dead-code gap remains. It is small, and not worth a reviewer.

The workspace currently has no lint config and exactly one pre-existing violation, so adoption is
close to free.

## 2. Replace the broad reviewer with focused ones

E7 measured 14 findings from three focused reviewers against 5 from three broad ones, on the same
diff. Proposed axes:

| Axis | Status | Why |
| --- | --- | --- |
| error-paths | **proven** — 10 findings, 15 cases run | Found 7 defects the frontier reviewer missed |
| consistency | **proven** — found the contradiction every broad reviewer but one missed | "Compute the same quantity two ways" is a procedure, not an insight |
| test-strength | **proven** — 7 mutations run, file restored | Proved by execution what the frontier review only asserted |
| **missing-coverage** | **new, untested** | The instructive E7 miss: `main()` has no test, the prompt listed absent coverage as a finding class, and the reviewer still spent every mutation on tests that exist |
| spec-compliance | untested standalone | Requirement-by-requirement against the spec |
| style / dead code | **drop** | The linter owns it, and does it better |

The general principle E7 established: **this model executes procedures well and has insights
rarely.** Every focused prompt that worked gave it a procedure — construct these eight inputs, check
these relations both ways, apply these mutations and record the result. Give it procedures.

Keep the honesty counters (`cases-tested`, `relations-checked`, `mutations-run`, `restored`). They
worked: no focused reviewer claimed an all-clear, and `mutations-run=7 restored=yes` is what makes a
zero-findings result trustworthy when it eventually happens.

## 3. Aggregate mechanically, and take the union

Union, never majority — E7's subtlest defect was found by exactly one reviewer of three, so majority
voting would have discarded the best finding in the experiment. Before the frontier model sees
anything:

- deduplicate by `(file, line, axis)`;
- sort by severity, then confidence;
- drop `suspected` findings with an empty `evidence` field — enforcing a rule the reviewer was
  already given;
- keep each finding's `repro` command attached; it becomes the acceptance test for its own fix.

## 4. Add a severity floor before auto-fix

Three of the error-path findings are reachable only by calling private functions directly with
malformed input. Real behaviours, not fabrications — but acting on them means adding defensive code
to helpers nobody misuses.

Triage currently handles this by judgement. A mechanical floor — only `severity: high` plus
`confidence: verified` becomes a task without review — would handle the common case and leave the
rest as advisory.

## 5. What stays as designed

One finding per cycle; the fix may only touch what its finding names; re-verify with tests, the
linter, and the finding's own `repro` command rather than a second review.
