"""Square Yards automation."""
import time
from sites.base_site import BaseSite, PostResult


class SquareYards(BaseSite):
    site_id = "squareyards"
    site_name = "Square Yards"
    post_url = "https://www.squareyards.com/sell"

    def post_ad(self) -> PostResult:
        try:
            self._navigate(self.post_url)
            time.sleep(3)
            self._manual(
                "Square Yards: Log in / register, fill the form and SUBMIT. Press Enter when done.",
                timeout=360,
            )
            return self._ok(url=self.driver.current_url, notes="Posted manually via browser")
        except Exception as exc:
            return self._fail(str(exc))
