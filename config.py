#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Единая конфигурация проекта.

Все адреса API, токены, пути и параметры публикации читаются из переменных
окружения (или из файла `.env` в корне репозитория). Секреты в коде не хранятся.

Схема файла `.env` — см. `.env.example`.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


# --- загрузка .env -----------------------------------------------------------
try:  # основной путь
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE, override=False)
except ImportError:  # запасной путь: простой разбор KEY=VALUE
    def _load_env_file(path):
        if not path.is_file():
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))

    _load_env_file(ENV_FILE)


def env(name, default=None, required=False):
    """Значение переменной окружения; при required=True — ошибка с подсказкой."""
    value = os.environ.get(name, "").strip()
    if not value:
        if required:
            raise SystemExit(
                f"Не задана переменная окружения {name}.\n"
                f"Скопируйте .env.example в .env и заполните значения:\n"
                f"    cp .env.example .env"
            )
        return default
    return value


def env_list(name, default=()):
    """Список значений через запятую: `A,B , C` -> ['A', 'B', 'C']."""
    raw = env(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_path(name, default):
    """Путь из env; относительный разрешается от каталога проекта."""
    value = env(name, default)
    path = Path(value).expanduser()
    return path if path.is_absolute() else (BASE_DIR / path)


# --- UISP CRM (абоненты) -----------------------------------------------------
CRM_API_URL = env("CRM_API_URL", "https://crm.example.com/crm/api/v1.0/")
CRM_API_KEY = env("CRM_API_KEY", required=True)

# --- UISP NMS (сайты и устройства) -------------------------------------------
NMS_API_URL = env("NMS_API_URL", "https://nms.example.com/nms/api/v2.1")
NMS_API_TOKEN = env("NMS_API_TOKEN", required=True)

# --- пути --------------------------------------------------------------------
OUTPUT_DIR = env_path("OUTPUT_DIR", "output")
CLIENTS_DIR = OUTPUT_DIR / "clients"            # markdown-карточки абонентов
UISP_MD_DIR = OUTPUT_DIR / "uisp"               # markdown-топология UISP
UISP_HTML_DIR = OUTPUT_DIR / "uisp_web"         # HTML-сайт по топологии UISP
CRM_WEB_DIR = OUTPUT_DIR / "web"                # HTML-сайт по абонентам CRM
DEPLOY_BUNDLE_DIR = OUTPUT_DIR / "deploy-uisp"  # собираемый бандл для сервера
DEPLOY_TAR = OUTPUT_DIR / "uisp-static-bundle.tar"
DOCS_DIR = BASE_DIR / "docs"

# --- публикация (docker + nginx по ssh) --------------------------------------
DEPLOY_HOST = env("DEPLOY_HOST", "192.0.2.10")
DEPLOY_PORT = env("DEPLOY_PORT", "22")
DEPLOY_USER = env("DEPLOY_USER", "deploy")
DEPLOY_DIR = env("DEPLOY_DIR", "/var/www/uisp-static")
DEPLOY_HTTPS_PORT = env("DEPLOY_HTTPS_PORT", "6443")
DEPLOY_CONTAINER = env("DEPLOY_CONTAINER", "uisp-static-archive")
DEPLOY_AUTH_REALM = env("DEPLOY_AUTH_REALM", "UNMS Bill Archive")
DEPLOY_ALLOWED_SUBNETS = env_list("DEPLOY_ALLOWED_SUBNETS", ["127.0.0.0/8"])
PUBLIC_URL = env("PUBLIC_URL", f"https://{DEPLOY_HOST}:{DEPLOY_HTTPS_PORT}/")
DOCKER_COMPOSE_CMD = env("DOCKER_COMPOSE_CMD", "docker compose")

# Учётные данные basic-auth: если не заданы — генерируются случайно при сборке.
DEPLOY_AUTH_LOGIN = env("DEPLOY_AUTH_LOGIN", "")
DEPLOY_AUTH_PASSWORD = env("DEPLOY_AUTH_PASSWORD", "")

# Проверки после публикации
PUBLISH_CHECK_SITE = env("PUBLISH_CHECK_SITE", "истрия")
PUBLISH_CHECK_MARKER = env("PUBLISH_CHECK_MARKER", "Индекс сайтов")

# --- внешние ресурсы страниц (CDN) --------------------------------------------
CDN_BOOTSTRAP_CSS = env(
    "CDN_BOOTSTRAP_CSS",
    "https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.3/css/bootstrap.min.css",
)
CDN_FONT_AWESOME_CSS = env(
    "CDN_FONT_AWESOME_CSS",
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css",
)
CDN_BOOTSTRAP_JS = env(
    "CDN_BOOTSTRAP_JS",
    "https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.3/js/bootstrap.bundle.min.js",
)
CDN_JQUERY = env(
    "CDN_JQUERY", "https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.1/jquery.min.js"
)
CDN_DATATABLES_CSS = env(
    "CDN_DATATABLES_CSS",
    "https://cdn.datatables.net/1.13.8/css/dataTables.bootstrap5.min.css",
)
CDN_DATATABLES_RESP_CSS = env(
    "CDN_DATATABLES_RESP_CSS",
    "https://cdn.datatables.net/responsive/2.5.0/css/responsive.bootstrap5.min.css",
)
CDN_DATATABLES_JS = env(
    "CDN_DATATABLES_JS",
    "https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js",
)
CDN_DATATABLES_BS5_JS = env(
    "CDN_DATATABLES_BS5_JS",
    "https://cdn.datatables.net/1.13.8/js/dataTables.bootstrap5.min.js",
)
CDN_DATATABLES_RESP_JS = env(
    "CDN_DATATABLES_RESP_JS",
    "https://cdn.datatables.net/responsive/2.5.0/js/responsive.bootstrap5.min.js",
)
CDN_MERMAID_JS = env(
    "CDN_MERMAID_JS",
    "https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js",
)


def ensure_dirs():
    """Создать каталоги результата (output/ и подкаталоги)."""
    for path in (OUTPUT_DIR, CLIENTS_DIR, UISP_MD_DIR):
        path.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    print(f"Каталог проекта: {BASE_DIR}")
    print(f"Файл .env:      {ENV_FILE} "
          f"({'найден' if ENV_FILE.is_file() else 'отсутствует'})")
    print(f"Каталог output: {OUTPUT_DIR}")
    print(f"CRM API:        {CRM_API_URL} "
          f"(ключ: {'задан' if CRM_API_KEY else 'НЕ ЗАДАН'})")
    print(f"NMS API:        {NMS_API_URL} "
          f"(токен: {'задан' if NMS_API_TOKEN else 'НЕ ЗАДАН'})")
    print(f"Публикация:     ssh {DEPLOY_USER}@{DEPLOY_HOST}:{DEPLOY_PORT} "
          f"-> {DEPLOY_DIR}")
    print(f"Публичный URL:  {PUBLIC_URL}")
    print(f"Разрешённые сети: {', '.join(DEPLOY_ALLOWED_SUBNETS)}")
    sys.exit(0)
