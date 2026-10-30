"""Платформа Update + функции установки для сервисов."""
from __future__ import annotations

import asyncio
import io
import zipfile
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .adapters import ADAPTERS
from .const import (
    CONF_APP, CONF_COMPOSE_DIR, CONF_HOST, CONF_SSH_PORT, CONF_SSH_USER,
    DEFAULT_COMPOSE_DIR, DEFAULT_SSH_PORT, DOMAIN,
    SSH_KEY_DIR, SSH_PRIVATE_KEY,
)
from .coordinator import ServiceUpdaterCoordinator

def _key_path(hass: HomeAssistant) -> str:
    return str(hass.config.path(SSH_KEY_DIR, SSH_PRIVATE_KEY))


async def ssh_exec(hass: HomeAssistant, entry: ConfigEntry, remote_cmd: str, timeout: int = 60) -> str:
    ssh_user = entry.data.get(CONF_SSH_USER, "root")
    ssh_port = int(entry.data.get(CONF_SSH_PORT, DEFAULT_SSH_PORT))
    host = entry.data.get(CONF_HOST)
    key = _key_path(hass)
    cmd = [
        "ssh", "-p", str(ssh_port), "-i", key, "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10",
        f"{ssh_user}@{host}", remote_cmd,
    ]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise HomeAssistantError(f"SSH {host}: {err.decode(errors='ignore').strip()}")
    return out.decode(errors="ignore")


async def install_debian(hass: HomeAssistant, entry: ConfigEntry, coordinator: ServiceUpdaterCoordinator) -> None:
    data = coordinator.data or {}
    if not data.get("debian_update_available"):
        return
    packages = data.get("apt_pending_packages", [])
    await ssh_exec(hass, entry, "sudo -n DEBIAN_FRONTEND=noninteractive apt-get upgrade -y", timeout=600)
    coordinator.record_debian_upgrade(packages)


async def install_app(hass: HomeAssistant, entry: ConfigEntry, coordinator: ServiceUpdaterCoordinator) -> None:
    app = entry.data.get(CONF_APP, "")
    data = coordinator.data or {}
    if not data.get(f"{app}_update_available"):
        return

    adapter = ADAPTERS[app]
    latest = data.get(f"{app}_latest")
    if not latest:
        raise HomeAssistantError(f"Неизвестная последняя версия {app}")

    # --- Логика для TorrServer (через официальный скрипт) ---
    if app == "torrserver":
        # Официальная команда для обновления через установочный скрипт
        remote_cmd = (
            "curl -s https://raw.githubusercontent.com/YouROK/TorrServer/master/installTorrServerLinux.sh | "
            "sudo bash -s -- --update --silent"
        )
        await ssh_exec(hass, entry, remote_cmd, timeout=300)
        return

    # --- Логика для Frigate (через Docker Compose) ---
    if app == "frigate":
        compose_dir = entry.data.get(CONF_COMPOSE_DIR, DEFAULT_COMPOSE_DIR)
        backup = f"tar czf {compose_dir}/config-backup-$(date +%F-%H%M).tar.gz -C {compose_dir} config 2>/dev/null || true"
        await ssh_exec(hass, entry, backup, timeout=120)
        remote = f"cd {compose_dir} && docker compose down frigate && docker compose pull && docker compose up -d"
        await ssh_exec(hass, entry, remote, timeout=900)
        return

    # --- Логика для CloudPub (прямое скачивание) ---
    if app == "cloudpub":
        url = f"https://github.com/{adapter.github_repo}/releases/download/{latest}/clo-linux-amd64.zip"
        remote_path = "/usr/local/bin/clo"
        
        async with coordinator.session.get(url, timeout=120) as resp:
            resp.raise_for_status()
            content = await resp.read()

        if url.endswith(".zip"):
            content = await hass.async_add_executor_job(_extract_from_zip, content, adapter.asset_pattern or "")

        # Используем cat через SSH для передачи файла
        tmp = f"{remote_path}.new"
        remote = (
            f"cat > {tmp} && "
            f"chmod +x {tmp} && mv {tmp} {remote_path} && "
            f"sudo -n systemctl restart {adapter.restart_service}"
        )
        
        # Создаем SSH процесс с возможностью записи в stdin
        ssh_user = entry.data.get(CONF_SSH_USER, "root")
        ssh_port = int(entry.data.get(CONF_SSH_PORT, DEFAULT_SSH_PORT))
        host = entry.data.get(CONF_HOST)
        key = _key_path(hass)
        cmd = [
            "ssh", "-p", str(ssh_port), "-i", key, "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10",
            f"{ssh_user}@{host}", remote,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, 
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, 
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await asyncio.wait_for(proc.communicate(input=content), timeout=300)
        if proc.returncode != 0:
            raise HomeAssistantError(f"SSH {host}: {err.decode(errors='ignore').strip()}")
        return

    # Если приложение не распознано
    raise HomeAssistantError(f"Неизвестное приложение {app}")


def _extract_from_zip(content: bytes, pattern: str) -> bytes:
    needle = pattern.split(".")[0].lower()
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        member = next((m for m in zf.namelist() if needle in m.lower() and not m.endswith("/")), None)
        if not member:
            raise HomeAssistantError("Бинарник не найден в архиве")
        return zf.read(member)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: ServiceUpdaterCoordinator = entry.runtime_data
    async_add_entities([ServiceUpdaterUpdateEntity(coordinator, entry)])


class ServiceUpdaterUpdateEntity(CoordinatorEntity[ServiceUpdaterCoordinator], UpdateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = UpdateEntityFeature.RELEASE_NOTES

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._app = entry.data.get(CONF_APP, "")
        self._attr_unique_id = f"{entry.entry_id}_update"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": self._app.capitalize(),
        }

    @property
    def suggested_object_id(self) -> str:
        return self._app

    @property
    def installed_version(self):
        return (self.coordinator.data or {}).get(f"{self._app}_current")

    @property
    def latest_version(self):
        return (self.coordinator.data or {}).get(f"{self._app}_latest")

    @property
    def release_url(self):
        return (self.coordinator.data or {}).get(f"{self._app}_release_url")

    async def async_release_notes(self) -> str | None:
        return "Обновление выполняется через сервисы service_updater.*"