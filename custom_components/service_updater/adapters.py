"""Описания поддерживаемых приложений."""
from __future__ import annotations

from dataclasses import dataclass
import aiohttp

@dataclass(frozen=True)
class ServiceAdapter:
    key: str
    title: str
    github_repo: str = ""
    default_port: int = 0
    version_url_path: str | None = None
    version_json_key: str | None = None
    asset_pattern: str | None = None
    restart_service: str | None = None
    is_docker: bool = False
    docker_service_name: str = "frigate"

    async def get_local_version(
        self, session: aiohttp.ClientSession, host: str, port: int
    ) -> str:
        if self.version_url_path:
            url = f"http://{host}:{port}{self.version_url_path}"
            async with session.get(url, timeout=10) as resp:
                resp.raise_for_status()
                if self.version_json_key:
                    return str((await resp.json())[self.version_json_key])
                return (await resp.text()).strip()
        raise RuntimeError(f"Адаптер {self.key} не умеет получать версию по HTTP")

ADAPTERS: dict[str, ServiceAdapter] = {
    "torrserver": ServiceAdapter(
        key="torrserver", title="TorrServer",
        github_repo="YouROK/TorrServer",
        default_port=8090,
        version_url_path="/echo",
        asset_pattern="torrserver-linux-amd64",
        restart_service="torrserver.service",
    ),
    "cloudpub": ServiceAdapter(
        key="cloudpub", title="CloudPub",
        github_repo="ermak-dev/cloudpub",
        default_port=8090,
        asset_pattern="clo-linux-amd64.zip",
        restart_service="cloudpub.service",
    ),
    "frigate": ServiceAdapter(
        key="frigate", title="Frigate",
        github_repo="blakeblackshear/frigate",
        default_port=5000,
        version_url_path="/api/version",
        version_json_key="version",
        is_docker=True,
        docker_service_name="frigate",
    ),
}