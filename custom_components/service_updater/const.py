"""Константы интеграции Service Updater."""
DOMAIN = "service_updater"

CONF_APP = "app"
CONF_HOST = "host"
CONF_SSH_USER = "ssh_user"
CONF_SSH_PORT = "ssh_port"
CONF_COMPOSE_DIR = "compose_dir"
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"

SERVICE_INSTALL_DEBIAN = "install_debian"
SERVICE_INSTALL_APP = "install_app"

DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "root"
DEFAULT_COMPOSE_DIR = "/opt/frigate"
DEFAULT_SCAN_INTERVAL_HOURS = 24
SCAN_INTERVAL_MIN_HOURS = 1
SCAN_INTERVAL_MAX_HOURS = 168

# Тайм-ауты (секунды)
PROGRAM_CHECK_TIMEOUT = 60
DEBIAN_CHECK_TIMEOUT = 120
INSTALL_DEBIAN_TIMEOUT = 900
INSTALL_APP_TIMEOUT = 1200

ATTR_ENTRY_ID = "entry_id"
ATTR_HOST = "host"

SSH_KEY_DIR = ".ssh"
SSH_PRIVATE_KEY = "id_rsa"
SSH_PUBLIC_KEY = "id_rsa.pub"