# 🎬 Movie Bot — бот регистрации на университетский киновечер

Telegram-бот на **aiogram 3.x** для регистрации студентов на киновечер через QR-код
(Telegram deep link) и полноценной админ-панели прямо внутри бота.

## Содержание

1. [Стек](#стек)
2. [Архитектура](#архитектура)
3. [Установка и запуск локально](#установка-и-запуск-локально)
4. [Настройка `.env`](#настройка-env)
5. [Получение Telegram Bot Token](#получение-telegram-bot-token)
6. [Запуск через Docker](#запуск-через-docker)
7. [Миграции Alembic](#миграции-alembic)
8. [Добавление администраторов](#добавление-администраторов)
9. [Создание первого мероприятия](#создание-первого-мероприятия)
10. [Генерация QR-кода](#генерация-qr-кода)
11. [Использование админ-панели](#использование-админ-панели)
12. [Тесты](#тесты)
13. [Возможные улучшения (v2)](#возможные-улучшения-v2)

---

## Стек

- Python 3.12+
- aiogram 3.x (Router / FSM / CallbackData)
- SQLAlchemy 2.x (async, `asyncpg`)
- PostgreSQL 16
- Alembic (async миграции)
- Pydantic Settings (конфигурация из `.env`, без `python-dotenv` напрямую)
- Docker + docker-compose

## Архитектура

```text
movie_bot/
├── app/
│   ├── bot.py              # сборка Bot/Dispatcher, регистрация роутеров и middleware
│   ├── config.py            # Pydantic Settings
│   ├── handlers/            # обработчики апдейтов (Routers)
│   │   ├── start.py         # /start и deep link с QR
│   │   ├── registration.py  # ✅ Пойду / ❌ Не пойду / 🔄 Изменить решение
│   │   ├── profile.py       # /profile — личный кабинет
│   │   ├── admin.py         # вся админ-панель
│   │   └── states.py        # FSM группы
│   ├── keyboards/
│   │   ├── user.py          # клавиатуры для студентов
│   │   ├── admin.py         # клавиатуры для админки
│   │   └── callback_data.py # структурированные CallbackData
│   ├── services/             # бизнес-логика (репозитории не знают про Telegram)
│   │   ├── participants.py
│   │   ├── statistics.py
│   │   ├── export.py         # CSV/Excel
│   │   └── qr.py              # генерация QR PNG
│   ├── database/
│   │   ├── models.py          # User, Event, Registration
│   │   ├── database.py        # async engine/session
│   │   └── repositories/      # чистый SQL/ORM-доступ
│   ├── middlewares/
│   │   ├── admin.py           # is_admin-флаг + guard для админ-роутера
│   │   └── db.py               # сессия БД на каждый апдейт
│   └── utils/
│       ├── pagination.py
│       └── helpers.py
├── migrations/                # Alembic (async env.py)
├── tests/                      # pytest + pytest-asyncio (SQLite in-memory)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
├── .env.example
└── main.py                     # entrypoint, graceful shutdown
```

**Поток данных:** `Telegram → Dispatcher → middlewares (DB session, is_admin) →
Router → Handler → Service → Repository → PostgreSQL`.

Небольшое отступление от исходного дерева файлов: помимо `repositories/users.py`
и `repositories/events.py` добавлен `repositories/registrations.py` (без него вся
работа с регистрациями оказалась бы либо в сервисах, либо дублировалась бы), а в
`services/` — `export.py` и `qr.py` для CSV/Excel-экспорта и генерации QR
соответственно. `middlewares/db.py` добавлен для инъекции `AsyncSession` в каждый
хендлер по стандартному для aiogram 3 паттерну.

---

## Установка и запуск локально

```bash
git clone <your-repo-url> movie_bot
cd movie_bot

python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# отредактируйте .env — см. раздел ниже

# локально нужен PostgreSQL; проще всего поднять только его через docker:
docker compose up -d postgres

alembic upgrade head

python main.py
```

## Настройка `.env`

Скопируйте `.env.example` в `.env` и заполните:

```env
BOT_TOKEN=                 # токен от @BotFather
ADMIN_IDS=123456789        # ваш Telegram ID (через запятую, если админов несколько)
BOT_USERNAME=your_bot_username   # username бота без @, нужен для генерации ссылок/QR

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=movie_bot
POSTGRES_USER=movie_bot
POSTGRES_PASSWORD=change_me

DATABASE_URL=postgresql+asyncpg://movie_bot:change_me@postgres:5432/movie_bot
```

Если запускаете `python main.py` **не через Docker**, замените в `DATABASE_URL`
хост `postgres` на `localhost` (или на тот адрес, где реально слушает Postgres).

## Получение Telegram Bot Token

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram.
2. Отправьте `/newbot`, задайте имя и username (должен заканчиваться на `bot`).
3. Скопируйте выданный токен в `BOT_TOKEN` в `.env`.
4. Тот же username (без `@`) укажите в `BOT_USERNAME` — он нужен для генерации
   ссылок вида `https://t.me/BOT_USERNAME?start=event_123`.

Чтобы узнать свой Telegram ID для `ADMIN_IDS`, напишите
[@userinfobot](https://t.me/userinfobot).

## Запуск через Docker

```bash
docker compose up --build
```

Это поднимет два сервиса:

- `postgres` — PostgreSQL 16 с healthcheck;
- `bot` — применяет миграции (`alembic upgrade head`) и запускает `python main.py`.

Логи бота:

```bash
docker compose logs -f bot
```

Остановить:

```bash
docker compose down          # с сохранением данных
docker compose down -v       # + удалить volume с данными Postgres
```

## Миграции Alembic

```bash
# применить все миграции
alembic upgrade head

# создать новую миграцию после изменения моделей
alembic revision --autogenerate -m "описание изменений"

# откатить последнюю миграцию
alembic downgrade -1
```

`migrations/env.py` берёт `DATABASE_URL` из тех же Pydantic Settings, что и
приложение — отдельно настраивать строку подключения для Alembic не нужно.

## Добавление администраторов

Добавьте Telegram ID через запятую в `ADMIN_IDS` в `.env` и перезапустите бота:

```env
ADMIN_IDS=111111111,222222222,333333333
```

Проверка прав происходит **только на сервере** (см. `app/config.py` →
`Settings.is_admin`) и применяется middleware'ом `AdminAccessGuard` перед
каждым обработчиком в `app/handlers/admin.py` — обычный пользователь не может
получить доступ, даже если каким-то образом отправит боту «админский»
`callback_data`.

## Создание первого мероприятия

1. Напишите боту `/admin` (доступно только ID из `ADMIN_IDS`).
2. «🎬 Мероприятия» → «➕ Создать мероприятие».
3. Последовательно введите: название → описание (или `-`, чтобы пропустить) →
   дату (`ДД.ММ.ГГГГ`) → время (`ЧЧ:ММ`) → место.
4. Бот покажет карточку мероприятия и ссылку для регистрации вида
   `https://t.me/BOT_USERNAME?start=event_1`.

## Генерация QR-кода

В карточке мероприятия (`/admin` → 🎬 Мероприятия → выбрать мероприятие) нажмите
**🔗 QR-ссылка** — бот пришлёт PNG-изображение с QR-кодом, который можно
скачать и распечатать для расклейки/раздачи студентам.

## Тестирование регистрации

1. Отсканируйте QR (или откройте ссылку `https://t.me/BOT_USERNAME?start=event_1`
   с другого аккаунта).
2. Бот покажет карточку мероприятия с кнопками «✅ Пойду» / «❌ Не пойду».
3. Нажмите «✅ Пойду» — статус сохранится, появится кнопка «🔄 Изменить решение».
4. Проверьте, что в `/admin` → 👥 Участники → ✅ Идут появился этот пользователь.
5. Повторное открытие той же ссылки или `/start` без параметров должно
   показать текущий статус, а не создавать вторую регистрацию (это
   покрыто тестами, см. `tests/test_registration.py`).

## Использование админ-панели

`/admin` → четыре раздела:

- **🎬 Мероприятия** — создание/редактирование/удаление, активация/деактивация,
  генерация QR.
- **👥 Участники** — фильтры (Идут / Не идут / Без ответа / Пришли / Все),
  постраничный список (по 10 на страницу через `LIMIT`/`OFFSET`), карточка
  участника (ручное изменение статуса, отметка check-in, удаление
  регистрации, отправка личного сообщения), поиск, экспорт в CSV/Excel.
- **📊 Статистика** — по каждому мероприятию отдельно: сколько зарегистрировано,
  идут/не идут/без ответа, сколько пришло, % подтверждения и % явки.
- **📢 Рассылка** — выбор аудитории (все / только идущие / только пришедшие),
  предпросмотр перед отправкой, отправка с троттлингом и обработкой
  заблокировавших бота пользователей.

## Тесты

```bash
pytest
```

Тесты используют in-memory SQLite (через `aiosqlite`) вместо реального
PostgreSQL, поэтому не требуют поднятого контейнера. Покрыты: регистрация,
идемпотентность повторной регистрации, смена решения, check-in администратором,
удаление регистрации, парсинг `ADMIN_IDS`/проверка прав, статистика, поиск
участников.

---

## Возможные улучшения (v2)

- Несколько параллельных мероприятий с явным выбором «на какое я иду» в профиле.
- Отдельный QR для входа (check-in), независимый от QR регистрации — архитектура
  уже это допускает (`RegistrationStatus.CHECKED_IN` не завязан на способ входа).
- Лимит мест на мероприятие + лист ожидания.
- Автоматические напоминания за N часов до начала (APScheduler / Celery beat).
- Уведомление администратора о каждой новой регистрации в реальном времени.
- Импорт списка студентов из CSV/Excel (сверка по Telegram ID или email).
- Роли `ADMIN` / `MODERATOR` с разными правами (например, модератор не может
  удалять мероприятия).
- Веб-админка (FastAPI + тот же слой `services`/`repositories`) как альтернатива
  Telegram-интерфейсу для больших списков участников.
