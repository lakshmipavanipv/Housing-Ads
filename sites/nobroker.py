"""NoBroker automation."""
import time
from sites.base_site import BaseSite, PostResult


class NoBroker(BaseSite):
    site_id = "nobroker"
    site_name = "NoBroker"
    post_url = "https://www.nobroker.in/post-your-property"

    def post_ad(self) -> PostResult:
        try:
            self._navigate("https://www.nobroker.in/login")
            time.sleep(2)
            self._manual(
                "NoBroker uses OTP-based login. Please log in manually (phone + OTP), "
                "then navigate to 'Post Property'. Press Enter when the form is open.",
                timeout=180,
            )

            p = self.prop
            try:
                self._type("input[placeholder*='price' i]", p["price_num"])
            except Exception:
                pass
            try:
                self._type("input[placeholder*='area' i]", p["area"])
            except Exception:
                pass
            try:
                self._type("textarea[placeholder*='desc' i]", p["description"])
            except Exception:
                pass

            self._manual(
                "NoBroker: Fill remaining fields (BHK, floor, amenities, photos) and SUBMIT. "
                "Press Enter when done.",
                timeout=300,
            )
            return self._ok(url=self.driver.current_url, notes="Posted via assisted automation")
        except Exception as exc:
            return self._fail(str(exc))
