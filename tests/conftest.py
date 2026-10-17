"""Shared pytest configuration: Hypothesis profiles for the property-based tests."""
import os

from hypothesis import settings

# "project" (default): fixed seed, so a CI failure reproduces locally, and no stored example database.
settings.register_profile("project", max_examples=200, deadline=None, derandomize=True, database=None)
# "explore": more examples and random seeds, for hunting new bugs: set HYPOTHESIS_PROFILE=explore.
settings.register_profile("explore", max_examples=3000, deadline=None, database=None)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "project"))
