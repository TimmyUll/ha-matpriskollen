"""Sensors: best offer per product, and when the stores were last read."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MatpriskollenCoordinator, Product
from .entity import MatpriskollenEntity, ProductEntity

NO_OFFER = "Inget extrapris"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: MatpriskollenCoordinator = entry.runtime_data
    async_add_entities([LastFetchSensor(coordinator)])
    for product in coordinator.products:
        async_add_entities(
            [
                BestPriceSensor(coordinator, product),
                BestOfferSensor(coordinator, product),
            ],
            config_subentry_id=product.subentry_id,
        )


class BestPriceSensor(ProductEntity, SensorEntity):
    """Lowest price per item this week, in kr."""

    _attr_native_unit_of_measurement = "kr/st"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:tag"

    def __init__(self, coordinator: MatpriskollenCoordinator, product: Product) -> None:
        super().__init__(coordinator, product, "best_price")

    @property
    def native_value(self) -> float | None:
        best = self.coordinator.data.best(self.product.name)
        return best.offer.unit_price if best else None


class BestOfferSensor(ProductEntity, SensorEntity):
    """The best offer as text, e.g. "12,00 kr/st på Coop Tyresö (3 för 36,00)"."""

    _attr_icon = "mdi:tag-text"

    def __init__(self, coordinator: MatpriskollenCoordinator, product: Product) -> None:
        super().__init__(coordinator, product, "best_offer")

    @property
    def native_value(self) -> str:
        best = self.coordinator.data.best(self.product.name)
        return best.summary[:255] if best else NO_OFFER


class LastFetchSensor(MatpriskollenEntity, SensorEntity):
    """When the store pages were last read."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MatpriskollenCoordinator) -> None:
        super().__init__(coordinator, "last_fetch")

    @property
    def native_value(self):
        return self.coordinator.data.fetched

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stores = self.coordinator.data.stores
        return {
            "stores_checked": self.coordinator.data.stores_ok,
            "stores_total": len(stores),
            "stores_failed": [s.name for s in stores.values() if not s.ok],
        }
