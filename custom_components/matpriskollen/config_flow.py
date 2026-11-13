"""Config flow (stores), options flow, and a subentry flow per product."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .api import MatpriskollenClient, MatpriskollenError
from .const import (
    CONF_CITIES,
    CONF_MAX_PRICE,
    CONF_NAME,
    CONF_NOTIFY,
    CONF_PRODUCTS,
    CONF_STORE_LINKS,
    CONF_STORES,
    CONF_UPDATE_HOURS,
    DEFAULT_UPDATE_HOURS,
    DOMAIN,
    MIN_UPDATE_HOURS,
    SUBENTRY_PRODUCT,
)
from .coordinator import entry_config
from .parse import name_from_slug, store_slug

TITLE = "Matpriskollen"
# Notify services that need more than a title and message.
SKIP_NOTIFY = {"send_message"}


def _clean_list(values: list[str] | str | None) -> list[str]:
    """Strip, drop empty and duplicate entries (case-insensitive)."""
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for v in values or []:
        v = " ".join(str(v).split())
        if v and v.lower() not in (o.lower() for o in out):
            out.append(v)
    return out


def _cities(value: str | None) -> list[str]:
    return _clean_list((value or "").replace(";", ",").split(","))


def _search_schema(hours: int) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_CITIES, default=""): TextSelector(),
            vol.Optional(CONF_STORE_LINKS, default=[]): TextSelector(
                TextSelectorConfig(multiple=True)
            ),
            vol.Required(CONF_UPDATE_HOURS, default=hours): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_UPDATE_HOURS, max=168, step=1, mode=NumberSelectorMode.BOX
                )
            ),
        }
    )


def _stores_schema(found: dict[str, str], selected: list[str]) -> vol.Schema:
    options = [
        SelectOptionDict(value=slug, label=name)
        for slug, name in sorted(found.items(), key=lambda kv: kv[1].lower())
    ]
    return vol.Schema(
        {
            vol.Required(CONF_STORES, default=selected): SelectSelector(
                SelectSelectorConfig(
                    options=options, multiple=True, mode=SelectSelectorMode.LIST
                )
            )
        }
    )


async def _search(
    hass: HomeAssistant, user_input: dict[str, Any], known: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """Stores found from towns and links, plus form errors."""
    errors: dict[str, str] = {}
    found: dict[str, str] = {}
    for link in _clean_list(user_input.get(CONF_STORE_LINKS)):
        if slug := store_slug(link):
            found[slug] = known.get(slug, name_from_slug(slug))
        else:
            errors[CONF_STORE_LINKS] = "bad_link"
    if errors:
        return found, errors

    if cities := _cities(user_input.get(CONF_CITIES)):
        client = MatpriskollenClient(async_get_clientsession(hass))
        try:
            for slug, name in (await client.async_find_stores(cities)).items():
                found.setdefault(slug, known.get(slug, name))
        except MatpriskollenError:
            errors["base"] = "cannot_connect"
    return found, errors


def _product_schema(
    hass: HomeAssistant, defaults: dict[str, Any], name_key: str | None
) -> vol.Schema:
    """Name (when adding), price limit and notify targets."""
    services = sorted(
        f"notify.{s}"
        for s in hass.services.async_services_for_domain("notify")
        if s not in SKIP_NOTIFY
    )
    services += [s for s in defaults.get(CONF_NOTIFY, []) if s not in services]
    schema: dict = {}
    if name_key == CONF_NAME:
        schema[vol.Required(CONF_NAME)] = TextSelector()
    elif name_key:
        schema[vol.Optional(name_key, default="")] = TextSelector()
    schema[vol.Optional(CONF_MAX_PRICE)] = NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=10000,
            step=0.5,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="kr/st",
        )
    )
    schema[vol.Optional(CONF_NOTIFY, default=[])] = SelectSelector(
        SelectSelectorConfig(
            options=services, multiple=True, mode=SelectSelectorMode.DROPDOWN
        )
    )
    return vol.Schema(schema)


def _product_data(name: str, user_input: dict[str, Any]) -> dict[str, Any]:
    max_price = user_input.get(CONF_MAX_PRICE)
    return {
        CONF_NAME: name,
        CONF_MAX_PRICE: float(max_price) if max_price not in (None, "") else None,
        CONF_NOTIFY: list(user_input.get(CONF_NOTIFY, [])),
    }


class MatpriskollenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Matpriskollen: choose stores."""

    VERSION = 1

    def __init__(self) -> None:
        self._input: dict[str, Any] = {}
        self._found: dict[str, str] = {}
        self._stores: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._input = user_input
            self._found, errors = await _search(self.hass, user_input, {})
            if not errors and not self._found:
                errors["base"] = "no_stores"
            if not errors:
                return await self.async_step_stores()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _search_schema(DEFAULT_UPDATE_HOURS), user_input
            ),
            errors=errors,
        )

    async def async_step_stores(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            stores = {
                slug: self._found[slug]
                for slug in user_input[CONF_STORES]
                if slug in self._found
            }
            if stores:
                self._stores = stores
                return await self.async_step_products()
        return self.async_show_form(
            step_id="stores",
            data_schema=_stores_schema(self._found, list(self._found)),
            errors={"base": "no_stores_selected"} if user_input is not None else {},
            description_placeholders={"count": str(len(self._found))},
        )

    async def async_step_products(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First products to follow, comma-separated, with one price limit and notify list."""
        if user_input is not None:
            names = _cities(user_input.get(CONF_PRODUCTS))
            return self.async_create_entry(
                title=TITLE,
                data={CONF_STORES: self._stores},
                options={CONF_UPDATE_HOURS: int(self._input[CONF_UPDATE_HOURS])},
                subentries=[
                    {
                        "subentry_type": SUBENTRY_PRODUCT,
                        "title": name,
                        "data": _product_data(name, user_input),
                        "unique_id": None,
                    }
                    for name in names
                ],
            )
        return self.async_show_form(
            step_id="products",
            data_schema=_product_schema(self.hass, {}, CONF_PRODUCTS),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MatpriskollenOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_PRODUCT: ProductSubentryFlow}


class MatpriskollenOptionsFlow(OptionsFlow):
    """Change stores and how often pages are read."""

    def __init__(self) -> None:
        self._input: dict[str, Any] = {}
        self._found: dict[str, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        cfg = entry_config(self.config_entry)
        current: dict[str, str] = dict(cfg.get(CONF_STORES, {}))
        errors: dict[str, str] = {}
        if user_input is not None:
            self._input = user_input
            new, errors = await _search(self.hass, user_input, current)
            if not errors:
                self._found = {**current, **new}
                if self._found:
                    return await self.async_step_stores()
                errors["base"] = "no_stores"
        hours = int(cfg.get(CONF_UPDATE_HOURS, DEFAULT_UPDATE_HOURS))
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _search_schema(hours), user_input
            ),
            errors=errors,
        )

    async def async_step_stores(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            stores = {
                slug: self._found[slug]
                for slug in user_input[CONF_STORES]
                if slug in self._found
            }
            if stores:
                return self.async_create_entry(
                    data={
                        CONF_STORES: stores,
                        CONF_UPDATE_HOURS: int(self._input[CONF_UPDATE_HOURS]),
                    }
                )
        return self.async_show_form(
            step_id="stores",
            data_schema=_stores_schema(self._found, list(self._found)),
            errors={"base": "no_stores_selected"} if user_input is not None else {},
            description_placeholders={"count": str(len(self._found))},
        )


class ProductSubentryFlow(ConfigSubentryFlow):
    """Add or change a product: name, price limit and who gets notified."""

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        name_key = CONF_NAME if self.source == "user" else None
        return self.add_suggested_values_to_schema(
            _product_schema(self.hass, defaults, name_key), defaults
        )

    @staticmethod
    def _data(name: str, user_input: dict[str, Any]) -> dict[str, Any]:
        return _product_data(name, user_input)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = " ".join(str(user_input.get(CONF_NAME, "")).split())
            existing = {
                s.data.get(CONF_NAME, s.title).lower()
                for s in self._get_entry().subentries.values()
                if s.subentry_type == SUBENTRY_PRODUCT
            }
            if not name:
                errors[CONF_NAME] = "no_name"
            elif name.lower() in existing:
                errors[CONF_NAME] = "already_added"
            else:
                return self.async_create_entry(
                    title=name, data=self._data(name, user_input)
                )
        return self.async_show_form(
            step_id="user", data_schema=self._schema(user_input or {}), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        name = subentry.data.get(CONF_NAME, subentry.title)
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, data=self._data(name, user_input)
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema(dict(subentry.data)),
            description_placeholders={"product": name},
        )
