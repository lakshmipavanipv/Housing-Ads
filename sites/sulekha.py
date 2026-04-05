"""Sulekha automation."""
import time
from sites.base_site import BaseSite, PostResult


class Sulekha(BaseSite):
    site_id = "sulekha"
    site_name = "Sulekha"
    post_url = "https://realestate.sulekha.com/sell-property"

    def post_ad(self) -> PostResult:
        try:
            self._navigate("https://www.sulekha.com/login")
            time.sleep(2)
            try:
                self._type("input[type='email'], input[name='email']", self.username)
                self._type("input[type='password']", self.password)
                self._click("button[type='submit']")
                time.sleep(3)
            except Exception:
                self._manual("Log in to Sulekha manually, then press Enter.")

            self._navigate(self.post_url)
            time.sleep(3)

            p = self.prop
            for sel in ["input[placeholder*='price' i]", "input[name*='price' i]"]:
                try:
                    self._type(sel, p["price_num"])
                    break
                except Exception:
                    pass
            for sel in ["textarea[placeholder*='desc' i]", "textarea[name*='desc' i]"]:
                try:
                    self._type(sel, p["description"])
                    break
                except Exception:
                    pass

            self._manual(
                "Sulekha: Complete the property form and SUBMIT. Press Enter when done.",
                timeout=300,
            )
            return self._ok(url=self.driver.current_url, notes="Posted via assisted automation")
        except Exception as exc:
            return self._fail(str(exc))
