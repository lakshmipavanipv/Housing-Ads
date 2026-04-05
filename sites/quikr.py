"""Quikr automation."""
import time
from sites.base_site import BaseSite, PostResult


class Quikr(BaseSite):
    site_id = "quikr"
    site_name = "Quikr"
    post_url = "https://www.quikr.com/post-ads"

    def post_ad(self) -> PostResult:
        try:
            self._navigate("https://www.quikr.com/login")
            time.sleep(2)
            try:
                self._type("input[type='email'], input[name='email']", self.username)
                self._type("input[type='password']", self.password)
                self._click("button[type='submit'], .login-btn")
                time.sleep(3)
            except Exception:
                self._manual("Log in to Quikr manually, then press Enter.")

            self._navigate(self.post_url)
            time.sleep(3)

            p = self.prop
            try:
                self._type("input[name='title'], input[placeholder*='title' i]", p["title"])
            except Exception:
                pass
            try:
                self._type("textarea[name='description']", p["description"])
            except Exception:
                pass
            try:
                self._type("input[name='price']", p["price_num"])
            except Exception:
                pass

            self._manual(
                "Quikr: Select category Homes & Apartments → Flats for Sale, "
                "upload photos, complete and SUBMIT. Press Enter when done.",
                timeout=300,
            )
            return self._ok(url=self.driver.current_url, notes="Posted via assisted automation")
        except Exception as exc:
            return self._fail(str(exc))
