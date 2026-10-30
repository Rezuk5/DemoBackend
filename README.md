# MeetPoint

Бэкенд для знакомств на мероприятиях. Участники выбирают интересы, находят друг друга и отправляют приглашения. Контакты открываются только после принятия запроса.

Стек: Python 3.12, FastAPI, PostgreSQL, SQLAlchemy и Alembic.

## Запуск

Нужен Docker с Compose. Из папки проекта:

```sh
docker compose up -d db
docker compose build app
docker compose run --rm app python -m alembic upgrade head
docker compose up -d app
```

Добавить демособытие и четыре профиля:

```sh
docker compose exec app python -m scripts.seed
```

## Тесты

Первую команду достаточно выполнить один раз:

```sh
docker compose exec db createdb -U meetpoint meetpoint_test
docker compose --profile test run --build --rm tests
```

Тесты проверяют знакомства, приватность контактов, права доступа и одновременные запросы. Они работают с отдельной тестовой БД.

## CI/CD

На push и pull request запускаются Ruff, миграции и тесты с покрытием. Затем пайплайн собирает Docker-образ, поднимает временный стенд и проверяет знакомство через HTTP. Отчёты и логи сохраняются в Actions, стенд после проверки удаляется.

[Workflow](.github/workflows/ci.yml) · [Архитектура](docs/ARCHITECTURE.md) · [Проверки и отчёты](docs/TESTING.md)
