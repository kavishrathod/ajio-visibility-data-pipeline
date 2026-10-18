"""Shared pytest configuration: Hypothesis profiles for the property-based tests."""
import os

from hypothesis import settings

# The tests check behaviour, not crash durability, so SQLite runs with an in-memory journal and no fsync. That removes
# a journal file create/delete and two disk syncs from every commit, which dominates the suite on slow file systems.
# Production leaves this unset and keeps SQLite's durable defaults (see tests/test_sqlite_settings.py).
os.environ.setdefault("AJIO_SQLITE_FAST", "1")

# "project" (default): fixed seed, so a CI failure reproduces locally, and no stored example database.
settings.register_profile("project", max_examples=200, deadline=None, derandomize=True, database=None)
# "explore": more examples and random seeds, for hunting new bugs: set HYPOTHESIS_PROFILE=explore.
settings.register_profile("explore", max_examples=3000, deadline=None, database=None)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "project"))
