"""
Browser utility – returns a configured Selenium WebDriver.
Uses Chrome in headed or headless mode.
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


def get_driver(headless: bool = False) -> webdriver.Chrome:
    """
    Create and return a Chrome WebDriver.
    Set headless=False so the user can see the browser and intervene if needed.
    """
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # Realistic user-agent
    options.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def wait_for(driver: webdriver.Chrome, by: By, selector: str, timeout: int = 15):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, selector)))


def safe_click(driver: webdriver.Chrome, by: By, selector: str, timeout: int = 10):
    el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, selector)))
    driver.execute_script("arguments[0].scrollIntoView(true);", el)
    time.sleep(0.3)
    el.click()
    return el


def safe_type(driver: webdriver.Chrome, by: By, selector: str, text: str, timeout: int = 10):
    el = wait_for(driver, by, selector, timeout)
    el.clear()
    el.send_keys(text)
    return el


def pause_for_user(driver: webdriver.Chrome, message: str, timeout_sec: int = 120):
    """
    Display a message and wait for the user to press Enter in the terminal,
    keeping the browser window open.  Used when automation hits a CAPTCHA or
    a login confirmation page that requires human interaction.
    """
    print(f"\n  ⚠  MANUAL ACTION NEEDED: {message}")
    print(f"     (You have {timeout_sec} seconds – press Enter when done)")
    try:
        import signal

        def _timeout(signum, frame):
            raise TimeoutError

        signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(timeout_sec)
        input("  >>> Press Enter to continue: ")
        signal.alarm(0)
    except (TimeoutError, Exception):
        pass
