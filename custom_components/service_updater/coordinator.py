"""DataUpdateCoordinator для Service Updater."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .adapters import ADAPTERS, ServiceAdapter
from .const import (
    CONF_APP, CONF_HOST, CONF_SSH_PORT, CONF_SSH_USER,
    DEFAULT_SSH_PORT, DEFAULT_SSH_USER, DOMAIN,
    PROGRAM_CHECK_TIMEOUT, DEBIAN_CHECK_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

class ServiceUpdaterCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry_data: dict, interval_hours: int) -> None:
        self.entry_data = entry_data
        self.app: str = entry_data.get(CONF_APP, "")
        self.adapter: ServiceAdapter = ADAPTERS[self.app]
        self.host: str = entry_data.get(CONF_HOST, "")
        self.ssh_user: str = entry_data.get(CONF_SSH_USER, DEFAULT_SSH_USER)
        self.ssh_port: int = int(entry_data.get(CONF_SSH_PORT, DEFAULT_SSH_PORT))
        self.session = async_get_clientsession(hass)
        self._interval = timedelta(hours=interval_hours)
        self._last_debian_upgrade: dict | None = None
        self._upgrade_history: list[dict] = []

        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_{self.app}", update_interval=self._interval)

    async def _async_update_data(self) -> dict:
        now = datetime.now(timezone.utc)
        data: dict = {
            "host": self.host,
            "app": self.app,
            "last_check": now.isoformat(),
            "next_check": (now + self._interval).isoformat(),
            "debian_last_upgrade": self._last_debian_upgrade,
            "debian_upgrade_history": self._upgrade_history,
        }

        data.update(await self._check_debian_with_timeout())
        data.update(await self._check_program_with_timeout())

        data["update_available"] = (
            data.get("debian_update_available", False)
            or data.get(f"{self.app}_update_available", False)
        )
        return data

    async def _check_debian_with_timeout(self) -> dict:
        try:
            return await asyncio.wait_for(self._check_debian(), timeout=DEBIAN_CHECK_TIMEOUT)
        except asyncio.TimeoutError:
            return {
                "debian_current": "error", "debian_latest": "error",
                "debian_update_available": False, "apt_pending_count": 0,
                "apt_pending_packages": [], "debian_error": "timeout",
                "debian_timeout": True,
            }
        except Exception as ex:
            return {
                "debian_current": "error", "debian_latest": "error",
                "debian_update_available": False, "apt_pending_count": 0,
                "apt_pending_packages": [], "debian_error": str(ex),
            }

    async def _check_program_with_timeout(self) -> dict:
        try:
            return await asyncio.wait_for(self._check_program(), timeout=PROGRAM_CHECK_TIMEOUT)
        except asyncio.TimeoutError:
            key = self.app
            return {
                f"{key}_update_available": False,
                f"{key}_error": "timeout",
                "program_timeout": True,
            }
        except Exception as ex:
            key = self.app
            return {f"{key}_error": str(ex)}

    async def _check_debian(self) -> dict:
        remote = "sudo -n apt-get update -qq && apt list --upgradable 2>/dev/null"
        out = await self.ssh_exec(remote, timeout=90)

        pending: list[dict] = []
        for line in out.splitlines():
            line = line.strip()
            if "upgradable from" not in line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[0].split("/")[0]
            new_ver = parts[1]
            old_ver = line.split("upgradable from:")[1].strip(" ]") if "upgradable from:" in line else ""
            pending.append({"package": name, "new_version": new_ver, "old_version": old_ver})

        count = len(pending)
        status = "up-to-date" if count == 0 else f"{count} pending"
        return {
            "debian_current": status, "debian_latest": status,
            "debian_update_available": count > 0, "apt_pending_count": count,
            "apt_pending_packages": pending,
        }

    async def _check_program(self) -> dict:
        adapter = self.adapter
        key = self.app
        result: dict = {}

        if adapter.version_url_path:
            current = await adapter.get_local_version(self.session, self.host, adapter.default_port)
        elif key == "cloudpub":
            current = (await self.ssh_exec("clo --version")).strip()
        else:
            current = "unknown"

        api = f"https://api.github.com/repos/{adapter.github_repo}/releases/latest"
        async with self.session.get(api, timeout=10) as resp:
            rel = await resp.json()
        latest = rel["tag_name"]

        result[f"{key}_current"] = current
        result[f"{key}_latest"] = latest
        result[f"{key}_release_url"] = rel.get("html_url")
        result[f"{key}_update_available"] = (
            (current or "").lstrip("v").split("-")[0] != latest.lstrip("v").split("-")[0]
        )
        return result

    async def ssh_exec(self, remote_cmd: str, timeout: int = 30) -> str:
        cmd = [
            "ssh", "-p", str(self.ssh_port), "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10",
            f"{self.ssh_user}@{self.host}", remote_cmd,
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            raise UpdateFailed(err.decode(errors="ignore").strip() or "SSH error")
        return out.decode(errors="ignore")

    def record_debian_upgrade(self, packages: list[dict]) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "packages": packages, "count": len(packages)}
        self._last_debian_upgrade = entry
        self._upgrade_history.append(entry)
        if len(self._upgrade_history) > 5:
            self._upgrade_history = self._upgrade_history[-5:]
        self.async_set_updated_data({
            **(self.data or {}),
            "debian_last_upgrade": self._last_debian_upgrade,
            "debian_upgrade_history": self._upgrade_history,
        })