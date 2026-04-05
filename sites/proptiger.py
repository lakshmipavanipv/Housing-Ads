"""PropTiger automation."""
import time
from sites.base_site import BaseSite, PostResult


class PropTiger(BaseSite):
    site_id = "proptiger"
    site_name = "PropTiger"
    post_url = "https://www.proptiger.com/post-property"

    def post_ad(self) -> PostResult:
        try:
            self._navigate(self.post_url)
            time.sleep(3)
            self._manual(
                "PropTiger: Log in / register, fill the property form and SUBMIT. "
                "Press Enter when done.",
                timeout=360,
            )
            return self._ok(url=self.driver.current_url, notes="Posted manually via browser")
        except Exception as exc:
            return self._fail(str(exc))
