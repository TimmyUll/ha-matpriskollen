"""Binary sensor per product: on when an offer is at or below the price limit."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MatpriskollenCoordinator, Product
from .entity import ProductEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: MatpriskollenCoordinator = entry.runtime_data
    for product in coordinator.products:
        async_add_entities(
            [UnderLimitSensor(coordinator, product)],
            config_subentry_id=product.subentry_id,
        )


class UnderLimitSensor(ProductEntity, BinarySensorEntity):
    """On when some store sells the product at or below the price limit."""

    _attr_icon = "mdi:cash-check"

    def __init__(self, coordinator: MatpriskollenCoordinator, product: Product) -> None:
        super().__init__(coordinator, product, "under_limit")

    @property
    def is_on(self) -> bool:
        return any(
            self.product.qualifies(o.offer)
            for o in self.coordinator.data.offers(self.product.name)
        )
