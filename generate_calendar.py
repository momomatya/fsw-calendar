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
    
    year_match = re.search(r'(\d{4})年\s*(\d{1,2})月', page_text)
    if year_match:
        year = int(year_match.group(1))
        month = int(year_match.group(2))
    else:
        return []

    chars = page.chars
    if not chars:
        return []

    words = page.extract_words(x_tolerance=2, y_tolerance=2)

    # 7:00 〜 18:00 の目盛りヘッダー文字から各時間の基準X座標を精密に取得
    hour_x_map = {}
    for h in range(7, 19):
        pattern = f"{h}:00"
        matches = [w for w in words if w['text'] == pattern and w['x0'] > 150 and w['top'] < 100]
        if matches:
            m = min(matches, key=lambda x: x['top'])
            # 文字の中心をその時間の基準点とする
            hour_x_map[h] = (m['x0'] + m['x1']) / 2.0

    # 1時間あたりの幅（ピクセル/ポイント数）を算出
    valid_hours = sorted(hour_x_map.keys())
    if len(valid_hours) >= 2:
        h_first, h_last = valid_hours[0], valid_hours[-1]
        points_per_hour = (hour_x_map[h_last] - hour_x_map[h_first]) / (h_last - h_first)
        # 基準となる 7:00 のX座標
        x_7 = hour_x_map[h_first] - (h_first - 7) * points_per_hour
    else:
        # 見つからない場合の安全値
        x_7 = 205.0
        points_per_hour = 30.8

    # 日付列（1〜31日）のY座標を取得
    day_rows = []
    for d in range(1, 32):
        d_chars = [c for c in chars if c['text'] == str(d) and c['x0'] < 65 and c['top'] > 70]
        if d_chars:
            chosen = min(d_chars, key=lambda c: c['x0'])
            day_rows.append((d, chosen['top'], chosen['bottom']))

    for day, top_y, bottom_y in day_rows:
        center_y = (top_y + bottom_y) / 2.0
        
        # 日付行の高さ内（±7pt）にある、表エリア（x >= x_7 - 10）の文字
        row_chars = [c for c in chars if abs(((c['top'] + c['bottom']) / 2.0) - center_y) < 7 and c['x0'] >= (x_7 - 10)]
        if not row_chars:
            continue

        row_chars = sorted(row_chars, key=lambda c: c['x0'])

        # ドット模様やノイズを吸収して単語をクラスタリング
        clusters = []
        curr_cluster = []
        for c in row_chars:
            if not curr_cluster:
                curr_cluster.append(c)
            else:
                prev_c = curr_cluster[-1]
                # 文字と文字の間隔が 8pt 未満なら同一枠の文字とみなす
                if (c['x0'] - prev_c['x1']) < 8.0:
                    curr_cluster.append(c)
                else:
                    clusters.append(curr_cluster)
                    curr_cluster = [c]
        if curr_cluster:
            clusters.append(curr_cluster)

        for cluster in clusters:
            raw_str = "".join([c['text'] for c in cluster])
            clean_str = re.sub(r'[^A-Za-z0-9]', '', raw_str).upper()

            # 対象枠の判定 (S4, NS4, N4, R4, RC4, FS4, L4, O4) + (A/B/C/D)
            match = re.search(r'(S4|NS4|N4|R4|RC4|FS4|L4|O4)([ABCD]?)', clean_str)
            if not match:
                continue

            cls_name = match.group(1)
            grp_name = match.group(2)
            formatted_title = f"{cls_name[:-1]}-{cls_name[-1]}"
            if grp_name:
                formatted_title += f" {grp_name}"

            # 枠の左端X座標（文字の開始位置）
            start_x = cluster[0]['x0']

            # 【重要】枠の中での文字の余白オフセット補正
            # FSWの表では、枠線の左端から文字開始位置まで約 4〜5pt ほど内側に描画される
            # そのため文字の左端から少し引いた位置を真の枠開始線とする
            adjusted_x = start_x - 4.5

            # 7:00からの経過時間を分換算
            total_minutes = 7 * 60 + ((adjusted_x - x_7) / points_per_hour) * 60.0

            # 富士の走行枠は 10分刻み（:00, :10, :20, :30, :40, :50）が基本
            # 最も近い 10分刻み（または例外的な5分刻み）に丸める
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
                    "description": f"富士スピードウェイ レーシングコース スポーツ走行枠\n枠名: {formatted_title}"
                })
            except ValueError:
                continue

    # 重複排除
    unique_events = []
    seen = set()
    for ev in sorted(page_events, key=lambda x: x['start']):
        key = (ev['start'], ev['summary'])
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    print(f"  -> {year}年{month}月のページから {len(unique_events)} 件の走行枠を抽出")
    # 11/2の抽出結果をログに出して検証
    if month == 11:
        nov2_events = [e for e in unique_events if e['start'].day == 2]
        print(f"     [11/2 検証] 抽出件数: {len(nov2_events)} 件")
        for e in nov2_events:
            print(f"       - {e['start'].strftime('%H:%M')} {e['summary']}")

    return unique_events

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
