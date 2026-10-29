import sys
import json
import os
import re
import glob
import subprocess
import urllib.parse
from datetime import datetime, timedelta
import pdfplumber
from icalendar import Calendar, Event

sys.stdout.reconfigure(line_buffering=True)

CALENDAR_PAGE_URL = "https://www.fsw.tv/driving/calendar/"
DEFAULT_DURATION_MINUTES = 30

def run_curl(url, output_path=None):
    cmd = [
        "curl", "-sL",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "-H", "Accept-Language: ja,en-US;q=0.9,en;q=0.8",
        "-H", "Referer: https://www.fsw.tv/",
        "--compressed",
        url
    ]
    if output_path:
        cmd.extend(["-o", output_path])
        subprocess.run(cmd, check=True)
        return output_path
    else:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout

def download_latest_fsw_pdf():
    print(f"カレンダー掲載ページを取得中: {CALENDAR_PAGE_URL}", flush=True)
    html_content = run_curl(CALENDAR_PAGE_URL)

    pdf_urls = re.findall(r'href=["\'](.*?\.pdf)["\']', html_content, re.IGNORECASE)
    if not pdf_urls:
        raise Exception("カレンダーページからPDFリンクが検出できませんでした。")

    target_href = None
    for href in pdf_urls:
        if any(k in href.lower() for k in ["sports", "calendar", "racing", "soukou", "drive"]):
            target_href = href
            break
    if not target_href:
        target_href = pdf_urls[0]

    full_url = urllib.parse.urljoin(CALENDAR_PAGE_URL, target_href)
    print(f"対象PDFのURL: {full_url}", flush=True)

    local_pdf = "downloaded_calendar.pdf"
    run_curl(full_url, output_path=local_pdf)
    
    if os.path.exists(local_pdf) and os.path.getsize(local_pdf) > 5000:
        print(f"PDFダウンロード成功: {local_pdf}", flush=True)
        return local_pdf
    else:
        raise Exception("ダウンロードされたファイルが空、またはアクセス制限を受けました。")

def parse_single_page(page, page_num):
    page_events = []
    page_text = page.extract_text() or ""
    
    year_match = re.search(r'(\d{4})年\s*(\d{1,2})月', page_text)
    if year_match:
        year = int(year_match.group(1))
        month = int(year_match.group(2))
    else:
        print(f"  [スキップ] ページ {page_num}: 年月が見つかりません", flush=True)
        return []

    print(f"  [解析開始] ページ {page_num} -> {year}年{month}月", flush=True)

    chars = page.chars
    if not chars:
        return []

    words = page.extract_words(x_tolerance=2, y_tolerance=2)

    hour_x_map = {}
    for h in range(7, 19):
        pattern = f"{h}:00"
        matches = [w for w in words if w['text'] == pattern and w['x0'] > 150 and w['top'] < 100]
        if matches:
            m = min(matches, key=lambda x: x['top'])
            hour_x_map[h] = (m['x0'] + m['x1']) / 2.0

    valid_hours = sorted(hour_x_map.keys())
    if len(valid_hours) >= 2:
        h_first, h_last = valid_hours[0], valid_hours[-1]
        points_per_hour = (hour_x_map[h_last] - hour_x_map[h_first]) / (h_last - h_first)
        x_7 = hour_x_map[h_first] - (h_first - 7) * points_per_hour
    else:
        x_7 = 205.0
        points_per_hour = 30.8

    day_rows = []
    for d in range(1, 32):
        d_chars = [c for c in chars if c['text'] == str(d) and c['x0'] < 65 and c['top'] > 70]
        if d_chars:
            chosen = min(d_chars, key=lambda c: c['x0'])
            day_rows.append((d, chosen['top'], chosen['bottom']))

    for day, top_y, bottom_y in day_rows:
        center_y = (top_y + bottom_y) / 2.0
        row_chars = [c for c in chars if abs(((c['top'] + c['bottom']) / 2.0) - center_y) < 7 and c['x0'] >= (x_7 - 10)]
        if not row_chars:
            continue
