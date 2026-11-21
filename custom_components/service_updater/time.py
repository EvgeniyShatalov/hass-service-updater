"""Платформа Time для Service Updater (Точное время проверки)."""
from __future__ import annotations

import datetime
from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, CONF_CHECK_TIME
)
from .coordinator import ServiceUpdaterCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: ServiceUpdaterCoordinator = entry.runtime_data
    async_add_entities([ServiceCheckTime(coordinator, entry)])


class ServiceCheckTime(CoordinatorEntity[ServiceUpdaterCoordinator], TimeEntity):
    _attr_icon = "mdi:clock-outline"
    _attr_has_entity_name = True
    _attr_name = "Exact Check Time"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_check_time"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
        }

    @property
    def suggested_object_id(self) -> str:
        return f"{self.entry.data.get('app', 'service')}_check_time"

    @property
    def native_value(self) -> datetime.time | None:
        time_str = self.entry.options.get(CONF_CHECK_TIME)
        if time_str:
            try:
                return datetime.time.fromisoformat(time_str)
            except ValueError:
                return None
        return None

    async def async_set_value(self, value: datetime.time) -> None:
        new_options = dict(self.entry.options)
        new_options[CONF_CHECK_TIME] = value.isoformat()
        # При установке точного времени интервал игнорируется (это уже заложено в __init__.py)
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)
        await self.hass.config_entries.async_reload(self.entry.entry_id)