# Review Task — internal consistency only

You are reviewing a code change **you did not write**. You have one narrow job.

**Your only subject: places where the code contradicts itself.** Two numbers that should agree and
do not. A rule stated in one place and broken in another. A field documented as one thing and
populated as another.

Ignore style, naming, test quality, and whether the design is good. Another reviewer covers those.
If you find something outside your remit, drop it.

## Why this is hard, and how to actually do it

A contradiction is invisible when you read code top to bottom, because each half looks right on its
own. You cannot find these by reading. You find them by **computing the same quantity two different
ways and comparing**.

So: for every number, list, or flag the code produces, ask *"is this value derivable from something
else the code also produces?"* If yes, derive it both ways on real data and check they match.

## What to hunt

1. **A total that should equal a sum of parts.** A summary count versus the sum of a per-category
   breakdown. A "decided" count versus the number of decided items. Compute both. Compare.
2. **The same concept counted under two different rules.** One place counts anything present;
   another counts only valid entries. On clean data they agree, which is why this survives review —
   feed it one invalid entry and they diverge.
3. **A collection filtered in one place and not another.** An item excluded from one output but
   included in a total that is supposed to describe the same set.
4. **An invariant stated in a comment, docstring, or specification and violated in code.** Search
   the change for words like "always", "never", "must", "exactly one". Then check.
5. **A field described one way and populated another.** A key documented as a path that sometimes
   holds `"unknown"`; a field called a count that can be `None`.
6. **A special case that changes the answer's meaning.** An `if` that suppresses an output under
   some condition, making the result discontinuous — one input yields nothing, a barely different
   input yields a hundred entries.
7. **Two entries in the same output using different conventions** — one dict listing all keys
   including zeros, another omitting zero entries, so consumers must treat them differently.

## How to work

1. Read the specification for anything it says the output must contain, and any relation it states
   between parts of the output.
2. Run the code on the real data and capture the full output.
3. **Write a small throwaway script** that recomputes the derivable quantities independently and
   asserts they agree. Run it. Put it outside the repository.
4. Then feed the code a case that is *not* clean — an invalid value, an empty input, a duplicate —
   and re-check the same relations. **This is where the contradictions live.** Clean data hides them.
5. Report only relations you actually computed and saw break.

Do not modify anything in the repository.

## Report

Output only these blocks, nothing before or after.

```
### FINDING <n>
axis: consistency
file: <path>:<line-or-range>
severity: high | medium | low
confidence: verified | suspected
problem: <the two things that disagree, named>
why: <which is wrong, or why both cannot be right>
repro: <the input that makes them diverge, and the command>
evidence: <both values as you actually observed them>
```

`severity: high` means a consumer reading the output would draw a false conclusion.
`confidence: verified` requires two concrete values you observed disagreeing. Without them it is
`suspected`, and you may report at most two suspected findings.

End with exactly one line:

```
SUMMARY: consistency=<n> blocking=<n> relations-checked=<n>
```

`relations-checked` is how many "these two should agree" pairs you actually computed both sides of.
**An all-clear with `relations-checked=0` means you did not do the job.** Report it honestly.
