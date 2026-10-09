# Деплой

Прод — один VPS с docker compose. На сервер попадают два файла: `compose.prod.yaml` (как `~/spectra/compose.yaml`) и `.env`, который собирается из переменных и секретов GitHub при каждом деплое. Руками на сервере ничего не правится.

## Что работает на сервере

| Сервис | Что делает |
|---|---|
| `caddy` | единственный, кто смотрит в интернет: TLS-сертификат Let's Encrypt для `SPECTRA_DOMAIN`, проксирует всё в api |
| `migrate` | при каждом старте: миграции Postgres, бакет в S3, группа воркеров в Redis; отработал и вышел |
| `api` | `spectra` в серверном режиме: принимает загрузки, отдаёт статусы, SSE и таймлайны |
| `worker` | `spectra-worker`: берёт задачи из Redis, анализирует, раз в час удаляет разборы, которые не открывали 30 дней |
| `postgres`, `redis`, `s3` | хранилища во внутренней сети без портов наружу и без выхода в интернет |

`api` и `worker` стартуют только после успешного `migrate`. Healthcheck api — `GET /ready`: пока какое-то хранилище не отвечает, контейнер не считается здоровым, и `up --wait` ждёт.

## Как запускается

- Пуш тега `v*` (например, `git tag v0.1.0 && git push origin v0.1.0`) или ручной запуск workflow `deploy` в Actions.
- Workflow собирает образ `ghcr.io/<владелец>/<репозиторий>:<коммит>`, кладёт файлы на сервер, делает `docker compose pull` и `up --wait`, затем `spectra-smoke` внутри контейнера api и `GET https://<домен>/ready` снаружи.
- Откат — ручной запуск `deploy` на предыдущем теге. Миграции пока только добавляют, старый код с новой схемой работает.

## Сервер, один раз

1. Docker Engine с плагином compose.
2. Отдельный пользователь для деплоя в группе `docker`. Группа `docker` равна root на этой машине, поэтому ключ этого пользователя — только для деплоя.
3. SSH-ключ без пароля: публичная часть в `~/.ssh/authorized_keys` пользователя деплоя, приватная — в секрет `DEPLOY_SSH_KEY`.
4. `ssh-keyscan <адрес сервера>` — вывод в секрет `DEPLOY_KNOWN_HOSTS`.
5. DNS: A-запись (и AAAA, если есть IPv6) домена на адрес сервера. Без неё Caddy не получит сертификат.
6. Открыть в файрволе 80/tcp, 443/tcp и 443/udp (HTTP/3).

## GitHub, один раз

Settings → Environments → `production`. Там же можно включить ручное подтверждение деплоя.

Секреты:

| Имя | Что |
|---|---|
| `DEPLOY_SSH_KEY` | приватный ключ пользователя деплоя |
| `DEPLOY_KNOWN_HOSTS` | вывод `ssh-keyscan` для сервера |
| `POSTGRES_PASSWORD` | пароль Postgres |
| `REDIS_PASSWORD` | пароль Redis |
| `S3_ACCESS_KEY` | ключ доступа versitygw |
| `S3_SECRET_KEY` | секрет versitygw |

Переменные:

| Имя | Что |
|---|---|
| `DEPLOY_HOST` | адрес сервера |
| `DEPLOY_USER` | пользователь деплоя |
| `SPECTRA_DOMAIN` | домен сервиса, например `spectra.example.org` |
| `SPECTRA_HTTP_PORT` | `80`: нужен Let's Encrypt и для редиректа на HTTPS |
| `SPECTRA_HTTPS_PORT` | `443` |
| `SPECTRA_LOG_LEVEL` | необязательно, по умолчанию `info` |
| `SPECTRA_API_MEMORY_LIMIT` | необязательно, по умолчанию `1g` (так же ограничен `migrate`) |
| `SPECTRA_WORKER_MEMORY_LIMIT` | необязательно, по умолчанию `2g` |

`SPECTRA_BIND_ADDRESS` и `SPECTRA_API_PORT` больше не нужны: api наружу не публикуется, их можно удалить из environment.

Значения без одинарных кавычек и переводов строк. Пароли и ключи удобно генерировать так: `openssl rand -hex 32`.

## Настройки движка

Compose задаёт их сам, перечислены для запуска без compose.

| Переменная | По умолчанию | Что |
|---|---|---|
| `SPECTRA_MODE` | `local` | `local` — всё в памяти, воркер внутри api; `hosted` — Postgres, Redis, S3 и отдельный `spectra-worker` |
| `SPECTRA_POSTGRES_HOST`, `_PORT`, `_DATABASE`, `_USER`, `_PASSWORD` | —, `5432`, `spectra`, `spectra`, — | Postgres |
| `SPECTRA_REDIS_HOST`, `_PORT`, `_DATABASE`, `_PASSWORD` | —, `6379`, `0`, нет | Redis |
| `SPECTRA_S3_URL`, `_REGION`, `_ACCESS_KEY`, `_SECRET_KEY`, `_BUCKET` | —, `us-east-1`, —, —, `spectra` | S3 |
| `SPECTRA_RETENTION_DAYS` | `30` | сколько дней хранить разбор после последнего открытия |
| `SPECTRA_SWEEP_INTERVAL_S` | `3600` | как часто воркер ищет устаревшие разборы |

Прочерк — значение обязательно в серверном режиме.

## Локально весь стек

`cp .env.example .env`, поменять пароли, `docker compose up --build --wait`. Api на `SPECTRA_BIND_ADDRESS:SPECTRA_API_PORT`, без Caddy и TLS. `spectra-smoke http://127.0.0.1:8000` проверяет весь путь от загрузки до таймлайна.

## Что важно знать

- Docker публикует порты в обход файрвола хоста (в том числе ufw). Наружу открыт только Caddy; не добавляйте `ports` хранилищам.
- Postgres берёт пароль только при первом создании тома. Смена секрета потом не меняет пароль в базе: сначала `ALTER ROLE spectra PASSWORD ...` в базе, потом секрет.
- Сертификаты Caddy лежат в томе `caddy-data`. Не удаляйте его без нужды: у Let's Encrypt лимиты на выпуск.
- Задача, на которой воркер упал или был убит, через 5 минут достаётся другому воркеру. Перезапуск воркера ничего не теряет.
- Образ в GHCR по умолчанию приватный; сервер логинится в реестр коротким токеном задачи деплоя.
