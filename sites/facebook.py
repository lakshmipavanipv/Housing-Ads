"""Facebook Marketplace automation."""
import time
from selenium.webdriver.common.by import By
from sites.base_site import BaseSite, PostResult


class FacebookMarketplace(BaseSite):
    site_id = "facebook"
    site_name = "Facebook Marketplace"
    post_url = "https://www.facebook.com/marketplace/create/property-for-sale"

    def post_ad(self) -> PostResult:
        try:
            self._navigate("https://www.facebook.com/login")
            time.sleep(2)
            try:
                self._type("input#email", self.username)
                self._type("input#pass", self.password)
                self._click("button[name='login']")
                time.sleep(4)
            except Exception:
                self._manual("Log in to Facebook manually, then press Enter.")

            self._navigate(self.post_url)
            time.sleep(4)

            p = self.prop
            try:
                self._type("input[placeholder*='price' i]", p["price_num"])
            except Exception:
                pass
            try:
                self._type("input[placeholder*='home type' i], select[aria-label*='type' i]",
                           "Apartment")
            except Exception:
                pass
            try:
                self._type("input[placeholder*='bedrooms' i]", p["bhk"])
            except Exception:
                pass
            try:
                self._type("input[placeholder*='bathrooms' i]", "2")
            except Exception:
                pass
            try:
                self._type("input[placeholder*='location' i], input[aria-label*='location' i]",
                           p["full_address"])
                time.sleep(2)
                self._click("ul[role='listbox'] li:first-child, .autocomplete li:first-child")
            except Exception:
                pass
            try:
                self._type(
                    "textarea[placeholder*='desc' i], div[role='textbox']",
                    p["description"],
                )
            except Exception:
                pass

            self._manual(
                "Facebook Marketplace: Add property photos (very important for reach!), "
                "review all details, and PUBLISH the listing. Press Enter when done.",
                timeout=360,
            )
            return self._ok(url=self.driver.current_url, notes="Posted via assisted automation")
        except Exception as exc:
            return self._fail(str(exc))
