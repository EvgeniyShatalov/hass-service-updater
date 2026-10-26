<div align="center">

**[🇷🇺 Русский](#-русский)** | **[🇬🇧 English](#-english)**

</div>

---

# 🇷🇺 Русский

# Service Updater для Home Assistant

Интеграция для Home Assistant, предназначенная для централизованного мониторинга и установки обновлений **операционной системы Debian** и **конкретных приложений** (TorrServer, CloudPub, Frigate) на удалённых серверах через SSH. 

Интеграция заменяет bash-скрипты и MQTT-костыли на полностью нативный Python-код с красивым интерфейсом.

## ✨ Основные возможности

*   **Мониторинг Debian:** Проверка наличия обновлений пакетов (`apt`) и вывод точного списка пакетов с их версиями «до → после».
*   **Мониторинг приложений:** Проверка текущей версии приложения и сравнение с последним релизом на GitHub.
*   **Установка в один клик (через сервисы):** Раздельные сервисы для обновления ОС и приложения, что позволяет гибко настраивать автоматизации.
*   **Безопасность (SSH):** Генерация SSH-ключа прямо в интерфейсе Home Assistant. Подключение происходит от имени пользователя `root` (или указанного вами).
*   **Умные проверки:** При настройке интеграция проверяет доступность хоста (ping), открытость SSH-порта (TCP) и валидность ключа (SSH Auth).
*   **Расписание:** Возможность задать конкретное время ежедневной проверки (например, в 03:00) или использовать интервал (раз в 24 часа).
*   **Ручная проверка:** Кнопка «Проверить сейчас» для мгновенного обновления статуса.

## 📦 Поддерживаемые приложения

| Приложение | Как проверяется версия | Как обновляется |
| :--- | :--- | :--- |
| **TorrServer** | HTTP API (`/echo`) | Скачивание бинарника + перезапуск systemd |
| **CloudPub** | CLI (`clo --version`) | Скачивание бинарника + перезапуск systemd |
| **Frigate** | HTTP API (`/api/version`) | `docker compose pull` + `up -d` |
| **Debian OS** | SSH (`apt list --upgradable`) | `apt-get upgrade -y` |

## ⚙️ Требования к удалённым хостам

1.  **SSH-сервер:** На хосте должен быть установлен и запущен `openssh-server`.
2.  **NOPASSWD для sudo:** Пользователь, от имени которого работает интеграция, должен иметь право выполнять команды без пароля.
    *   Для **Debian**: `/usr/bin/apt-get update, /usr/bin/apt-get upgrade`
    *   Для **TorrServer**: `/usr/bin/systemctl restart torrserver.service`
    *   Для **CloudPub**: `/usr/bin/systemctl restart cloudpub.service`
    *   Для **Frigate**: `/usr/bin/docker compose` (если пользователь не в группе `docker`).

## 🚀 Установка

1.  Создайте Personal Access Token (classic) на GitHub с правами `repo`.
2.  В Home Assistant перейдите в **HACS → Integrations → ⋮ → Custom repositories**.
3.  Вставьте ссылку на этот репозиторий и выберите тип **Integration**.
4.  Установите интеграцию и перезагрузите Home Assistant.

## 🛠 Настройка

1.  Перейдите в **Настройки → Устройства и службы → Добавить интеграцию → Service Updater**.
2.  **Шаг 1:** Сгенерируйте SSH-ключ (если его еще нет).
3.  **Шаг 2:** Выберите приложение, укажите IP-адрес хоста, порт (по умолчанию 22) и пользователя (по умолчанию `root`).
4.  **Шаг 3:** Скопируйте предложенную команду (она также появится в уведомлениях) и выполните её в консоли вашего сервера. Это добавит публичный ключ в `authorized_keys` и настроит `sudoers`.
5.  Нажмите «Проверить подключение» и завершите настройку.

## 📊 Сущности

Для каждого настроенного хоста создаются:
*   `update.<app>` — стандартная сущность обновлений (только для чтения).
*   `sensor.<app>_version` — текущая версия приложения.
*   `sensor.<app>_next_check` — точное время следующей проверки.
*   `sensor.<app>_debian_last_upgrade` — время и список последних обновлённых пакетов Debian.
*   `binary_sensor.<app>_update` — есть ли обновление для приложения (Вкл/Выкл).
*   `binary_sensor.<app>_debian_update` — есть ли обновления для Debian (Вкл/Выкл).
*   `button.<app>_check_now` — кнопка «Проверить сейчас».

## ⚡ Сервисы

Вызывайте эти сервисы в автоматизациях (через `action` в YAML):
*   `service_updater.install_debian` — запускает только `apt upgrade`. Параметры: `host` или `entry_id`.
*   `service_updater.install_app` — запускает только обновление приложения. Параметры: `host` или `entry_id`.

---

<div align="center">
<a href="#-русский">⬆️ Наверх</a>
</div>

---

# 🇬🇧 English

# Service Updater for Home Assistant

A Home Assistant integration designed to centrally monitor and install updates for the **Debian operating system** and **specific applications** (TorrServer, CloudPub, Frigate) on remote servers via SSH.

This integration replaces bash scripts and MQTT workarounds with native Python code and a clean user interface.

## ✨ Key Features

*   **Debian Monitoring:** Checks for `apt` package updates and displays an exact list of packages with their "old → new" versions.
*   **Application Monitoring:** Checks the current app version and compares it with the latest GitHub release.
*   **One-click Install (via Services):** Independent services for updating the OS and the app, allowing flexible automation setups.
*   **Security (SSH):** SSH key generation directly in the Home Assistant UI. Connections are made as `root` (or a specified user).
*   **Smart Checks:** During setup, the integration verifies host availability (ping), SSH port (TCP), and key validity (SSH Auth).
*   **Scheduling:** Set a specific daily check time (e.g., 03:00) or use an interval (every 24 hours).
*   **Manual Check:** A "Check Now" button for instant status updates.

## 📦 Supported Applications

| Application | How version is checked | How it updates |
| :--- | :--- | :--- |
| **TorrServer** | HTTP API (`/echo`) | Binary download + systemd restart |
| **CloudPub** | CLI (`clo --version`) | Binary download + systemd restart |
| **Frigate** | HTTP API (`/api/version`) | `docker compose pull` + `up -d` |
| **Debian OS** | SSH (`apt list --upgradable`) | `apt-get upgrade -y` |

## ⚙️ Remote Host Requirements

1.  **SSH Server:** `openssh-server` must be installed and running.
2.  **NOPASSWD for sudo:** The user running the integration must have passwordless sudo rights for specific commands.
    *   **Debian:** `/usr/bin/apt-get update, /usr/bin/apt-get upgrade`
    *   **TorrServer:** `/usr/bin/systemctl restart torrserver.service`
    *   **CloudPub:** `/usr/bin/systemctl restart cloudpub.service`
    *   **Frigate:** `/usr/bin/docker compose` (if the user is not in the `docker` group).

## 🚀 Installation

1.  Create a Personal Access Token (classic) on GitHub with `repo` scope.
2.  In Home Assistant, go to **HACS → Integrations → ⋮ → Custom repositories**.
3.  Paste the repository URL and select **Integration** as the category.
4.  Install the integration and restart Home Assistant.

## 🛠 Configuration

1.  Go to **Settings → Devices & Services → Add Integration → Service Updater**.
2.  **Step 1:** Generate an SSH key (if not already present).
3.  **Step 2:** Select the application, enter the host IP, port (default 22), and user (default `root`).
4.  **Step 3:** Copy the provided command (it also appears in notifications) and run it in your server's console. This adds the public key to `authorized_keys` and configures `sudoers`.
5.  Click "Check connection" and finish the setup.

## 📊 Entities

For each configured host, the following entities are created:
*   `update.<app>` — standard update entity (read-only).
*   `sensor.<app>_version` — current app version.
*   `sensor.<app>_next_check` — exact time of the next check.
*   `sensor.<app>_debian_last_upgrade` — timestamp and list of recently updated Debian packages.
*   `binary_sensor.<app>_update` — app update available (On/Off).
*   `binary_sensor.<app>_debian_update` — Debian update available (On/Off).
*   `button.<app>_check_now` — "Check Now" button.

## ⚡ Services

Call these services in your automations (via `action` in YAML):
*   `service_updater.install_debian` — runs only `apt upgrade`. Parameters: `host` or `entry_id`.
*   `service_updater.install_app` — runs only the app update. Parameters: `host` or `entry_id`.

---

<div align="center">
<a href="#-english">⬆️ Back to top</a>
</div>