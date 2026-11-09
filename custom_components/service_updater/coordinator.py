"""DataUpdateCoordinator для Service Updater."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .adapters import ADAPTERS, ServiceAdapter
from .const import (
    CONF_APP, CONF_HOST, CONF_SSH_PORT, CONF_SSH_USER,
    DEFAULT_SSH_PORT, DEFAULT_SSH_USER, DOMAIN,
    PROGRAM_CHECK_TIMEOUT, DEBIAN_CHECK_TIMEOUT,
    SSH_KEY_DIR, SSH_PRIVATE_KEY,
)

_LOGGER = logging.getLogger(__name__)

class ServiceUpdaterCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry_data: dict, interval_hours: int | None, check_time: str | None) -> None:
        self.entry_data = entry_data
        self.app: str = entry_data.get(CONF_APP, "")
        self.adapter: ServiceAdapter = ADAPTERS[self.app]
        self.host: str = entry_data.get(CONF_HOST, "")
        self.ssh_user: str = entry_data.get(CONF_SSH_USER, DEFAULT_SSH_USER)
        self.ssh_port: int = int(entry_data.get(CONF_SSH_PORT, DEFAULT_SSH_PORT))
        self.session = async_get_clientsession(hass)
        
        self._interval = timedelta(hours=interval_hours) if interval_hours else None
        self._check_time = check_time

        store_key_hist = f"service_updater_history_{self.app}_{self.host}"
        store_key_ver = f"service_updater_versions_{self.app}_{self.host}"
        
        self._store_hist = Store(hass, 1, store_key_hist)
        self._store_ver = Store(hass, 1, store_key_ver)

        self._last_debian_upgrade: dict | None = None
        self._upgrade_history: list[dict] = []
        self._last_known_versions: dict[str, str] = {}

        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_{self.app}", update_interval=self._interval)

    async def async_load_history(self) -> None:
        stored_hist = await self._store_hist.async_load()
        if stored_hist:
            self._last_debian_upgrade = stored_hist.get("last_upgrade")
            self._upgrade_history = stored_hist.get("history", [])
            
        stored_ver = await self._store_ver.async_load()
        if stored_ver:
            self._last_known_versions = stored_ver

    async def _async_update_data(self) -> dict:
        now_local = dt_util.now()
        now_utc = datetime.now(timezone.utc)
        
        if self._interval:
            next_check_dt = now_local + self._interval
            next_check_iso = next_check_dt.isoformat()
        elif self._check_time:
            try:
                h, m, s = map(int, self._check_time.split(":"))
                next_check_dt = now_local.replace(hour=h, minute=m, second=s, microsecond=0)
                if next_check_dt <= now_local:
                    next_check_dt += timedelta(days=1)
                next_check_iso = next_check_dt.isoformat()
            except ValueError:
                next_check_iso = None
        else:
            next_check_iso = None

        data: dict = {
            "host": self.host,
            "app": self.app,
            "last_check": now_utc.isoformat(),
            "next_check": next_check_iso,
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
            return self._get_fallback_result(key, "timeout")
        except Exception as ex:
            key = self.app
            return self._get_fallback_result(key, str(ex))
            
    def _get_fallback_result(self, key: str, error_msg: str) -> dict:
        last_ver = self._last_known_versions.get(key)
        return {
            f"{key}_current": last_ver,
            f"{key}_latest": None,
            f"{key}_update_available": False,
            f"{key}_error": f"{error_msg} (из кэша)" if last_ver else error_msg,
            "program_timeout": True
        }

    async def _check_debian(self) -> dict:
        remote = "sudo -n apt-get update -qq && apt list --upgradable 2>/dev/null"
        out = await self.ssh_exec(remote, timeout=90)

        pending: list[dict] = []
        for line in out.splitlines():
            line = line.strip()
            if "upgradable from" not in line: continue
            parts = line.split()
            if len(parts) < 2: continue
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
        current = None
        latest = None
        release_url = None
        release_notes = "Описание изменений недоступно."
        error_msg = None

        # 1. Получаем текущую версию
        try:
            if adapter.version_url_path:
                current = await adapter.get_local_version(self.session, self.host, adapter.default_port)
                if key == "frigate":
                    match = re.search(r'(\d+\.\d+\.\d+)', current)
                    current = match.group(1) if match else current
            elif key == "cloudpub":
                raw_version = (await self.ssh_exec("/usr/local/bin/clo --version 2>&1 || true")).strip()
                match = re.search(r'(\d+\.\d+\.\d+)', raw_version)
                current = match.group(1) if match else raw_version
        except Exception as ex:
            _LOGGER.warning("Не удалось получить текущую версию %s: %s", key, ex)
            error_msg = str(ex)

        if current:
            if self._last_known_versions.get(key) != current:
                self._last_known_versions[key] = current
                self.hass.async_create_task(self._store_ver.async_save(self._last_known_versions))
        else:
            current = self._last_known_versions.get(key)
            if current:
                error_msg = f"{error_msg} (показана из кэша)" if error_msg else "Показана из кэша"

        # 2. Получаем последнюю версию
        try:
            if key == "cloudpub":
                release_url = "https://cloudpub.ru/download/"
                release_notes = "Команда `clo upgrade` загружает и устанавливает последнюю стабильную версию с официального сервера CloudPub."
                
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                
                # Способ А: Читаем заголовок Content-Disposition при скачивании файла
                try:
                    url = "https://cloudpub.ru/download/stable/clo-latest-stable-linux-x86_64.tar.gz"
                    async with self.session.get(url, allow_redirects=True, headers=headers, timeout=15) as resp:
                        cd = resp.headers.get("Content-Disposition", "")
                        match = re.search(r'clo-(\d+\.\d+\.\d+)-', cd)
                        if match:
                            latest = match.group(1)
                        else:
                            # Если заголовка нет, пробуем вытащить версию из финального URL
                            match = re.search(r'clo-(\d+\.\d+\.\d+)-', str(resp.url))
                            if match:
                                latest = match.group(1)
                except Exception as ex:
                    _LOGGER.debug("Не удалось прочитать заголовки при скачивании: %s", ex)
                
                # Способ Б: Парсим главную страницу сайта
                if not latest:
                    try:
                        async with self.session.get("https://cloudpub.ru/", headers=headers, timeout=10) as resp:
                            if resp.status == 200:
                                html = await resp.text()
                                match = re.search(r'clo-(\d+\.\d+\.\d+)-stable', html)
                                if not match:
                                    match = re.search(r'CLOUDPUB\s+(\d+\.\d+\.\d+)', html)
                                if match:
                                    latest = match.group(1)
                    except Exception as ex:
                        _LOGGER.debug("Не удалось спарсить главную страницу: %s", ex)

                if not latest:
                    latest = current # Если не удалось узнать, считаем что версия актуальна
            else:
                api = f"https://api.github.com/repos/{adapter.github_repo}/releases/latest"
                async with self.session.get(api, timeout=10) as resp:
                    if resp.status == 200:
                        rel = await resp.json()
                        latest_tag = rel.get("tag_name", "0.0.0")
                        latest_match = re.search(r'(\d+\.\d+\.\d+)', latest_tag)
                        latest = latest_match.group(1) if latest_match else latest_tag
                        release_url = rel.get("html_url")
                        release_notes = rel.get("body") or "Разработчик не приложил описание к этому релизу."
                        release_notes = release_notes[:3000]
        except Exception as ex:
            _LOGGER.warning("Не удалось получить последнюю версию %s: %s", key, ex)
            if not error_msg:
                error_msg = f"Ошибка GitHub: {ex}"

        result[f"{key}_current"] = current
        result[f"{key}_release_url"] = release_url
        result[f"{key}_release_notes"] = release_notes
        result[f"{key}_error"] = error_msg

        if current and latest:
            current_clean = current.lstrip("v").split("-")[0]
            latest_clean = latest.lstrip("v").split("-")[0]
            result[f"{key}_update_available"] = current_clean != latest_clean
            result[f"{key}_latest"] = latest
        else:
            result[f"{key}_update_available"] = False
            result[f"{key}_latest"] = None

        return result

    async def ssh_exec(self, remote_cmd: str, timeout: int = 30) -> str:
        key = str(self.hass.config.path(SSH_KEY_DIR, SSH_PRIVATE_KEY))
        cmd = [
            "ssh", "-p", str(self.ssh_port), "-i", key, "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10",
            f"{self.ssh_user}@{self.host}", remote_cmd,
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            err_text = err.decode(errors="ignore").strip()
            out_text = out.decode(errors="ignore").strip()
            if out_text:
                return out_text
            raise UpdateFailed(err_text or "SSH error")
        return out.decode(errors="ignore")

    def record_debian_upgrade(self, packages: list[dict]) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "packages": packages, "count": len(packages)}
        self._last_debian_upgrade = entry
        self._upgrade_history.append(entry)
        if len(self._upgrade_history) > 5:
            self._upgrade_history = self._upgrade_history[-5:]
            
        self.hass.async_create_task(self._store_hist.async_save({
            "last_upgrade": self._last_debian_upgrade,
            "history": self._upgrade_history
        }))
        
        self.async_set_updated_data({
            **(self.data or {}),
            "debian_last_upgrade": self._last_debian_upgrade,
            "debian_upgrade_history": self._upgrade_history,
        })