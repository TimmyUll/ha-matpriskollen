"""Tests for the config flow, options and sensors."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.matpriskollen.const import DOMAIN

BASE = "https://matpriskollen.se"
COOP = "coop-tyreso--09fdbb65-bb43-45c0-ba22-306af46244ac"
ICA = "ica-kvantum-tyreso--88fa9cd5-019b-45f7-a194-ec266f443bda"
WILLYS = "willys-tyreso--bab1d36d-7f87-4092-aba1-eaa0c67b3fd2"


def _store_page(name: str, offers: list[tuple[str, str, str]]) -> str:
    rows = "".join(
        f"<li><p>Energidryck, burk</p><p>{brand}</p><p>{price}</p><p>{name}</p></li>"
        for brand, _, price in offers
    )
    return f"<html><body><h1>{name}</h1><ul>{rows}</ul></body></html>"


def _mock_site(aioclient_mock):
    aioclient_mock.get(
        f"{BASE}/mataffarer",
        text='<a href="/mataffarer/ica">ICA</a><a href="/mataffarer/coop">Coop</a><a href="/mataffarer/willys">W</a>',
    )
    aioclient_mock.get(
        f"{BASE}/mataffarer/ica/tyreso", text=f'<a href="/butiker/{ICA}">Tyresö</a>'
    )
    aioclient_mock.get(
        f"{BASE}/mataffarer/coop/tyreso", text=f'<a href="/butiker/{COOP}">Tyresö</a>'
    )
    aioclient_mock.get(f"{BASE}/mataffarer/willys/tyreso", status=404)
    aioclient_mock.get(
        f"{BASE}/butiker/{COOP}",
        text=_store_page("Coop Tyresö", [("Celsius, 25-35,5 cl", "", "3 för 36,00")]),
    )
    aioclient_mock.get(
        f"{BASE}/butiker/{ICA}",
        text=_store_page(
            "ICA Kvantum Tyresö",
            [
                ("Celsius, 35,5 cl", "", "2 för 25,00"),
                ("Red Bull, 25 cl", "", "2 för 22,00"),
            ],
        ),
    )
    aioclient_mock.get(
        f"{BASE}/butiker/{WILLYS}", text=_store_page("Willys Tyresö", [])
    )


async def _add_product(hass, entry, name, max_price=None, notify=None):
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "product"), context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    data = {"name": name, "notify": notify or []}
    if max_price is not None:
        data["max_price"] = max_price
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], data
    )
    if result.get("step_id") in ("found", "mentioned", "not_found"):
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], {"name": name}
        )
    await hass.async_block_till_done()
    return result


async def test_config_flow_products_and_sensors(
    hass: HomeAssistant, aioclient_mock
) -> None:
    _mock_site(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cities": "Tyresö", "store_links": [], "update_hours": 24}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "stores"
    assert result["description_placeholders"] == {"count": "2"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"stores": [COOP, ICA]}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "products"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"products": "Celsius, Nocco, celsius", "max_price": 12.5, "notify": []},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["stores"] == {COOP: "Coop Tyresö", ICA: "ICA Tyresö"}
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert sorted(s.title for s in entry.subentries.values()) == ["Celsius", "Nocco"]
    assert hass.states.get("sensor.matpriskollen_last_fetch") is not None
    dup = await _add_product(hass, entry, "celsius")
    assert dup["errors"] == {"name": "already_added"}

    price = hass.states.get("sensor.celsius_best_price")
    assert price is not None
    assert float(price.state) == 12.0
    assert price.attributes["store"] == "Coop Tyresö"
    assert [o["store"] for o in price.attributes["offers"]] == [
        "Coop Tyresö",
        "ICA Kvantum Tyresö",
    ]
    assert (
        hass.states.get("sensor.celsius_best_offer").state
        == "12,00 kr/st på Coop Tyresö (3 för 36,00)"
    )
    assert hass.states.get("binary_sensor.celsius_under_price_limit").state == "on"
    assert hass.states.get("sensor.nocco_best_price").state == "unknown"
    assert hass.states.get("sensor.nocco_best_offer").state == "Inget extrapris"
    assert hass.states.get("binary_sensor.nocco_under_price_limit").state == "off"


async def test_notify_once_and_reconfigure(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_site(aioclient_mock)
    calls: list[ServiceCall] = []

    async def _notify(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("notify", "mobile_app_phone", _notify)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Matpriskollen",
        data={"stores": {COOP: "Coop Tyresö", ICA: "ICA Tyresö"}},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await _add_product(hass, entry, "Celsius", 12.5, ["notify.mobile_app_phone"])
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["title"] == "Celsius på extrapris"
    assert "12,00 kr/st på Coop Tyresö" in calls[0].data["message"]
    assert "12,50 kr/st på ICA Kvantum Tyresö" in calls[0].data["message"]
    assert hass.states.get("binary_sensor.celsius_under_price_limit").state == "on"

    # A new fetch with the same offers sends nothing new.
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(calls) == 1

    # Lower the limit below every offer.
    sub = next(iter(entry.subentries.values()))
    result = await entry.start_subentry_reconfigure_flow(hass, sub.subentry_id)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"max_price": 5, "notify": ["notify.mobile_app_phone"]}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.celsius_under_price_limit").state == "off"
    assert len(calls) == 1


async def test_bad_link(hass: HomeAssistant, aioclient_mock) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cities": "", "store_links": [], "update_hours": 24}
    )
    assert result["errors"] == {"base": "no_stores"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"cities": "", "store_links": ["https://example.com"], "update_hours": 24},
    )
    assert result["errors"] == {"store_links": "bad_link"}


async def test_options_add_link(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_site(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Matpriskollen", data={"stores": {COOP: "Coop Tyresö"}}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _add_product(hass, entry, "Celsius")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"cities": "", "store_links": [f"{BASE}/butiker/{WILLYS}"], "update_hours": 12},
    )
    assert result["step_id"] == "stores"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"stores": [COOP, WILLYS]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("sensor.celsius_best_price").attributes["stores_total"] == 2
    assert er.async_get(hass).async_get("sensor.celsius_best_price") is not None


async def test_unreachable_site_retries(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE}/butiker/{COOP}", status=500)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Matpriskollen", data={"stores": {COOP: "Coop Tyresö"}}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY


async def test_setup_without_products(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_site(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"cities": "", "store_links": [f"{BASE}/butiker/{COOP}"], "update_hours": 24},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"stores": [COOP]}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"products": "", "notify": []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert not hass.config_entries.async_entries(DOMAIN)[0].subentries


async def test_add_product_checks_name(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_site(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Matpriskollen",
        data={"stores": {COOP: "Coop Tyresö", ICA: "ICA Tyresö"}},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    flows = hass.config_entries.subentries
    result = await flows.async_init(
        (entry.entry_id, "product"), context={"source": config_entries.SOURCE_USER}
    )
    result = await flows.async_configure(
        result["flow_id"], {"name": "Celcius", "max_price": 12, "notify": []}
    )
    assert result["step_id"] == "not_found"
    assert result["description_placeholders"]["similar"] == "Celsius"

    # Correct the spelling on the check form.
    result = await flows.async_configure(result["flow_id"], {"name": "Celsius"})
    assert result["step_id"] == "found"
    assert result["description_placeholders"]["count"] == "2"
    assert result["description_placeholders"]["best"] == (
        "12,00 kr/st på Coop Tyresö (3 för 36,00)"
    )
    result = await flows.async_configure(result["flow_id"], {"name": "Celsius"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    sub = next(iter(entry.subentries.values()))
    assert sub.title == "Celsius"
    assert sub.data["max_price"] == 12.0
    assert hass.states.get("binary_sensor.celsius_under_price_limit").state == "on"
