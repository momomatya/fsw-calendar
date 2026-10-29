import json
import os
import re
import subprocess
import urllib.parse
from datetime import datetime, timedelta
import pdfplumber
from icalendar import Calendar, Event

# ================= 設定 =================
CALENDAR_PAGE_URL = "https://www.fsw.tv/driving/calendar/"
DEFAULT_DURATION_MINUTES = 30
# ========================================

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
    print(f"カレンダー掲載ページを取得中: {CALENDAR_PAGE_URL}")
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
    print(f"対象PDFのURL: {full_url}")

    local_pdf = "downloaded_calendar.pdf"
    run_curl(full_url, output_path=local_pdf)
    
    if os.path.exists(local_pdf) and os.path.getsize(local_pdf) > 5000:
        print(f"PDFダウンロード成功: {local_pdf}")
        return local_pdf
    else:
        raise Exception("ダウンロードされたファイルが空、またはアクセス制限を受けました。")

def parse_single_page(page):
    """1ページ分の走行予定表を解析してイベントリストを返す"""
    page_events = []
    page_text = page.extract_text() or ""
    
    # 年月を抽出
    year_match = re.search(r'(\d{4})年\s*(\d{1,2})月', page_text)
    if year_match:
        year = int(year_match.group(1))
        month = int(year_match.group(2))
    else:
        return []

    words = page.extract_words()
    if not words:
        return []

    # 時間目盛りの基準（7:00 と 18:00 のX座標）
    time_headers = {}
    for h in range(7, 19):
        matches = [w for w in words if w['text'] == f"{h}:00" and w['x0'] > 180]
        if matches:
            time_headers[h] = min(matches, key=lambda x: x['top'])['x0']

    x_7 = time_headers.get(7, 201.1)
    x_18 = time_headers.get(18, 540.2)
    points_per_hour = (x_18 - x_7) / 11.0

    # 日付行の特定
    day_rows = []
    for d in range(1, 32):
        d_words = [w for w in words if w['text'] == str(d) and w['x0'] < 70 and w['top'] > 90]
        if d_words:
            day_rows.append((d, d_words[0]['top']))

    for day, y_top in day_rows:
        row_words = [w for w in words if abs(w['top'] - y_top) < 7 and w['x0'] >= (x_7 - 10)]
        if not row_words:
            continue

        row_words = sorted(row_words, key=lambda x: x['x0'])
        
        clusters = []
        curr_cluster = []
        for w in row_words:
            if not curr_cluster:
                curr_cluster.append(w)
            else:
                prev_w = curr_cluster[-1]
                gap = w['x0'] - prev_w['x1']
                if gap < 6.0:
                    curr_cluster.append(w)
                else:
                    clusters.append(curr_cluster)
                    curr_cluster = [w]
        if curr_cluster:
            clusters.append(curr_cluster)

        for cluster in clusters:
            text = " ".join([w['text'] for w in cluster]).strip()
            text = re.sub(r'\s+', ' ', text)
            
            if not any(cls in text for cls in ['S-4', 'NS-4', 'N-4', 'R-4', 'RC-4', 'FS-4', 'L-4', 'O-4']):
                continue

            start_x = cluster[0]['x0']
            offset_hours = (start_x - x_7) / points_per_hour
            total_minutes = 7 * 60 + int(offset_hours * 60)
            
            hour = total_minutes // 60
            minute = total_minutes % 60
            
            minute = int(round(minute / 5.0) * 5)
            if minute >= 60:
                hour += 1
                minute -= 60

            try:
                start_dt = datetime(year, month, day, hour, minute)
                end_dt = start_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES)
                page_events.append({
                    "summary": f"{text}",
                    "start": start_dt,
                    "end": end_dt,
                    "description": f"富士スピードウェイ レーシングコース スポーツ走行枠\n枠名: {text}"
                })
            except ValueError as e:
                print(f"日付パースエラー: {year}-{month}-{day} {hour}:{minute} -> {e}")
                continue

    print(f"  -> {year}年{month}月のページから {len(page_events)} 件の走行枠を抽出")
    if page_events:
        print(f"     [サンプル] 初回枠: {page_events[0]['start']} ({page_events[0]['summary']})")
    return page_events

def parse_fsw_pdf(pdf_path):
    all_events = []
    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if "レーシングコース" in text and "スポーツ走行予定表" in text:
                print(f"対象ページ検出: ページ {idx + 1}")
                events = parse_single_page(page)
                all_events.extend(events)

    return all_events

def create_ical(events, output_filename="fsw_calendar.ics"):
    cal = Calendar()
    cal.add('prodid', '-//FSW Member Track Calendar//JP')
    cal.add('version', '2.0')

    for ev in events:
        event = Event()
        event.add('summary', f"FSW {ev['summary']}")
        event.add('dtstart', ev['start'])
        event.add('dtend', ev['end'])
        event.add('description', ev['description'])
        event.add('location', '富士スピードウェイ')
        cal.add_component(event)

    with open(output_filename, 'wb') as f:
        f.write(cal.to_ical())
    print(f"[成功] iCalカレンダー生成完了: {output_filename}")

def save_events_json(events, output_filename="events.json"):
    web_events = []
    for ev in events:
        # FullCalendarが完全に認識できるISO8601フォーマット (YYYY-MM-DDTHH:MM:SS)
        start_str = ev["start"].strftime("%Y-%m-%dT%H:%M:%S")
        end_str = ev["end"].strftime("%Y-%m-%dT%H:%M:%S")
        web_events.append({
            "title": ev["summary"],
            "start": start_str,
            "end": end_str,
            "description": ev["description"]
        })
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(web_events, f, ensure_ascii=False, indent=2)
    print(f"[成功] Web用JSON生成完了: {output_filename} (合計 {len(web_events)} 件)")

if __name__ == '__main__':
    pdf_file = None
    try:
        pdf_file = download_latest_fsw_pdf()
    except Exception as e:
        print(f"Web自動取得をスキップ（または失敗）: {e}")
        import glob
        local_pdfs = [f for f in glob.glob("*.pdf") if "downloaded" not in f]
        if local_pdfs:
            pdf_file = local_pdfs[0]
            print(f"リポジトリ内のバックアップPDFを使用します: {pdf_file}")
        else:
            raise e

    events = parse_fsw_pdf(pdf_file)
    create_ical(events, output_filename="fsw_calendar.ics")
    save_events_json(events, output_filename="events.json")
