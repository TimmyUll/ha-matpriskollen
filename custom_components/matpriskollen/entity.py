"""Base entities for Matpriskollen."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import MatpriskollenCoordinator, Product


class MatpriskollenEntity(CoordinatorEntity[MatpriskollenCoordinator]):
    """An entity on the main Matpriskollen device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MatpriskollenCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Matpriskollen",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=VERSION,
            configuration_url="https://matpriskollen.se",
        )


class ProductEntity(CoordinatorEntity[MatpriskollenCoordinator]):
    """An entity on a product's own device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MatpriskollenCoordinator, product: Product, key: str
    ) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.product = product
        self._attr_translation_key = key
        self._attr_unique_id = f"{product.subentry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, product.subentry_id)},
            name=product.name,
            manufacturer="Matpriskollen",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=VERSION,
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        offers = self.coordinator.data.offers(self.product.name)
        best = offers[0] if offers else None
        return {
            "product": self.product.name,
            "max_price": self.product.max_price,
            "store": best.store if best else None,
            "offer": best.offer.text if best else None,
            "size": best.offer.size if best else None,
            "unit_price": best.offer.unit_price if best else None,
            "url": best.url if best else None,
            "offers": [
                {
                    "store": o.store,
                    "offer": o.offer.text,
                    "size": o.offer.size,
                    "unit_price": o.offer.unit_price,
                    "url": o.url,
                }
                for o in offers
            ],
            "stores_checked": self.coordinator.data.stores_ok,
            "stores_total": len(self.coordinator.data.stores),
        }
