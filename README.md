# Service Updater

Мониторинг и установка обновлений Debian и одного приложения (TorrServer/CloudPub/Frigate) на хосте по SSH. Пользователь SSH — **root**.

## Возможности
- Генерация SSH-ключа в UI.
- Проверки при настройке: ping, TCP-порт (на шаге параметров), SSH-аутентификация (на шаге команды).
- Готовая команда для добавления ключа и NOPASSWD.
- Тайм-аут проверки приложения: 60 секунд; Debian: 120 секунд.
- Сервисы: `service_updater.install_debian`, `service_updater.install_app`.
- `update.install` не поддерживается.