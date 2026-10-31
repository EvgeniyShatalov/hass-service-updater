"""Кнопка принудительной проверки обновлений."""
from __future__ import annotations
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, CONF_APP
from .coordinator import ServiceUpdaterCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: ServiceUpdaterCoordinator = entry.runtime_data
    async_add_entities([CheckUpdateButton(coordinator, entry)])

class CheckUpdateButton(CoordinatorEntity[ServiceUpdaterCoordinator], ButtonEntity):
    _attr_icon = "mdi:refresh"
    _attr_has_entity_name = True
    _attr_name = "Проверить сейчас"

    def __init__(self, coordinator: ServiceUpdaterCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_check_now"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": entry.title}

    @property
    def suggested_object_id(self) -> str:
        return f"{self.entry.data.get(CONF_APP, 'service')}_check_now"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()