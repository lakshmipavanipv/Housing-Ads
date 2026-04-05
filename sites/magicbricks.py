"""
MagicBricks automation – post property ad.
URL: https://www.magicbricks.com
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from sites.base_site import BaseSite, PostResult


class MagicBricks(BaseSite):
    site_id = "magicbricks"
    site_name = "MagicBricks"
    post_url = "https://www.magicbricks.com/sell/post-property.html"

    def post_ad(self) -> PostResult:
        try:
            # ── Step 1: Login ────────────────────────────────────────────────
            self._navigate("https://www.magicbricks.com/login")
            time.sleep(2)

            try:
                self._type("input[name='email'], input[id='email'], input[type='email']",
                           self.username)
                self._type("input[name='password'], input[id='password'], input[type='password']",
                           self.password)
                self._click("button[type='submit'], input[type='submit'], .login-btn")
                time.sleep(3)
            except Exception:
                self._manual("Please log in manually to MagicBricks, then press Enter.")

            # ── Step 2: Navigate to post property ───────────────────────────
            self._navigate(self.post_url)
            time.sleep(3)

            # Handle possible OTP / verification popup
            self._manual(
                "If any OTP/verification is shown on MagicBricks, complete it now, "
                "then navigate to the 'Post Free Property' page and press Enter.",
                timeout=180,
            )

            # ── Step 3: Fill property details ────────────────────────────────
            p = self.prop
            try:
                # Property type (Residential / Apartment)
                self._click("label[for='Apartment'], input[value='Apartment']")
            except Exception:
                pass

            try:
                self._type("#city, input[placeholder*='city' i]", p["city"])
            except Exception:
                pass

            try:
                self._type("#locality, input[placeholder*='locality' i], input[placeholder*='area' i]",
                           p["location"])
                time.sleep(1)
                # Click first autocomplete suggestion
                self._click(".autocomplete-item:first-child, .suggestion:first-child, li.pac-item:first-child")
            except Exception:
                pass

            try:
                self._type("input[name*='price' i], input[placeholder*='price' i]", p["price_num"])
            except Exception:
                pass

            try:
                self._type("input[name*='area' i], input[placeholder*='area' i]", p["area"])
            except Exception:
                pass

            try:
                self._type("textarea[name*='desc' i], textarea[placeholder*='desc' i]",
                           p["description"])
            except Exception:
                pass

            # Let user complete the form and submit
            self._manual(
                "MagicBricks: Please review the pre-filled form, complete any remaining "
                "fields (images, BHK, floor, etc.), then SUBMIT the ad and press Enter.",
                timeout=300,
            )

            ad_url = self.driver.current_url
            return self._ok(url=ad_url, notes="Posted via automation + manual completion")

        except Exception as exc:
            return self._fail(f"Error: {exc}")
