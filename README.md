# JobRadar

Сервис поиска и оценки вакансий: собирает вакансии из открытых источников, фильтрует их по критериям, оценивает соответствие резюме с помощью LLM, присылает подходящие в Telegram и ведёт журнал откликов.

Проект в разработке.

## Стек

- Backend: Python, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL
- Фоновые задачи: Celery, Redis
- Интеграции: getmatch, hh.ru API, Telegram (aiogram 3), LLM API
- Frontend: React, TypeScript, Vite
- Инфраструктура: Docker Compose, GitHub Actions

## Лицензия

MIT
