"""
drive_uploader.py
─────────────────
Upload the .xlsx tracker file to Google Drive using Selenium.
No Google Cloud API or service account needed – just your Google login.

The script:
  1. Opens Chrome → drive.google.com
  2. If not already logged in, prompts the user to log in
  3. Creates / replaces the file in a "Housing Ads" folder
  4. Returns the shareable URL
"""

import time
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from utils.browser import get_driver, pause_for_user
from config import TRACKER_FILE, TRACKER_FILE_GIT

DRIVE_URL = "https://drive.google.com"
FOLDER_NAME = "Housing Ads Tracker"


def upload_to_drive(headless: bool = False) -> str:
    """
    Upload TRACKER_FILE to Google Drive.
    Returns the Google Drive file URL, or empty string on failure.
    """
    # Use the git-accessible copy if the user's Windows path isn't reachable
    upload_file = TRACKER_FILE_GIT if TRACKER_FILE_GIT.exists() else TRACKER_FILE

    if not upload_file.exists():
        print(f"  [ERROR] Tracker file not found: {upload_file}")
        return ""

    driver = get_driver(headless=headless)

    try:
        driver.get(DRIVE_URL)
        time.sleep(3)

        # ── Check if logged in ──────────────────────────────────────────
        if "accounts.google.com" in driver.current_url or "signin" in driver.current_url.lower():
            pause_for_user(
                driver,
                "Please log into your Google account in the browser window. "
                "Press Enter when you are on Google Drive.",
                timeout=180,
            )

        # Wait until we are on drive.google.com
        WebDriverWait(driver, 30).until(
            lambda d: "drive.google.com" in d.current_url
        )
        time.sleep(2)

        # ── Find or create the Housing Ads folder ───────────────────────
        _ensure_folder(driver, FOLDER_NAME)
        time.sleep(2)

        # ── Upload via the New → File upload button ─────────────────────
        file_url = _upload_file(driver, str(upload_file.resolve()))
        return file_url

    except Exception as exc:
        print(f"  [Drive Upload Error] {exc}")
        pause_for_user(
            driver,
            f"Automatic upload failed ({exc}). "
            "Please upload the file manually: drag-and-drop "
            f"'{TRACKER_FILE}' into the Google Drive window. Press Enter when done.",
            timeout=300,
        )
        return driver.current_url

    finally:
        time.sleep(2)
        driver.quit()


def _ensure_folder(driver: webdriver.Chrome, folder_name: str):
    """Navigate into the Housing Ads folder, creating it if needed."""
    try:
        # Search for the folder
        search_box = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[placeholder*='Search'], input[aria-label*='Search']"))
        )
        search_box.clear()
        search_box.send_keys(folder_name)
        search_box.send_keys(Keys.RETURN)
        time.sleep(3)

        # Check if folder found
        folders = driver.find_elements(By.CSS_SELECTOR, "[data-target='doc'], [aria-label*='folder']")
        for f in folders:
            if folder_name.lower() in (f.get_attribute("aria-label") or f.text or "").lower():
                f.click()
                time.sleep(2)
                return

        # Folder not found – create it
        driver.get(DRIVE_URL)
        time.sleep(2)
        _create_folder(driver, folder_name)

    except Exception:
        # Just stay on Drive root if folder navigation fails
        driver.get(DRIVE_URL)
        time.sleep(2)


def _create_folder(driver: webdriver.Chrome, folder_name: str):
    """Create a new folder in Google Drive."""
    try:
        new_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "[aria-label='New'], button[aria-label*='New'], div[data-tooltip='New']"))
        )
        new_btn.click()
        time.sleep(1)

        folder_opt = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "[aria-label='New folder'], [data-id='new-folder']"))
        )
        folder_opt.click()
        time.sleep(1)

        # Type folder name
        name_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[aria-label*='folder name']"))
        )
        name_input.clear()
        name_input.send_keys(folder_name)
        name_input.send_keys(Keys.RETURN)
        time.sleep(2)

    except Exception as e:
        print(f"  [Folder create] {e} – uploading to Drive root")


def _upload_file(driver: webdriver.Chrome, file_path: str) -> str:
    """Click New → File upload and select the file."""
    try:
        new_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "[aria-label='New'], button[data-tooltip='New'], div[guidedhelpid='new_menu_button']"))
        )
        new_btn.click()
        time.sleep(1.5)

        upload_opt = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "[aria-label='File upload'], [id*='file-upload'], [data-id='file-upload']"))
        )
        upload_opt.click()
        time.sleep(1.5)

        # Send file path to the hidden file input
        file_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
        )
        file_input.send_keys(file_path)
        time.sleep(5)   # wait for upload to complete

        print(f"  [Drive] File uploaded: {Path(file_path).name}")
        return driver.current_url

    except Exception as exc:
        raise RuntimeError(f"File upload via UI failed: {exc}")
