"""
Abstract base class for all housing site automation modules.
Every site handler must inherit from BaseSite and implement post_ad().
"""

import time
from abc import ABC, abstractmethod
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from utils.browser import pause_for_user


class PostResult:
    """Returned by post_ad() to report outcome."""

    def __init__(
        self,
        success: bool,
        site_id: str,
        site_name: str,
        ad_url: str = "",
        ad_title: str = "",
        status: str = "Pending",
        notes: str = "",
    ):
        self.success = success
        self.site_id = site_id
        self.site_name = site_name
        self.ad_url = ad_url
        self.ad_title = ad_title
        self.status = status
        self.notes = notes
        self.posted_date = datetime.today().strftime("%d-%m-%Y") if success else ""
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "site_id": self.site_id,
            "site_name": self.site_name,
            "ad_url": self.ad_url,
            "ad_title": self.ad_title,
            "status": self.status,
            "notes": self.notes,
            "posted_date": self.posted_date,
        }

    def __str__(self):
        icon = "✅" if self.success else "❌"
        return f"{icon} {self.site_name}: {self.status} – {self.notes or self.ad_url}"


class BaseSite(ABC):
    """Base class for site automation."""

    site_id: str = ""
    site_name: str = ""
    post_url: str = ""

    def __init__(self, driver: webdriver.Chrome, credentials: dict, property_data: dict):
        self.driver = driver
        self.creds = credentials        # {username, password, phone, api_key}
        self.prop = property_data       # parsed from HTML
        self.username = credentials.get("username", "")
        self.password = credentials.get("password", "")
        self.phone = credentials.get("phone", "")

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _navigate(self, url: str):
        self.driver.get(url)
        time.sleep(2)

    def _find(self, selector: str, by: By = By.CSS_SELECTOR, timeout: int = 10):
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )

    def _click(self, selector: str, by: By = By.CSS_SELECTOR):
        el = self._find(selector, by)
        self.driver.execute_script("arguments[0].scrollIntoView(true);", el)
        time.sleep(0.3)
        el.click()
        return el

    def _type(self, selector: str, text: str, by: By = By.CSS_SELECTOR):
        el = self._find(selector, by)
        el.clear()
        el.send_keys(str(text))
        return el

    def _manual(self, msg: str, timeout: int = 120):
        pause_for_user(self.driver, msg, timeout)

    def _ok(self, url: str = "", notes: str = "") -> PostResult:
        return PostResult(True, self.site_id, self.site_name, ad_url=url,
                          ad_title=self.prop.get("title", ""), status="Active", notes=notes)

    def _fail(self, reason: str) -> PostResult:
        return PostResult(False, self.site_id, self.site_name, status="Failed", notes=reason)

    def _manual_required(self, reason: str) -> PostResult:
        return PostResult(False, self.site_id, self.site_name,
                          status="Manual Required", notes=reason)

    # ── Abstract interface ───────────────────────────────────────────────────

    @abstractmethod
    def post_ad(self) -> PostResult:
        """
        Open the browser, log in, fill the ad form, submit, and return PostResult.
        If any step fails irreversibly, return self._fail(reason).
        If the user must intervene (CAPTCHA, OTP, etc.) call self._manual(msg)
        and continue automation afterward.
        """
        ...

    def scrape_stats(self, ad_url: str) -> dict:
        """
        Optional: scrape views/clicks/inquiries from the live ad page.
        Return dict with keys: views, clicks, inquiries.
        Override in subclass where the site exposes public stats.
        """
        return {"views": 0, "clicks": 0, "inquiries": 0}
