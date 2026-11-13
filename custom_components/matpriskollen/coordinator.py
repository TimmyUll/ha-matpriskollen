"""Fetch the store pages, find the offers and send notifications."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import MatpriskollenClient, MatpriskollenError
from .const import (
    CONF_MAX_PRICE,
    CONF_NAME,
    CONF_NOTIFY,
    CONF_STORES,
    CONF_UPDATE_HOURS,
    DEFAULT_UPDATE_HOURS,
    DOMAIN,
    MIN_UPDATE_HOURS,
    REQUEST_DELAY,
    SUBENTRY_PRODUCT,
)
from .parse import Offer, find_offers, format_kr

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1
MAX_LINES = 5


def entry_config(entry: ConfigEntry) -> dict:
    """Data with options on top."""
    return {**entry.data, **entry.options}


@dataclass(frozen=True)
class Product:
    """A product to follow, from a subentry."""

    subentry_id: str
    name: str
    max_price: float | None
    notify: tuple[str, ...]

    def qualifies(self, offer: Offer) -> bool:
        """True when the price per item is at or below the limit (or there is no limit)."""
        if offer.unit_price is None:
            return False
        return self.max_price is None or offer.unit_price <= self.max_price


def products_of(entry: ConfigEntry) -> list[Product]:
    """Products from the entry's subentries."""
    products = []
    for sub in entry.subentries.values():
        if sub.subentry_type != SUBENTRY_PRODUCT:
            continue
        max_price = sub.data.get(CONF_MAX_PRICE)
        products.append(
            Product(
                subentry_id=sub.subentry_id,
                name=sub.data.get(CONF_NAME, sub.title),
                max_price=float(max_price) if max_price not in (None, "") else None,
                notify=tuple(sub.data.get(CONF_NOTIFY, [])),
            )
        )
    return products


@dataclass
class StoreResult:
    """What one store page gave."""

    name: str
    url: str
    offers: dict[str, list[Offer]] = field(default_factory=dict)
    fetched: datetime | None = None
    ok: bool = False


@dataclass
class BestOffer:
    """An offer on a product in a store."""

    store: str
    url: str
    offer: Offer

    @property
    def summary(self) -> str:
        return f"{format_kr(self.offer.unit_price)} kr/st på {self.store} ({self.offer.text})"


@dataclass
class MatpriskollenData:
    """All stores, keyed by slug."""

    stores: dict[str, StoreResult]
    fetched: datetime | None

    def offers(self, product: str) -> list[BestOffer]:
        """Every offer on a product with a price per item, cheapest first."""
        found = [
            BestOffer(store=s.name, url=s.url, offer=o)
            for s in self.stores.values()
            for o in s.offers.get(product, [])
            if o.unit_price is not None
        ]
        return sorted(found, key=lambda b: (b.offer.unit_price, b.store))

    def best(self, product: str) -> BestOffer | None:
        offers = self.offers(product)
        return offers[0] if offers else None

    @property
    def stores_ok(self) -> int:
        return sum(1 for s in self.stores.values() if s.ok)


class MatpriskollenCoordinator(DataUpdateCoordinator[MatpriskollenData]):
    """Reads each store page at most once per update interval."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        cfg = entry_config(entry)
        hours = max(
            int(cfg.get(CONF_UPDATE_HOURS, DEFAULT_UPDATE_HOURS)), MIN_UPDATE_HOURS
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(hours=hours),
        )
        self.client = MatpriskollenClient(async_get_clientsession(hass))
        self.stores: dict[str, str] = dict(cfg.get(CONF_STORES, {}))
        self.products = products_of(entry)
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._saved: dict | None = None
        self._notified: dict[str, list[str]] = {}

    @property
    def product_names(self) -> list[str]:
        return sorted({p.name for p in self.products})

    async def _load(self) -> MatpriskollenData | None:
        """Read what was saved before a restart. Returns the offers if still fresh."""
        saved = await self._store.async_load() or {}
        self._notified = saved.get("notified", {})
        if saved.get("products") != self.product_names:
            return None
        fetched = dt_util.parse_datetime(saved.get("fetched") or "")
        if not fetched or dt_util.utcnow() - fetched > self.update_interval:
            return None
        stores: dict[str, StoreResult] = {}
        for slug, s in saved.get("stores", {}).items():
            if slug not in self.stores:
                continue
            stores[slug] = StoreResult(
                name=s["name"],
                url=s["url"],
                offers={
                    p: [Offer(**o) for o in offers] for p, offers in s["offers"].items()
                },
                fetched=dt_util.parse_datetime(s.get("fetched") or ""),
                ok=s.get("ok", False),
            )
        if set(stores) != set(self.stores):
            return None
        return MatpriskollenData(stores=stores, fetched=fetched)

    async def _save(self, data: MatpriskollenData) -> None:
        await self._store.async_save(
            {
                "products": self.product_names,
                "fetched": data.fetched.isoformat() if data.fetched else None,
                "notified": self._notified,
                "stores": {
                    slug: {
                        "name": s.name,
                        "url": s.url,
                        "offers": {
                            p: [o.as_dict() for o in offers]
                            for p, offers in s.offers.items()
                        },
                        "fetched": s.fetched.isoformat() if s.fetched else None,
                        "ok": s.ok,
                    }
                    for slug, s in data.stores.items()
                },
            }
        )

    async def _async_update_data(self) -> MatpriskollenData:
        if self._saved is None:
            self._saved = {}
            if cached := await self._load():
                _LOGGER.debug("Using saved offers from %s", cached.fetched)
                # A changed price limit can make saved offers qualify.
                await self._async_notify(cached)
                await self._save(cached)
                return cached

        previous = self.data.stores if self.data else {}
        names = self.product_names
        stores: dict[str, StoreResult] = {}
        for i, (slug, name) in enumerate(self.stores.items()):
            if i:
                await asyncio.sleep(REQUEST_DELAY)
            url = f"https://matpriskollen.se/butiker/{slug}"
            try:
                page = await self.client.async_store_page(slug)
            except MatpriskollenError as err:
                _LOGGER.warning("Could not read %s: %s", url, err)
                old = previous.get(slug)
                stores[slug] = StoreResult(
                    name=old.name if old else name,
                    url=url,
                    offers=old.offers if old else {},
                    fetched=old.fetched if old else None,
                    ok=False,
                )
                continue
            stores[slug] = StoreResult(
                name=page.name or name,
                url=url,
                offers={p: find_offers(page.text, p) for p in names},
                fetched=dt_util.utcnow(),
                ok=True,
            )

        if self.stores and not any(s.ok for s in stores.values()):
            raise UpdateFailed("No store page could be read from Matpriskollen")
        data = MatpriskollenData(stores=stores, fetched=dt_util.utcnow())
        await self._async_notify(data)
        await self._save(data)
        return data

    async def _async_notify(self, data: MatpriskollenData) -> None:
        """Notify each product's devices when its offers under the limit change."""
        for product in self.products:
            hits = [o for o in data.offers(product.name) if product.qualifies(o.offer)]
            key = sorted(f"{o.store}|{o.offer.text}" for o in hits)
            if key == self._notified.get(product.subentry_id, []):
                continue
            self._notified[product.subentry_id] = key
            if not hits or not product.notify:
                continue
            lines = [o.summary for o in hits[:MAX_LINES]]
            if len(hits) > MAX_LINES:
                lines.append(f"+ {len(hits) - MAX_LINES} till")
            for target in product.notify:
                domain, _, service = target.partition(".")
                if not self.hass.services.has_service(domain, service):
                    _LOGGER.warning("Notify service %s not found", target)
                    continue
                await self.hass.services.async_call(
                    domain,
                    service,
                    {
                        "title": f"{product.name} på extrapris",
                        "message": "\n".join(lines),
                    },
                    blocking=False,
                )

    async def async_remove_cache(self) -> None:
        await self._store.async_remove()
