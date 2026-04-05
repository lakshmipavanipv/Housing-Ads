"""
99acres automation – post property ad.
URL: https://www.99acres.com
"""

import time
from selenium.webdriver.common.by import By
from sites.base_site import BaseSite, PostResult


class NinetyNineAcres(BaseSite):
    site_id = "99acres"
    site_name = "99acres"
    post_url = "https://www.99acres.com/seller/postProperty.php"

    def post_ad(self) -> PostResult:
        try:
            # ── Login ────────────────────────────────────────────────────────
            self._navigate("https://www.99acres.com/seller/login.php")
            time.sleep(2)

            try:
                self._type("input[name='email'], input[id*='email' i]", self.username)
                self._type("input[name='password'], input[id*='pass' i]", self.password)
                self._click("button[type='submit'], input[type='submit']")
                time.sleep(3)
            except Exception:
                self._manual("Please log in manually to 99acres, then press Enter.")

            self._navigate(self.post_url)
            time.sleep(3)

            self._manual(
                "99acres: Complete OTP/verification if shown. "
                "Then fill in the property form. Fields auto-filled where possible. "
                "Press Enter when the ad is successfully submitted.",
                timeout=300,
            )

            # Try to fill basic fields
            p = self.prop
            try:
                self._type("input[placeholder*='locality' i], input[name*='locality' i]",
                           p["location"])
            except Exception:
                pass
            try:
                self._type("input[placeholder*='price' i], input[name*='price' i]", p["price_num"])
            except Exception:
                pass
            try:
                self._type("textarea[name*='desc' i], textarea[placeholder*='desc' i]",
                           p["description"])
            except Exception:
                pass

            self._manual(
                "99acres: Review all fields, add images, and SUBMIT. Press Enter when done.",
                timeout=300,
            )

            ad_url = self.driver.current_url
            return self._ok(url=ad_url, notes="Posted via assisted automation")

        except Exception as exc:
            return self._fail(f"Error: {exc}")
