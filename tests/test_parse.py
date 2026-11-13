"""Tests for reading offers and links from page text."""

from custom_components.matpriskollen.parse import (
    city_slug,
    find_offers,
    page_text,
    store_links,
    store_slug,
    unit_price,
)

# Visible text of a store page runs together like this.
TEXT = (
    "Dressing/SåsLohmanders, 2,5 dl2 för 49,00Coop Tyresö"
    "Energidryck, burkCelsius, 25-35,5 cl3 för 36,00Coop Tyresö"
    "Fish & Crisp Fish BurgerFindus, 230 g25,00/frpCoop Tyresö"
    "Energidryck, flakNOCCO, 24x33 cl240,00/flakCoop Tyresö"
    "Energidryck, burkNocco, 33 cl15,90/stCoop Tyresö"
    "LösviktsgodisNocco godis, hg9,90/kgCoop Tyresö"
)


def test_find_celsius():
    offers = find_offers(TEXT, "Celsius")
    assert len(offers) == 1
    assert offers[0].price == "3 för 36,00"
    assert offers[0].size == "25-35,5 cl"
    assert offers[0].unit_price == 12.0
    assert offers[0].text == "3 för 36,00"


def test_find_nocco_flak_and_can():
    offers = find_offers(TEXT, "nocco")
    by_price = {o.price: o for o in offers}
    assert by_price["240,00/flak"].unit_price == 10.0
    assert by_price["240,00/flak"].text == "240,00/flak (24 st)"
    assert by_price["15,90/st"].unit_price == 15.9
    # Weight price has no price per item
    assert by_price["9,90/kg"].unit_price is None


def test_no_offer():
    assert find_offers(TEXT, "Red Bull") == []


def test_unit_price():
    assert unit_price("2 för 25,00", "35,5 cl") == (12.5, None)
    assert unit_price("19,90", "") == (19.9, None)
    assert unit_price("199,00/förp", "24-pack") == (8.29, 24)
    assert unit_price("1 299,00", "") == (1299.0, None)
    assert unit_price("29,90/l", "") == (None, None)


def test_page_text_and_links():
    html = """<html><head><title>x</title><script>var a = "Celsius, 1 cl9,00X";</script></head>
    <body><h1>Coop Tyresö</h1><div><span>Energidryck, burk</span><span>Celsius, 25-35,5 cl</span>
    <span>3 för 36,00</span><span>Coop Tyresö</span></div>
    <a href="/butiker/ica-kvantum-tyreso--88fa9cd5-019b-45f7-a194-ec266f443bda">Tyresö</a>
    <a href="https://matpriskollen.se/butiker/ica-supermarket-trollbacken--8b025714-ff87-4e76-a506-0091def9de7e">Trollbäcken</a>
    <a href="/butiker">Butiker</a></body></html>"""
    name, text = page_text(html)
    assert name == "Coop Tyresö"
    assert [o.price for o in find_offers(text, "Celsius")] == ["3 för 36,00"]
    assert store_links(html) == {
        "ica-kvantum-tyreso--88fa9cd5-019b-45f7-a194-ec266f443bda": "Tyresö",
        "ica-supermarket-trollbacken--8b025714-ff87-4e76-a506-0091def9de7e": "Trollbäcken",
    }


def test_slugs():
    assert city_slug(" Tyresö ") == "tyreso"
    assert city_slug("Upplands Väsby") == "upplands-vasby"
    slug = "coop-tyreso--09fdbb65-bb43-45c0-ba22-306af46244ac"
    assert store_slug(f"https://matpriskollen.se/butiker/{slug}") == slug
    assert store_slug(slug) == slug
    assert store_slug("https://example.com") is None
