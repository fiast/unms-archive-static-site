#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка и публикация HTML-документации UISP на удалённом сервере.

Все параметры подключения и публикации берутся из переменных окружения
(см. config.py и .env.example): DEPLOY_HOST / DEPLOY_PORT / DEPLOY_USER /
DEPLOY_DIR / DEPLOY_ALLOWED_SUBNETS и т.д.

Действия:
 1. конвертация output/uisp/ markdown -> output/uisp_web/ HTML
    (generate_uisp_html.py);
 2. сборка деплой-бандла output/deploy-uisp/:
      nginx.conf      — SSL + IP-фильтр + basic auth;
      docker-compose.yml — сервис nginx (nginx:alpine, 6443:443);
      tls/            — самоподписанный сертификат (SAN: localhost, IP сервера);
      htpasswd        — файл basic-auth (htpasswd -nb);
      site/           — HTML-сайт;
      credentials.txt — логин/пароль;
 3. push tar+scp на сервер -> DEPLOY_DIR;
 4. docker compose up -d (контейнер из DEPLOY_CONTAINER);
 5. проверки: 401 без пароля, 200 с паролем, 403 из чужой подсети;
 6. печать URL / логина / пароля.
"""

import os
import time
import shutil
import secrets
import string
import shlex
import subprocess
import urllib.parse

import config

BASE_DIR = str(config.BASE_DIR)
HTML_DIR = str(config.UISP_HTML_DIR)
BUNDLE_DIR = str(config.DEPLOY_BUNDLE_DIR)
BUNDLE_TAR = str(config.DEPLOY_TAR)

REMOTE_HOST = config.DEPLOY_HOST
REMOTE_PORT = config.DEPLOY_PORT
REMOTE_USER = config.DEPLOY_USER
REMOTE_DIR = config.DEPLOY_DIR
PUBLIC_URL = config.PUBLIC_URL
CONTAINER_NAME = config.DEPLOY_CONTAINER
AUTH_REALM = config.DEPLOY_AUTH_REALM
ALLOWED_SUBNETS = config.DEPLOY_ALLOWED_SUBNETS
COMPOSE_CMD = config.DOCKER_COMPOSE_CMD
HTTPS_PORT = config.DEPLOY_HTTPS_PORT

NGINX_CONF = """server {{
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/nginx/tls/selfsigned.crt;
    ssl_certificate_key /etc/nginx/tls/selfsigned.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    root /usr/share/nginx/html;
    index index.html;

    # Доступ разрешен только из подсетей: {allowed}
{allow_rules}
    auth_basic "{realm}";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {{
        try_files $uri $uri/ =404;
    }}
}}
"""

DOCKER_COMPOSE = """services:
  nginx:
    image: nginx:alpine
    container_name: {container}
    restart: unless-stopped
    ports:
      - "{https_port}:443"
    volumes:
      - {remote_dir}/site:/usr/share/nginx/html:ro
      - {remote_dir}/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - {remote_dir}/tls:/etc/nginx/tls:ro
      - {remote_dir}/htpasswd:/etc/nginx/.htpasswd:ro
"""


def render_nginx_conf():
    """Текст nginx.conf: IP-фильтр и realm берутся из конфигурации."""
    if ALLOWED_SUBNETS:
        allowed = ", ".join(ALLOWED_SUBNETS)
        allow_rules = "".join(f"    allow {net};\n" for net in ALLOWED_SUBNETS)
        allow_rules += "    deny all;\n"
    else:
        allowed = "(без фильтра)"
        allow_rules = ""
    return NGINX_CONF.format(allowed=allowed, allow_rules=allow_rules,
                             realm=AUTH_REALM)


def render_docker_compose():
    return DOCKER_COMPOSE.format(container=CONTAINER_NAME,
                                 https_port=HTTPS_PORT,
                                 remote_dir=REMOTE_DIR)


def sh(cmd, check=True, timeout=600, verbose=True):
    """Локальное выполнение команды."""
    if verbose:
        print(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, text=True, timeout=timeout,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = (r.stdout or "").strip()
    if verbose and out:
        print(out[:3000])
    if check and r.returncode != 0:
        raise SystemExit(f"Ошибка (код {r.returncode}): {cmd}\n{out}")
    return out


def ssh(cmd, check=True, timeout=600, verbose=True):
    """Команда на сервере по ssh (порт из DEPLOY_PORT)."""
    q = shlex.join(["ssh", "-p", REMOTE_PORT, "-o", "BatchMode=yes",
                    "-o", "StrictHostKeyChecking=accept-new",
                    f"{REMOTE_USER}@{REMOTE_HOST}", cmd])
    return sh(q, check=check, timeout=timeout, verbose=verbose)


def scp(local_path, remote_path):
    q = shlex.join(["scp", "-P", REMOTE_PORT, "-o", "BatchMode=yes",
                    "-o", "StrictHostKeyChecking=accept-new",
                    local_path, f"{REMOTE_USER}@{REMOTE_HOST}:{remote_path}"])
    return sh(q)


def gen_credentials():
    """Учётные данные basic-auth: из DEPLOY_AUTH_LOGIN/PASSWORD или случайные."""
    if config.DEPLOY_AUTH_LOGIN and config.DEPLOY_AUTH_PASSWORD:
        return config.DEPLOY_AUTH_LOGIN, config.DEPLOY_AUTH_PASSWORD
    login = "uisp" + "".join(secrets.choice(string.digits) for _ in range(3))
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(18))
    return login, password


def write_file(path, text, mode=None):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    if mode is not None:
        os.chmod(path, mode)


def build_html():
    """Генерация HTML из markdown-документации output/uisp/."""
    import generate_uisp_html
    generate_uisp_html.main()


def build_bundle():
    """Собирает output/deploy-uisp/: конфиги, сертификат, htpasswd, HTML-сайт."""
    print("=== Сборка деплой-бандла ===")
    if os.path.isdir(BUNDLE_DIR):
        shutil.rmtree(BUNDLE_DIR)
    os.makedirs(os.path.join(BUNDLE_DIR, "tls"), exist_ok=True)

    write_file(os.path.join(BUNDLE_DIR, "nginx.conf"), render_nginx_conf())
    write_file(os.path.join(BUNDLE_DIR, "docker-compose.yml"),
               render_docker_compose())

    # самоподписанный сертификат (SAN: localhost + IP сервера)
    crt = os.path.join(BUNDLE_DIR, "tls", "selfsigned.crt")
    key = os.path.join(BUNDLE_DIR, "tls", "selfsigned.key")
    sh(f'openssl req -x509 -newkey rsa:2048 -nodes -days 3650 '
       f'-keyout {key} -out {crt} '
       f'-subj "/CN={REMOTE_HOST}/O=UISP Static Archive" '
       f'-addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:{REMOTE_HOST}"')

    # basic auth
    login, password = gen_credentials()
    htpasswd_out = sh(f"htpasswd -nb {login} {password}")
    write_file(os.path.join(BUNDLE_DIR, "htpasswd"), htpasswd_out + "\n")
    write_file(os.path.join(BUNDLE_DIR, "credentials.txt"),
               f"{login} {password}\n")
    print(f"Созданы учётные данные: {login} / {password}")

    # HTML-сайт
    if not os.path.isdir(HTML_DIR):
        raise SystemExit(f"Не найден HTML-каталог: {HTML_DIR} — сначала сгенерируйте сайт")
    shutil.copytree(HTML_DIR, os.path.join(BUNDLE_DIR, "site"))

    n_files = sum(len(files) for _, _, files in os.walk(BUNDLE_DIR))
    print(f"Бандл готов: {BUNDLE_DIR} (файлов: {n_files})")
    return login, password


def pack_bundle():
    """Упаковка бандла в один tar для передачи на сервер."""
    if os.path.exists(BUNDLE_TAR):
        os.remove(BUNDLE_TAR)
    sh(f"tar -cf {BUNDLE_TAR} -C {BUNDLE_DIR} "
       f"site nginx.conf docker-compose.yml tls htpasswd credentials.txt")
    size = os.path.getsize(BUNDLE_TAR) / (1024 * 1024)
    print(f"tar-архив: {BUNDLE_TAR} ({size:.1f} МБ)")
    return BUNDLE_TAR


def deploy(tar_path):
    """Перенос бандла на сервер и запуск контейнера."""
    print(f"=== Публикация на {REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PORT} -> {REMOTE_DIR} ===")
    ssh(f"sudo -n mkdir -p {REMOTE_DIR} && sudo -n chown -R "
        f"{REMOTE_USER}:{REMOTE_USER} {REMOTE_DIR}")
    scp(tar_path, f"{REMOTE_DIR}/uisp-static-bundle.tar")
    # tar заменяет bind-mount файлы новыми inode -> обязателен restart контейнера,
    # иначе nginx продолжит читать старые htpasswd/сертификат/конфиг
    ssh(f"set -e; cd {REMOTE_DIR}; "
        f"tar -xf uisp-static-bundle.tar; rm -f uisp-static-bundle.tar; "
        f"({COMPOSE_CMD} up -d --remove-orphans 2>/dev/null || "
        f"sudo -n {COMPOSE_CMD} up -d --remove-orphans); "
        f"({COMPOSE_CMD} restart 2>/dev/null || sudo -n {COMPOSE_CMD} restart); "
        f"{COMPOSE_CMD} ps || sudo -n {COMPOSE_CMD} ps")


def http_code(url, auth=None, check=False, verbose=True):
    """HTTP-код через curl НА СЕРВЕРЕ (его IP в разрешенной подсети)."""
    auth_part = f"-u {auth} " if auth else ""
    out = ssh(f"curl -sk -o /dev/null -w '%{{http_code}}' {auth_part}{url}",
              check=check, timeout=60, verbose=verbose)
    return out.strip() or "000"


def verify(login, password):
    """Проверки доступности: 401 / 200 / 403 (+ содержимое)."""
    print("=== Проверка доступности ===")
    results = {}
    marker = config.PUBLISH_CHECK_MARKER
    site = config.PUBLISH_CHECK_SITE
    site_url = PUBLIC_URL + "sites/" + urllib.parse.quote(site + ".html")

    # 1. ожидание запуска nginx: 401 без пароля (запрос выполняется на сервере)
    code = "000"
    for _ in range(15):
        code = http_code(PUBLIC_URL, verbose=False)
        if code == "401":
            break
        time.sleep(1)
    results[f"без пароля (запрос с сервера {REMOTE_HOST})"] = code

    # 2. с паролем -> 200
    results["с паролем (запрос с сервера)"] = \
        http_code(PUBLIC_URL, auth=f"{login}:{password}")

    # 3. содержимое индекса
    title = ssh(f"curl -sk -u {login}:{password} {PUBLIC_URL} | grep -c '{marker}'",
                check=False, timeout=60).strip()
    results[f"маркер '{marker}' найден в HTML (строк)"] = title

    # 4. страница сайта (имя может содержать кириллицу)
    results[f"страница {site_url} с паролем"] = \
        http_code(site_url, auth=f"{login}:{password}")

    # 5. источник вне разрешенных подсетей -> 403 (запрос на 127.0.0.1 с сервера;
    #    loopback обычно не входит в allow -> доказывает работу deny all)
    results["с паролем, источник вне подсетей (127.0.0.1)"] = \
        ssh(f"curl -sk -o /dev/null -w '%{{http_code}}' -u {login}:{password} "
            f"https://127.0.0.1:{HTTPS_PORT}/", check=False, timeout=60).strip() or "000"

    # 6. доступность с этой рабочей машины (если маршрут попадает в allow)
    local_auth = subprocess.run(
        ["curl", "-sk", "-o", "/dev/null", "-w", "%{http_code}",
         "-u", f"{login}:{password}", PUBLIC_URL],
        text=True, capture_output=True, timeout=60)
    results["с паролем, с этой рабочей машины"] = \
        local_auth.stdout.strip() or "000"

    for k, v in results.items():
        print(f"  {k}: {v}")

    ok = (results[f"без пароля (запрос с сервера {REMOTE_HOST})"] == "401"
          and results["с паролем (запрос с сервера)"] == "200"
          and results[f"маркер '{marker}' найден в HTML (строк)"] not in ("", "0")
          and results[f"страница {site_url} с паролем"] == "200"
          and results["с паролем, источник вне подсетей (127.0.0.1)"] == "403"
          and results["с паролем, с этой рабочей машины"] == "200")
    if not ok:
        raise SystemExit("Проверка НЕ пройдена — см. коды выше")
    print("Все проверки пройдены.")
    return results


def main():
    print("=== Публикация статического архива UISP ===")
    t0 = time.time()

    build_html()
    login, password = build_bundle()
    tar_path = pack_bundle()
    deploy(tar_path)
    verify(login, password)
    os.remove(tar_path)

    print()
    print("=" * 56)
    print("  ПУБЛИКАЦИЯ ЗАВЕРШЕНА")
    print(f"  URL:    {PUBLIC_URL}")
    print(f"  Логин:  {login}")
    print(f"  Пароль: {password}")
    print(f"  (копия: {BUNDLE_DIR}/credentials.txt")
    print(f"   и на сервере: {REMOTE_DIR}/credentials.txt)")
    print("=" * 56)
    print(f"Готово за {time.time() - t0:.1f} сек.")


if __name__ == "__main__":
    main()

