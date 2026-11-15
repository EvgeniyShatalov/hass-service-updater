"""Платформа Switch для Service Updater."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, CONF_APP,
    SWITCH_CHECK_DEBIAN, SWITCH_CHECK_APP,
    SWITCH_AUTO_INSTALL_DEBIAN, SWITCH_AUTO_INSTALL_APP,
)
from .coordinator import ServiceUpdaterCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: ServiceUpdaterCoordinator = entry.runtime_data

    entities = [
        ServiceSwitch(coordinator, entry, SWITCH_CHECK_DEBIAN, "Check Debian", "mdi:debian"),
        ServiceSwitch(coordinator, entry, SWITCH_CHECK_APP, "Check App", "mdi:package-up"),
        ServiceSwitch(coordinator, entry, SWITCH_AUTO_INSTALL_DEBIAN, "Auto Install Debian", "mdi:download"),
        ServiceSwitch(coordinator, entry, SWITCH_AUTO_INSTALL_APP, "Auto Install App", "mdi:download"),
    ]
    async_add_entities(entities)


class ServiceSwitch(CoordinatorEntity[ServiceUpdaterCoordinator], SwitchEntity):
    """Переключатель для управления проверкой/установкой."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str, name: str, icon: str):
        super().__init__(coordinator)
        self.entry = entry
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
        }

    @property
    def suggested_object_id(self) -> str:
        app = self.entry.data.get(CONF_APP, "service")
        return f"{app}_{self._key}"

    @property
    def is_on(self) -> bool:
        return self.coordinator.switches.get(self._key, True)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_switch(self._key, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_switch(self._key, False)