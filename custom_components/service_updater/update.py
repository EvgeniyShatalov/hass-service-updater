"""Платформа Update + функции установки для сервисов."""
from __future__ import annotations

import asyncio
import io
import zipfile
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.components import persistent_notification
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
    host = entry.data.get(CONF_HOST)
    data = coordinator.data or {}
    if not data.get("debian_update_available"):
        return
    packages = data.get("apt_pending_packages", [])
    try:
        await ssh_exec(hass, entry, "sudo -n DEBIAN_FRONTEND=noninteractive apt-get upgrade -y", timeout=600)
        coordinator.record_debian_upgrade(packages)
        persistent_notification.async_create(
            hass,
            f"Система **Debian** на хосте `{host}` успешно обновлена.\nОбновлено пакетов: {len(packages)}.",
            title="Service Updater: Успех",
            notification_id=f"update_success_debian_{host}"
        )
    except Exception as e:
        persistent_notification.async_create(
            hass,
            f"Ошибка обновления **Debian** на хосте `{host}`:\n```\n{e}\n```",
            title="Service Updater: Ошибка",
            notification_id=f"update_error_debian_{host}"
        )
        raise


async def install_app(hass: HomeAssistant, entry: ConfigEntry, coordinator: ServiceUpdaterCoordinator) -> None:
    app = entry.data.get(CONF_APP, "")
    host = entry.data.get(CONF_HOST)
    data = coordinator.data or {}
    if not data.get(f"{app}_update_available"):
        return

    adapter = ADAPTERS[app]
    latest = data.get(f"{app}_latest")
    if not latest:
        raise HomeAssistantError(f"Неизвестная последняя версия {app}")

    try:
        # --- Логика для TorrServer (официальный скрипт) ---
        if app == "torrserver":
            remote_cmd = (
                "curl -s https://raw.githubusercontent.com/YouROK/TorrServer/master/installTorrServerLinux.sh | "
                "sudo bash -s -- --update --silent"
            )
            await ssh_exec(hass, entry, remote_cmd, timeout=300)

        # --- Логика для Frigate (Docker Compose) ---
        elif app == "frigate":
            compose_dir = entry.data.get(CONF_COMPOSE_DIR, DEFAULT_COMPOSE_DIR)
            backup = f"tar czf {compose_dir}/config-backup-$(date +%F-%H%M).tar.gz -C {compose_dir} config 2>/dev/null || true"
            await ssh_exec(hass, entry, backup, timeout=120)
            remote = f"cd {compose_dir} && docker compose down frigate && docker compose pull && docker compose up -d"
            await ssh_exec(hass, entry, remote, timeout=900)

        # --- Логика для CloudPub (штатная команда CLI) ---
        elif app == "cloudpub":
            # Выполняем команду обновления. Флаг --silent не нужен, если clo его не поддерживает.
            # Команда upgrade сама скачает и заменит бинарник.
            await ssh_exec(hass, entry, "sudo clo upgrade", timeout=300)

        else:
            raise HomeAssistantError(f"Неизвестное приложение {app}")

        # Если ошибок нет — уведомление об успехе
        persistent_notification.async_create(
            hass,
            f"Приложение **{app.capitalize()}** на хосте `{host}` успешно обновлено до версии `{latest}`.",
            title="Service Updater: Успех",
            notification_id=f"update_success_{app}_{host}"
        )

    except Exception as e:
        persistent_notification.async_create(
            hass,
            f"Ошибка обновления **{app.capitalize()}** на хосте `{host}`:\n```\n{e}\n```",
            title="Service Updater: Ошибка",
            notification_id=f"update_error_{app}_{host}"
        )
        raise

    finally:
        await coordinator.async_request_refresh()