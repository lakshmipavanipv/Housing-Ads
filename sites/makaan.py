"""Makaan.com automation."""
import time
from sites.base_site import BaseSite, PostResult


class Makaan(BaseSite):
    site_id = "makaan"
    site_name = "Makaan.com"
    post_url = "https://www.makaan.com/post-property"

    def post_ad(self) -> PostResult:
        try:
            self._navigate(self.post_url)
            time.sleep(3)
            self._manual(
                "Makaan.com: Log in / register, fill the form and SUBMIT. Press Enter when done.",
                timeout=360,
            )
            return self._ok(url=self.driver.current_url, notes="Posted manually via browser")
        except Exception as exc:
            return self._fail(str(exc))
