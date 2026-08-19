"""Keep this repository's tests out of the workspace's collection.

The experiment checkout lives inside C:\Dev\homelab, which git ignores but
pytest does not: `python -m pytest -q` at the workspace root walks into
experiments/ and collects tests/test_run_triage.py alongside the workspace's own
suite. That inflated a worker's verify count from 180 to 247 in f02-auto-fix-02
and would let a failure here break a worker run on an unrelated task.

So: when pytest's rootdir is not this directory, ignore our tests.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent


def pytest_ignore_collect(collection_path, config):  # noqa: ARG001 - pytest hook signature
    if Path(str(config.rootpath)).resolve() != HERE:
        return Path(str(collection_path)).resolve() == HERE / "tests"
    return None
