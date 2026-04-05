"""
Central configuration for Housing Ads Automation.
All housing sites for India/Hyderabad and app-level settings.
"""

# ---------------------------------------------------------------------------
# Google Sheets settings
# ---------------------------------------------------------------------------
SPREADSHEET_TITLE = "Housing Ads Tracker - Hyderabad"

SHEET_NAMES = {
    "sites": "Sites & Credentials",
    "property1": "Property 1 Status",
    "property2": "Property 2 Status",
    "contacts": "Contacts",
    "dashboard": "Dashboard",
}

# ---------------------------------------------------------------------------
# Housing sites list (India – Hyderabad focus)
# ---------------------------------------------------------------------------
HOUSING_SITES = [
    {
        "id": "magicbricks",
        "name": "MagicBricks",
        "url": "https://www.magicbricks.com",
        "post_url": "https://www.magicbricks.com/sell/post-property.html",
        "free_listing": True,
        "tier": "Tier-1",
    },
    {
        "id": "99acres",
        "name": "99acres",
        "url": "https://www.99acres.com",
        "post_url": "https://www.99acres.com/seller/postProperty.php",
        "free_listing": True,
        "tier": "Tier-1",
    },
    {
        "id": "housing",
        "name": "Housing.com",
        "url": "https://housing.com",
        "post_url": "https://housing.com/post-property",
        "free_listing": True,
        "tier": "Tier-1",
    },
    {
        "id": "nobroker",
        "name": "NoBroker",
        "url": "https://www.nobroker.in",
        "post_url": "https://www.nobroker.in/post-your-property",
        "free_listing": True,
        "tier": "Tier-1",
    },
    {
        "id": "olx",
        "name": "OLX",
        "url": "https://www.olx.in",
        "post_url": "https://www.olx.in/post-ad",
        "free_listing": True,
        "tier": "Tier-1",
    },
    {
        "id": "quikr",
        "name": "Quikr",
        "url": "https://www.quikr.com",
        "post_url": "https://www.quikr.com/post-ads",
        "free_listing": True,
        "tier": "Tier-2",
    },
    {
        "id": "commonfloor",
        "name": "CommonFloor",
        "url": "https://www.commonfloor.com",
        "post_url": "https://www.commonfloor.com/post-property",
        "free_listing": True,
        "tier": "Tier-2",
    },
    {
        "id": "sulekha",
        "name": "Sulekha",
        "url": "https://www.sulekha.com",
        "post_url": "https://realestate.sulekha.com/sell-property",
        "free_listing": True,
        "tier": "Tier-2",
    },
    {
        "id": "proptiger",
        "name": "PropTiger",
        "url": "https://www.proptiger.com",
        "post_url": "https://www.proptiger.com/post-property",
        "free_listing": True,
        "tier": "Tier-2",
    },
    {
        "id": "makaan",
        "name": "Makaan.com",
        "url": "https://www.makaan.com",
        "post_url": "https://www.makaan.com/post-property",
        "free_listing": True,
        "tier": "Tier-2",
    },
    {
        "id": "squareyards",
        "name": "Square Yards",
        "url": "https://www.squareyards.com",
        "post_url": "https://www.squareyards.com/sell",
        "free_listing": True,
        "tier": "Tier-2",
    },
    {
        "id": "indiaproperty",
        "name": "India Property",
        "url": "https://www.indiaproperty.com",
        "post_url": "https://www.indiaproperty.com/property/post",
        "free_listing": True,
        "tier": "Tier-3",
    },
    {
        "id": "nestoria",
        "name": "Nestoria India",
        "url": "https://www.nestoria.in",
        "post_url": "https://www.nestoria.in/post",
        "free_listing": True,
        "tier": "Tier-3",
    },
    {
        "id": "propertywala",
        "name": "PropertyWala",
        "url": "https://www.propertywala.com",
        "post_url": "https://www.propertywala.com/free-property-ads",
        "free_listing": True,
        "tier": "Tier-3",
    },
    {
        "id": "homeonline",
        "name": "HomeOnline",
        "url": "https://www.homeonline.com",
        "post_url": "https://www.homeonline.com/post-property",
        "free_listing": True,
        "tier": "Tier-3",
    },
    {
        "id": "facebook",
        "name": "Facebook Marketplace",
        "url": "https://www.facebook.com/marketplace",
        "post_url": "https://www.facebook.com/marketplace/create/item",
        "free_listing": True,
        "tier": "Social",
    },
    {
        "id": "instagram",
        "name": "Instagram (Manual)",
        "url": "https://www.instagram.com",
        "post_url": "https://www.instagram.com",
        "free_listing": True,
        "tier": "Social",
    },
    {
        "id": "jll",
        "name": "JLL India",
        "url": "https://www.jll.co.in",
        "post_url": "https://www.jll.co.in/en/sell-a-property",
        "free_listing": False,
        "tier": "Premium",
    },
    {
        "id": "anarock",
        "name": "Anarock",
        "url": "https://www.anarock.com",
        "post_url": "https://www.anarock.com/sell",
        "free_listing": False,
        "tier": "Premium",
    },
]

# Columns for the Sites & Credentials sheet
SITES_SHEET_HEADERS = [
    "Site ID",
    "Site Name",
    "URL",
    "Post URL",
    "Tier",
    "Free Listing",
    "Username / Email",
    "Password",
    "Phone (if needed)",
    "API Key (if any)",
    "Account Status",
    "Notes",
]

# Columns for each Property Status sheet
PROPERTY_SHEET_HEADERS = [
    "Site ID",
    "Site Name",
    "Ad Posted Date",
    "Ad URL",
    "Ad Title",
    "Status",          # Active / Pending / Expired / Failed
    "Views",
    "Clicks",
    "Inquiries",
    "Last Scraped",
    "Ad Expiry Date",
    "Renewal Needed",
    "Notes",
]

# Columns for Contacts sheet
CONTACTS_SHEET_HEADERS = [
    "Date",
    "Time",
    "Property",        # Property 1 / Property 2
    "Site",
    "Contact Name",
    "Phone",
    "Email",
    "Message / Query",
    "Follow-up Status",   # New / Interested / Very Interested / Negotiating / Closed / Not Interested
    "Last Follow-up Date",
    "Next Follow-up Date",
    "Asking Price",
    "Offered Price",
    "Notes",
]

# Ad posting status values
AD_STATUS = {
    "pending": "Pending",
    "active": "Active",
    "failed": "Failed",
    "expired": "Expired",
    "manual": "Manual Required",
}

FOLLOW_UP_STATUS = [
    "New",
    "Interested",
    "Very Interested",
    "Negotiating",
    "Closed / Sold",
    "Not Interested",
    "No Response",
]
