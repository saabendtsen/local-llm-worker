# f02 triage — a worked example

The triage step done by hand, with reasoning recorded, so the triage prompt can be written from
this rather than guessed at. Input: 11 findings from four focused reviewers, already deduplicated
and ordered by `scripts/aggregate_findings.py`.

## The first rule triage taught me: verify before converting

I checked each high and medium finding against the actual source before turning it into work. That
was not ceremony — **one finding would have caused real damage if converted mechanically.**

### Finding 5 has a wrong problem statement

It reads:

> `--state` uses `nargs="*"` instead of `action="append"`, breaking repeated `--state` flags

The source says otherwise:

```
835:    history_parser.add_argument("--state", action="append", default=None)
```

The code is **already correct**. Reading its own `mutation:` line explains what happened — the
reviewer described the state *after* its mutation as though it were the state before:

> mutation: Changed `add_argument("--state", action="append", ...)` to `nargs="*"`
> result: 42 passed

So the real finding is *"no test pins `--state`'s repeatability"*, and the `problem:` line inverts
it. A mechanical finding-to-task conversion would have instructed the worker to change working code
into the broken form the reviewer had used as its mutation.

**This is the argument for triage being a frontier job, in one example.** The finding is
structurally perfect — verified, with a repro, correctly severity-rated — and still wrong in the
one field a converter would read.

### Two other findings are test gaps, not defects

- **Read-only (finding 1).** Every `mkdir` in the module sits in the writer path — lines 244, 686,
  688, 694, 767 — and none in `list_runs`. The implementation honours the constraint. What is
  missing is a test asserting it, which the reviewer proved by injecting a `mkdir` and watching the
  test pass anyway.
- **`--limit` / `--state` ordering (findings 4 and 7).** Lines 902-904 apply the state filter before
  the limit slice, exactly as the spec requires. Again correct, again unpinned.

Both are still worth fixing — an untested constraint is one refactor away from being violated — but
the task must say *add a test*, never *fix the behaviour*.

## Dispositions

| # | Finding | Verified against source | Disposition |
| --- | --- | --- | --- |
| 3 | `list_runs` crashes on valid-JSON-not-a-dict | real defect | **fix** — task 1 |
| 2 | unreadable entries omit the `abandoned` key | real defect | **fix** — task 2 |
| 1 | read-only constraint untested | implementation correct, test missing | **fix (test only)** — task 3 |
| 6 | `TypeError` sorting mixed `run_id` types | real defect, narrow trigger | **fix** — task 4 |
| 4+7+5 | `--limit`/`--state` interaction and `--state` repeatability unpinned | implementation correct, tests missing | **fix (test only)** — task 5, merged from three findings |
| 8 | `places=2` too lenient for the `3.501` case | real test weakness | **fix (test only)** — task 6 |
| 9 | key-presence test does not assert duration value | its own mutation result shows the dedicated duration tests *did* catch it | **drop** — covered elsewhere |
| 10 | `abandoned` flag untested | genuine gap, needs `datetime.now` mocking; correctly self-rated `suspected` | **defer** — real, low value, disproportionate effort |
| 11 | `duration_seconds` rounding gives "variable JSON decimal precision" | **false positive** | **drop** |

### On finding 11, the first false positive in the project

JSON numbers have no decimal-precision property. `3605.0` and `3605.000` parse to the same value,
and no consumer can distinguish them. The claim is a misunderstanding of the format.

Worth noting how the machinery handled it: the reviewer graded it `severity: low,
confidence: suspected` — its own weakest classification — so `--verified-only` or
`--min-severity medium` would have dropped it before triage ever saw it. **The confidence system
caught its own bad finding.** That is the behaviour the severity floor was designed for, arriving
unprompted.

## What this says about the triage prompt

Three rules, all earned here:

1. **Verify each finding against the source before converting it.** The `problem:` field is a
   claim, not a fact. One of eleven was inverted.
2. **Classify defect versus test gap explicitly**, because the resulting task is completely
   different — *fix the behaviour* against *pin the behaviour*. Three of the eight actionable
   findings were test gaps against correct code.
3. **Merge across axes before ordering.** Findings 4, 5 and 7 are one issue seen by two reviewers
   through different lenses; the aggregator could not merge them because they cite different files.
   That is the intended trade-off — a visible duplicate is cheap to merge here and a swallowed
   defect would not be — but merging is triage's job, not the aggregator's.
