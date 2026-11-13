"""Constants for Matpriskollen."""

from __future__ import annotations

DOMAIN = "matpriskollen"
VERSION = "0.3.1"

BASE_URL = "https://matpriskollen.se"
USER_AGENT = f"HomeAssistant-Matpriskollen/{VERSION} (+https://github.com/TimmyUll/ha-matpriskollen)"

CONF_CITIES = "cities"
CONF_MAX_PRICE = "max_price"
CONF_NAME = "name"
CONF_NOTIFY = "notify"
CONF_PRODUCTS = "products"
CONF_STORE_LINKS = "store_links"
CONF_STORES = "stores"
CONF_UPDATE_HOURS = "update_hours"

SUBENTRY_PRODUCT = "product"

DEFAULT_UPDATE_HOURS = 24
MIN_UPDATE_HOURS = 6

# Pause between page loads so the site is not loaded in bursts.
REQUEST_DELAY = 1.5

# Used when the chain list on /mataffarer cannot be read.
DEFAULT_CHAINS = [
    "ica",
    "coop",
    "willys",
    "lidl",
    "hemkop",
    "city-gross",
    "tempo",
    "dollarstore",
    "rusta",
]

CHAIN_NAMES = {
    "ica": "ICA",
    "coop": "Coop",
    "willys": "Willys",
    "lidl": "Lidl",
    "hemkop": "Hemköp",
    "city-gross": "City Gross",
    "tempo": "Tempo",
    "dollarstore": "Dollarstore",
    "rusta": "Rusta",
}
