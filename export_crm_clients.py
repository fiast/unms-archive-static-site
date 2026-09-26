#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Выгрузка абонентов из UISP CRM в markdown-карточки.

Адрес API и App Key берутся из переменных окружения CRM_API_URL / CRM_API_KEY
(см. config.py и .env.example). Результат пишется в output/clients/.
"""

import os
import sys
import ssl
import json
import time
import urllib.request
from collections import defaultdict

import config

API_URL = config.CRM_API_URL
API_KEY = config.CRM_API_KEY
OUTPUT_DIR = str(config.CLIENTS_DIR)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

INVOICE_STATUS_MAP = {
    0: "Черновик (Draft)",
    1: "Не оплачен (Unpaid)",
    2: "Частично оплачен (Partially paid)",
    3: "Оплачен (Paid)",
    4: "Аннулирован (Void)",
    5: "Обработанная проформа (Processed proforma)"
}

SERVICE_STATUS_MAP = {
    0: "Подготавливается (Prepared)",
    1: "Активен (Active)",
    2: "Завершен (Ended)",
    3: "Приостановлен (Suspended)",
    4: "Заблокирован при подготовке (Prepared blocked)",
    5: "Устарел (Obsolete)",
    6: "Отложен (Deferred)",
    7: "Квота / Коммерческое (Quoted)",
    8: "Неактивен (Inactive)"
}

TICKET_STATUS_MAP = {
    0: "Новый (New)",
    1: "Открыт (Open)",
    2: "В ожидании (Pending)",
    3: "Решен (Solved)"
}

def fetch_paged(endpoint, label=""):
    items = []
    offset = 0
    limit = 1000
    sep = '&' if '?' in endpoint else '?'
    t0 = time.time()
    while True:
        url = f"{API_URL}{endpoint}{sep}limit={limit}&offset={offset}"
        req = urllib.request.Request(url, headers={"X-Auth-App-Key": API_KEY})
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items.extend(data)
            if len(data) < limit:
                break
            offset += limit
    print(f"[{label or endpoint}] Получено записей: {len(items)} за {time.time()-t0:.2f} сек.")
    return items

def format_date(dt_str):
    if not dt_str:
        return "-"
    try:
        if "T" in dt_str:
            d_part, t_part = dt_str.split("T", 1)
            time_clean = t_part.split("+")[0].split("-")[0]
            if time_clean == "00:00:00":
                return d_part
            return f"{d_part} {time_clean}"
        return dt_str
    except Exception:
        return dt_str

def sanitize_cell(val):
    if val is None:
        return "-"
    s = str(val).strip()
    if not s:
        return "-"
    s = s.replace(chr(13) + chr(10), ' ').replace(chr(10), ' ').replace(chr(13), ' ')
    s = s.replace('|', r'\|')
    return s

def fmt_money(val, currency="RUB"):
    if val is None or val == "":
        return "-"
    try:
        fval = float(val)
        return f"{fval:,.2f} {currency}".replace(",", " ")
    except Exception:
        return str(val)

def main():
    print("=== Начало выгрузки данных из UISP CRM ===")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Справочники
    payment_methods_raw = fetch_paged("payment-methods", "Справочник способов оплаты")
    payment_methods = {m["id"]: m["name"] for m in payment_methods_raw}

    admins_raw = fetch_paged("users/admins", "Администраторы")
    admins = {}
    for a in admins_raw:
        uname = a.get("username") or ""
        fn = a.get("firstName") or ""
        ln = a.get("lastName") or ""
        name = f"{fn} {ln}".strip() or uname or f"ID {a.get('id')}"
        admins[a["id"]] = name

    # 2. Клиенты
    active_clients = fetch_paged("clients?isArchived=0", "Активные абоненты")
    archived_clients = fetch_paged("clients?isArchived=1", "Архивные абоненты")
    clients = active_clients + archived_clients
    print(f"Всего клиентов для обработки: {len(clients)}")

    # 3. Платежи
    payments_raw = fetch_paged("payments", "Платежи")
    payments_by_client = defaultdict(list)
    for p in payments_raw:
        payments_by_client[p.get("clientId")].append(p)

    # 4. Счета (Invoices)
    invoices_raw = fetch_paged("invoices", "Счета / Списания")
    invoices_by_client = defaultdict(list)
    for inv in invoices_raw:
        invoices_by_client[inv.get("clientId")].append(inv)

    # 5. Возвраты (Refunds)
    refunds_raw = fetch_paged("refunds", "Возвраты (Refunds)")
    refunds_by_client = defaultdict(list)
    for r in refunds_raw:
        refunds_by_client[r.get("clientId")].append(r)

    # 6. Кредитовые ноты (Credit notes)
    credit_notes_raw = fetch_paged("credit-notes", "Кредит-ноты (Credit Notes)")
    credit_notes_by_client = defaultdict(list)
    for cn in credit_notes_raw:
        credit_notes_by_client[cn.get("clientId")].append(cn)

    # 7. Услуги / Тарифы
    services_raw = fetch_paged("clients/services", "Тарифные планы / Услуги")
    services_by_client = defaultdict(list)
    for s in services_raw:
        services_by_client[s.get("clientId")].append(s)

    # 8. Заметки (Client Logs)
    client_logs_raw = fetch_paged("client-logs", "Системные логи / Заметки")
    logs_by_client = defaultdict(list)
    for log in client_logs_raw:
        logs_by_client[log.get("clientId")].append(log)

    # 9. Тикеты (Tickets)
    tickets_raw = fetch_paged("ticketing/tickets", "Тикеты / Заявки")
    tickets_by_client = defaultdict(list)
    for t in tickets_raw:
        if t.get("clientId"):
            tickets_by_client[t.get("clientId")].append(t)

    print("Группировка данных завершена. Формирование markdown файлов...")

    for client in clients:
        cid = client.get("id")
        user_ident = client.get("userIdent") or str(cid)

        first_name = (client.get("firstName") or "").strip()
        last_name = (client.get("lastName") or "").strip()
        fio = f"{first_name} {last_name}".strip() or "-"
        company = client.get("companyName")
        if company:
            fio = f"{company} ({fio})"

        is_active = client.get("isActive")
        is_archived = client.get("isArchived")
        status_str = "Архивный" if is_archived else ("Активен" if is_active else "Неактивен")

        balance = client.get("accountBalance", 0.0)
        credit = client.get("accountCredit", 0.0)
        outstanding = client.get("accountOutstanding", 0.0)
        currency = client.get("currencyCode") or "RUB"

        address = client.get("fullAddress") or client.get("street1") or "-"
        reg_date = format_date(client.get("registrationDate"))
        org_name = client.get("organizationName") or "-"

        # Контакты
        contacts = client.get("contacts") or []
        emails = []
        phones = []
        tg_contacts = []
        for c in contacts:
            if c.get("email"):
                emails.append(c["email"])
            if c.get("phone"):
                types = [t.get("name") for t in c.get("types", []) if t.get("name")]
                if "telegram" in types:
                    tg_contacts.append(c["phone"])
                else:
                    phones.append(c["phone"])

        # Атрибуты клиента
        attrs = client.get("attributes") or []
        mac = "-"
        tariff_attr = "-"
        fio_attr = "-"
        sber_addr = "-"
        for a in attrs:
            k = (a.get("key") or "").lower()
            val = a.get("value") or "-"
            if k == "mac":
                mac = val
            elif k == "tariff":
                tariff_attr = val
            elif k == "fio":
                fio_attr = val
            elif k == "sberbankaddress":
                sber_addr = val

        # Теги
        tags = client.get("tags") or []
        tags_str = ", ".join([t.get("name", "") for t in tags if t.get("name")]) or "Нет"

        client_note = (client.get("note") or "").strip()
        logs = logs_by_client.get(cid, [])
        client_services = services_by_client.get(cid, [])
        client_payments = payments_by_client.get(cid, [])
        client_invoices = invoices_by_client.get(cid, [])
        client_refunds = refunds_by_client.get(cid, [])
        client_credit_notes = credit_notes_by_client.get(cid, [])
        client_tickets = tickets_by_client.get(cid, [])

        lines = []
        lines.append(f"# Абонент {user_ident} (ID: {cid})")
        lines.append("")
        lines.append("## Общая информация")
        lines.append(f"- **ID**: {cid}")
        lines.append(f"- **Номер договора / Лицевой счет (userIdent)**: {user_ident}")
        lines.append(f"- **ФИО / Наименование**: {fio}")
        if fio_attr != "-" and fio_attr != fio:
            lines.append(f"- **ФИО (доп. поле)**: {fio_attr}")
        lines.append(f"- **Статус**: {status_str}")
        lines.append(f"- **Организация**: {org_name}")
        lines.append(f"- **Адрес**: {address}")
        if sber_addr != "-" and sber_addr != address:
            lines.append(f"- **Адрес для Сбербанка**: {sber_addr}")
        lines.append(f"- **Телефон**: {', '.join(phones) if phones else '-'}")
        lines.append(f"- **Email**: {', '.join(emails) if emails else '-'}")
        if tg_contacts:
            lines.append(f"- **Telegram ID**: {', '.join(tg_contacts)}")
        lines.append(f"- **MAC-адрес**: {mac}")
        lines.append(f"- **Теги**: {tags_str}")
        lines.append(f"- **Дата регистрации**: {reg_date}")
        lines.append("")

        # Баланс
        lines.append("## Баланс")
        lines.append(f"- **Текущий баланс**: {balance:,.2f} {currency}".replace(",", " "))
        lines.append(f"- **Кредит (аванс)**: {credit:,.2f} {currency}".replace(",", " "))
        lines.append(f"- **Задолженность**: {outstanding:,.2f} {currency}".replace(",", " "))
        lines.append("")

        # Услуги и подключение
        if client_services:
            lines.append("## Услуги и подключение")
            for idx, s in enumerate(client_services, 1):
                s_name = s.get("name") or s.get("servicePlanName") or "Интернет"
                s_status_code = s.get("status")
                s_status = SERVICE_STATUS_MAP.get(s_status_code, f"Статус {s_status_code}")
                s_price = s.get("price") or s.get("totalPrice") or 0.0
                s_active_from = format_date(s.get("activeFrom"))
                s_active_to = format_date(s.get("activeTo"))
                
                s_attrs = s.get("attributes") or []
                s_ip = "-"
                s_login = "-"
                s_pass = "-"
                s_auth = "-"
                for sa in s_attrs:
                    sk = (sa.get("key") or "").lower()
                    sval = sa.get("value") or "-"
                    if sk in ("customerip", "ip"):
                        s_ip = sval
                    elif sk in ("ppplogin", "login", "username"):
                        s_login = sval
                    elif sk in ("ppppass", "password"):
                        s_pass = sval
                    elif sk in ("authtype", "auth-type"):
                        s_auth = sval

                lines.append(f"### Услуга #{idx}: {s_name}")
                lines.append(f"- **Статус**: {s_status}")
                lines.append(f"- **Стоимость**: {s_price:,.2f} {currency}".replace(",", " "))
                lines.append(f"- **Дата активации**: {s_active_from}")
                if s_active_to != "-":
                    lines.append(f"- **Активна до**: {s_active_to}")
                if s_ip != "-":
                    lines.append(f"- **IP-адрес**: {s_ip}")
                if s_login != "-":
                    lines.append(f"- **Логин PPPoE**: {s_login}")
                if s_pass != "-":
                    lines.append(f"- **Пароль PPPoE**: {s_pass}")
                if s.get("note"):
                    lines.append(f"- **Примечание к услуге**: {s.get('note')}")
                lines.append("")

        # Заметки
        lines.append("## Заметки")
        has_notes = False
        if client_note:
            lines.append("### Заметка в профиле:")
            lines.append(f"```\n{client_note}\n```")
            lines.append("")
            has_notes = True

        if logs:
            lines.append("### Журнал заметок:")
            for l in logs:
                l_date = format_date(l.get("createdDate"))
                l_msg = l.get("message") or ""
                lines.append(f"- **{l_date}**: {l_msg}")
            lines.append("")
            has_notes = True

        if not has_notes:
            lines.append("Заметок нет.")
            lines.append("")

        # Тикеты / Заявки
        lines.append("## Тикеты / Заявки")
        if client_tickets:
            sorted_tickets = sorted(client_tickets, key=lambda x: x.get("createdAt") or "", reverse=True)
            for t_idx, t in enumerate(sorted_tickets, 1):
                t_id = t.get("id")
                t_subj = t.get("subject") or "Без темы"
                t_status_code = t.get("status")
                t_status = TICKET_STATUS_MAP.get(t_status_code, f"Статус {t_status_code}")
                t_created = format_date(t.get("createdAt"))
                t_last = format_date(t.get("lastActivity"))

                lines.append(f"### Тикет #{t_id}: {t_subj}")
                lines.append(f"- **Статус**: {t_status}")
                lines.append(f"- **Дата создания**: {t_created}")
                lines.append(f"- **Последняя активность**: {t_last}")

                activities = t.get("activity") or []
                if activities:
                    lines.append("- **История обращений / действий**:")
                    for act in activities:
                        act_date = format_date(act.get("createdAt"))
                        act_type = act.get("type")
                        u_name = admins.get(act.get("userId"), "Клиент" if not act.get("userId") else f"Сотрудник (ID {act.get('userId')})")
                        
                        if act_type == "comment" and act.get("comment"):
                            body = (act["comment"].get("body") or "").strip()
                            lines.append(f"  - **{act_date} [{u_name}]**: {body}")
                        elif act_type == "status_change" and act.get("statusChange"):
                            sc = act["statusChange"]
                            p_st = TICKET_STATUS_MAP.get(sc.get("previousStatus"), str(sc.get("previousStatus")))
                            n_st = TICKET_STATUS_MAP.get(sc.get("status"), str(sc.get("status")))
                            lines.append(f"  - **{act_date} [{u_name}]**: Смена статуса с «{p_st}» на «{n_st}»")
                        elif act_type == "assignment":
                            lines.append(f"  - **{act_date} [{u_name}]**: Назначение ответственного")
                        else:
                            lines.append(f"  - **{act_date} [{u_name}]**: Событие {act_type}")
                lines.append("")
        else:
            lines.append("Тикетов нет.")
            lines.append("")

        # Выписка со счета (Объединенная таблица: invoices, payments, refunds, credit_notes)
        lines.append("## Выписка со счета")

        events = []
        # Invoices
        for inv in client_invoices:
            items_desc = []
            for it in inv.get("items", []):
                lbl = it.get("label") or "Услуга"
                tot = it.get("total", 0.0)
                items_desc.append(f"{lbl} ({tot:,.2f})".replace(",", " "))
            items_str = "; ".join(items_desc) if items_desc else "Услуги связи"
            inv_num = inv.get("number") or str(inv.get("id"))
            events.append({
                "raw_date": inv.get("createdDate") or "",
                "date": format_date(inv.get("createdDate")),
                "element": f"Счет #{inv_num} ({items_str})",
                "invoiced": float(inv.get("total") or 0.0),
                "paid": 0.0,
                "type": "invoice"
            })

        # Payments
        for p in client_payments:
            pmethod_id = p.get("methodId") or ""
            pmethod_name = payment_methods.get(pmethod_id, "" if not pmethod_id else pmethod_id)
            pnote = (p.get("note") or "").strip()
            desc_parts = [f"Платеж #{p.get('id')}"]
            if pmethod_name:
                desc_parts.append(f"[{pmethod_name}]")
            if pnote:
                desc_parts.append(f"- {pnote}")
            pdesc = " ".join(desc_parts)

            events.append({
                "raw_date": p.get("createdDate") or "",
                "date": format_date(p.get("createdDate")),
                "element": pdesc,
                "invoiced": 0.0,
                "paid": float(p.get("amount") or 0.0),
                "type": "payment"
            })

        # Refunds
        for r in client_refunds:
            rnote = (r.get("note") or "").strip()
            rdesc = f"Возврат средств #{r.get('id')}" + (f" - {rnote}" if rnote else "")
            events.append({
                "raw_date": r.get("createdDate") or "",
                "date": format_date(r.get("createdDate")),
                "element": rdesc,
                "invoiced": 0.0,
                "paid": -float(r.get("amount") or 0.0),
                "type": "refund"
            })

        # Credit Notes
        for cn in client_credit_notes:
            cn_note = (cn.get("notes") or "").strip()
            cn_items = []
            for cni in cn.get("items", []):
                lbl = cni.get("label") or "-"
                cn_items.append(lbl)
            items_str = "; ".join(cn_items) if cn_items else ""
            desc_parts = [f"Кредит-нота #{cn.get('number')}"]
            if items_str and items_str != "-":
                desc_parts.append(f"({items_str})")
            if cn_note:
                desc_parts.append(f"- {cn_note}")
            cndesc = " ".join(desc_parts)

            cn_amt = abs(float(cn.get("total") or 0.0))
            events.append({
                "raw_date": cn.get("createdDate") or "",
                "date": format_date(cn.get("createdDate")),
                "element": cndesc,
                "invoiced": -cn_amt,
                "paid": 0.0,
                "type": "credit_note"
            })

        if events:
            events.sort(key=lambda x: (x["raw_date"], 0 if x["type"] in ("payment", "refund") else 1))

            running_balance = 0.0
            total_invoiced = 0.0
            total_paid = 0.0

            for e in events:
                total_invoiced += e["invoiced"]
                total_paid += e["paid"]
                running_balance += (e["paid"] - e["invoiced"])
                e["balance"] = running_balance

            lines.append("| Дата | Элемент | Выставлен счет | Платежи | Баланс |")
            lines.append("|---|---|---|---|---|")

            for e in events:
                d_str = sanitize_cell(e["date"])
                elem_str = sanitize_cell(e["element"])
                inv_str = fmt_money(e["invoiced"], currency) if e["invoiced"] != 0.0 else "-"
                paid_str = fmt_money(e["paid"], currency) if e["paid"] != 0.0 else "-"
                bal_str = fmt_money(e["balance"], currency)
                lines.append(f"| {d_str} | {elem_str} | {inv_str} | {paid_str} | {bal_str} |")

            tot_inv_str = fmt_money(total_invoiced, currency)
            tot_paid_str = fmt_money(total_paid, currency)
            tot_bal_str = fmt_money(running_balance, currency)
            lines.append(f"| **ИТОГО** | | **{tot_inv_str}** | **{tot_paid_str}** | **{tot_bal_str}** |")
            lines.append("")
            lines.append(f"**ИТОГО БАЛАНС**: **{tot_bal_str}**")
        else:
            lines.append("Операций по счету нет.")
            lines.append("")
            lines.append(f"**ИТОГО БАЛАНС**: **{balance:,.2f} {currency}**".replace(",", " "))

        lines.append("")

        file_path = os.path.join(OUTPUT_DIR, f"{cid}.md")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        if str(user_ident) != str(cid):
            u_path = os.path.join(OUTPUT_DIR, f"{user_ident}.md")
            with open(u_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

    print(f"=== Готово! Обработано {len(clients)} абонентов, файлы сохранены в {OUTPUT_DIR} ===")

if __name__ == "__main__":
    main()
