#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сбор информации о Sites и Devices из UISP (nms/api/v2.1)
и генерация markdown-документации в каталог output/uisp/.

Адрес API и токен авторизации берутся из переменных окружения NMS_API_URL /
NMS_API_TOKEN (см. config.py и .env.example).

Используемые эндпоинты (см. docs/unms-swagger.json):
  GET /sites                — список сайтов (site/endpoint)
  GET /devices?withInterfaces=true — устройства вместе с интерфейсами
  GET /data-links           — связи между устройствами (отрезки сети)
  GET /devices/ssids        — SSID-ы беспроводных устройств

Выход:
  output/uisp/index.md             — индекс всех сайтов со ссылками
  output/uisp/sites/{slug}.md      — карточка каждого сайта с описанием устройств
  output/uisp/mermaid.md           — схема связей между сайтами (mermaid)
  output/uisp/README.md            — описание структуры каталога
"""

import os
import re
import ssl
import json
import time
import urllib.request
import urllib.parse
from collections import defaultdict, Counter

import config

API_URL = config.NMS_API_URL
TOKEN = config.NMS_API_TOKEN
OUTPUT_DIR = str(config.UISP_MD_DIR)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

ROLE_RU = {
    "ap": "AP (точка доступа)",
    "station": "станция",
    "router": "маршрутизатор",
    "switch": "коммутатор",
    "gateway": "шлюз",
    "gpon": "GPON",
    "ptp": "PTP",
    "convertor": "конвертер",
    "wireless": "беспроводное",
    "wired": "проводное",
    "server": "сервер",
    "other": "прочее",
    "ups": "ИБП",
    "optical": "оптика",
}

SITE_TYPE_RU = {"site": "сайт", "endpoint": "точка / абонент", "client": "клиент", "subscriber": "подписчик"}


def api_get(path, params=None, label="", timeout=120):
    """GET-запрос к UISP API с заголовком x-auth-token и повторами."""
    url = API_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"x-auth-token": TOKEN})
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                print(f"[{label or path}] получено записей: {len(data)}")
            else:
                print(f"[{label or path}] ответ получен")
            return data
        except Exception as e:  # noqa: BLE001 — любая сетевая ошибка повод к повтору
            last_err = e
            print(f"[{label or path}] попытка {attempt}/3 не удалась: {e}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"Не удалось получить {url}: {last_err}")


def sanitize_cell(val):
    """Экранирование значения для markdown-таблицы."""
    if val is None:
        return "-"
    s = str(val).strip()
    if not s:
        return "-"
    s = s.replace(chr(13) + chr(10), " ").replace(chr(10), " ").replace(chr(13), " ")
    s = s.replace("|", r"\|")
    return s


def format_date(dt_str):
    """ISO-дата -> 'YYYY-MM-DD HH:MM' (дата без времени -> 'YYYY-MM-DD')."""
    if not dt_str:
        return "-"
    try:
        if "T" in str(dt_str):
            d_part, t_part = str(dt_str).split("T", 1)
            time_clean = t_part.split("+")[0].split("Z")[0]
            time_clean = re.sub(r"\.\d+$", "", time_clean)
            if time_clean in ("00:00:00", ""):
                return d_part
            return f"{d_part} {time_clean[:5]}"
        return str(dt_str)
    except Exception:
        return str(dt_str)


def github_anchor(text):
    """Приблизительный алгоритм построения якоря заголовка как на GitHub."""
    s = str(text).strip().lower()
    s = re.sub(r"[^\w\- ]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s.strip())
    return s


def slugify(name):
    """Имя сайта -> безопасное имя файла (без символов, ломающих markdown-ссылки)."""
    s = str(name).strip().lower()
    s = re.sub(r'[\\/:*?"<>|#\[\]{}()!]+', " ", s)
    s = re.sub(r"\s+", "-", s.strip())
    s = s.strip("-._")
    return s or "site"


def md_link(text, href):
    """Ссылка вида [текст](href) с экранированием скобок в тексте."""
    t = sanitize_cell(text).replace("[", "(").replace("]", ")")
    return f"[{t}]({href})"


def site_rel(ctx, sid):
    """Путь к файлу сайта, относительный каталога sites/ (для ссылок изнутри)."""
    p = ctx["site_path"].get(sid)
    if not p:
        return None
    return os.path.basename(p)


def role_label(role):
    if not role:
        return "-"
    return ROLE_RU.get(role, role)


def fmt_signal(val):
    if val is None:
        return "-"
    try:
        return f"{float(val):.0f} dBm"
    except (TypeError, ValueError):
        return str(val)


def fmt_freq(val):
    if val is None:
        return "-"
    try:
        f = float(val)
        return f"{f:.0f}" if f == int(f) else str(f)
    except (TypeError, ValueError):
        return str(val)


def fetch_all():
    """Забирает все исходные данные одним проходом (4 запроса)."""
    print("=== Сбор данных из UISP ===")
    t0 = time.time()
    sites = api_get("/sites", label="Sites")
    devices = api_get("/devices", {"withInterfaces": "true"}, label="Devices + interfaces")
    links = api_get("/data-links", label="Data Links")
    ssids = api_get("/devices/ssids", label="SSIDs")
    print(f"Данные получены за {time.time() - t0:.1f} сек.")
    return sites, devices, links, ssids


def build_indexes(sites, devices, links, ssids):
    """Строит все вспомогательные индексы."""
    site_by_id = {s["id"]: s for s in sites}

    # дочерние сайты: parent_id -> [site_id, ...]
    children = defaultdict(list)
    for s in sites:
        parent = (s.get("identification") or {}).get("parent")
        if parent and parent.get("id"):
            children[parent["id"]].append(s["id"])

    dev_by_id = {}
    devs_by_site = defaultdict(list)   # site_id | None -> [device, ...]
    dev_freq = {}                      # device_id -> частота (МГц)
    for d in devices:
        ident = d.get("identification") or {}
        did = ident.get("id")
        if not did:
            continue
        dev_by_id[did] = d
        site = ident.get("site")
        sid = site.get("id") if site else None
        devs_by_site[sid].append(d)

        freq = (d.get("overview") or {}).get("frequency")
        if not freq:
            for ifc in d.get("interfaces") or []:
                w = ifc.get("wireless") or {}
                if w.get("frequency"):
                    freq = w["frequency"]
                    break
        if freq:
            dev_freq[did] = freq

    for lst in list(devs_by_site.values()):
        # защита от дубликатов: API может вернуть одну device несколько раз
        seen = set()
        uniq = []
        for d in lst:
            did = (d.get("identification") or {}).get("id")
            if did and did in seen:
                continue
            if did:
                seen.add(did)
            uniq.append(d)
        lst[:] = uniq
        lst.sort(key=lambda x: ((x.get("identification") or {}).get("name") or "").lower())

    # SSID-ы: device_id -> [{ssid, mac, key}, ...]
    ssids_by_dev = defaultdict(list)
    for rec in ssids or []:
        ssids_by_dev[rec.get("deviceId")].append(rec)

    # data-links: device_id -> [(направление, link, side, other_side), ...]
    links_by_dev = defaultdict(list)
    for lnk in links or []:
        fr = lnk.get("from") or {}
        to = lnk.get("to") or {}
        fid = ((fr.get("device") or {}).get("identification") or {}).get("id")
        tid = ((to.get("device") or {}).get("identification") or {}).get("id")
        if fid:
            links_by_dev[fid].append(("→", lnk, fr, to))
        if tid:
            links_by_dev[tid].append(("←", lnk, to, fr))

    # количество data-links на сайт
    links_by_site = Counter()
    for lnk in links or []:
        fsid = (((lnk.get("from") or {}).get("site") or {}).get("identification") or {}).get("id")
        tsid = (((lnk.get("to") or {}).get("site") or {}).get("identification") or {}).get("id")
        if fsid:
            links_by_site[fsid] += 1
        if tsid:
            links_by_site[tsid] += 1

    # имена файлов сайтов (с защитой от дублей)
    site_path = {}
    used = set()
    ordered = sorted(sites, key=lambda s: ((s.get("identification") or {}).get("name") or "").lower())
    for s in ordered:
        sid = s["id"]
        name = (s.get("identification") or {}).get("name") or sid
        slug = slugify(name)
        if slug in used:
            slug = f"{slug}-{sid[:8]}"
        used.add(slug)
        site_path[sid] = f"sites/{slug}.md"

    # якоря разделов устройств внутри файлов сайтов: (site_id, dev_id) -> anchor
    dev_anchor = {}
    for sid, lst in devs_by_site.items():
        for idx, d in enumerate(lst, 1):
            did = (d.get("identification") or {}).get("id")
            name = (d.get("identification") or {}).get("name") or did
            dev_anchor[(sid, did)] = github_anchor(f"{idx}. {name}")

    return {
        "site_by_id": site_by_id,
        "children": children,
        "dev_by_id": dev_by_id,
        "devs_by_site": devs_by_site,
        "dev_freq": dev_freq,
        "ssids_by_dev": ssids_by_dev,
        "links_by_dev": links_by_dev,
        "links_by_site": links_by_site,
        "site_path": site_path,
        "dev_anchor": dev_anchor,
    }


def wireless_rows(dev):
    """Строки таблицы радиоинтерфейсов: SSID, частота, ширина канала и т.д."""
    rows = []
    for ifc in dev.get("interfaces") or []:
        w = ifc.get("wireless") or {}
        if not w or not (w.get("ssid") or w.get("frequency")):
            continue
        ident = ifc.get("identification") or {}
        antenna = w.get("antenna") or {}
        gain = antenna.get("gain")
        rows.append({
            "iface": ident.get("name") or "-",
            "ssid": w.get("ssid") or "-",
            "freq": fmt_freq(w.get("frequency")),
            "band": w.get("frequencyBand") or "-",
            "width": fmt_freq(w.get("channelWidth")),
            "security": w.get("security") or "-",
            "tx": fmt_freq(w.get("transmitPower")) if w.get("transmitPower") is not None else "-",
            "antenna": f"{antenna.get('name') or 'antenna'} (усиление {gain} дБи)" if gain is not None else "-",
            "noise": fmt_signal(w.get("noiseFloor")),
        })
    return rows


def iface_rows(dev):
    """Строки таблицы интерфейсов устройства."""
    rows = []
    for ifc in dev.get("interfaces") or []:
        ident = ifc.get("identification") or {}
        status = ifc.get("status") or {}
        stats = ifc.get("statistics") or {}
        addrs = ", ".join(a.get("cidr") or "" for a in (ifc.get("addresses") or [])) or "-"
        plug = "подключён" if status.get("plugged") else "не подключён"
        speed = status.get("currentSpeed") or status.get("speed") or "-"
        sig = stats.get("signalLocal")
        rows.append({
            "name": ident.get("name") or "-",
            "display": ident.get("displayName") or ident.get("name") or "-",
            "type": ident.get("type") or "-",
            "status": f"{status.get('status') or '-'} ({plug}, {speed})",
            "addr": addrs,
            "signal": fmt_signal(sig) if sig is not None else "-",
        })
    return rows


def station_rows(dev):
    """Строки со станциями, подключёнными к AP-интерфейсам устройства."""
    out = []
    for ifc in dev.get("interfaces") or []:
        st_list = ifc.get("stations") or []
        if not st_list:
            continue
        iface_name = (ifc.get("identification") or {}).get("name") or "-"
        for st in st_list:
            out.append({
                "iface": iface_name,
                "name": st.get("name") or st.get("mac") or "-",
                "model": f"{st.get('model') or '-'}/{st.get('modelName') or '-'}",
                "radio": st.get("radio") or "-",
                "signal": f"{st.get('rxSignal') if st.get('rxSignal') is not None else '-'} / "
                          f"{st.get('txSignal') if st.get('txSignal') is not None else '-'}",
                "distance": f"{st.get('distance')} м" if st.get("distance") is not None else "-",
            })
    return out


def device_md(dev, idx, ctx):
    """Генерирует markdown-раздел одного устройства."""
    ident = dev.get("identification") or {}
    ov = dev.get("overview") or {}
    did = ident.get("id")
    name = ident.get("name") or did
    lines = [f"### {idx}. {name}", ""]

    ip = dev.get("ipAddress") or "-"
    ip_list = ", ".join(dev.get("ipAddressList") or [])
    if ip_list and ip_list != ip:
        ip = f"{ip} (все адреса: {ip_list})"

    rows = [
        ("ID", f"`{did}`"),
        ("Железо (model)", f"`{ident.get('model') or '-'}` / {ident.get('modelName') or '-'}"),
        ("Производитель", ident.get("vendor") or ident.get("vendorName") or "-"),
        ("Платформа", f"{ident.get('platformId') or '-'} / {ident.get('platformName') or '-'}"),
        ("Тип / Роль", f"{ident.get('type') or '-'} / {role_label(ident.get('role'))}"),
        ("IP-адрес", ip),
        ("MAC-адрес", f"`{ident.get('mac') or '-'}`"),
        ("Серийный номер", ident.get("serialNumber") or "-"),
        ("Прошивка", ident.get("firmwareVersion") or "-"),
        ("Статус", ov.get("status") or "-"),
        ("Авторизован в UISP", "да" if ident.get("authorized") else "нет"),
        ("Создан", format_date(ov.get("createdAt"))),
        ("Последний отклик", format_date(ov.get("lastSeen"))),
    ]
    freq = ctx["dev_freq"].get(did)
    if freq:
        rows.append(("Частота", f"{fmt_freq(freq)} МГц"))
    if ov.get("channelWidth"):
        rows.append(("Ширина канала", f"{fmt_freq(ov.get('channelWidth'))} МГц"))
    if ov.get("wirelessMode"):
        rows.append(("Режим радио", ov.get("wirelessMode")))
    if ov.get("signal") is not None:
        rows.append(("Сигнал", fmt_signal(ov.get("signal"))))
    if ov.get("antenna"):
        ant = ov.get("antenna") or {}
        rows.append(("Антенна", f"{ant.get('name') or '-'} (усиление {ant.get('gain')} дБи)"))
    if ov.get("stationsCount") is not None:
        rows.append(("Станций на устройстве", ov.get("stationsCount")))
    ls = ov.get("linkScore")
    if isinstance(ls, dict):
        hint = ls.get("linkScoreHint") or ""
        rows.append(("Оценка линка (linkScore)",
                     f"{ls.get('linkScore')} (макс {ls.get('scoreMax')})" + (f" — {hint}" if hint else "")))
    elif ls is not None:
        rows.append(("Оценка линка (linkScore)", ls))

    lines.append("| Параметр | Значение |")
    lines.append("|---|---|")
    for k, v in rows:
        lines.append(f"| {sanitize_cell(k)} | {sanitize_cell(v)} |")
    lines.append("")

    # --- Радио ---
    wrows = wireless_rows(dev)
    ssid_recs = ctx["ssids_by_dev"].get(did) or []
    if wrows:
        lines.append("**Радио:**")
        lines.append("")
        lines.append("| Интерфейс | SSID | Частота, МГц | Диапазон | Ширина канала, МГц | Шифрование | Мощность, дБм | Антенна | Шум, дБм |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for r in wrows:
            lines.append(
                f"| {sanitize_cell(r['iface'])} | {sanitize_cell(r['ssid'])} | {sanitize_cell(r['freq'])} "
                f"| {sanitize_cell(r['band'])} | {sanitize_cell(r['width'])} | {sanitize_cell(r['security'])} "
                f"| {sanitize_cell(r['tx'])} | {sanitize_cell(r['antenna'])} | {sanitize_cell(r['noise'])} |"
            )
        lines.append("")
    if ssid_recs:
        ssid_str = ", ".join(
            f"`{r.get('ssid')}` (MAC {r.get('mac') or '-'})" for r in ssid_recs
        )
        lines.append(f"**SSID из UISP:** {ssid_str}")
        lines.append("")

    lines.extend(_device_md_tail(dev, did, ctx))
    return lines


def _device_md_tail(dev, did, ctx):
    """Вторая половина раздела устройства: интерфейсы, станции, связи."""
    lines = []

    # --- Интерфейсы ---
    ifrows = iface_rows(dev)
    if ifrows:
        lines.append("**Интерфейсы:**")
        lines.append("")
        lines.append("| Интерфейс | Отображаемое имя | Тип | Статус | IP-адреса | Сигнал |")
        lines.append("|---|---|---|---|---|---|")
        for r in ifrows:
            lines.append(
                f"| {sanitize_cell(r['name'])} | {sanitize_cell(r['display'])} | {sanitize_cell(r['type'])} "
                f"| {sanitize_cell(r['status'])} | {sanitize_cell(r['addr'])} | {sanitize_cell(r['signal'])} |"
            )
        lines.append("")

    # --- Станции (для AP) ---
    strows = station_rows(dev)
    if strows:
        lines.append(f"**Подключённые станции ({len(strows)}):**")
        lines.append("")
        lines.append("| Интерфейс | Станция | Модель | Радио | Сигнал rx/tx, дБм | Дистанция |")
        lines.append("|---|---|---|---|---|---|")
        for r in strows:
            lines.append(
                f"| {sanitize_cell(r['iface'])} | {sanitize_cell(r['name'])} | {sanitize_cell(r['model'])} "
                f"| {sanitize_cell(r['radio'])} | {sanitize_cell(r['signal'])} | {sanitize_cell(r['distance'])} |"
            )
        lines.append("")

    # --- Связи (data links) ---
    entries = ctx["links_by_dev"].get(did) or []
    if entries:
        lines.append(f"**Связи (data links) — {len(entries)}:**")
        lines.append("")
        lines.append("| Направление | Лок. интерфейс | Удалённое устройство | Удал. интерфейс | Удалённый сайт | Частота, МГц | Сигнал, дБм |")
        lines.append("|---|---|---|---|---|---|---|")
        for direction, _lnk, side, other in entries:
            local_if = ((side.get("interface") or {}).get("identification") or {}).get("name") or "-"
            o_dev = other.get("device") or {}
            o_ident = o_dev.get("identification") or {}
            o_did = o_ident.get("id")
            o_name = o_ident.get("name") or o_did or "-"
            o_site = ((other.get("site") or {}).get("identification") or {})
            o_sid = o_site.get("id")
            o_site_name = o_site.get("name") or "без сайта"
            o_if = ((other.get("interface") or {}).get("identification") or {}).get("name") or "-"

            # ссылка на устройство в файле его сайта (пути относительно sites/)
            if o_sid and site_rel(ctx, o_sid):
                href = site_rel(ctx, o_sid)
                anchor = ctx["dev_anchor"].get((o_sid, o_did))
                if anchor:
                    href += "#" + anchor
                o_dev_link = md_link(o_name, href)
                o_site_link = md_link(o_site_name, site_rel(ctx, o_sid))
            else:
                o_dev_link = sanitize_cell(o_name)
                o_site_link = sanitize_cell(o_site_name)

            o_freq = ctx["dev_freq"].get(o_did)
            o_signal = (o_dev.get("overview") or {}).get("signal")
            lines.append(
                f"| {direction} | {sanitize_cell(local_if)} | {o_dev_link} | {sanitize_cell(o_if)} "
                f"| {o_site_link} | {fmt_freq(o_freq) if o_freq else '-'} | {fmt_signal(o_signal)} |"
            )
        lines.append("")

    return lines


def render_site_md(site, devs, ctx):
    """Генерирует содержимое markdown-файла одного сайта."""
    ident = site.get("identification") or {}
    desc = site.get("description") or {}
    sid = site["id"]
    name = (ident.get("name") or sid).strip()
    stype = ident.get("type") or "-"
    status = ident.get("status") or "-"
    suspended = "да" if ident.get("suspended") else "нет"

    lines = [f"# {name}", ""]
    lines.append(
        f"Тип: **{SITE_TYPE_RU.get(stype, stype)}** · Статус: **{status}** · "
        f"Приостановлен: **{suspended}**"
    )
    lines.append("")

    parent = ident.get("parent")
    if parent and site_rel(ctx, parent.get("id")):
        parent_link = md_link(parent.get("name") or parent["id"], site_rel(ctx, parent["id"]))
    elif parent:
        parent_link = sanitize_cell(parent.get("name"))
    else:
        parent_link = "-"

    loc = desc.get("location") or {}
    coords = "-"
    if loc.get("latitude") is not None and loc.get("longitude") is not None:
        coords = f"{loc.get('latitude')}, {loc.get('longitude')}"

    contact = desc.get("contact") or {}
    contact_str = " · ".join(
        x for x in [contact.get("name"), contact.get("phone"), contact.get("email")] if x
    ) or "-"

    info_rows = [
        ("ID", f"`{sid}`"),
        ("Родительский сайт", parent_link),
        ("Адрес", desc.get("address") or "-"),
        ("Координаты", coords),
        ("Высота установки", f"{desc.get('height')} м" if desc.get("height") is not None else "-"),
        ("Превышение (elevation)", f"{desc.get('elevation')} м" if desc.get("elevation") is not None else "-"),
        ("Контакт", contact_str),
        ("Устройств на сайте", len(devs)),
        ("Data links сайта", ctx["links_by_site"].get(sid, 0)),
        ("Заметка", desc.get("note") or "-"),
    ]
    lines.append("| Параметр | Значение |")
    lines.append("|---|---|")
    for k, v in info_rows:
        lines.append(f"| {sanitize_cell(k)} | {sanitize_cell(v)} |")
    lines.append("")

    kids = ctx["children"].get(sid) or []
    if kids:
        kid_sorted = sorted(
            kids,
            key=lambda k: ((ctx["site_by_id"].get(k, {}).get("identification") or {}).get("name") or "").lower(),
        )
        kid_links = []
        for k in kid_sorted:
            ksite = ctx["site_by_id"].get(k) or {}
            kname = ((ksite.get("identification") or {}).get("name") or k).strip()
            kid_links.append(md_link(kname, site_rel(ctx, k)))
        lines.append(f"**Дочерние сайты ({len(kids)}):** " + ", ".join(kid_links))
        lines.append("")

    lines.append(f"## Устройства ({len(devs)})")
    lines.append("")
    if devs:
        lines.append("| # | Устройство | Железо | Тип / Роль | IP | MAC | Статус | Data links |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for idx, d in enumerate(devs, 1):
            i = d.get("identification") or {}
            o = d.get("overview") or {}
            did = i.get("id")
            dname = i.get("name") or did
            anchor = ctx["dev_anchor"].get((sid, did), "")
            dev_link = md_link(dname, f"#{anchor}") if anchor else sanitize_cell(dname)
            nlinks = len(ctx["links_by_dev"].get(did) or [])
            lines.append(
                f"| {idx} | {dev_link} | {sanitize_cell(i.get('model') or '-')} / {sanitize_cell(i.get('modelName') or '-')} "
                f"| {sanitize_cell(i.get('type') or '-')} / {sanitize_cell(role_label(i.get('role')))} "
                f"| {sanitize_cell(d.get('ipAddress') or '-')} | {sanitize_cell(i.get('mac') or '-')} "
                f"| {sanitize_cell(o.get('status') or '-')} | {nlinks or '-'} |"
            )
        lines.append("")
    else:
        lines.append("_Устройства на сайте не привязаны._")
        lines.append("")

    if devs:
        lines.append("## Описание устройств")
        lines.append("")
        for idx, d in enumerate(devs, 1):
            lines.extend(device_md(d, idx, ctx))

    lines.append("---")
    lines.append("")
    lines.append("[← Индекс сайтов](../index.md) · [Схема связей (mermaid)](../mermaid.md)")
    lines.append("")
    return "\n".join(lines)


def render_index_md(sites, ctx, extra_sections):
    """Генерирует index.md — индекс всех сайтов."""
    lines = ["# Индекс сайтов UISP", ""]
    lines.append(f"Всего сайтов: **{len(sites)}**. Файлы каталога `sites/`.")
    lines.append("")
    lines.append("[Схема связей между сайтами (mermaid)](mermaid.md)")
    lines.append("")

    for title, stype in (("Сайты", "site"), ("Точки / абоненты (endpoint)", "endpoint")):
        group = [s for s in sites if (s.get("identification") or {}).get("type") == stype]
        group.sort(key=lambda s: ((s.get("identification") or {}).get("name") or "").lower())
        lines.append(f"## {title} ({len(group)})")
        lines.append("")
        if not group:
            lines.append("_Нет записей._")
            lines.append("")
            continue
        lines.append("| Сайт | Статус | Устройств | Data links | Адрес |")
        lines.append("|---|---|---|---|---|")
        for s in group:
            i = s.get("identification") or {}
            d = s.get("description") or {}
            sid = s["id"]
            nm = (i.get("name") or sid).strip()
            ndev = len(ctx["devs_by_site"].get(sid) or [])
            nlink = ctx["links_by_site"].get(sid, 0)
            lines.append(
                f"| {md_link(nm, ctx['site_path'][sid])} | {sanitize_cell(i.get('status') or '-')} "
                f"| {ndev} | {nlink or '-'} | {sanitize_cell(d.get('address') or '-')} |"
            )
        lines.append("")

    for title, devs in extra_sections:
        if not devs:
            continue
        lines.append(f"## {title} ({len(devs)})")
        lines.append("")
        lines.append("| Устройство | Железо | IP | MAC | Сайт |")
        lines.append("|---|---|---|---|---|")
        for d in devs:
            i = d.get("identification") or {}
            site = i.get("site") or {}
            lines.append(
                f"| {sanitize_cell(i.get('name') or '-')} | {sanitize_cell(i.get('model') or '-')} "
                f"| {sanitize_cell(d.get('ipAddress') or '-')} | {sanitize_cell(i.get('mac') or '-')} "
                f"| {sanitize_cell(site.get('name') if site else 'без сайта')} |"
            )
        lines.append("")

    return "\n".join(lines)


def _mnode(sid):
    """Идентификатор узла mermaid по ID сайта."""
    if not sid:
        return "sNosite"
    return "s" + re.sub(r"[^0-9a-zA-Z]", "", sid)[:8]


def _mtext(text):
    """Безопасная текстовая метка для mermaid."""
    s = str(text or "-").replace('"', "'").replace("`", "").replace("\n", " ").strip()
    return s or "-"


def render_mermaid_md(sites, links, ctx):
    """Генерирует mermaid.md: связи между сайтами + иерархия сайтов."""
    site_by_id = ctx["site_by_id"]

    # --- агрегация data-links по парам сайтов (from -> to) ---
    edge_map = defaultdict(list)
    intra = 0
    skipped = 0
    for lnk in links or []:
        fs = (((lnk.get("from") or {}).get("site") or {}).get("identification") or {})
        ts = (((lnk.get("to") or {}).get("site") or {}).get("identification") or {})
        fid, tid = fs.get("id"), ts.get("id")
        if not fid and not tid:
            skipped += 1
            continue
        if fid and tid and fid == tid:
            intra += 1
            continue
        edge_map[(fid, tid)].append(lnk)

    def site_label(sid):
        if not sid:
            return "(устройство без сайта)"
        s = site_by_id.get(sid) or {}
        i = s.get("identification") or {}
        name = (i.get("name") or sid).strip()
        stype = i.get("type") or "-"
        return f"{name}<br/>({SITE_TYPE_RU.get(stype, stype)})"

    def edge_label(lst):
        if len(lst) == 1:
            lnk = lst[0]
            fd = (((lnk.get("from") or {}).get("device") or {}).get("identification") or {})
            td = (((lnk.get("to") or {}).get("device") or {}).get("identification") or {})
            fname = fd.get("name") or "?"
            tname = td.get("name") or "?"
            freq = ctx["dev_freq"].get(fd.get("id")) or ctx["dev_freq"].get(td.get("id"))
            lbl = f"{fname} <-> {tname}"
            if freq:
                lbl += f", {fmt_freq(freq)} МГц"
            return lbl
        return f"{len(lst)} связей"

    nodes = set()
    edge_lines = []
    for (fid, tid), lst in sorted(edge_map.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        nodes.add(fid)
        nodes.add(tid)
        edge_lines.append(
            f"    {_mnode(fid)} -->|\"{_mtext(edge_label(lst))}\"| {_mnode(tid)}"
        )

    node_lines = []
    for sid in sorted(nodes, key=lambda x: (x is None, site_label(x).lower())):
        node_lines.append(f'    {_mnode(sid)}["{_mtext(site_label(sid))}"]')

    # --- иерархия: родитель -> потомок ---
    hier_lines = []
    hier_nodes = set()
    for s in sites:
        p = (s.get("identification") or {}).get("parent")
        if p and p.get("id") in site_by_id:
            hier_nodes.add(p["id"])
            hier_nodes.add(s["id"])
            hier_lines.append(f"    {_mnode(p['id'])} --> {_mnode(s['id'])}")
    hier_node_lines = [
        f'    {_mnode(sid)}["{_mtext(site_label(sid))}"]'
        for sid in sorted(hier_nodes, key=lambda x: site_label(x).lower())
    ]

    total_inter = sum(len(v) for v in edge_map.values())
    lines = ["# Схема связей (Mermaid)", ""]
    lines.append("Источник: `GET /data-links` и структура `GET /sites`.")
    lines.append("")
    lines.append(f"- Связей между сайтами: **{total_inter}** (уникальных пар: **{len(edge_map)}**)")
    lines.append(f"- Связей внутри одного сайта (в схему не входят): **{intra}**")
    lines.append(f"- Связей без сайтов с обеих сторон (пропущено): **{skipped}**")
    lines.append("")
    lines.append("Направление стрелки: `from` → `to` (from — как правило AP/master-сторона).")
    lines.append("")

    lines.append("## 1. Связи между сайтами (data links)")
    lines.append("")
    lines.append("```mermaid")
    lines.append("graph LR")
    lines.extend(node_lines)
    lines.extend(edge_lines)
    lines.append("```")
    lines.append("")

    lines.append("## 2. Иерархия сайтов (родитель → потомок)")
    lines.append("")
    lines.append("```mermaid")
    lines.append("graph TD")
    lines.extend(hier_node_lines)
    lines.extend(hier_lines)
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("[← Индекс сайтов](index.md)")
    lines.append("")
    return "\n".join(lines)


def render_readme(sites, devices, links, ssids):
    """Генерирует uisp/README.md — описание каталога."""
    n_site = sum(1 for s in sites if (s.get("identification") or {}).get("type") == "site")
    n_endpoint = sum(1 for s in sites if (s.get("identification") or {}).get("type") == "endpoint")
    n_unique = len({(d.get("identification") or {}).get("id") for d in devices})
    return f"""# Документация UISP: Sites и Devices

Каталог сгенерирован скриптом `export_uisp_topology.py` из API
`{API_URL}`.

## Что собрано

| Данные | Количество | Источник (API) |
|---|---|---|
| Сайтов (site) | {n_site} | `GET /sites` |
| Точек / абонентов (endpoint) | {n_endpoint} | `GET /sites` |
| Устройств | {len(devices)} (уникальных: {n_unique}) | `GET /devices?withInterfaces=true` |
| Data links (связей) | {len(links)} | `GET /data-links` |
| SSID-записей | {len(ssids)} | `GET /devices/ssids` |

## Структура каталога

- `index.md` — индекс всех сайтов: тип, статус, количество устройств и data links, адрес.
- `sites/*.md` — отдельный файл на каждый сайт. Внутри:
  - реквизиты сайта (ID, родитель, адрес, координаты, высота, контакт, дочерние сайты);
  - таблица устройств сайта (железо, тип/роль, IP, MAC, статус, число связей);
  - подробное описание каждого устройства:
    - общие параметры (model/modelName, производитель, платформа, IP, MAC, серийный номер, прошивка, статус);
    - **радио**: SSID, частота, диапазон, ширина канала, шифрование, мощность, антенна, шум;
    - интерфейсы (имя, тип, статус, IP-адреса, сигнал);
    - подключённые станции (для AP);
    - **связи (data links)** с именами локального и удалённого интерфейса и ссылками
      на удалённое устройство и его сайт.
- `mermaid.md` — схема связей между сайтами (mermaid `graph LR`) и иерархия сайтов
  (`graph TD`, родитель → потомок).

## Обновление

```bash
python3 export_uisp_topology.py
```

Скрипт заново обращается к API и перезаписывает все файлы каталога `output/uisp/`.
"""


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    print("=== Начало сбора документации UISP (Sites + Devices) ===")
    os.makedirs(os.path.join(OUTPUT_DIR, "sites"), exist_ok=True)

    # убираем результаты предыдущего запуска, чтобы не осталось устаревших файлов
    for fname in os.listdir(os.path.join(OUTPUT_DIR, "sites")):
        if fname.endswith(".md"):
            os.remove(os.path.join(OUTPUT_DIR, "sites", fname))

    sites, devices, links, ssids = fetch_all()
    ctx = build_indexes(sites, devices, links, ssids)

    # --- файлы сайтов ---
    written = 0
    for s in sites:
        sid = s["id"]
        devs = ctx["devs_by_site"].get(sid) or []
        path = os.path.join(OUTPUT_DIR, ctx["site_path"][sid])
        _write(path, render_site_md(s, devs, ctx))
        written += 1
    print(f"Файлов сайтов записано: {written}")

    # --- устройства, не привязанные к сайту / с неизвестным сайтом ---
    orphan = list(ctx["devs_by_site"].get(None) or [])
    for sid, devs in ctx["devs_by_site"].items():
        if sid and sid not in ctx["site_by_id"]:
            orphan.extend(devs)
    if orphan:
        orphan.sort(key=lambda x: ((x.get("identification") or {}).get("name") or "").lower())
        lines = ["# Устройства без привязки к сайту", ""]
        lines.append(f"Всего: **{len(orphan)}**. Эти устройства не отображаются в файлах сайтов.")
        lines.append("")
        for idx, d in enumerate(orphan, 1):
            lines.extend(device_md(d, idx, ctx))
        _write(os.path.join(OUTPUT_DIR, "sites", "_bez-saita.md"), "\n".join(lines))
        print(f"Устройств без сайта: {len(orphan)} (sites/_bez-saita.md)")

    # --- индекс ---
    extra = [("Устройства без привязки к сайту", orphan)]
    _write(os.path.join(OUTPUT_DIR, "index.md"), render_index_md(sites, ctx, extra))

    # --- mermaid ---
    _write(os.path.join(OUTPUT_DIR, "mermaid.md"), render_mermaid_md(sites, links, ctx))

    # --- README ---
    _write(os.path.join(OUTPUT_DIR, "README.md"), render_readme(sites, devices, links, ssids))

    print(f"=== Готово! Каталог: {OUTPUT_DIR} ===")


if __name__ == "__main__":
    main()








