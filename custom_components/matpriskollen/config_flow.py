"""Config flow (stores), options flow, and a subentry flow per product."""

from __future__ import annotations

import asyncio
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
from homeassistant.util import dt as dt_util

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
    REQUEST_DELAY,
    SUBENTRY_PRODUCT,
)
from .coordinator import Lookup, MatpriskollenData, StoreResult, entry_config
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


def _lookup_line(name: str, found: Lookup | None) -> str:
    """One line per product for the check step (Swedish, like the offer texts)."""
    if found is None:
        return f"- **{name}**: kunde inte kontrolleras just nu"
    if found.offers:
        n = len(found.offers)
        return f"- **{name}**: {n} erbjudande{'n' if n != 1 else ''}, billigast {found.offers[0].summary}"
    if found.stores:
        return f"- **{name}**: finns hos {', '.join(found.stores)}, men utan styckpris"
    line = f"- **{name}**: hittades inte denna vecka"
    if found.similar:
        line += f". Menade du {' eller '.join(found.similar)}?"
    return line


class MatpriskollenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Matpriskollen: choose stores."""

    VERSION = 1

    def __init__(self) -> None:
        self._input: dict[str, Any] = {}
        self._found: dict[str, str] = {}
        self._stores: dict[str, str] = {}
        self._product_input: dict[str, Any] = {}
        self._pages: dict[str, StoreResult] = {}
        self._fetch_task: asyncio.Task | None = None

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
            self._product_input = user_input
            if not _cities(user_input.get(CONF_PRODUCTS)):
                return self._create()
            return await self.async_step_fetch()
        return self.async_show_form(
            step_id="products",
            data_schema=_product_schema(self.hass, {}, CONF_PRODUCTS),
        )

    async def async_step_fetch(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Read the chosen store pages once, to check the products against them."""
        if self._fetch_task is None:
            self._fetch_task = self.hass.async_create_task(self._async_fetch_pages())
        if not self._fetch_task.done():
            return self.async_show_progress(
                step_id="fetch",
                progress_action="fetch",
                progress_task=self._fetch_task,
                description_placeholders={"count": str(len(self._stores))},
            )
        return self.async_show_progress_done(next_step_id="products_check")

    async def _async_fetch_pages(self) -> None:
        client = MatpriskollenClient(async_get_clientsession(self.hass))
        for i, (slug, name) in enumerate(self._stores.items()):
            if i:
                await asyncio.sleep(REQUEST_DELAY)
            url = f"https://matpriskollen.se/butiker/{slug}"
            try:
                page = await client.async_store_page(slug)
            except MatpriskollenError:
                self._pages[slug] = StoreResult(name=name, url=url)
                continue
            self._pages[slug] = StoreResult(
                name=page.name or name,
                url=url,
                fetched=dt_util.utcnow(),
                ok=True,
                text=page.text,
            )

    async def async_step_products_check(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show what the store pages say about each product; edit the names to check again."""
        names = _cities(self._product_input.get(CONF_PRODUCTS))
        if user_input is not None:
            new = _cities(user_input.get(CONF_PRODUCTS))
            if [n.lower() for n in new] == [n.lower() for n in names]:
                return self._create()
            self._product_input = {**self._product_input, CONF_PRODUCTS: ", ".join(new)}
            names = new
            if not names:
                return self._create()
        data = MatpriskollenData(stores=self._pages, fetched=dt_util.utcnow())
        lines = [_lookup_line(name, data.lookup(name)) for name in names]
        return self.async_show_form(
            step_id="products_check",
            data_schema=vol.Schema(
                {vol.Optional(CONF_PRODUCTS, default=", ".join(names)): TextSelector()}
            ),
            description_placeholders={"results": "\n".join(lines)},
            last_step=True,
        )

    def _create(self) -> ConfigFlowResult:
        names = _cities(self._product_input.get(CONF_PRODUCTS))
        if self._pages and any(p.ok for p in self._pages.values()):
            # Let the first update use these pages instead of reading them again.
            prefetch = self.hass.data.setdefault(DOMAIN, {}).setdefault("prefetch", {})
            prefetch[frozenset(self._stores)] = self._pages
        return self.async_create_entry(
            title=TITLE,
            data={CONF_STORES: self._stores},
            options={CONF_UPDATE_HOURS: int(self._input[CONF_UPDATE_HOURS])},
            subentries=[
                {
                    "subentry_type": SUBENTRY_PRODUCT,
                    "title": name,
                    "data": _product_data(name, self._product_input),
                    "unique_id": None,
                }
                for name in names
            ],
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

    _pending: dict[str, Any]

    def _name_error(self, name: str) -> str | None:
        existing = {
            s.data.get(CONF_NAME, s.title).lower()
            for s in self._get_entry().subentries.values()
            if s.subentry_type == SUBENTRY_PRODUCT
        }
        if not name:
            return "no_name"
        if name.lower() in existing:
            return "already_added"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = " ".join(str(user_input.get(CONF_NAME, "")).split())
            if error := self._name_error(name):
                errors[CONF_NAME] = error
            else:
                self._pending = {**user_input, CONF_NAME: name}
                return await self.async_step_check()
        return self.async_show_form(
            step_id="user", data_schema=self._schema(user_input or {}), errors=errors
        )

    async def async_step_check(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show what this week's store pages say about the name before adding it."""
        name = self._pending[CONF_NAME]
        errors: dict[str, str] = {}
        if user_input is not None:
            new = " ".join(str(user_input.get(CONF_NAME, "")).split())
            if not new or new == name:
                return self.async_create_entry(
                    title=name, data=_product_data(name, self._pending)
                )
            if error := self._name_error(new):
                errors[CONF_NAME] = error
            else:
                name = self._pending[CONF_NAME] = new

        coordinator = getattr(self._get_entry(), "runtime_data", None)
        found = (
            coordinator.data.lookup(name) if coordinator and coordinator.data else None
        )
        if found is None:
            # No saved pages to check against yet.
            return self.async_create_entry(
                title=name, data=_product_data(name, self._pending)
            )
        placeholders = {"product": name, "count": str(len(found.offers))}
        if found.offers:
            step = "found"
            placeholders["best"] = found.offers[0].summary
            placeholders["stores"] = ", ".join(
                dict.fromkeys(o.store for o in found.offers)
            )
        elif found.stores:
            step = "mentioned"
            placeholders["stores"] = ", ".join(found.stores)
        else:
            step = "not_found"
            placeholders["similar"] = ", ".join(found.similar) or "-"
        schema = vol.Schema({vol.Optional(CONF_NAME, default=name): TextSelector()})
        return self.async_show_form(
            step_id=step,
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
            last_step=True,
        )

    async_step_found = async_step_check
    async_step_mentioned = async_step_check
    async_step_not_found = async_step_check

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
