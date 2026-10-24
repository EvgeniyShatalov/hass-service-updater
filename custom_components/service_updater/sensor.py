"""Платформа Sensor для Service Updater."""
from __future__ import annotations

from datetime import datetime
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_APP, DOMAIN
from .coordinator import ServiceUpdaterCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: ServiceUpdaterCoordinator = entry.runtime_data
    app = entry.data.get(CONF_APP, "")
    entities: list = []
    if app in ("torrserver", "cloudpub", "frigate"):
        entities.append(AppVersionSensor(coordinator, entry))
        entities.append(DebianLastUpgradeSensor(coordinator, entry))
        entities.append(NextCheckSensor(coordinator, entry)) # Новый сенсор
    async_add_entities(entities)

class AppVersionSensor(CoordinatorEntity[ServiceUpdaterCoordinator], SensorEntity):
    _attr_icon = "mdi:package-up"
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._app = entry.data.get(CONF_APP, "")
        self._attr_unique_id = f"{entry.entry_id}_{self._app}_version"
        self._attr_name = f"{self._app.capitalize()} Version"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
        }

    @property
    def suggested_object_id(self) -> str:
        return f"{self._app}_version"

    @property
    def native_value(self) -> str | None:
        return (self.coordinator.data or {}).get(f"{self._app}_current")

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        interval = self.coordinator.update_interval
        return {
            "latest_version": data.get(f"{self._app}_latest"),
            "update_available": data.get(f"{self._app}_update_available"),
            "release_url": data.get(f"{self._app}_release_url"),
            "host": data.get("host"),
            "last_check": data.get("last_check"),
            "next_check": data.get("next_check"),
            "scan_interval_hours": int(interval.total_seconds() // 3600) if interval else None,
            "timeout": data.get("program_timeout", False),
            "error": data.get(f"{self._app}_error"),
        }

class DebianLastUpgradeSensor(CoordinatorEntity[ServiceUpdaterCoordinator], SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:package-check"
    _attr_has_entity_name = True
    _attr_name = "Debian Last Upgrade"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._app = entry.data.get(CONF_APP, "")
        self._attr_unique_id = f"{entry.entry_id}_debian_last_upgrade"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
        }

    @property
    def suggested_object_id(self) -> str:
        return f"{self._app}_debian_last_upgrade"

    @property
    def native_value(self) -> datetime | None:
        last = (self.coordinator.data or {}).get("debian_last_upgrade")
        if not last or not last.get("timestamp"):
            return None
        return datetime.fromisoformat(last["timestamp"])

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        last = data.get("debian_last_upgrade") or {}
        return {
            "count": last.get("count", 0),
            "packages": last.get("packages", []),
            "history": data.get("debian_upgrade_history", []),
            "host": data.get("host"),
            "timeout": data.get("debian_timeout", False),
            "error": data.get("debian_error"),
        }

class NextCheckSensor(CoordinatorEntity[ServiceUpdaterCoordinator], SensorEntity):
    """Сенсор показывает точное время следующей проверки."""
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"
    _attr_has_entity_name = True
    _attr_name = "Next Check Time"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._app = entry.data.get(CONF_APP, "")
        self._attr_unique_id = f"{entry.entry_id}_{self._app}_next_check"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
        }

    @property
    def suggested_object_id(self) -> str:
        return f"{self._app}_next_check"

    @property
    def native_value(self) -> datetime | None:
        next_check = (self.coordinator.data or {}).get("next_check")
        if not next_check:
            return None
        return datetime.fromisoformat(next_check)
