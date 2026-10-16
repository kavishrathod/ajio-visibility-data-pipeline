"""LiveAdapter is intentionally NOT implemented.

AJIO robots.txt disallows /search and /api/*. See docs/source_research.md.
Raising here makes it impossible to run live by accident.
"""
from .base import Adapter


class LiveAdapter(Adapter):
    def fetch_page(self, keyword, page):
        raise NotImplementedError(
            "Live collection disabled: robots.txt disallows /search and /api/*. Use MockAdapter."
        )
