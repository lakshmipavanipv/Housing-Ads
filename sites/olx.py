"""OLX automation."""
import time
from selenium.webdriver.common.by import By
from sites.base_site import BaseSite, PostResult


class OLX(BaseSite):
    site_id = "olx"
    site_name = "OLX"
    post_url = "https://www.olx.in/post-ad"

    def post_ad(self) -> PostResult:
        try:
            self._navigate("https://www.olx.in/login")
            time.sleep(2)
            try:
                self._type("input[type='email']", self.username)
                self._click("button[type='submit']")
                time.sleep(2)
                self._type("input[type='password']", self.password)
                self._click("button[type='submit']")
                time.sleep(3)
            except Exception:
                self._manual("Please log in to OLX manually, then press Enter.")

            self._navigate(self.post_url)
            time.sleep(3)

            # OLX category: Real Estate > Flats for Sale
            try:
                self._click("a[href*='flats-for-sale'], button[data-aut-id*='flat' i]")
                time.sleep(1)
            except Exception:
                pass

            p = self.prop
            try:
                self._type("input[name='title'], input[placeholder*='title' i]", p["title"])
            except Exception:
                pass
            try:
                self._type("textarea[name='description'], textarea[placeholder*='desc' i]",
                           p["description"])
            except Exception:
                pass
            try:
                self._type("input[name='price'], input[placeholder*='price' i]", p["price_num"])
            except Exception:
                pass

            self._manual(
                "OLX: Select category (Flats for Sale → Hyderabad), add photos, "
                "complete remaining fields and POST. Press Enter when done.",
                timeout=300,
            )
            return self._ok(url=self.driver.current_url, notes="Posted via assisted automation")
        except Exception as exc:
            return self._fail(str(exc))

    def scrape_stats(self, ad_url: str) -> dict:
        """OLX shows view count on the ad page."""
        try:
            self._navigate(ad_url)
            time.sleep(3)
            views_el = self.driver.find_elements(By.CSS_SELECTOR, "span[data-aut-id='adViews'], .view-count")
            views = int(views_el[0].text.strip().replace(",", "")) if views_el else 0
            return {"views": views, "clicks": 0, "inquiries": 0}
        except Exception:
            return {"views": 0, "clicks": 0, "inquiries": 0}
