# E7 scoring — local reviewer against the frontier answer key

Each E6 diff was reviewed in depth by a frontier reviewer working in an isolated worktree, with
findings verified by execution and mutation testing. Those lists are the answer key. The local
reviewer sees the same diff, the same spec, and a checkout — in a fresh context, having not written
the code.

Scoring is deliberately harsh on false positives and lenient on misses. A miss costs nothing; a
confident wrong finding that a pipeline then "fixes" costs working code.

---

## rv-f01-pi — reviewing `worker/f01-pi`

607 s, 35 turns, 44 tool calls (`bash` 38, `read` 6). Worktree unmodified. **3 errored turns.**
Reported 3 findings, all `verified`, none `blocking`.

### Answer key vs. what it found

| # | Frontier finding | Class | Local reviewer |
| --- | --- | --- | --- |
| 1 | Traceback on malformed/unreadable JSON — violates an explicit spec constraint | **defect** | **miss** |
| 2 | `total_decided` and per-kind `decided_count` contradict each other when a disposition is invalid | **defect** | **miss** |
| 3 | No de-duplication of ledger sources — 101 phantom duplicate anomalies | **defect** | **miss** |
| 4 | `main()` never exercised by any test | **defect** | **miss** |
| 5 | Per-kind counts only spot-checked; two kinds could be swapped undetected | nit (test) | **miss** |
| 6 | `test_per_kind_decided_plus_undecided` is tautological | nit (test) | **miss** |
| 7 | `test_each_ledger_decision_count_matches` is vacuous | nit (test) | **HIT** |
| 8 | `disp_sum` computed and never used | nit | **HIT** |
| 9 | `LEGEND` dead, `import glob` unused | nit | **HIT** (LEGEND; missed `glob`) |

**Hits 3 / 9. All three are quality nits. None of the four defects found.**

**False positives: 0.** Every finding it reported is real and appears in the answer key.

### What this says

**Prediction 1 held.** It found the surface — dead constants, a vacuous assertion — and missed
everything requiring two facts to be held together. The two contradiction defects (#2, #3) are
exactly that shape: each needs comparing one part of the report against another.

**Prediction 3 was too pessimistic, in an interesting way.** I expected it to catch no test-quality
findings. It caught one, and caught it *properly*: for the vacuous test it wrote *"A stub
implementation returning `decision_count: 0` for every ledger would pass this test."* That is the
mutation-naming instruction doing its job — the prompt asked for the specific mutation that would
not fail the test, and it produced one. The instruction converted a vague suspicion into a
falsifiable claim.

It still missed the *harder* test findings, which needed either running a mutation (#5) or noticing
that an assertion is true by construction (#6).

**Zero false positives is the significant number.** The decision rule set in advance was that hits
must clearly exceed false positives and that false positives must be cheap to dismiss. On this
sample, false positives are not a problem at all — which is the opposite of what I feared, and the
main thing that would have made an automatic fix step dangerous.

**Three errored turns** — worth watching. Not enough to invalidate the run, but the runner now
counts them for exactly this reason.

---

## rv-f01-lc — reviewing `worker/f01-lc`

755.7 s, 15 turns, 37 tool calls. Worktree unmodified, no errored turns. Three findings.

| # | Frontier finding | Class | Local reviewer |
| --- | --- | --- | --- |
| 1 | `_analyze.mjs` committed to the repo root | **defect** (scope) | **HIT** — and correctly rated `high` |
| 2 | Undecided anomaly suppressed when no ledgers supplied | **defect** | miss |
| 3 | Invalid dispositions flagged *and* counted into the headline aggregate | **defect** | miss |
| 4 | Tests cannot detect per-kind misattribution | **defect** (test) | miss |
| 5 | `source_file` smuggled in by side effect; the "pure" function is not pure | **defect** (design) | miss |
| 6 | CLI treats zero ledgers as fatal, foreclosing a valid case | nit | miss |
| 7 | `_LEDGER_FILENAME_PATTERN` not SCREAMING_CASE | nit | miss |
| 8 | `collections` imported unused (also `LEDGER_NAMES`, re-imported `subprocess`) | nit | **HIT** (partial — got `collections` only) |
| 9 | `RealDataTests` recomputes the report in all eight methods | nit | miss |
| 10 | Duplicate anomaly does not name the conflicting ledgers | nit | miss |

**Hits 2 / 10, false positives 0.** It caught the single most obvious defect — the stray committed
file — and rated it `high`, which is right.

### It found something the frontier reviewer did not

Its third finding is **not in the answer key**, and it is **correct**. I verified it rather than
taking it on trust.

It claimed `test_retain_in_place_survives_round_trip` checks key *presence* rather than *value*,
because the implementation inserts every permitted disposition as a key regardless of the data.
The implementation does exactly that:

```python
for disp in PERMITTED_DISPOSITIONS:
    kinds_breakdown[k][disp] = kind_disposition[k].get(disp, 0)
```

So `self.assertIn("retain in place", kind_data)` is true for every kind no matter what the ledgers
say. The assertion cannot fail. The frontier reviewer checked that `retain in place` survived the
round trip *empirically*, found it did, and never questioned whether the **test** proved it.

**One overstatement, in fairness.** It said *"A mutation replacing all 'retain in place' counts
with 0 would not fail this test."* That holds for the per-kind loop but not for the companion
assertion on `disposition_totals`, which is a `Counter` and would drop a zero-count key. The core
claim is right; the blast radius is overstated.

This is the first evidence that a local review adds something a frontier review does not — not
because it is smarter, but because it was *told* to hunt for tests that pass by construction, and
it went looking. The instruction found what expertise had skipped over.

### Format compliance slipped (rv-f01-lc)

The prompt says *"Output only the block below. No preamble."* The review opens with *"Now I have
all the evidence I need. Let me compile the findings."* and **omits the required `SUMMARY:` line
entirely**. Any pipeline parsing that summary would have to handle its absence.

---

## rv-f01-pi-repeat — reviewing `worker/f01-pi-repeat`

1097.5 s (18 minutes), 22 turns, 31 tool calls. Worktree unmodified, no errored turns.

**It reported nothing.** The entire output was `SUMMARY: spec=0 standards=0 tests=0 tooling=0
blocking=0`.

| # | Frontier finding | Class | Local reviewer |
| --- | --- | --- | --- |
| 1 | `unknown_units` filtered by duplicates — silently swallows the anomaly the tool exists to surface | **defect** | miss |
| 2 | Only `FileNotFoundError`/`JSONDecodeError` caught — traceback on a directory or permission failure | **defect** | miss |
| 3 | No shape validation — `KeyError` traceback on valid JSON of the wrong shape | **defect** | miss |
| 4 | `--ledgers` is `required=True`, foreclosing the zero-ledger case the spec calls valid | **defect** | miss |
| 5 | Tests never invoke `main()` | **defect** (test) | miss |
| 6 | No `subTest` despite three parameterised loops, contrary to stated conventions | nit | miss |

**Hits 0 / 6. Eighteen minutes, thirty-one tool calls, nothing found.**

This is not a legitimate all-clear — there are four real defects in that diff, two of them
violations of an explicit spec constraint.

**The prompt's own escape hatch is implicated.** It says *"Reporting zero findings is a valid,
respectable outcome"* — written to suppress false positives, and on that count it worked
perfectly. But it also hands a graceful exit to a reviewer that has run out of ideas, and nothing
in the output distinguishes *"I looked hard and it is clean"* from *"I gave up."* Thirty-one tool
calls says it did look.

The permission needs a counterweight: require an empty result to say **what was checked and how**.
An all-clear should have to be argued for, not merely declared.

---

## The variance arms — three reviewers, one diff

`worker/f01-pi` reviewed three times by fresh instances. Identical input, identical prompt.
607 s / 35 turns / 3 findings, 711 s / 30 turns / 3 findings, 714 s / 23 turns / 5 findings.

| Finding | R1 | R2 | R3 | In answer key |
| --- | :-: | :-: | :-: | --- |
| **Traceback on malformed JSON** (`high`) | — | ✅ | ✅ | **defect 1** |
| **Summary and per-kind counts contradict** (`medium`) | — | ✅ | — | **defect 2** |
| `LEGEND` dead constant | ✅ | ✅ | ✅ | nit |
| `test_each_ledger_decision_count_matches` vacuous | ✅ | — | ✅ | nit |
| `disp_sum` unused | ✅ | — | ✅ | nit |

**The single most important result in E7 is in that table.**

Review 1 — the one I scored first and reported as "3 hits, all quality nits, no defects found" —
**missed both defects that its two identical siblings found.** Judging the local reviewer from that
run alone would have understated it badly.

**Union of three: 2 of the 4 documented defects, plus 3 nits, still zero false positives.**
Best single run: 2 defects. Worst single run: **zero**.

### This inverts the design I proposed earlier

I suggested majority voting — *"findings appearing in 2 of 3 reviews are probably real; ones
appearing once are probably noise."*

**That rule would have discarded the best finding in the entire experiment.** The summary/per-kind
contradiction — the subtlest defect, the one requiring two parts of the report to be held against
each other — was found by **exactly one** reviewer out of three.

Majority voting suppresses precisely the rare-and-real. It is the right rule when false positives
are the problem. Here they are not: **zero false positives across five reviews**. So the correct
aggregation is the **union**, and the frequency count is worth keeping only as a display hint, never
as a filter.

### So: parallel union, not sequential rounds

For the question of whether to iterate implement → review → fix → review:

- **Sequential rounds are the wrong shape.** The variance is between *reviewers*, not between
  *versions of the code*. A second round after a fix re-rolls the dice on a nearly identical diff —
  it does not go deeper, it just samples again, while adding the oscillation risk of a fresh
  reviewer undoing what the previous round's fix deliberately introduced.
- **Parallel reviews of one diff sample the same distribution without any of that risk.** They all
  see identical code, so they cannot fight each other.
- **Three is enough to be worth it here** — it took the defect yield from 0 to 2. Whether five beats
  three is unmeasured.

Recommended shape: **N parallel reviews → union of findings → one fix pass → mechanical re-verify
(tests plus the specific check each finding named), not a second full review.**
