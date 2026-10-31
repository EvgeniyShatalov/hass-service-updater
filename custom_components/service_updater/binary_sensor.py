"""Binary sensors для Service Updater."""
from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
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
        entities.append(AppUpdateBinarySensor(coordinator, entry))
        entities.append(DebianUpdateBinarySensor(coordinator, entry))
    async_add_entities(entities)

class AppUpdateBinarySensor(CoordinatorEntity[ServiceUpdaterCoordinator], BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.UPDATE
    _attr_icon = "mdi:package-up"
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._app = entry.data.get(CONF_APP, "")
        self._attr_unique_id = f"{entry.entry_id}_{self._app}_update"
        self._attr_name = f"{self._app.capitalize()} Update"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": entry.title}

    @property
    def suggested_object_id(self) -> str:
        return f"{self._app}_update"

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get(f"{self._app}_update_available"))

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        return {
            "current_version": data.get(f"{self._app}_current"),
            "latest_version": data.get(f"{self._app}_latest"),
            "host": data.get("host"),
            "last_check": data.get("last_check"),
            "next_check": data.get("next_check"),
            "timeout": data.get("program_timeout", False),
            "error": data.get(f"{self._app}_error"),
        }

class DebianUpdateBinarySensor(CoordinatorEntity[ServiceUpdaterCoordinator], BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.UPDATE
    _attr_icon = "mdi:debian"
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._app = entry.data.get(CONF_APP, "")
        self._attr_unique_id = f"{entry.entry_id}_debian_update"
        self._attr_name = "Debian Update"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": entry.title}

    @property
    def suggested_object_id(self) -> str:
        return f"{self._app}_debian_update"

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("debian_update_available"))

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        return {
            "status": "updates_available" if data.get("debian_update_available") else "up_to_date",
            "pending_count": data.get("apt_pending_count", 0),
            "packages": data.get("apt_pending_packages", []),
            "host": data.get("host"),
            "last_check": data.get("last_check"),
            "next_check": data.get("next_check"),
            "timeout": data.get("debian_timeout", False),
            "error": data.get("debian_error"),
        }