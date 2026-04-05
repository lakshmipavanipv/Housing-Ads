"""CommonFloor automation."""
import time
from sites.base_site import BaseSite, PostResult


class CommonFloor(BaseSite):
    site_id = "commonfloor"
    site_name = "CommonFloor"
    post_url = "https://www.commonfloor.com/post-property"

    def post_ad(self) -> PostResult:
        try:
            self._navigate("https://www.commonfloor.com/login")
            time.sleep(2)
            self._manual("Log in to CommonFloor, navigate to Post Property. Press Enter.", timeout=180)

            p = self.prop
            try:
                self._type("input[placeholder*='price' i]", p["price_num"])
            except Exception:
                pass
            try:
                self._type("textarea[placeholder*='desc' i]", p["description"])
            except Exception:
                pass

            self._manual(
                "CommonFloor: Complete the form and SUBMIT. Press Enter when done.", timeout=300
            )
            return self._ok(url=self.driver.current_url, notes="Posted via assisted automation")
        except Exception as exc:
            return self._fail(str(exc))
