"""Housing.com automation."""
import time
from sites.base_site import BaseSite, PostResult


class HousingCom(BaseSite):
    site_id = "housing"
    site_name = "Housing.com"
    post_url = "https://housing.com/post-property"

    def post_ad(self) -> PostResult:
        try:
            self._navigate("https://housing.com/login")
            time.sleep(2)
            try:
                self._type("input[type='email'], input[placeholder*='email' i]", self.username)
                self._type("input[type='password']", self.password)
                self._click("button[type='submit']")
                time.sleep(3)
            except Exception:
                self._manual("Please log in to Housing.com manually, then press Enter.")

            self._navigate(self.post_url)
            time.sleep(3)

            p = self.prop
            try:
                self._type("input[placeholder*='price' i], input[name*='price' i]", p["price_num"])
            except Exception:
                pass
            try:
                self._type("input[placeholder*='area' i], input[name*='area' i]", p["area"])
            except Exception:
                pass
            try:
                self._type("textarea[placeholder*='desc' i]", p["description"])
            except Exception:
                pass

            self._manual(
                "Housing.com: Complete all form fields and SUBMIT. Press Enter when done.",
                timeout=300,
            )
            return self._ok(url=self.driver.current_url, notes="Posted via assisted automation")
        except Exception as exc:
            return self._fail(str(exc))
