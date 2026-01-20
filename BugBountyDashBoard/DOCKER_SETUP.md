# Docker Setup для Bug Bounty Dashboard

## Структура проекта

```
BugBountyMCP/
├── docker-compose.yml  (основной - добавить сервис frontend)
├── .env
├── playwright/
├── ...
└── BugBountyDashBoard/  (эта директория)
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── src/
    └── ...
```

## Что добавить в основной docker-compose.yml

Добавьте следующий сервис в ваш `docker-compose.yml` в директории `../BugBountyMCP`:

```yaml
  frontend:
    build:
      context: ./BugBountyDashBoard
      dockerfile: Dockerfile
    container_name: bb-frontend
    ports:
      - "${FRONTEND_PORT:-3000}:80"
    depends_on:
      - api
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## Настройка .env

Добавьте в `.env` файл в `../BugBountyMCP` (опционально, по умолчанию 3000):

```bash
FRONTEND_PORT=3000
```

## Запуск

Из директории `../BugBountyMCP`:

```bash
# Собрать и запустить все сервисы
docker-compose up -d --build

# Или только фронтенд
docker-compose up -d --build frontend
```

## Проверка

```bash
# Проверить статус
docker-compose ps

# Посмотреть логи фронтенда
docker-compose logs -f frontend
```

## Доступ

- **Фронтенд**: http://localhost:3000
- **API**: http://localhost:${API_PORT} (обычно 8000)

Все запросы к `/api/*` автоматически проксируются к сервису `bb-api:8000` через Nginx.

## Особенности

- ✅ Nginx проксирует все `/api/*` запросы к `bb-api:8000`
- ✅ SPA роутинг настроен - все маршруты ведут на index.html
- ✅ Gzip компрессия включена
- ✅ Кэширование статических файлов настроено
- ✅ Healthcheck для автоматического перезапуска
- ✅ Security headers добавлены

## Пересборка после изменений в коде

```bash
# Пересобрать только фронтенд
docker-compose build frontend

# Перезапустить фронтенд
docker-compose up -d --no-deps frontend
```

## Troubleshooting

### Фронтенд не подключается к API
- Убедитесь, что API контейнер запущен: `docker-compose ps`
- Проверьте логи: `docker-compose logs api`
- Проверьте, что в nginx.conf проксирование настроено на `bb-api:8000`

### Nginx не стартует
- Проверьте логи: `docker-compose logs frontend`
- Проверьте синтаксис nginx.conf: `docker exec bb-frontend nginx -t`

### Порт занят
- Измените `FRONTEND_PORT` в .env файле
- Или остановите сервис, занимающий порт 3000

### Сборка образа
- Убедитесь, что Dockerfile и nginx.conf находятся в `./BugBountyDashBoard`
- Проверьте, что package.json существует
