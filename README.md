# JobRadar

[![CI](https://github.com/Smirnoff-Sergey/jobradar/actions/workflows/ci.yml/badge.svg)](https://github.com/Smirnoff-Sergey/jobradar/actions/workflows/ci.yml)

Сервис поиска и оценки вакансий: собирает вакансии из открытых источников, фильтрует их по критериям, оценивает соответствие резюме с помощью LLM, присылает подходящие в Telegram и ведёт журнал откликов.

Проект в разработке. Готов этап 1 — каркас: API на FastAPI, PostgreSQL, миграции, JWT-авторизация, тесты и CI.

## Стек

- Backend: Python 3.13, FastAPI, SQLAlchemy 2 (async), asyncpg, Alembic, PostgreSQL
- Авторизация: JWT (access + refresh), хеширование паролей Argon2
- Качество: pytest, ruff, mypy (strict), GitHub Actions
- Запуск: Docker Compose
- В планах: Celery и Redis, адаптеры getmatch и hh.ru, Telegram-бот на aiogram 3, LLM-оценка, frontend на React и TypeScript

## Быстрый старт

```bash
cp .env.example .env
# впишите в .env секрет JOBRADAR_JWT_SECRET:
python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up -d --build --wait
docker compose exec api python -m app.cli create-user --email you@example.com
```

Документация API: http://localhost:8000/docs

Регистрации нет: сервис рассчитан на одного владельца, пользователь создаётся командой `create-user`.

## API

| Метод и путь | Назначение |
|---|---|
| `GET /api/v1/health` | Проверка живости API и БД (`503`, если БД недоступна) |
| `POST /api/v1/auth/login` | Вход по email и паролю, выдаёт пару токенов |
| `POST /api/v1/auth/refresh` | Новая пара токенов по refresh-токену |
| `GET /api/v1/auth/me` | Текущий пользователь (заголовок `Authorization: Bearer <access>`) |

Все ошибки приходят в одном формате:

```json
{"error": {"code": "invalid_credentials", "message": "Неверный email или пароль"}}
```

## Устройство backend

```
backend/
  app/
    api/            # роуты FastAPI, зависимости, обработчики ошибок
    core/           # настройки, ошибки предметной области, JWT и пароли
    db/             # модели SQLAlchemy, создание движка и сессий
    repositories/   # доступ к БД
    services/       # бизнес-логика
    schemas/        # схемы Pydantic для API
    cli.py          # служебные команды
  migrations/       # Alembic
  tests/
```

Слои связаны в одну сторону: `api` → `services` → `repositories`. Роуты не обращаются к БД напрямую. Репозитории делают `flush`, транзакцию завершает (`commit`) сервис.

## Разработка

Нужны [uv](https://docs.astral.sh/uv/) и PostgreSQL для интеграционных тестов.

```bash
cd backend
uv sync

uv run ruff format .
uv run ruff check .
uv run mypy

# интеграционные тесты пересоздают схему в указанной БД, поэтому её имя обязано оканчиваться на _test
export JOBRADAR_TEST_DATABASE_URL=postgresql+asyncpg://jobradar:jobradar@localhost:5432/jobradar_test
uv run pytest --cov
```

Без `JOBRADAR_TEST_DATABASE_URL` выполняются только юнит-тесты, интеграционные пропускаются. В CI (`CI=true`) отсутствие переменной — ошибка, а не пропуск.

Как устроены тесты:

- схема тестовой БД создаётся миграциями Alembic, так что миграции проверяются на каждом прогоне;
- отдельный тест сверяет модели с миграциями: если поменять модель и забыть миграцию, он упадёт;
- каждый тест идёт внутри транзакции, которая откатывается после теста, даже если код вызывал `commit()`.

Хуки pre-commit: `uv run --directory backend pre-commit install`.

## Лицензия

MIT
