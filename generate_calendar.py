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

    words = page.extract_words(x_tolerance=3, y_tolerance=3)

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

    day_rows = []
    for d in range(1, 32):
        d_str = str(d)
        d_words = [w for w in words if w['text'].strip() == d_str and w['x0'] < 60 and w['top'] > 50]
        if d_words:
            chosen = min(d_words, key=lambda w: w['x0'])
            day_rows.append((d, chosen['top'], chosen['bottom']))

    day_rows = sorted(day_rows, key=lambda x: x[1])

    for i, (day, top_y, bottom_y) in enumerate(day_rows):
        if i == 0:
            upper_bound = top_y - 6
        else:
            upper_bound = (day_rows[i-1][2] + top_y) / 2.0

        if i == len(day_rows) - 1:
            lower_bound = bottom_y + 14
        else:
            lower_bound = (bottom_y + day_rows[i+1][1]) / 2.0

        row_chars = [c for c in chars if upper_bound <= ((c['top'] + c['bottom']) / 2.0) <= lower_bound and c['x0'] >= (x_7 - 15)]
        if not row_chars:
            continue

        row_chars = sorted(row_chars, key=lambda c: c['x0'])

        clusters = []
        curr = []
        for c in row_chars:
            if not curr:
                curr.append(c)
            else:
                prev_c = curr[-1]
                if c['text'] in ['・', '･', '.', ' ']:
                    continue
                if (c['x0'] - prev_c['x1']) < 8.0:
                    curr.append(c)
                else:
                    clusters.append(curr)
                    curr = [c]
        if curr:
            clusters.append(curr)

        for cluster in clusters:
            raw_text = "".join([c['text'] for c in cluster])
            clean_str = re.sub(r'[^A-Za-z0-9]', '', raw_text).upper()

            # L4, S4, NS4, N4, R4, RC4, FS4, O4 に対応
            match = re.search(r'(S4|NS4|N4|R4|RC4|FS4|L4|O4)([ABCD]?)', clean_str)
            if not match:
                continue

            cls_name = match.group(1)
            grp_name = match.group(2)
            formatted_title = f"{cls_name[:-1]}-{cls_name[-1]}"
            if grp_name:
                formatted_title += f" {grp_name}"

            start_x = cluster[0]['x0']
            adjusted_x = start_x - 4.0
            total_minutes = 7 * 60 + ((adjusted_x - x_7) / points_per_hour) * 60.0

            snapped_minute = int(round(total_minutes / 10.0) * 10)
            hour = snapped_minute // 60
            minute = snapped_minute % 60

            try:
                start_dt = datetime(year, month, day, hour, minute)
                end_dt = start_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES)
                page_events.append({
                    "summary": formatted_title,
                    "start": start_dt,
                    "end": end_dt,
                    "time_str": f"{hour}:{minute:02d}",
                    "description": f"富士スピードウェイ レーシングコース スポーツ走行枠\n枠名: {formatted_title}\n時間: {hour}:{minute:02d}〜"
                })
            except ValueError:
                continue

    unique_events = []
    seen = set()
    for ev in sorted(page_events, key=lambda x: x['start']):
        key = (ev['start'], ev['summary'])
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    print(f"  -> {year}年{month}月のページから {len(unique_events)} 件の走行枠を抽出完了", flush=True)
    # L-4 枠の検出ログ
    l4_events = [e for e in unique_events if "L-4" in e['summary']]
    if l4_events:
        print(f"     [L-4 検出] {len(l4_events)} 件: {', '.join([f'{e[\"start\"].day}日 {e[\"time_str\"]}' for e in l4_events])}", flush=True)

    return unique_events

def parse_fsw_pdf(pdf_path):
    print(f"=== PDF解析開始: {pdf_path} ===", flush=True)
    all_events = []
    with pdfplumber.open(pdf_path) as pdf:
        print(f"PDF総ページ数: {len(pdf.pages)}", flush=True)
        for idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if ("レーシング" in text or "RC" in text or "コース" in text) and ("予定" in text or "カレンダー" in text or "走行" in text):
                events = parse_single_page(page, idx + 1)
                all_events.extend(events)
            else:
                first_line = text.split('\n')[0] if text else "(テキストなし)"
                print(f"  [対象外ページ] ページ {idx + 1}: {first_line[:40]}", flush=True)

    return all_events

def create_ical(events, output_filename="fsw_calendar.ics"):
    cal = Calendar()
    cal.add('prodid', '-//FSW Member Track Calendar//JP')
    cal.add('version', '2.0')

    for ev in events:
        event = Event()
        event.add('summary', f"FSW {ev['time_str']} {ev['summary']}")
        event.add('dtstart', ev['start'])
        event.add('dtend', ev['end'])
        event.add('description', ev['description'])
        event.add('location', '富士スピードウェイ')
        cal.add_component(event)

    with open(output_filename, 'wb') as f:
        f.write(cal.to_ical())
    print(f"[成功] iCalカレンダー生成完了: {output_filename}", flush=True)

def save_events_json(events, output_filename="events.json"):
    web_events = []
    for ev in events:
        start_str = ev["start"].strftime("%Y-%m-%dT%H:%M:%S")
        end_str = ev["end"].strftime("%Y-%m-%dT%H:%M:%S")
        display_title = f"{ev['time_str']} {ev['summary']}"
        web_events.append({
            "title": display_title,
            "raw_summary": ev["summary"],
            "start": start_str,
            "end": end_str,
            "description": ev["description"]
        })
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(web_events, f, ensure_ascii=False, indent=2)
    print(f"[成功] Web用JSON生成完了: {output_filename} (合計 {len(web_events)} 件)", flush=True)

def main():
    print("=== スクリプト実行開始 ===", flush=True)
    local_pdfs = [f for f in glob.glob("*.pdf") if "downloaded" not in f]

    pdf_file = None
    try:
        pdf_file = download_latest_fsw_pdf()
    except Exception as e:
        print(f"Web自動取得をスキップ（または失敗）: {e}", flush=True)
        if local_pdfs:
            pdf_file = sorted(local_pdfs, key=lambda x: os.path.getsize(x), reverse=True)[0]
            print(f"リポジトリ内のバックアップPDFを使用します: {pdf_file}", flush=True)
        else:
            raise e

    events = parse_fsw_pdf(pdf_file)
    create_ical(events, output_filename="fsw_calendar.ics")
    save_events_json(events, output_filename="events.json")
    print("=== スクリプト全処理完了 ===", flush=True)

if __name__ == '__main__':
    main()
