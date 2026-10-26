"""Config + Options flow для Service Updater."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.helpers import selector
from homeassistant.components import persistent_notification

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_APP, CONF_COMPOSE_DIR, CONF_HOST, CONF_SCAN_INTERVAL_HOURS,
    CONF_SSH_PORT, CONF_SSH_USER, DEFAULT_COMPOSE_DIR, DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_SSH_PORT, DEFAULT_SSH_USER, DOMAIN, SCAN_INTERVAL_MAX_HOURS,
    SCAN_INTERVAL_MIN_HOURS, SSH_KEY_DIR, SSH_PRIVATE_KEY, SSH_PUBLIC_KEY,
    CONF_CHECK_TIME,
)

_LOGGER = logging.getLogger(__name__)

APPS = {
    "torrserver": "TorrServer",
    "cloudpub": "CloudPub",
    "frigate": "Frigate (Docker)",
}


def _key_paths(hass) -> tuple[Path, Path]:
    base = Path(hass.config.path(SSH_KEY_DIR))
    return base / SSH_PRIVATE_KEY, base / SSH_PUBLIC_KEY


async def _generate_keypair(hass) -> str:
    priv, pub = _key_paths(hass)
    priv.parent.mkdir(mode=0o700, exist_ok=True)
    if priv.exists():
        return pub.read_text()

    proc = await asyncio.create_subprocess_exec(
        "ssh-keygen", "-t", "ed25519", "-f", str(priv), "-N", "",
        "-C", "home-assistant@service-updater",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(err.decode(errors="ignore").strip())
    priv.chmod(0o600)
    return pub.read_text()


async def _ping_host(host: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", "2", host,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=5)
        return proc.returncode == 0
    except Exception as exc:
        _LOGGER.debug("Ping failed for %s: %s", host, exc)
        return False


async def _tcp_check(host: str, port: int) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=5
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception as exc:
        _LOGGER.debug("TCP %s:%d failed: %s", host, port, exc)
        return False


async def _ssh_key_auth(host: str, port: int, user: str, key: Path) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh", "-p", str(port), "-i", str(key), "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=5",
            f"{user}@{host}", "true",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        return proc.returncode == 0
    except Exception as exc:
        _LOGGER.debug("SSH key auth failed: %s", exc)
        return False


class ServiceUpdaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        priv, pub = _key_paths(self.hass)
        errors: dict[str, str] = {}

        if user_input is not None:
            action = user_input.get("action", "continue")
            if action == "generate":
                try:
                    await _generate_keypair(self.hass)
                    return await self.async_step_user()
                except Exception as exc:
                    _LOGGER.error("SSH keygen failed: %s", exc)
                    errors["base"] = "keygen_failed"
            elif action == "continue":
                if not pub.exists():
                    errors["base"] = "no_key"
                else:
                    return await self.async_step_connection()

        public_key = pub.read_text().strip() if pub.exists() else ""
        has_key = bool(public_key)

        schema = vol.Schema({
            vol.Optional("public_key", default=public_key or "Ключ не создан"): str,
            vol.Optional("action", default="continue"): vol.In(
                ["continue"] + ([] if has_key else ["generate"])
            ),
        })

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors,
            description_placeholders={
                "status": "Ключ найден" if has_key else "Ключ не найден",
                "path": str(pub),
                "instruction": (
                    "Сгенерируйте SSH-ключ кнопкой «generate», чтобы продолжить."
                    if not has_key else
                    "Нажмите «continue», чтобы перейти к добавлению хоста."
                ),
            },
        )

    async def async_step_connection(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            ssh_port = int(user_input[CONF_SSH_PORT])
            app = user_input[CONF_APP]
            ssh_user = user_input[CONF_SSH_USER]

            if not await _ping_host(host):
                errors["base"] = "cannot_ping"
            elif not await _tcp_check(host, ssh_port):
                errors["base"] = "cannot_connect_ssh"
            else:
                self._app = app
                self._host = host
                self._ssh_user = ssh_user
                self._ssh_port = ssh_port
                self._interval = user_input.get(
                    CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
                )
                return await self.async_step_show_command()

        schema = vol.Schema({
            vol.Required(CONF_APP): vol.In(APPS),
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_SSH_USER, default=DEFAULT_SSH_USER): str,
            vol.Required(CONF_SSH_PORT, default=DEFAULT_SSH_PORT): int,
            vol.Optional(CONF_SCAN_INTERVAL_HOURS, default=DEFAULT_SCAN_INTERVAL_HOURS):
                vol.All(int, vol.Range(
                    min=SCAN_INTERVAL_MIN_HOURS, max=SCAN_INTERVAL_MAX_HOURS,
                )),
        })

        return self.async_show_form(
            step_id="connection", data_schema=schema, errors=errors
        )

    async def async_step_show_command(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        priv, pub = _key_paths(self.hass)
        public_key = pub.read_text().strip() if pub.exists() else "КЛЮЧ_НЕ_НАЙДЕН"

        if user_input is not None:
            action = user_input.get("action", "check")
            if action == "check":
                if await _ssh_key_auth(self._host, self._ssh_port, self._ssh_user, priv):
                    return await self._create_entry()
                errors["base"] = "ssh_auth_failed"
            elif action == "finish":
                return await self._create_entry()

        if self._app == "torrserver":
            sudo_cmd = (
                "/usr/bin/apt-get update, /usr/bin/apt-get upgrade, "
                "/usr/bin/systemctl restart torrserver.service"
            )
        elif self._app == "cloudpub":
            sudo_cmd = (
                "/usr/bin/apt-get update, /usr/bin/apt-get upgrade, "
                "/usr/bin/systemctl restart cloudpub.service"
            )
        else:
            sudo_cmd = (
                "/usr/bin/apt-get update, /usr/bin/apt-get upgrade, "
                "/usr/bin/docker compose"
            )

        full_command = (
            f"mkdir -p ~/.ssh && chmod 700 ~/.ssh\n"
            f"echo '{public_key}' >> ~/.ssh/authorized_keys\n"
            f"chmod 600 ~/.ssh/authorized_keys\n\n"
            f"echo '{self._ssh_user} ALL=(ALL) NOPASSWD: {sudo_cmd}' "
            "| sudo tee /etc/sudoers.d/ha-service-updater\n"
            "sudo chmod 440 /etc/sudoers.d/ha-service-updater"
        )

        persistent_notification.async_create(
            self.hass,
            title=f"Service Updater: команда для {self._host}",
            message=(
                f"Скопируйте этот блок и выполните на хосте `{self._host}`:\n\n"
                f"```bash\n{full_command}\n```\n\n"
                f"После выполнения вернитесь в окно настройки и нажмите «Проверить подключение»."
            ),
            notification_id=f"service_updater_setup_{self._host}",
        )

        schema = vol.Schema({
            vol.Optional("full_command", default=full_command): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional("action", default="check"): vol.In(["check", "finish"]),
        })

        return self.async_show_form(
            step_id="show_command",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "host": self._host,
                "instruction": (
                    "1. Кликните в поле с командой ниже, нажмите Ctrl+A (выделить всё) и Ctrl+C (скопировать).\n"
                    "2. Выполните скопированную команду на вашем сервере.\n"
                    "3. Вернитесь сюда и нажмите «Отправить» с действием «check»."
                ),
            },
        )

    async def _create_entry(self) -> FlowResult:
        await self.async_set_unique_id(
            f"{self._app}_{self._ssh_user}@{self._host}:{self._ssh_port}"
        )
        self._abort_if_unique_id_configured()

        persistent_notification.async_dismiss(
            self.hass, f"service_updater_setup_{self._host}"
        )

        data = {
            CONF_APP: self._app,
            CONF_HOST: self._host,
            CONF_SSH_USER: self._ssh_user,
            CONF_SSH_PORT: self._ssh_port,
            CONF_SCAN_INTERVAL_HOURS: self._interval,
        }
        if self._app == "frigate":
            data[CONF_COMPOSE_DIR] = DEFAULT_COMPOSE_DIR

        title = f"{APPS[self._app]} @ {self._host}"
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ServiceUpdaterOptionsFlow()


class ServiceUpdaterOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_HOURS,
            self.config_entry.data.get(
                CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
            ),
        )
        current_time = self.config_entry.options.get(CONF_CHECK_TIME)

        return self.async_show_form(
            step_id="init",
            description_placeholders={
                "host": self.config_entry.data.get(CONF_HOST, ""),
                "app": APPS.get(self.config_entry.data.get(CONF_APP), ""),
                "default": DEFAULT_SCAN_INTERVAL_HOURS,
                "min": SCAN_INTERVAL_MIN_HOURS,
                "max": SCAN_INTERVAL_MAX_HOURS,
            },
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_CHECK_TIME, description={"suggested_value": current_time}
                ): selector.TimeSelector(),
                vol.Optional(CONF_SCAN_INTERVAL_HOURS, default=current_interval):
                    vol.All(int, vol.Range(
                        min=SCAN_INTERVAL_MIN_HOURS, max=SCAN_INTERVAL_MAX_HOURS,
                    )),
            }),
        )