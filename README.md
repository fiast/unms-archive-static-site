# Выгрузка абонентов и топологии из UISP (CRM + NMS) в статический сайт

Набор скриптов для выгрузки данных из **UISP CRM** (абоненты) и **UISP NMS**
(сайты и устройства), генерации по ним статического HTML-сайта и публикации
этого сайта в docker-контейнер `nginx` под HTTPS с basic-auth и IP-фильтром.

## Структура репозитория

| Файл / каталог | Назначение |
|---|---|
| `config.py` | Загрузка конфигурации из `.env` (адреса API, токены, пути, параметры деплоя) |
| `export_crm_clients.py` | Выгрузка абонентов из UISP CRM в markdown-карточки |
| `export_uisp_topology.py` | Выгрузка Sites/Devices/Data-links из UISP NMS в markdown-документацию |
| `generate_html_site.py` | Сборка HTML-портала по карточкам абонентов |
| `generate_uisp_html.py` | Конвертация markdown-документации UISP в HTML (в т.ч. mermaid-схемы) |
| `publish_uisp_static.py` | Сборка деплой-бандла и публикация в docker-контейнер nginx по ssh |
| `docs/` | Справочные материалы |
| `output/` | **Результат работы скриптов** (в репозиторий не попадает, см. `.gitignore`) |

### Каталоги результата (`output/`)

- `output/clients/` — markdown-карточки абонентов (`{id}.md`, `{userIdent}.md`);
- `output/uisp/` — markdown-документация по сайтам и устройствам UISP;
- `output/web/` — HTML-портал по абонентам CRM;
- `output/uisp_web/` — HTML-сайт по топологии UISP;
- `output/deploy-uisp/` — собранный бандл для публикации (nginx.conf, docker-compose.yml, TLS, htpasswd, site);
- `output/deploy/` — бандл предыдущей версии публикации (если использовался);
- `output/uisp-static-bundle.tar` — временный архив бандла (удаляется после публикации).

## Установка и настройка

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Секреты и адреса хранятся **только** в `.env` (файл в `.gitignore`):

```bash
cp .env.example .env
$EDITOR .env
```

Минимально обязательные переменные:

| Переменная | Смысл |
|---|---|
| `CRM_API_URL`, `CRM_API_KEY` | Адрес CRM API и App Key (UISP CRM → Settings → Security → App keys → Read) |
| `NMS_API_URL`, `NMS_API_TOKEN` | Адрес NMS API и токен авторизации (заголовок `x-auth-token`) |

Остальные переменные (пути, параметры публикации, CDN) имеют значения по умолчанию
и описаны в `.env.example`.

Проверить, что конфигурация загрузилась:

```bash
python3 config.py
```

> **Важно:** каталог `output/` и файл `.env` добавлены в `.gitignore` — реальные
> данные абонентов, учётные данные и закрытые ключи в публичный репозиторий
> не попадают. Перед публикацией убедитесь, что в репозитории нет других
> файлов с персональными данными или секретами.

## Выгрузка абонентов из UISP CRM

`export_crm_clients.py` скачивает данные через API и генерирует markdown-файлы
в `output/clients/`. В каждой карточке:

1. **Общая информация**: ID, номер договора / лицевой счёт (`userIdent`), ФИО или организация,
   статус, адрес подключения и адрес для Сбербанка, телефоны, email, Telegram ID,
   MAC-адрес оборудования, теги, дата регистрации.
2. **Баланс**: текущий баланс, кредит (аванс), задолженность.
3. **Услуги и подключение**: тарифный план, абонентская плата, статус услуги, даты
   активации и окончания, выделенный IP, логин и пароль PPPoE, примечания.
4. **Заметки**: заметка из профиля и системный журнал заметок (`client-logs`).
5. **Тикеты / Заявки**: обращения из `ticketing/tickets` — тема, номер, статус, даты,
   полная хронология активности (комментарии инженеров и абонентов, смена статусов).
6. **Выписка со счёта**: единая хронологическая таблица операций (платежи, счета,
   возвраты, кредитовые ноты) с нарастающим балансом и строкой `ИТОГО`.

### Запуск

```bash
python3 export_crm_clients.py
```


## Генерация HTML-портала по абонентам

```bash
python3 generate_html_site.py
```

Результат — в `output/web/`:

- `output/web/index.html` — реестр абонентов: мгновенный поиск (DataTables) по ФИО,
  лицевому счёту, адресу, телефону, IP и MAC, KPI-сводка (всего / активные /
  должники / с открытыми тикетами), быстрые фильтры в один клик, переход в карточку
  по клику на строку;
- `output/web/clients/{id}.html` и `{userIdent}.html` — персональные страницы
  абонентов с адаптивными таблицами и кнопкой возврата к реестру.

### Публикация на свой Nginx (Apache) под паролем

Каталог `output/web/` — чистая статика, готовая к публикации под `auth_basic`.
Пример серверного блока nginx:

```nginx
server {
    listen 80;
    server_name crm.example.com;

    root /path/to/project/output/web;
    index index.html;

    auth_basic "Закрытая зона CRM";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        try_files $uri $uri/ =404;
    }
}
```

Файл с логином и паролем создаётся утилитой `htpasswd`:

```bash
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

Перезапуск: `sudo nginx -t && sudo systemctl reload nginx`.

## Выгрузка топологии UISP (Sites + Devices)

`export_uisp_topology.py` собирает данные из NMS API и формирует markdown-документацию
в `output/uisp/`.

### Используемые эндпоинты

- `GET /sites` — все сайты и точки подключения;
- `GET /devices?withInterfaces=true` — устройства вместе с интерфейсами, радиоконфигурацией и станциями;
- `GET /data-links` — связи между устройствами (отрезки сети);
- `GET /devices/ssids` — SSID-ы беспроводных устройств.

### Что генерируется (`output/uisp/`)

- `index.md` — индекс всех сайтов: тип, статус, количество устройств и data links, адрес;
- `sites/*.md` — отдельный файл на каждый сайт: реквизиты (ID, родительский сайт со ссылкой,
  адрес, координаты, дочерние сайты), таблица устройств, подробное описание каждого
  устройства (модель, IP, MAC, прошивка, **радио** — SSID/частота/диапазон/ширина канала/
  мощность/антенна, интерфейсы, станции), **связи (data links)** с именами локального и
  удалённого интерфейса и ссылками на удалённое устройство и его сайт;
- `mermaid.md` — схема связей между сайтами (`graph LR`) и иерархия сайтов (`graph TD`);
- `README.md` — описание каталога и статистика.

### Запуск и конвертация в HTML

```bash
python3 export_uisp_topology.py     # -> output/uisp/*.md
python3 generate_uisp_html.py       # -> output/uisp_web/*.html
```

`generate_uisp_html.py` строит якоря заголовков тем же алгоритмом, что и
`export_uisp_topology.py`, поэтому кросс-ссылки вида `файл.html#2-устройство`
продолжают работать; блоки ```mermaid``` рендерятся библиотекой mermaid с CDN.


## Публикация в Docker-контейнер (nginx + HTTPS + basic-auth + IP-фильтр)

`publish_uisp_static.py` выполняет полный цикл: генерация HTML → сборка бандла →
передача по ssh → запуск контейнера → проверки доступности.

```bash
python3 publish_uisp_static.py
```

1. Конвертация `output/uisp/` → `output/uisp_web/`;
2. Сборка бандла `output/deploy-uisp/`:
   - `nginx.conf` — SSL, IP-фильтр (`DEPLOY_ALLOWED_SUBNETS`), basic-auth (`DEPLOY_AUTH_REALM`);
   - `docker-compose.yml` — сервис `nginx:alpine`, контейнер `DEPLOY_CONTAINER`, порт `DEPLOY_HTTPS_PORT`;
   - `tls/` — самоподписанный сертификат (SAN: `localhost`, IP сервера);
   - `htpasswd` — файл basic-auth; логин/пароль берутся из `DEPLOY_AUTH_LOGIN` /
     `DEPLOY_AUTH_PASSWORD`, а если они не заданы — генерируются случайно;
   - `site/` — HTML-сайт;
   - `credentials.txt` — копия логина и пароля;
3. Упаковка в tar, копирование по ssh в `DEPLOY_DIR` и `docker compose up -d`;
4. Проверки: `401` без пароля, `200` с паролем, наличие маркера в `index.html`,
   доступ к странице сайта с кириллическим именем, `403` для источника вне
   разрешённых подсетей, `200` с рабочей машины.

Параметры подключения и публикации задаются в `.env`:
`DEPLOY_HOST`, `DEPLOY_PORT`, `DEPLOY_USER`, `DEPLOY_DIR`, `DEPLOY_HTTPS_PORT`,
`DEPLOY_CONTAINER`, `DEPLOY_AUTH_REALM`, `DEPLOY_ALLOWED_SUBNETS`, `PUBLIC_URL`,
`DOCKER_COMPOSE_CMD`.

> Учётные данные, TLS-ключи и `htpasswd` попадают только в `output/deploy-uisp/`,
> который не отслеживается git.

## Полный цикл обновления данных

```bash
python3 export_crm_clients.py      # -> output/clients/
python3 generate_html_site.py      # -> output/web/
python3 export_uisp_topology.py    # -> output/uisp/
python3 generate_uisp_html.py      # -> output/uisp_web/
python3 publish_uisp_static.py     # публикация output/uisp_web на сервер
```

## Требования

- Python 3.8+;
- `Markdown` и `python-dotenv` (см. `requirements.txt`; `config.py` работает и без
  `python-dotenv`, разбирая `.env` самостоятельно);
- для публикации: `ssh`/`scp` с доступом к серверу, `docker compose` на нём,
  а также `openssl` и `htpasswd` локально (используются при генерации сертификата
  и файла паролей).
