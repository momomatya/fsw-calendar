import os
import re
import urllib.parse
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import pdfplumber
from icalendar import Calendar, Event

# ================= 設定 =================
# FSW公式サイトのスケジュール掲載ページ（走行カレンダー）
CALENDAR_PAGE_URL = "https://www.fsw.tv/driving/calendar/"

# 抽出対象とする主要クラス
TARGET_PATTERN = re.compile(r'^(NS-4|S-4|N-4|R-4|RC-4|FS-4|L-4|O-4)')
DEFAULT_DURATION_MINUTES = 30
# ========================================

def download_latest_fsw_pdf():
    """FSW公式サイトから最新のスポーツ走行PDFのURLを探してダウンロードする"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    print(f"カレンダー掲載ページを取得中: {CALENDAR_PAGE_URL}")
    res = requests.get(CALENDAR_PAGE_URL, headers=headers)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    
    # ページ内のPDFリンクを探す
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower():
            full_url = urllib.parse.urljoin(CALENDAR_PAGE_URL, href)
            # レーシングコース、スポーツ走行、カレンダー等の関連キーワードで判定
            link_text = a.get_text()
            if any(k in href or k in link_text for k in ["sports", "calendar", "racing", "走行"]):
                pdf_links.append(full_url)

    if not pdf_links:
        # 見つからない場合はPDFリンクの先頭を取得
        all_pdfs = [urllib.parse.urljoin(CALENDAR_PAGE_URL, a["href"]) for a in soup.find_all("a", href=True) if ".pdf" in a["href"].lower()]
        if not all_pdfs:
            raise Exception("ページ内から走行カレンダーのPDFリンクが見つかりませんでした。")
        target_url = all_pdfs[0]
    else:
        target_url = pdf_links[0]

    print(f"対象PDFのURL: {target_url}")
    pdf_res = requests.get(target_url, headers=headers)
    pdf_res.raise_for_status()

    local_pdf = "latest_calendar.pdf"
    with open(local_pdf, "wb") as f:
        f.write(pdf_res.content)
    
    print(f"PDFのダウンロード完了: {local_pdf}")
    return local_pdf

def parse_fsw_pdf(pdf_path):
    events = []
    with pdfplumber.open(pdf_path) as pdf:
        target_page = None
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "レーシングコース" in text and "スポーツ走行予定表" in text:
                target_page = page
                break
        
        if not target_page:
            target_page = pdf.pages[6] if len(pdf.pages) >= 7 else pdf.pages[-1]

        page_text = target_page.extract_text() or ""
        year_match = re.search(r'(\d{4})年\s*(\d{1,2})月', page_text)
        if year_match:
            year = int(year_match.group(1))
            month = int(year_match.group(2))
        else:
            now = datetime.now()
            year, month = now.year, now.month

        words = target_page.extract_words()

        time_headers = {}
        for h in range(7, 19):
            matches = [w for w in words if w['text'] == f"{h}:00" and w['x0'] > 180]
            if matches:
                time_headers[h] = min(matches, key=lambda x: x['top'])['x0']

        x_7 = time_headers.get(7, 201.1)
        x_18 = time_headers.get(18, 540.2)
        points_per_hour = (x_18 - x_7) / 11.0

        day_rows = []
        for d in range(1, 32):
            d_words = [w for w in words if w['text'] == str(d) and w['x0'] < 60 and w['top'] > 100]
            if d_words:
                day_rows.append((d, d_words[0]['top']))

        for day, y_top in day_rows:
            row_words = [w for w in words if abs(w['top'] - y_top) < 6 and w['x0'] >= (x_7 - 5)]
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
                    if gap < 5.0:
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
                    events.append({
                        "summary": f"FSW {text}",
                        "start": start_dt,
                        "end": end_dt,
                        "description": f"富士スピードウェイ レーシングコース スポーツ走行枠\n枠名: {text}"
                    })
                except ValueError:
                    continue

    return events

def create_ical(events, output_filename="fsw_calendar.ics"):
    cal = Calendar()
    cal.add('prodid', '-//FSW Member Track Calendar//JP')
    cal.add('version', '2.0')

    for ev in events:
        event = Event()
        event.add('summary', ev['summary'])
        event.add('dtstart', ev['start'])
        event.add('dtend', ev['end'])
        event.add('description', ev['description'])
        event.add('location', '富士スピードウェイ')
        cal.add_component(event)

    with open(output_filename, 'wb') as f:
        f.write(cal.to_ical())
    print(f"\n[成功] カレンダー生成完了: {output_filename} (合計 {len(events)} 件)")

if __name__ == '__main__':
    try:
        pdf_file = download_latest_fsw_pdf()
    except Exception as e:
        print(f"Webからの取得に失敗したため、ローカルのPDFを探します: {e}")
        import glob
        local_pdfs = glob.glob("*.pdf")
        if not local_pdfs:
            raise e
        pdf_file = local_pdfs[0]

    events = parse_fsw_pdf(pdf_file)
    create_ical(events, output_filename="fsw_calendar.ics")
