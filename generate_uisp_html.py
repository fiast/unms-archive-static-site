#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конвертация markdown-документации UISP в статический HTML-сайт.

Вход:  output/uisp/       (index.md, mermaid.md, README.md, sites/*.md)
Выход: output/uisp_web/   (index.html, mermaid.html, readme.html, sites/*.html)

Особенности:
 - якоря заголовков строятся тем же алгоритмом, что и в export_uisp_topology.py
   (расширение toc с кастомным slugify), поэтому кросс-ссылки вида
   файл.html#2-устройство продолжают работать;
 - ссылки .md переписываются в .html;
 - блоки ```mermaid``` превращаются в <div class="mermaid"> и рендерятся
   библиотекой mermaid с CDN.
"""

import os
import re
import html
import time
import shutil
import markdown

import config

SRC_DIR = str(config.UISP_MD_DIR)
OUT_DIR = str(config.UISP_HTML_DIR)

MERMAID_CDN = config.CDN_MERMAID_JS


def toc_slugify(value, separator="-"):
    """Совпадает с github_anchor() из export_uisp_topology.py."""
    s = str(value).strip().lower()
    s = re.sub(r"[^\w\- ]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", separator, s.strip())
    return s or "section"


def sanitize_html(s):
    if not s:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def build_page(title, body_html, rel_root="", has_mermaid=False):
    """HTML-страница в стиле CRM-портала (Bootstrap + таблицы)."""
    mermaid_js = ""
    mermaid_init = ""
    if has_mermaid:
        mermaid_js = f'<script src="{MERMAID_CDN}"></script>'
        mermaid_init = """
    if (window.mermaid && document.querySelector('.mermaid')) {
      mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', theme: 'neutral' });
      mermaid.run({ querySelector: '.mermaid' });
    }"""

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
    .navbar-brand {{ font-weight: 700; letter-spacing: 0.5px; }}
    .content-card {{
      background: #ffffff;
      border-radius: 12px;
      box-shadow: 0 4px 18px rgba(0,0,0,0.06);
      padding: 32px;
      margin-top: 24px;
    }}
    h1 {{
      font-size: 1.85rem; font-weight: 700; color: #1a3353;
      border-bottom: 2px solid #e9ecef; padding-bottom: 14px; margin-bottom: 24px;
    }}
    h2 {{
      font-size: 1.35rem; font-weight: 600; color: #2c3e50;
      margin-top: 32px; margin-bottom: 16px; padding-bottom: 8px;
      border-bottom: 1px solid #edf2f7;
    }}
    h3 {{
      font-size: 1.1rem; font-weight: 600; color: #4a5568;
      margin-top: 24px; margin-bottom: 12px;
      background: #f8fafc; padding: 8px 12px; border-radius: 8px;
      border-left: 4px solid #2b3a4a;
    }}
    ul {{ padding-left: 20px; }}
    li {{ margin-bottom: 6px; }}
    pre {{
      background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
      padding: 14px; font-size: 0.85rem; overflow-x: auto;
      max-height: 500px;
    }}
    code {{ color: #d63384; }}
    pre code {{ color: #212529; }}
    a {{ color: #1a6fb5; }}
    .table-responsive {{
      margin-top: 16px; margin-bottom: 24px; border-radius: 8px;
      overflow: auto; border: 1px solid #dee2e6;
      box-shadow: 0 1px 3px rgba(0,0,0,0.02);
      max-height: 640px;
    }}
    table {{ width: 100%; margin-bottom: 0 !important; font-size: 0.88rem; }}
    thead th {{
      background-color: #2b3a4a !important; color: #ffffff !important;
      font-weight: 600; vertical-align: middle; white-space: nowrap;
      padding: 10px 14px !important; border: none !important;
      position: sticky; top: 0; z-index: 1;
    }}
    tbody tr:nth-of-type(even) {{ background-color: #fcfdfe; }}
    tbody tr:hover {{ background-color: #f1f5f9; }}
    tbody td {{
      padding: 10px 14px !important; vertical-align: middle; border-color: #edf2f7;
      white-space: nowrap;
    }}
    .mermaid {{
      background: #ffffff; border: 1px solid #dee2e6; border-radius: 8px;
      padding: 16px; margin: 20px 0; overflow-x: auto; text-align: center;
    }}
    blockquote {{
      border-left: 4px solid #cbd5e1; color: #64748b;
      padding: 4px 16px; margin: 12px 0;
    }}
    hr {{ margin-top: 32px; margin-bottom: 32px; }}
  </style>
</head>
<body>
  <nav class="navbar navbar-expand-lg navbar-dark" style="background-color:#1a3353;">
    <div class="container">
      <a class="navbar-brand" href="{rel_root}index.html"><i class="fa-solid fa-tower-broadcast"></i> UISP Архив</a>
      <div class="d-flex gap-3" style="font-size:0.95rem;">
        <a class="nav-link text-white" href="{rel_root}index.html">Индекс сайтов</a>
        <a class="nav-link text-white" href="{rel_root}mermaid.html">Схема связей</a>
        <a class="nav-link text-white" href="{rel_root}readme.html">О проекте</a>
      </div>
    </div>
  </nav>
  <div class="container">
    <div class="content-card">
{body_html}
    </div>
  </div>
  <script src="{config.CDN_BOOTSTRAP_JS}"></script>
  {mermaid_js}
  <script>
    document.addEventListener('DOMContentLoaded', function () {{{mermaid_init}
    }});
  </script>
</body>
</html>
"""


def md_to_html(parser, md_text):
    """Markdown -> HTML: таблицы, mermaid, переписывание ссылок .md -> .html."""
    body = parser.convert(md_text)

    # адаптивные таблицы
    body = body.replace("<table>", '<div class="table-responsive"><table class="table table-bordered table-hover">')
    body = body.replace("</table>", "</table></div>")

    # блоки ```mermaid``` -> <div class="mermaid">...</div>
    def repl_pre(m):
        code = html.unescape(m.group("code"))
        if code.lstrip().startswith("graph "):
            return f'<div class="mermaid">\n{code}\n</div>'
        return m.group(0)

    body = re.sub(r"<pre[^>]*>\s*<code[^>]*>(?P<code>.*?)</code>\s*</pre>",
                  repl_pre, body, flags=re.S)

    # ссылки вида foo.md / foo.md#anchor -> foo.html / foo.html#anchor
    body = re.sub(r'href="([^"]+?)\.md(#[^"]*)?"', r'href="\1.html\2"', body)
    return body


def first_heading(md_text):
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "UISP"


def convert_file(parser, src_path, out_path, rel_root, default_title="UISP"):
    with open(src_path, encoding="utf-8") as f:
        md_text = f.read()
    body = md_to_html(parser, md_text)
    title = first_heading(md_text) or default_title
    page = build_page(title, body, rel_root=rel_root,
                      has_mermaid='class="mermaid"' in body)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    return len(md_text)


def main():
    print("=== Конвертация uisp/ markdown -> HTML ===")
    t0 = time.time()
    if not os.path.isdir(SRC_DIR):
        raise SystemExit(f"Не найден исходный каталог: {SRC_DIR}")

    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(os.path.join(OUT_DIR, "sites"), exist_ok=True)

    parser = markdown.Markdown(
        extensions=["tables", "fenced_code", "nl2br", "toc"],
        extension_configs={"toc": {"slugify": toc_slugify, "permalink": False}},
    )

    # корневые страницы
    root_pages = [
        ("index.md", "index.html", "Индекс сайтов UISP"),
        ("mermaid.md", "mermaid.html", "Схема связей UISP"),
        ("README.md", "readme.html", "Документация UISP"),
    ]
    converted = 0
    for src_name, out_name, default_title in root_pages:
        src = os.path.join(SRC_DIR, src_name)
        if not os.path.isfile(src):
            print(f"Пропущен отсутствующий файл: {src_name}")
            continue
        convert_file(parser, src, os.path.join(OUT_DIR, out_name),
                     rel_root="", default_title=default_title)
        converted += 1
        print(f"  {src_name} -> {out_name}")

    # страницы сайтов
    sites_src = os.path.join(SRC_DIR, "sites")
    files = sorted(os.listdir(sites_src)) if os.path.isdir(sites_src) else []
    total_bytes = 0
    for fn in files:
        if not fn.endswith(".md"):
            continue
        out_name = fn[:-3] + ".html"
        total_bytes += convert_file(
            parser,
            os.path.join(sites_src, fn),
            os.path.join(OUT_DIR, "sites", out_name),
            rel_root="../",
            default_title=fn,
        )
        converted += 1

    print(f"Страниц создано: {converted} (исходного markdown: "
          f"{total_bytes / 1024:.0f} КБ) за {time.time() - t0:.1f} сек.")
    print(f"Каталог: {OUT_DIR}")
    return converted


if __name__ == "__main__":
    main()

