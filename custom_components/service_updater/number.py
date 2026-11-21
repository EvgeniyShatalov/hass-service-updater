"""Платформа Number для Service Updater (Интервал проверки)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS,
    SCAN_INTERVAL_MIN_HOURS, SCAN_INTERVAL_MAX_HOURS, CONF_CHECK_TIME
)
from .coordinator import ServiceUpdaterCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: ServiceUpdaterCoordinator = entry.runtime_data
    async_add_entities([ServiceIntervalNumber(coordinator, entry)])


class ServiceIntervalNumber(CoordinatorEntity[ServiceUpdaterCoordinator], NumberEntity):
    _attr_icon = "mdi:timer-outline"
    _attr_has_entity_name = True
    _attr_name = "Check Interval"
    _attr_native_min_value = SCAN_INTERVAL_MIN_HOURS
    _attr_native_max_value = SCAN_INTERVAL_MAX_HOURS
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "h"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_check_interval"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
        }

    @property
    def suggested_object_id(self) -> str:
        return f"{self.entry.data.get('app', 'service')}_check_interval"

    @property
    def native_value(self) -> float:
        return self.entry.options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS)

    async def async_set_native_value(self, value: float) -> None:
        new_options = dict(self.entry.options)
        new_options[CONF_SCAN_INTERVAL_HOURS] = int(value)
        new_options[CONF_CHECK_TIME] = None  # Сбрасываем точное время, если выбран интервал
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)
        await self.hass.config_entries.async_reload(self.entry.entry_id)