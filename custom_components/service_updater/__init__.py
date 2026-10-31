"""Точка входа Service Updater."""
from __future__ import annotations
import asyncio
import logging
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from .const import (
    ATTR_ENTRY_ID, ATTR_HOST, CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN, SERVICE_INSTALL_APP, SERVICE_INSTALL_DEBIAN,
    INSTALL_DEBIAN_TIMEOUT, INSTALL_APP_TIMEOUT, CONF_CHECK_TIME,
)
from .coordinator import ServiceUpdaterCoordinator
from .update import install_app, install_debian

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.UPDATE, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

SERVICE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTRY_ID): cv.string,
    vol.Optional(ATTR_HOST): cv.string,
    vol.Optional("entity_id"): cv.string,
    vol.Optional("device_id"): cv.string,
})

def _select_entries(hass: HomeAssistant, call: ServiceCall) -> list[ConfigEntry]:
    entries = hass.config_entries.async_entries(DOMAIN)
    entry_id = call.data.get(ATTR_ENTRY_ID)
    host = call.data.get(ATTR_HOST)
    entity_id = call.data.get("entity_id")
    device_id = call.data.get("device_id")

    if entity_id and not entry_id and not host:
        reg = er.async_get(hass)
        reg_entry = reg.async_get(entity_id)
        if reg_entry and reg_entry.config_entry_id:
            entry_id = reg_entry.config_entry_id
            
    if device_id and not entry_id and not host:
        dev_reg = er.async_get(hass)
        entity_entries = er.async_entries_for_device(dev_reg, device_id)
        for ent in entity_entries:
            if ent.config_entry_id:
                entry_id = ent.config_entry_id
                break

    if entry_id: entries = [e for e in entries if e.entry_id == entry_id]
    elif host: entries = [e for e in entries if e.data.get("host") == host]
    return entries

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def _handle_install_debian(call: ServiceCall) -> None:
        for entry in _select_entries(hass, call):
            if not hasattr(entry, "runtime_data"): continue
            _LOGGER.info("Service install_debian: %s", entry.title)
            try:
                await asyncio.wait_for(install_debian(hass, entry, entry.runtime_data), timeout=INSTALL_DEBIAN_TIMEOUT)
            except asyncio.TimeoutError:
                _LOGGER.error("install_debian timeout: %s", entry.title)
            await entry.runtime_data.async_request_refresh()

    async def _handle_install_app(call: ServiceCall) -> None:
        for entry in _select_entries(hass, call):
            if not hasattr(entry, "runtime_data"): continue
            _LOGGER.info("Service install_app: %s", entry.title)
            try:
                await asyncio.wait_for(install_app(hass, entry, entry.runtime_data), timeout=INSTALL_APP_TIMEOUT)
            except asyncio.TimeoutError:
                _LOGGER.error("install_app timeout: %s", entry.title)
            await entry.runtime_data.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_INSTALL_DEBIAN, _handle_install_debian, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_INSTALL_APP, _handle_install_app, schema=SERVICE_SCHEMA)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    interval_hours = entry.options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS)
    check_time = entry.options.get(CONF_CHECK_TIME)
    
    if check_time: interval_hours = None

    coordinator = ServiceUpdaterCoordinator(hass, entry.data, interval_hours, check_time)
    
    # Загружаем историю с диска перед первым опросом
    await coordinator.async_load_history()
    
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    if check_time:
        try:
            h, m, s = map(int, check_time.split(":"))
            entry.async_on_unload(async_track_time_change(hass, coordinator.async_refresh, h, m, s))
        except Exception as e:
            _LOGGER.error("Ошибка парсинга времени проверки %s: %s", check_time, e)

    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def _async_reload_on_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)