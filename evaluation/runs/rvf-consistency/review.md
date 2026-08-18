### FINDING 1
axis: consistency
file: scripts/report-migration-coverage.py:99-103 / scripts/report-migration-coverage.py:128-131
severity: high
confidence: verified
problem: When a unit's disposition is not in the permitted vocabulary (e.g. "retire"), `total_decided` counts it as decided but neither `aggregate` nor the per-kind breakdown accounts for it — the aggregate sum is 0 while total_decided is 1, and the unit is placed in `undecided_count` of the kind breakdown despite the summary saying 0 undecided.
why: The code adds the unit to `decided_ids` whenever it appears in any ledger (line 99: `decided_ids = set(id_to_ledgers.keys()) & unit_ids`), regardless of whether its disposition is permitted. But then at lines 128-131 it only adds the unit to `aggregate_counts` and `kind_dispositions` when `first_disp in PERMITTED_DISPOSITIONS`. Units with invalid dispositions fall through both buckets entirely. The summary says "decided" (correct — the unit has a disposition), the aggregate says 0 accounted for (gap), and the kind breakdown puts it in `undecided_count = registry_count - decided_count` (semantically wrong — the unit is decided, just not with a permitted disposition).
repro: `python scripts/report-migration-coverage.py --registry inventories/migration-unit-registry-2026-08-08.json --ledger inventories/service-dispositions-2026-08-10.json` on a synthetic registry containing one unit and a ledger deciding it with disposition "retire"
evidence: On the invalid-disposition edge case: summary total_decided=1, aggregate_sum=0, skill kind decided_count=0, undecided_count=1, and 1 invalid_disposition anomaly for the same unit. The unit is simultaneously "decided" in the summary, "undecided" in the kind breakdown, and missing from the aggregate — three mutually inconsistent descriptions of the same unit.

SUMMARY: consistency=1 blocking=1 relations-checked=11