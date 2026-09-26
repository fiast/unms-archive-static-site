#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерация статического HTML-портала по markdown-карточкам абонентов.

Вход:  output/clients/  ({id}.md, {userIdent}.md)
Выход: output/web/      (index.html, clients/{id}.html)
"""

import os
import re
import json
import time
import markdown

import config

CLIENTS_DIR = str(config.CLIENTS_DIR)
SITE_DIR = str(config.CRM_WEB_DIR)
CLIENTS_HTML_DIR = os.path.join(SITE_DIR, "clients")

def sanitize_html(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def build_client_html(title, content_html, user_ident, cid):
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{sanitize_html(title)}</title>
  <link rel="stylesheet" href="{config.CDN_BOOTSTRAP_CSS}">
  <link rel="stylesheet" href="{config.CDN_FONT_AWESOME_CSS}">
  <style>
    body {{
      background-color: #f4f6f9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      color: #212529;
      padding-bottom: 60px;
    }}
    .navbar-brand {{
      font-weight: 700;
      letter-spacing: 0.5px;
    }}
    .client-card {{
      background: #ffffff;
      border-radius: 12px;
      box-shadow: 0 4px 18px rgba(0,0,0,0.06);
      padding: 32px;
      margin-top: 24px;
    }}
    h1 {{
      font-size: 1.85rem;
      font-weight: 700;
      color: #1a3353;
      border-bottom: 2px solid #e9ecef;
      padding-bottom: 14px;
      margin-bottom: 24px;
    }}
    h2 {{
      font-size: 1.35rem;
      font-weight: 600;
      color: #2c3e50;
      margin-top: 32px;
      margin-bottom: 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid #edf2f7;
    }}
    h3 {{
      font-size: 1.1rem;
      font-weight: 600;
      color: #4a5568;
      margin-top: 20px;
      margin-bottom: 12px;
    }}
    ul {{
      padding-left: 20px;
    }}
    li {{
      margin-bottom: 6px;
    }}
    pre {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 14px;
      font-size: 0.9rem;
    }}
    code {{
      color: #d63384;
    }}
    /* Responsive Table Styles */
    .table-responsive {{
      margin-top: 16px;
      margin-bottom: 24px;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid #dee2e6;
      box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }}
    table {{
      width: 100%;
      margin-bottom: 0 !important;
      font-size: 0.88rem;
    }}
    thead th {{
      background-color: #2b3a4a !important;
      color: #ffffff !important;
      font-weight: 600;
      vertical-align: middle;
      white-space: nowrap;
      padding: 10px 14px !important;
      border: none !important;
    }}
    tbody tr:nth-of-type(even) {{
      background-color: #fcfdfe;
    }}
    tbody tr:hover {{
      background-color: #f1f5f9;
    }}
    tbody td {{
      padding: 10px 14px !important;
      vertical-align: middle;
      border-color: #edf2f7;
    }}
    /* Highlight negative and positive numbers in statement */
    td:last-child {{
      font-weight: 600;
    }}
    .back-btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-weight: 500;
      margin-bottom: 12px;
    }}
  </style>
</head>
<body>

  <!-- Top Navigation -->
  <nav class="navbar navbar-expand-lg navbar-dark bg-dark sticky-top shadow-sm">
    <div class="container-fluid px-4">
      <a class="navbar-brand d-flex align-items-center gap-2" href="../index.html">
        <i class="fa-solid fa-network-wired text-info"></i>
        <span>Абоненты CRM</span>
      </a>
      <div class="ms-auto d-flex align-items-center gap-2">
        <a href="../index.html" class="btn btn-outline-light btn-sm">
          <i class="fa-solid fa-list me-1"></i> К общему реестру
        </a>
      </div>
    </div>
  </nav>

  <div class="container">
    <div class="client-card">
      <a href="../index.html" class="btn btn-link text-decoration-none px-0 back-btn">
        <i class="fa-solid fa-arrow-left"></i> Вернуться к списку абонентов
      </a>
      {content_html}
    </div>
  </div>

  <script src="{config.CDN_BOOTSTRAP_JS}"></script>
</body>
</html>
"""

def build_index_html(records_json):
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Реестр абонентов UISP CRM</title>
  <!-- Bootstrap 5 -->
  <link rel="stylesheet" href="{config.CDN_BOOTSTRAP_CSS}">
  <!-- FontAwesome -->
  <link rel="stylesheet" href="{config.CDN_FONT_AWESOME_CSS}">
  <!-- DataTables BS5 -->
  <link rel="stylesheet" href="{config.CDN_DATATABLES_CSS}">
  <link rel="stylesheet" href="{config.CDN_DATATABLES_RESP_CSS}">
  <style>
    body {{
      background-color: #f0f2f5;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      color: #1e293b;
      padding-bottom: 60px;
    }}
    .navbar-brand {{
      font-weight: 700;
      letter-spacing: 0.5px;
    }}
    .stats-card {{
      background: #ffffff;
      border-radius: 12px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.04);
      padding: 16px 20px;
      border-left: 4px solid #3b82f6;
      transition: transform 0.15s ease;
    }}
    .stats-card:hover {{
      transform: translateY(-2px);
    }}
    .stats-card.debt {{ border-left-color: #ef4444; }}
    .stats-card.active {{ border-left-color: #10b981; }}
    .stats-card.tickets {{ border-left-color: #f59e0b; }}
    .stats-num {{
      font-size: 1.6rem;
      font-weight: 700;
      line-height: 1.2;
    }}
    .stats-label {{
      font-size: 0.85rem;
      color: #64748b;
      font-weight: 500;
    }}
    .main-card {{
      background: #ffffff;
      border-radius: 14px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.05);
      padding: 24px;
      margin-top: 20px;
    }}
    .filter-btn-group .btn {{
      font-size: 0.88rem;
      font-weight: 500;
      padding: 6px 14px;
      border-radius: 8px !important;
      margin-right: 6px;
      margin-bottom: 6px;
    }}
    .table-container {{
      margin-top: 18px;
    }}
    table.dataTable thead th {{
      background-color: #1e293b !important;
      color: #f8fafc !important;
      font-size: 0.86rem;
      font-weight: 600;
      border: none !important;
      vertical-align: middle;
      white-space: nowrap;
    }}
    table.dataTable tbody td {{
      font-size: 0.88rem;
      vertical-align: middle;
      cursor: pointer;
    }}
    table.dataTable tbody tr:hover {{
      background-color: #f1f5f9 !important;
    }}
    .badge-status {{
      font-size: 0.76rem;
      padding: 4px 8px;
      border-radius: 6px;
      font-weight: 600;
    }}
    .badge-active {{ background-color: #dcfce7; color: #15803d; }}
    .badge-inactive {{ background-color: #f1f5f9; color: #475569; }}
    .badge-archived {{ background-color: #fee2e2; color: #b91c1c; }}
    .balance-positive {{ color: #16a34a; font-weight: 600; }}
    .balance-negative {{ color: #dc2626; font-weight: 700; }}
    .balance-zero {{ color: #64748b; font-weight: 500; }}
    .badge-ticket {{
      background-color: #fef3c7;
      color: #b45309;
      font-size: 0.74rem;
      padding: 3px 7px;
      border-radius: 5px;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .search-box {{
      position: relative;
    }}
    .search-box i {{
      position: absolute;
      left: 14px;
      top: 12px;
      color: #94a3b8;
    }}
    .search-box input {{
      padding-left: 38px;
      border-radius: 8px;
    }}
  </style>
</head>
<body>

  <!-- Top Navigation -->
  <nav class="navbar navbar-dark bg-dark sticky-top shadow-sm py-2">
    <div class="container-fluid px-4">
      <span class="navbar-brand d-flex align-items-center gap-2">
        <i class="fa-solid fa-network-wired text-info"></i>
        <span>UISP CRM — Реестр абонентов</span>
      </span>
      <span class="navbar-text text-light-50 text-sm small d-none d-md-block">
        База данных активных и архивных клиентов
      </span>
    </div>
  </nav>

  <div class="container-fluid px-4 mt-3">

    <!-- KPI / Statistics Cards -->
    <div class="row g-3">
      <div class="col-6 col-md-3">
        <div class="stats-card">
          <div class="stats-label"><i class="fa-solid fa-users me-1"></i> Всего абонентов</div>
          <div class="stats-num text-primary" id="kpi-total">0</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="stats-card active">
          <div class="stats-label"><i class="fa-solid fa-user-check me-1"></i> Активных</div>
          <div class="stats-num text-success" id="kpi-active">0</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="stats-card debt">
          <div class="stats-label"><i class="fa-solid fa-triangle-exclamation me-1"></i> С задолженностью</div>
          <div class="stats-num text-danger" id="kpi-debt">0</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="stats-card tickets">
          <div class="stats-label"><i class="fa-solid fa-headset me-1"></i> С открытыми тикетами</div>
          <div class="stats-num text-warning" id="kpi-tickets">0</div>
        </div>
      </div>
    </div>

    <!-- Main Table Container -->
    <div class="main-card">
      <div class="row align-items-center mb-3">
        <div class="col-12 col-md-7 mb-2 mb-md-0">
          <div class="filter-btn-group d-flex flex-wrap gap-1">
            <button class="btn btn-primary active" id="filter-all"><i class="fa-solid fa-list me-1"></i> Все абоненты</button>
            <button class="btn btn-outline-success" id="filter-active"><i class="fa-solid fa-user-check me-1"></i> Только активные</button>
            <button class="btn btn-outline-danger" id="filter-debt"><i class="fa-solid fa-circle-exclamation me-1"></i> С долгом (&lt; 0)</button>
            <button class="btn btn-outline-warning text-dark" id="filter-tickets"><i class="fa-solid fa-comments me-1"></i> С открытыми тикетами</button>
          </div>
        </div>
        <div class="col-12 col-md-5">
          <div class="search-box">
            <i class="fa-solid fa-magnifying-glass"></i>
            <input type="text" id="global-search" class="form-control" placeholder="Поиск по ФИО, л/с, адресу, телефону, IP, MAC...">
          </div>
        </div>
      </div>

      <div class="table-responsive table-container">
        <table id="clients-table" class="table table-hover align-middle w-100">
          <thead>
            <tr>
              <th>Л/С</th>
              <th>ФИО / Наименование</th>
              <th>Статус</th>
              <th>Баланс</th>
              <th>Адрес</th>
              <th>Телефон</th>
              <th>IP-адрес</th>
              <th>MAC-адрес</th>
              <th>Тикеты</th>
              <th>Действие</th>
            </tr>
          </thead>
          <tbody>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- jQuery & Bootstrap & DataTables -->
  <script src="{config.CDN_JQUERY}"></script>
  <script src="{config.CDN_BOOTSTRAP_JS}"></script>
  <script src="{config.CDN_DATATABLES_JS}"></script>
  <script src="{config.CDN_DATATABLES_BS5_JS}"></script>
  <script src="https://cdn.datatables.net/responsive/2.5.0/js/dataTables.responsive.min.js"></script>
  <script src="{config.CDN_DATATABLES_RESP_JS}"></script>

  <script>
    const clientsData = {records_json};

    // Calculate stats
    let totalCount = clientsData.length;
    let activeCount = clientsData.filter(c => c.status === 'Активен').length;
    let debtCount = clientsData.filter(c => c.balance < 0).length;
    let ticketCount = clientsData.filter(c => c.has_open_ticket).length;

    document.getElementById('kpi-total').textContent = totalCount;
    document.getElementById('kpi-active').textContent = activeCount;
    document.getElementById('kpi-debt').textContent = debtCount;
    document.getElementById('kpi-tickets').textContent = ticketCount;

    // Custom filtering state
    let currentFilter = 'all';

    $.fn.dataTable.ext.search.push(function(settings, data, dataIndex) {{
      const client = clientsData[dataIndex];
      if (currentFilter === 'active') {{
        return client.status === 'Активен';
      }} else if (currentFilter === 'debt') {{
        return client.balance < 0;
      }} else if (currentFilter === 'tickets') {{
        return client.has_open_ticket;
      }}
      return true;
    }});

    $(document).ready(function() {{
      const table = $('#clients-table').DataTable({{
        data: clientsData,
        responsive: true,
        pageLength: 25,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "Все"]],
        language: {{
          search: "Быстрый фильтр:",
          lengthMenu: "Показывать по _MENU_ строк",
          info: "Показано с _START_ по _END_ из _TOTAL_ абонентов",
          infoEmpty: "Записей нет",
          infoFiltered: "(отфильтровано из _MAX_ всего)",
          zeroRecords: "Ничего не найдено",
          paginate: {{
            first: "Первая",
            last: "Последняя",
            next: "Вперед",
            previous: "Назад"
          }}
        }},
        columns: [
          {{
            data: 'userIdent',
            render: function(data, type, row) {{
              return '<span class="fw-bold text-primary">' + data + '</span>';
            }}
          }},
          {{
            data: 'fio',
            render: function(data, type, row) {{
              return '<div class="fw-semibold">' + data + '</div><small class="text-muted">ID: ' + row.id + '</small>';
            }}
          }},
          {{
            data: 'status',
            render: function(data, type, row) {{
              if (data === 'Активен') {{
                return '<span class="badge badge-status badge-active">Активен</span>';
              }} else if (data === 'Архивный') {{
                return '<span class="badge badge-status badge-archived">Архивный</span>';
              }} else {{
                return '<span class="badge badge-status badge-inactive">' + data + '</span>';
              }}
            }}
          }},
          {{
            data: 'balance',
            render: function(data, type, row) {{
              if (type === 'sort' || type === 'type') return data;
              const formatted = data.toLocaleString('ru-RU', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}) + ' ₽';
              if (data < 0) {{
                return '<span class="balance-negative">' + formatted + '</span>';
              }} else if (data > 0) {{
                return '<span class="balance-positive">' + formatted + '</span>';
              }} else {{
                return '<span class="balance-zero">' + formatted + '</span>';
              }}
            }}
          }},
          {{
            data: 'addr',
            render: function(data) {{
              return '<span class="text-truncate d-inline-block" style="max-width: 250px;" title="' + data + '">' + data + '</span>';
            }}
          }},
          {{ data: 'phone' }},
          {{
            data: 'ip',
            render: function(data) {{
              return data !== '-' ? '<code>' + data + '</code>' : '-';
            }}
          }},
          {{
            data: 'mac',
            render: function(data) {{
              return data !== '-' ? '<small class="text-secondary">' + data + '</small>' : '-';
            }}
          }},
          {{
            data: 'has_open_ticket',
            render: function(data) {{
              if (data) {{
                return '<span class="badge-ticket"><i class="fa-solid fa-bell"></i> Открыт</span>';
              }}
              return '<span class="text-muted small">-</span>';
            }}
          }},
          {{
            data: null,
            orderable: false,
            render: function(data, type, row) {{
              return '<a href="clients/' + row.file_name + '" class="btn btn-sm btn-outline-primary"><i class="fa-solid fa-arrow-right"></i></a>';
            }}
          }}
        ],
        order: [[0, 'asc']]
      }});

      // Row click to navigate
      $('#clients-table tbody').on('click', 'tr td:not(:last-child)', function() {{
        const rowData = table.row(this).data();
        if (rowData && rowData.file_name) {{
          window.location.href = 'clients/' + rowData.file_name;
        }}
      }});

      // Custom global search input
      $('#global-search').on('keyup', function() {{
        table.search(this.value).draw();
      }});

      // Filter button clicks
      $('.filter-btn-group .btn').on('click', function() {{
        $('.filter-btn-group .btn').removeClass('btn-primary btn-success btn-danger btn-warning active')
          .addClass('btn-outline-primary');
        
        const btnId = $(this).attr('id');
        if (btnId === 'filter-all') {{
          currentFilter = 'all';
          $(this).removeClass('btn-outline-primary').addClass('btn-primary active');
        }} else if (btnId === 'filter-active') {{
          currentFilter = 'active';
          $(this).removeClass('btn-outline-primary').addClass('btn-success active');
        }} else if (btnId === 'filter-debt') {{
          currentFilter = 'debt';
          $(this).removeClass('btn-outline-primary').addClass('btn-danger active');
        }} else if (btnId === 'filter-tickets') {{
          currentFilter = 'tickets';
          $(this).removeClass('btn-outline-primary').addClass('btn-warning text-dark active');
        }}
        table.draw();
      }});
    }});
  </script>
</body>
</html>
"""

def main():
    print("=== Начало сборки статического веб-портала ===")
    t0 = time.time()
    os.makedirs(CLIENTS_HTML_DIR, exist_ok=True)

    md_files = [f for f in os.listdir(CLIENTS_DIR) if f.endswith(".md")]
    print(f"Найдено {len(md_files)} markdown файлов.")

    records = {}
    md_parser = markdown.Markdown(extensions=["tables", "fenced_code", "nl2br"])

    for fname in md_files:
        path = os.path.join(CLIENTS_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        m_id = re.search(r"\- \*\*ID\*\*:\s*(\d+)", text)
        if not m_id:
            continue
        cid = m_id.group(1)

        # Skip duplicate parsing for the index table
        if cid in records:
            continue

        m_ident = re.search(r"\- \*\*Номер договора / Лицевой счет \(userIdent\)\*\*:\s*(.*)", text)
        ident = m_ident.group(1).strip() if m_ident else cid

        m_fio = re.search(r"\- \*\*ФИО / Наименование\*\*:\s*(.*)", text)
        fio = m_fio.group(1).strip() if m_fio else "-"

        m_status = re.search(r"\- \*\*Статус\*\*:\s*(.*)", text)
        status = m_status.group(1).strip() if m_status else "-"

        m_addr = re.search(r"\- \*\*Адрес\*\*:\s*(.*)", text)
        addr = m_addr.group(1).strip() if m_addr else "-"

        m_phone = re.search(r"\- \*\*Телефон\*\*:\s*(.*)", text)
        phone = m_phone.group(1).strip() if m_phone else "-"

        m_mac = re.search(r"\- \*\*MAC-адрес\*\*:\s*(.*)", text)
        mac = m_mac.group(1).strip() if m_mac else "-"

        ips = re.findall(r"\- \*\*IP-адрес\*\*:\s*([^\s\n\r]+)", text)
        ip_str = ", ".join(sorted(list(set(ips)))) if ips else "-"

        m_bal = re.search(r"\- \*\*Текущий баланс\*\*:\s*([\-\d\s\.,]+)\s*([A-Z]+)", text)
        bal_str = m_bal.group(1).strip() if m_bal else "0.00"
        bal_val = float(bal_str.replace(" ", "").replace(",", ".")) if m_bal else 0.0

        ticket_part = text[text.find("## Тикеты"):] if "## Тикеты" in text else ""
        has_open_ticket = bool(re.search(r"\- \*\*Статус\*\*:\s*(Новый|Открыт|В ожидании)", ticket_part))

        records[cid] = {
            "id": cid,
            "userIdent": ident,
            "fio": fio,
            "status": status,
            "addr": addr,
            "phone": phone,
            "ip": ip_str,
            "mac": mac,
            "balance": bal_val,
            "has_open_ticket": has_open_ticket,
            "file_name": f"{ident}.html",
            "md_text": text
        }

    print(f"Извлечено {len(records)} уникальных абонентов. Генерация HTML карточек...")

    # Convert each client md to HTML
    converted_count = 0
    for cid, rec in records.items():
        ident = rec["userIdent"]
        raw_md = rec["md_text"]

        md_parser.reset()
        html_body = md_parser.convert(raw_md)

        # Wrap tables in table-responsive
        html_body = html_body.replace("<table>", '<div class="table-responsive"><table class="table table-bordered table-hover">')
        html_body = html_body.replace("</table>", "</table></div>")

        page_title = f"Абонент {ident} — Карточка клиента"
        full_html = build_client_html(page_title, html_body, ident, cid)

        # Write {userIdent}.html
        out_ident_path = os.path.join(CLIENTS_HTML_DIR, f"{ident}.html")
        with open(out_ident_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        converted_count += 1

        # If userIdent != cid, also write {cid}.html for direct ID access
        if str(ident) != str(cid):
            out_cid_path = os.path.join(CLIENTS_HTML_DIR, f"{cid}.html")
            with open(out_cid_path, "w", encoding="utf-8") as f:
                f.write(full_html)
            converted_count += 1

    print(f"Сгенерировано {converted_count} HTML карточек в {CLIENTS_HTML_DIR}.")

    # Build index.html
    # Prepare records without large md_text
    clean_records = []
    for r in records.values():
        c = dict(r)
        del c["md_text"]
        clean_records.append(c)

    # Sort by userIdent
    clean_records.sort(key=lambda x: str(x["userIdent"]))

    records_json = json.dumps(clean_records, ensure_ascii=False)
    index_html = build_index_html(records_json)

    index_path = os.path.join(SITE_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"Главная страница создана: {index_path}")
    print(f"=== Сборка успешно завершена за {time.time()-t0:.2f} сек. ===")

if __name__ == "__main__":
    main()
