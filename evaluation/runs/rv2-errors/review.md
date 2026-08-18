Now let me compile the report.

---

### FINDING 1
axis: error-paths
file: scripts/wayfinder_autopilot.py:865
severity: high
confidence: verified
problem: `list_runs` crashes with unhandled `AttributeError` when `run.json` contains valid JSON that is not a dict.
why: The code parses `run.json` with `json.loads()` then immediately calls `metadata.get("started_at")`. When the JSON is a list, string, number, boolean, or `null`, this raises `AttributeError`, which is not caught by the existing `except (json.JSONDecodeError, OSError)` block. The traceback reaches the user and the process exits with code 1 instead of reporting the unreadable run.
repro: `python scripts/wayfinder_autopilot.py --workspace <workspace> history` where `<workspace>/logs/runs/20260816T120000-000000/run.json` contains `[1, 2, 3]`
evidence: 
```
Traceback (most recent call last):
  File ".../wayfinder_autopilot.py", line 940, in <module>
    raise SystemExit(main())
  File ".../wayfinder_autopilot.py", line 929, in main
    result = list_runs(config, limit=args.limit, states=states)
  File ".../wayfinder_autopilot.py", line 865, in list_runs
    started = metadata.get("started_at")
              ^^^^^^^^^^^^
AttributeError: 'list' object has no attribute 'get'
EXIT: 1
```
(Same traceback for JSON string, `null`, `42`, `true`, `false`.)

### FINDING 2
axis: error-paths
file: scripts/wayfinder_autopilot.py:901
severity: medium
confidence: verified
problem: `list_runs` crashes with `TypeError` during sort when run entries have mixed `run_id` types.
why: The sort key is `e["run_id"]`. Valid entries may have a numeric `run_id` from the JSON, while unreadable entries use `child.name` (a string) as the fallback. Python 3 cannot compare `int` and `str`, so `entries.sort(...)` raises `TypeError`, which escapes to the user.
repro: `python scripts/wayfinder_autopilot.py --workspace <workspace> history` where one run dir has `run.json` containing `{"run_id": 123, "state": "completed"}` and another has `run.json` containing `NOT JSON`
evidence:
```
Traceback (most recent call last):
  File ".../wayfinder_autopilot.py", line 940, in <module>
    raise SystemExit(main())
  File ".../wayfinder_autopilot.py", line 929, in main
    result = list_runs(config, limit=args.limit, states=states)
  File ".../wayfinder_autopilot.py", line 901, in list_runs
    entries.sort(key=lambda e: e["run_id"], reverse=True)
    ~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: '<' not supported between instances of 'int' and 'str'
EXIT: 1
```

SUMMARY: error-paths=2 blocking=2 cases-tested=8