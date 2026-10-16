"""Live AJIO adapter intentionally disabled unless source permission is confirmed.

The assessment's initial source research recorded that automated access to the
AJIO search/API paths was disallowed. This adapter therefore fails closed; it
never attempts to bypass robots rules, CAPTCHAs, authentication, or throttling.
"""
from .base import Adapter, RawResponse


class AjioAdapter(Adapter):
    def fetch_page(self, keyword: str, page: int) -> RawResponse:
        raise PermissionError(
            "Live AJIO collection is disabled. Use the clearly labelled mock adapter; "
            "only enable live collection after checking current terms, robots.txt, and written permission."
        )
