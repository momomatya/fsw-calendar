<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FSW 会員走行カレンダー</title>
  <script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.15/index.global.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .fc-event {
      cursor: pointer;
      font-size: 0.75rem;
      border: none !important;
      border-radius: 4px;
      padding: 1px 3px;
      margin-bottom: 2px;
    }
    .fc-event-title {
      font-weight: 600;
    }
  </style>
</head>
<body class="bg-slate-50 text-slate-800">

  <div class="max-w-6xl mx-auto p-3 sm:p-6">
    <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div>
        <h1 class="text-xl sm:text-2xl font-bold flex items-center gap-2">
          🏁 FSW 会員走行枠
        </h1>
        <p class="text-xs text-slate-500 mt-1">富士スピードウェイ レーシングコース（RC）</p>
      </div>

      <div class="flex items-center gap-2">
        <a href="fsw_calendar.ics" download class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg shadow-sm transition">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
          iCal連携
        </a>
      </div>
    </div>

    <!-- フィルターボタン -->
    <div class="flex flex-wrap gap-1.5 mb-4 text-xs font-semibold" id="filter-container">
      <button onclick="filterCategory('ALL')" id="btn-ALL" class="px-3 py-1 rounded-full bg-slate-900 text-white shadow">すべて</button>
      <button onclick="filterCategory('NS-4')" id="btn-NS-4" class="px-3 py-1 rounded-full bg-cyan-100 text-cyan-800 border border-cyan-300">NS-4</button>
      <button onclick="filterCategory('S-4')" id="btn-S-4" class="px-3 py-1 rounded-full bg-red-100 text-red-800 border border-red-300">S-4</button>
      <button onclick="filterCategory('N-4')" id="btn-N-4" class="px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">N-4</button>
      <button onclick="filterCategory('R-4')" id="btn-R-4" class="px-3 py-1 rounded-full bg-amber-100 text-amber-800 border border-amber-300">R-4</button>
    </div>

    <!-- カレンダー本体 -->
    <div class="bg-white p-3 sm:p-5 rounded-2xl shadow-sm border border-slate-200">
      <div id="calendar"></div>
    </div>
  </div>

  <script>
    let calendar;
    let allEvents = [];
    let currentFilter = 'ALL';

    function getEventColor(title) {
      if (title.includes('S-4')) return '#ef4444';
      if (title.includes('NS-4')) return '#06b6d4';
      if (title.includes('N-4')) return '#10b981';
      if (title.includes('R-4')) return '#f59e0b';
      return '#64748b';
    }

    document.addEventListener('DOMContentLoaded', async function() {
      const calendarEl = document.getElementById('calendar');

      try {
        const res = await fetch('events.json?v=' + Date.now());
        allEvents = await res.json();
      } catch (e) {
        console.error('イベント取得エラー:', e);
      }

      calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'ja',
        headerToolbar: {
          left: 'prev,next today',
          center: 'title',
          right: 'dayGridMonth,timeGridWeek,listMonth'
        },
        buttonText: {
          today: '今日',
          month: '月カレンダー',
          week: '週',
          list: 'リスト一覧'
        },
        // 00分でも省略させず、常に "8:00" 形式で表示
        eventTimeFormat: {
          hour: 'numeric',
          minute: '2-digit',
          omitZeroMinute: false,
          meridiem: false,
          hour12: false
        },
        events: getFilteredEvents(),
        eventDidMount: function(info) {
          info.el.style.backgroundColor = getEventColor(info.event.title);
        }
      });

      calendar.render();
    });

    function getFilteredEvents() {
      if (currentFilter === 'ALL') return allEvents;
      return allEvents.filter(ev => ev.title.includes(currentFilter));
    }

    function filterCategory(cat) {
      currentFilter = cat;
      document.querySelectorAll('#filter-container button').forEach(b => {
        b.className = "px-3 py-1 rounded-full bg-white text-slate-700 border border-slate-300";
      });
      const activeBtn = document.getElementById('btn-' + cat);
      if (activeBtn) {
        activeBtn.className = "px-3 py-1 rounded-full bg-slate-900 text-white shadow";
      }
      calendar.removeAllEvents();
      calendar.addEventSource(getFilteredEvents());
    }
  </script>
</body>
</html>
