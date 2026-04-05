"""
Parse property details from HTML ad files.
Reads <meta> tags and body content to extract structured property data.
"""

from bs4 import BeautifulSoup
from pathlib import Path


def parse_property_html(html_path: str) -> dict:
    """
    Parse an HTML ad file and return a dict of property details.
    Reads meta tags first, then falls back to body text scraping.
    """
    path = Path(html_path)
    if not path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    def meta(name: str, default: str = "") -> str:
        tag = soup.find("meta", attrs={"name": name})
        return tag["content"].strip() if tag and tag.get("content") else default

    data = {
        "title":          meta("property-title"),
        "type":           meta("property-type"),
        "price":          meta("property-price"),
        "price_num":      meta("property-price-num"),
        "area":           meta("property-area"),
        "area_unit":      meta("property-area-unit", "sq.ft"),
        "bhk":            meta("property-bhk"),
        "floor":          meta("property-floor"),
        "total_floors":   meta("property-total-floors"),
        "location":       meta("property-location"),
        "city":           meta("property-city"),
        "state":          meta("property-state"),
        "pincode":        meta("property-pincode"),
        "age":            meta("property-age"),
        "parking":        meta("property-parking"),
        "facing":         meta("property-facing"),
        "furnishing":     meta("property-furnishing"),
        "description":    meta("property-description"),
        "amenities":      meta("property-amenities"),
        "contact_name":   meta("property-contact-name"),
        "contact_phone":  meta("property-contact-phone"),
        "contact_email":  meta("property-contact-email"),
        "html_file":      str(path.resolve()),
        "html_content":   html,
    }

    # Parse amenities into a list
    if data["amenities"]:
        data["amenities_list"] = [a.strip() for a in data["amenities"].split(",")]
    else:
        data["amenities_list"] = []

    # Build a full address string
    parts = [p for p in [data["location"], data["city"], data["state"], data["pincode"]] if p]
    data["full_address"] = ", ".join(parts)

    return data


def validate_property_data(data: dict) -> list[str]:
    """Return a list of missing required fields."""
    required = [
        "title", "type", "price_num", "area", "bhk",
        "location", "city", "description",
        "contact_name", "contact_phone",
    ]
    missing = [f for f in required if not data.get(f) or data[f] in ("YOUR NAME", "YOUR PHONE", "YOUR EMAIL", "")]
    return missing
