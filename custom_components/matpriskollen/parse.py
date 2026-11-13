"""Read offers and store links from Matpriskollen pages.

Kept free of Home Assistant imports so it can be tested on its own.

A store page lists the week's offers. Its visible text runs together like
"Energidryck, burkCelsius, 25-35,5 cl3 för 36,00Coop Tyresö": product name,
"brand, size", price and store name, with no separators between them.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import get_close_matches

from bs4 import BeautifulSoup

UPPER = "A-ZÅÄÖÉÜ"
PRICE = r"(?:\d+ för )?\d{1,3}(?:[  ]?\d{3})*,\d\d(?:/[a-zåäö]+)?"
PRICE_RE = re.compile(
    r"^(?:(?P<qty>\d+) för )?(?P<kr>\d{1,3}(?:[  ]?\d{3})*),(?P<ore>\d\d)(?:/(?P<unit>[a-zåäö]+))?$"
)
# Units that mean "per item or package". Weight and volume prices (/kg, /l) are skipped.
ITEM_UNITS = {"st", "frp", "förp", "pkt", "flak"}
# "3 för 2" (take three, pay for two) when the store shows it next to the item price.
TAKE_PAY_RE = re.compile(r"(\d+) för (\d+)\s*$")
PACK_RE = re.compile(r"(\d+) ?(?:[x×] ?\d|-?pack)", re.IGNORECASE)

STORE_LINK_RE = re.compile(
    r"^(?:https?://(?:www\.)?matpriskollen\.se)?/butiker/([a-z0-9-]+--[0-9a-f-]{36})/?$"
)
CHAIN_LINK_RE = re.compile(
    r"^(?:https?://(?:www\.)?matpriskollen\.se)?/mataffarer/([a-z0-9-]+)/?$"
)
STORE_SLUG_RE = re.compile(r"/butiker/([a-z0-9-]+--[0-9a-f-]{36})")


@dataclass(frozen=True)
class Offer:
    """One offer on a product in one store."""

    price: str
    size: str
    unit_price: float | None
    pack: int | None = None

    @property
    def text(self) -> str:
        """Price as shown, with the pack size when the price is for a whole pack."""
        return f"{self.price} ({self.pack} st)" if self.pack else self.price

    def as_dict(self) -> dict:
        return asdict(self)


def _variants(product: str) -> list[str]:
    product = product.strip()
    forms = {
        product,
        product.lower(),
        product.upper(),
        product.capitalize(),
        product.title(),
    }
    return sorted(forms, key=len, reverse=True)


def offer_pattern(product: str) -> re.Pattern[str]:
    """Regex for "<product>..., <size><price>" followed by the next capitalised word."""
    alt = "|".join(re.escape(v) for v in _variants(product))
    return re.compile(rf"(?:{alt})[^,]*, ([^{UPPER}]*?)({PRICE})(?=[{UPPER}]|$)")


def unit_price(price: str, size: str) -> tuple[float | None, int | None]:
    """Price per item, and the pack size it was divided by (if any)."""
    m = PRICE_RE.match(price.strip())
    if not m:
        return None, None
    unit = m["unit"]
    if unit and unit not in ITEM_UNITS:
        return None, None
    amount = int(re.sub(r"\D", "", m["kr"])) + int(m["ore"]) / 100
    if m["qty"]:
        return round(amount / max(int(m["qty"]), 1), 2), None
    pack = None
    if unit != "st" and (p := PACK_RE.search(size)):
        pack = int(p[1]) if int(p[1]) > 1 else None
    return round(amount / (pack or 1), 2), pack


def find_offers(text: str, product: str) -> list[Offer]:
    """All offers on a product in a store page's text, without duplicates."""
    offers: list[Offer] = []
    for size, price in offer_pattern(product).findall(text):
        size = " ".join(size.split())
        take_pay = TAKE_PAY_RE.search(size)
        if take_pay:
            size = size[: take_pay.start()].strip()
        each, pack = unit_price(price, size)
        if take_pay and each is not None:
            take, pay = int(take_pay[1]), int(take_pay[2])
            if 0 < pay < take:
                each = round(each * pay / take, 2)
                price = f"{take} för {pay}, {price}"
        offer = Offer(price=price, size=size, unit_price=each, pack=pack)
        if offer not in offers:
            offers.append(offer)
    return offers


def page_text(html: str) -> tuple[str | None, str]:
    """Store name (from the heading) and the visible text of a store page."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    h1 = soup.find("h1")
    name = h1.get_text(" ", strip=True) if h1 else None
    body = soup.body or soup
    return name or None, body.get_text()


def store_links(html: str) -> dict[str, str]:
    """Store slug -> link text, for every store link on a page."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        if m := STORE_LINK_RE.match(a["href"]):
            text = a.get_text(" ", strip=True)
            if m[1] not in found or (text and not found[m[1]]):
                found[m[1]] = text
    return found


def chain_links(html: str) -> list[str]:
    """Chain slugs linked from the chain overview page."""
    soup = BeautifulSoup(html, "html.parser")
    chains: list[str] = []
    for a in soup.find_all("a", href=True):
        if (m := CHAIN_LINK_RE.match(a["href"])) and m[1] not in chains:
            chains.append(m[1])
    return chains


def store_slug(value: str) -> str | None:
    """Slug from a store link, or from the slug itself."""
    value = value.strip()
    if m := STORE_SLUG_RE.search(value):
        return m[1]
    if re.fullmatch(r"[a-z0-9-]+--[0-9a-f-]{36}", value):
        return value
    return None


def name_from_slug(slug: str) -> str:
    """Readable fallback name, e.g. "coop-tyreso--…" -> "Coop Tyreso"."""
    return slug.split("--")[0].replace("-", " ").title()


def city_slug(city: str) -> str:
    """URL form of a town name, e.g. "Tyresö" -> "tyreso"."""
    city = city.strip().lower()
    for a, b in (("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e"), ("ü", "u")):
        city = city.replace(a, b)
    city = re.sub(r"[^a-z0-9]+", "-", city)
    return city.strip("-")


def format_kr(value: float) -> str:
    """12.0 -> "12,00"."""
    return f"{value:.2f}".replace(".", ",")


WORD_RE = re.compile(rf"[{UPPER}]?[a-zåäöéü]+(?:-[{UPPER}a-zåäöéü]+)*|[{UPPER}]{{2,}}")


def similar_names(texts: list[str], name: str, limit: int = 3) -> list[str]:
    """Words in the store pages that look like a misspelling of the name."""
    words: dict[str, str] = {}
    for text in texts:
        for word in WORD_RE.findall(text):
            if len(word) > 2:
                words.setdefault(word.lower(), word)
    target = name.lower()
    matches = get_close_matches(target, list(words), n=limit + 1, cutoff=0.75)
    return [words[m] for m in matches if m != target][:limit]
