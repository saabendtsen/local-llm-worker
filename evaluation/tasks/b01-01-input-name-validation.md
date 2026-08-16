---
id: b01-01-input-name-validation
repo: C:\Dev\homelab
category: bugfix
complexity: small
verify: python -m pytest -q tests/test_codex_task_bridge.py
base: experiment/74-local-llm-worker
---

# Task: reject unsafe input names in Bridge.submit

**Edit `scripts/codex_task_server.py`.** Then **edit `tests/test_codex_task_bridge.py`** to add
tests covering the fix.

## The defect

`Bridge.submit` validates each supplied input name with:

```python
if Path(name).name != name or name in seen_names:
    raise ValueError(f"invalid or duplicate input name: {name!r}")
```

On Python 3.14, `Path("").name` is `""` and `Path("..").name` is `".."`, so both names satisfy the
guard and reach the filesystem write. They then fail as `PermissionError`, not `ValueError`.

That matters because `main()` catches only `ValueError`, `FileNotFoundError`, and
`json.JSONDecodeError`. An escaping name therefore kills the CLI with a traceback instead of
emitting the `{"error": ...}` envelope.

## Acceptance criteria

- `""`, `"."`, `".."`, and any name containing a path separator are rejected with `ValueError`.
- The existing message shape is preserved: `invalid or duplicate input name: {name!r}`. An
  existing test asserts the substring `"invalid or duplicate"`.
- Legitimate dot-prefixed names such as `.gitignore` and `.env.sample` are still **accepted**.
- Duplicate-name rejection still works.
- `python -m pytest -q tests/test_codex_task_bridge.py` passes.
- Return a concise summary of what changed and anything left unresolved.

## Constraints

- Do not change the atomicity design: a task is built in `.{task_id}.tmp` and then moved into
  place with `os.replace`. That shape must survive.
- Change no files other than the two named above.

## Notes

- `os.path.basename(name) != name` looks like an equivalent fix and is not — `basename("..")` is
  `".."`, so `".."` would still be accepted. A fix that only special-cases `""` has the same hole.
- Rejecting everything beginning with `.` would be wrong; see the dot-prefixed criterion above.
- Test conventions: plain `unittest.TestCase`, no pytest features. `setUp` builds a
  `tempfile.TemporaryDirectory()`, writes a `fake_codex.py` stub and a `config.json`, then
  constructs `self.bridge = Bridge(self.config_path)`. Error cases use `self.assertRaisesRegex`.
  Inputs are `{"name": ..., "content_base64": base64.b64encode(b"...").decode()}`. A `subTest`
  loop over the rejected names fits the house style.
