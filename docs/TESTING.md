# Проверка MeetPoint

[Критерии Backend-жюри, стр. 2](https://static.centraluniversity.ru/documents/events/Prod/Kriterii-Khakaton-PROD-Minsk-2026.pdf#page=2) учитывают интеграционные сценарии и отчёт, показывающий их покрытие. Здесь перечислены конкретные проверки проекта и способ получить измеримый результат.

## Среда

Тесты вызывают настоящее FastAPI-приложение через `TestClient` и выполняют SQL в PostgreSQL. Запросы ORM не подменяются моками. [tests/conftest.py](../tests/conftest.py) применяет миграции и создаёт независимые браузерные сессии.

Адрес тестовой БД задаётся явно через `TEST_DATABASE_URL`. Разрешён PostgreSQL с именем БД, заканчивающимся на `_test`; это имя должно отличаться от рабочей БД. Перед каждым тестом и после него очищаются таблицы этой тестовой БД. Одновременные независимые запуски должны использовать разные тестовые БД.

## Соответствие сценариев тестам

Имена в таблице — функции существующих тестов; все файлы находятся в `tests/`.

| Сценарий | Файл и тесты | Что проверяется |
| --- | --- | --- |
| Повторный вход | [test_profiles.py](../tests/test_profiles.py): `test_session_and_profile_survive_repeated_entry` | Cookie сохраняется; обновляется прежний профиль и его интересы |
| Валидация профиля и события | [test_profiles.py](../tests/test_profiles.py): `test_invalid_profile_does_not_overwrite_existing_one`, `test_event_tags_are_normalized_and_duplicates_rejected` | Невалидный ввод не портит профиль; нормализация тегов не создаёт дубли |
| Одновременная регистрация | [test_profiles.py](../tests/test_profiles.py): `test_parallel_registration_keeps_one_profile_and_complete_tag_set` | Один профиль и полный набор тегов после двух конкурирующих сохранений |
| Знакомство и статистика | [test_connections.py](../tests/test_connections.py): `test_contacts_open_for_both_sides_only_after_acceptance` | До согласия контактов нет, после согласия видны обеим сторонам; пара учитывается один раз |
| Пропуск приглашения | [test_connections.py](../tests/test_connections.py): `test_skipping_is_final_and_never_reveals_contacts` | Контакты закрыты, повтор решения допустим, смена решения запрещена |
| Ограничения приглашений | [test_connections.py](../tests/test_connections.py): `test_self_duplicate_and_reverse_invitations_are_rejected`, `test_only_recipient_can_decide_and_sender_cannot_be_forged` | Запрос себе и дубли отклоняются; отправитель и третий человек не принимают чужой запрос |
| Гонки приглашений и ответов | [test_connections.py](../tests/test_connections.py): `test_parallel_invitations_create_one_pair`, `test_parallel_opposite_decisions_have_one_winner` | Одна запись на пару и одно окончательное решение |
| Права и границы событий | [test_access.py](../tests/test_access.py): `test_membership_and_organizer_permissions`, `test_event_boundaries_apply_to_tags_people_requests_and_contacts` | Только свои события, запросы и контакты; статистика доступна владельцу |
| Сессии и Origin | [test_access.py](../tests/test_access.py): `test_expired_session_cannot_recover_profile_or_organizer_rights`, `test_foreign_origin_is_rejected_before_session_creation` | Истёкшая cookie не восстанавливает права; запросы с чужого сайта блокируются |
| Сведения о событии и QR | [test_access.py](../tests/test_access.py): `test_public_event_and_qr_do_not_expose_private_state` | Ссылка ведёт на JSON API, SVG отдаётся, закрытых данных в ответе нет |
| Рекомендации | [test_discovery.py](../tests/test_discovery.py): `test_recommendations_rank_before_pagination_and_keep_stable_ties` | Сортировка по пересечениям до пагинации, стабильные равенства и нулевой результат |
| Фильтрация и пагинация | [test_discovery.py](../tests/test_discovery.py): `test_tag_filter_uses_any_selected_tag_and_validates_pagination` | Совпадение хотя бы одного выбранного тега, границы limit/offset |

Общий [assert_public](../tests/helpers.py) рекурсивно проверяет отсутствие полей контакта, токена и сессии в публичных ответах. Параллельные сценарии используют отдельные клиенты и барьер старта. Они проверяют конкурирующие запросы; нагрузочное тестирование этим не заменяется.

## Отчёты

После установки зависимостей разработки и настройки отдельной тестовой БД запусти из корня проекта:

```sh
python -m pytest --cov=app --cov-branch --cov-report=term-missing --cov-report=xml:reports/coverage.xml --cov-report=html:reports/html --junitxml=reports/junit.xml
```

В PowerShell переменную задают, например, так:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://meetpoint:meetpoint@localhost:5432/meetpoint_test"
```

Результаты проверок:

| Файл | Кто создаёт | Назначение |
| --- | --- | --- |
| `reports/coverage.xml` | `pytest-cov` | Машиночитаемое покрытие кода приложения |
| `reports/html/index.html` | `pytest-cov` | Покрытые строки, ветви и пропуски по файлам |
| `reports/junit.xml` | pytest | Результаты выполнения отдельных тестов |
| `reports/demo.json` | `scripts.smoke` | Результат HTTP-проверки демонстрационного развёртывания |

XML и HTML описывают покрытие кода. Таблица выше связывает его с бизнес-сценариями, а JUnit показывает, какие тесты были выполнены. Процент покрытия нужно брать из свежего отчёта конкретного запуска; число в документации не фиксируется. Наличие теста само по себе не подтверждает успешный запуск.

В [pyproject.toml](../pyproject.toml) настроен порог покрытия 90%. Это выбранное правило проекта, а не измеренный результат и не числовое требование кейса.

## CI и демонстрационный CD

[.github/workflows/ci.yml](../.github/workflows/ci.yml) разделяет проверки и временное развёртывание. После успешных проверок job собирает приложение, поднимает Compose, применяет миграции, загружает демоданные и запускает [scripts/smoke.py](../scripts/smoke.py) по настоящему HTTP. Для локального повторения после старта приложения:

```sh
python -m scripts.smoke --base-url http://localhost:8000 --report reports/demo.json
```

Это проверка работающего процесса дополнительно к `TestClient`. Отчёты покрытия и логи контейнеров сохраняются как артефакты workflow. Если шаг завершился с ошибкой, нужно смотреть лог и доступные артефакты; этот документ не заявляет, что pipeline или его deploy-job уже прошли.

Развёртывание заканчивается вместе с runner. Оно демонстрирует механизм CD и не предоставляет постоянный публичный адрес.
