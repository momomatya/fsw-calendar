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

    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    if not words:
        return []

    # 7:00 〜 18:00 の目盛りヘッダー座標を特定
    hour_x_map = {}
    for h in range(7, 19):
        pattern = f"{h}:00"
        matches = [w for w in words if pattern in w['text'] and w['x0'] > 150 and w['top'] < 130]
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

    # 左端の日付（1〜31）の検出範囲を広げる（x0 < 90、top > 50）
    day_rows = []
    for d in range(1, 32):
        d_str = str(d)
        d_words = [w for w in words if w['text'] == d_str and w['x0'] < 90 and w['top'] > 50]
        if d_words:
            chosen = min(d_words, key=lambda w: w['x0'])
            day_rows.append((d, chosen['top'], chosen['bottom']))

    # 日付順（Y座標順）に並べ替え
    day_rows = sorted(day_rows, key=lambda x: x[1])
    print(f"     検出された日付行数: {len(day_rows)} 日分", flush=True)

    for i, (day, top_y, bottom_y) in enumerate(day_rows):
        # 行の上下範囲を前後の日付行の中間まで動的に割り当て
        if i == 0:
            upper_bound = top_y - 5
        else:
            upper_bound = (day_rows[i-1][2] + top_y) / 2.0

        if i == len(day_rows) - 1:
            lower_bound = bottom_y + 12
        else:
            lower_bound = (bottom_y + day_rows[i+1][1]) / 2.0

        # 当該日付行の文字群を抽出（時間軸エリア：x0 >= x_7 - 15）
        row_words = [w for w in words if upper_bound <= ((w['top'] + w['bottom']) / 2.0) <= lower_bound and w['x0'] >= (x_7 - 15)]
        if not row_words:
            continue

        row_words = sorted(row_words, key=lambda w: w['x0'])

        # 単語同士が近ければクラスタリング（網掛けで分断された文字を再結合）
        clusters = []
        curr = []
        for w in row_words:
            if not curr:
                curr.append(w)
            else:
                prev_w = curr[-1]
                if (w['x0'] - prev_w['x1']) < 9.0:
                    curr.append(w)
                else:
                    clusters.append(curr)
                    curr = [w]
        if curr:
            clusters.append(curr)

        for cluster in clusters:
            raw_text = "".join([w['text'] for w in cluster])
            clean_str = re.sub(r'[^A-Za-z0-9]', '', raw_text).upper()

            # クラス名のパターンマッチ
            match = re.search(r'(S4|NS4|N4|R4|RC4|FS4|L4|O4)([ABCD]?)', clean_str)
            if not match:
                continue

            cls_name = match.group(1)
            grp_name = match.group(2)
            formatted_title = f"{cls_name[:-1]}-{cls_
