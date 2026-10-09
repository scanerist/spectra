# Деплой

Прод — один VPS с docker compose. На сервер попадают два файла: `compose.prod.yaml` (как `~/spectra/compose.yaml`) и `.env`, который собирается из переменных и секретов GitHub при каждом деплое. Руками на сервере ничего не правится.

## Как запускается

- Пуш тега `v*` (например, `git tag v0.1.0 && git push origin v0.1.0`) или ручной запуск workflow `deploy` в Actions.
- Workflow собирает образ `ghcr.io/<владелец>/<репозиторий>:<коммит>`, кладёт файлы на сервер, делает `docker compose pull` и `up --wait`, затем `spectra-smoke` внутри контейнера api.
- Откат — ручной запуск `deploy` на предыдущем теге.

## Сервер, один раз

1. Docker Engine с плагином compose.
2. Отдельный пользователь для деплоя в группе `docker`. Группа `docker` равна root на этой машине, поэтому ключ этого пользователя — только для деплоя.
3. SSH-ключ без пароля: публичная часть в `~/.ssh/authorized_keys` пользователя деплоя, приватная — в секрет `DEPLOY_SSH_KEY`.
4. `ssh-keyscan <адрес сервера>` — вывод в секрет `DEPLOY_KNOWN_HOSTS`.

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
| `SPECTRA_BIND_ADDRESS` | `127.0.0.1`: наружу api отдаёт reverse proxy |
| `SPECTRA_API_PORT` | порт api на сервере, например `8000` |
| `SPECTRA_LOG_LEVEL` | необязательно, по умолчанию `info` |
| `SPECTRA_API_MEMORY_LIMIT` | необязательно, по умолчанию `2g` |

Значения без одинарных кавычек и переводов строк. Пароли и ключи удобно генерировать так: `openssl rand -hex 32`.

## Что важно знать

- Docker публикует порты в обход файрвола хоста (в том числе ufw). `SPECTRA_BIND_ADDRESS=0.0.0.0` откроет api в интернет мимо reverse proxy.
- Postgres берёт пароль только при первом создании тома. Смена секрета потом не меняет пароль в базе: сначала `ALTER ROLE spectra PASSWORD ...` в базе, потом секрет.
- Postgres, Redis и versitygw живут во внутренней сети compose без портов наружу и без выхода в интернет.
- Образ в GHCR по умолчанию приватный; сервер логинится в реестр коротким токеном задачи деплоя.
