# JSONL Log Viewer
LOGS_PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hokusai VLM Logs</title>
<style>
  :root { --bg:#f0f2f5; --panel:#fff; --text:#243044; --muted:#7b8794; --line:#e3e7ee;
          --brand:#3949ab; --brand2:#1a237e; --ok:#2e7d32; --warn:#f57f17; --err:#c62828; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; }
  header { background:linear-gradient(135deg,var(--brand2),var(--brand)); color:#fff;
           padding:18px 22px; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  header h1 { margin:0; font-size:20px; }
  header p { margin:2px 0 0; font-size:12px; opacity:.85; }
  header a { color:#fff; text-decoration:none; opacity:.9; font-size:12px; }
  header a:hover { text-decoration:underline; }
  .badge { padding:5px 12px; border-radius:999px; font-size:11px; font-weight:700; background:rgba(255,255,255,.18); }
  .badge.ok { background:var(--ok); }
  .badge.warn { background:var(--warn); color:#3a2600; }
  .badge.bad { background:var(--err); }
  main { max-width:1280px; margin:0 auto; padding:18px; }
  .panel { background:var(--panel); border-radius:14px; padding:16px; box-shadow:0 1px 6px rgba(0,0,0,.08); }
  .bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:16px; }
  input, select, button { font:inherit; padding:7px 12px; border:1px solid var(--line); border-radius:8px; background:#fafbfc; }
  button { background:var(--brand); color:#fff; border-color:var(--brand); font-weight:600; cursor:pointer; }
  button:hover:not(:disabled) { background:var(--brand2); border-color:var(--brand2); }
  button:disabled { opacity:.45; cursor:not-allowed; }
  .log-list { list-style:none; padding:0; margin:0; }
  .log-item { border-bottom:1px solid var(--line); padding:14px 0; display:grid; gap:8px; }
  .log-item:last-child { border-bottom:none; }
  .log-header { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
  .log-image { font-family:ui-monospace,monospace; font-size:13px; color:var(--brand); font-weight:600; }
  .log-time { color:var(--muted); font-size:12px; }
  .log-badge { display:inline-flex; gap:6px; font-size:11px; padding:2px 8px; border-radius:6px; background:#eef1f5; }
  .log-badge.suit { background:#e8f5e9; color:#2e7d32; }
  .log-badge.cat { background:#e3f2fd; color:#1565c0; }
  .log-toggle { background:none; border:none; color:var(--brand); cursor:pointer; font-size:12px; padding:0; font-weight:600; }
  .log-toggle:hover { text-decoration:underline; }
  .log-detail { display:none; background:#0f172a; color:#e2e8f0; border-radius:10px; padding:12px; font:12px/1.55 ui-monospace,monospace; overflow:auto; max-height:400px; }
  .log-detail.open { display:block; }
  .log-raw { white-space:pre-wrap; word-break:break-word; }
  .log-img { max-width:200px; border-radius:8px; margin-top:8px; border:1px solid var(--line); }
  .muted { color:var(--muted); font-size:12px; }
  .empty { text-align:center; color:var(--muted); padding:40px; }
</style>
</head>
<body>
<header>
  <div style="flex:1">
    <a href="/">← Dashboard</a>
    <h1>📜 VLM Review Logs</h1>
    <p>JSONL レビュー履歴の閲覧・検索</p>
  </div>
  <span id="count" class="badge">読み込み中…</span>
</header>
<main>
  <div class="panel">
    <form class="bar" id="filterForm">
      <input type="search" id="q" placeholder="画像名 / subject / notes で検索" style="flex:1; min-width:200px;">
      <select id="category">
        <option value="">全カテゴリ</option>
      </select>
      <select id="minSuit">
        <option value="">適合度フィルタなし</option>
        <option value="8">8以上</option>
        <option value="6">6以上</option>
        <option value="4">4以上</option>
      </select>
      <button type="submit">絞り込み</button>
      <button type="button" id="clearBtn">クリア</button>
    </form>
    <ul id="logList" class="log-list"></ul>
    <div id="empty" class="empty" hidden>該当するログがありません</div>
    <div class="bar" style="margin-top:16px;">
      <span class="muted" id="showing">0 / 0 件</span>
      <button type="button" id="loadMore" hidden>もっと読み込む</button>
    </div>
  </div>
</main>
<script>
const $ = id => document.getElementById(id);
const logList = $('logList'), empty = $('empty'), showing = $('showing'), loadMoreBtn = $('loadMore');
const q = $('q'), category = $('category'), minSuit = $('minSuit'), countEl = $('count');

let allLogs = [];
let filteredLogs = [];
let displayedCount = 0;
const PAGE_SIZE = 50;

async function loadLogs() {
  try {
    const res = await fetch('/api/logs', { cache: 'no-store' });
    const data = await res.json();
    allLogs = data.items || [];
    populateCategories();
    applyFilter();
    countEl.textContent = allLogs.length + ' 件';
    countEl.className = 'badge ok';
  } catch (err) {
    countEl.textContent = '読み込み失敗';
    countEl.className = 'badge bad';
    console.error(err);
  }
}

function populateCategories() {
  const cats = [...new Set(allLogs.map(l => l.category).filter(Boolean))].sort();
  category.innerHTML = '<option value="">全カテゴリ</option>' +
    cats.map(c => `<option value="${c}">${c}</option>`).join('');
}

function applyFilter() {
  const query = q.value.toLowerCase().trim();
  const cat = category.value;
  const suit = parseInt(minSuit.value) || 0;

  filteredLogs = allLogs.filter(log => {
    if (query) {
      const haystack = (log.image + ' ' + (log.subject || '') + ' ' + (log.notes || '')).toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (cat && log.category !== cat) return false;
    if (suit && (log.suit || 0) < suit) return false;
    return true;
  });
  displayedCount = 0;
  renderLogs();
  loadMoreBtn.hidden = filteredLogs.length <= PAGE_SIZE;
}

function renderLogs(append = false) {
  if (!append) logList.innerHTML = '';
  const next = filteredLogs.slice(displayedCount, displayedCount + PAGE_SIZE);
  if (next.length === 0 && !append) {
    empty.hidden = false;
    logList.hidden = true;
  } else {
    empty.hidden = true;
    logList.hidden = false;
    for (const log of next) {
      logList.appendChild(createLogElement(log));
    }
    displayedCount += next.length;
  }
  showing.textContent = `${displayedCount} / ${filteredLogs.length} 件`;
  loadMoreBtn.hidden = displayedCount >= filteredLogs.length;
}

function createLogElement(log) {
  const li = document.createElement('li');
  li.className = 'log-item';

  const parsed = typeof log.response === 'string' ? JSON.parse(log.response) : log.response;
  const suit = parsed.training_suitability || parsed.suitability || log.suit || 0;
  const cat = parsed.category || log.category || '';

  li.innerHTML = `
    <div class="log-header">
      <span class="log-image">${log.image}</span>
      <span class="log-badge suit">適合度: ${suit}/10</span>
      ${cat ? `<span class="log-badge cat">${cat}</span>` : ''}
      <span class="log-time">${log.timestamp || ''}</span>
      <button class="log-toggle" onclick="toggleDetail(this)">詳細 ▼</button>
    </div>
    <div class="log-detail">
      <div class="log-raw">${escapeHtml(JSON.stringify(parsed, null, 2))}</div>
      <img class="log-img" src="/images/${log.image}" alt="${log.image}" loading="lazy" onerror="this.style.display='none'">
    </div>
  `;
  return li;
}

function toggleDetail(btn) {
  const detail = btn.closest('.log-item').querySelector('.log-detail');
  const isOpen = detail.classList.toggle('open');
  btn.textContent = isOpen ? '詳細 ▲' : '詳細 ▼';
}

function escapeHtml(text) {
  return text.replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>');
}

$('filterForm').addEventListener('submit', e => { e.preventDefault(); applyFilter(); });
$('clearBtn').onclick = () => { q.value = ''; category.value = ''; minSuit.value = ''; applyFilter(); };
loadMoreBtn.onclick = () => renderLogs(true);

loadLogs();
</script>
</body>
</html>
"""


@app.get("/logs", response_class=HTMLResponse)
@app.get("/logs/", response_class=HTMLResponse)
def logs_page() -> HTMLResponse:
    return HTMLResponse(LOGS_PAGE)


@app.get("/api/logs")
def api_logs() -> JSONResponse:
    if not JSONL_PATH.exists():
        return JSONResponse({"items": [], "total": 0})
    items = []
    with JSONL_PATH.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                # Parse response JSON string if needed
                parsed = {}
                if isinstance(record.get('response'), str):
                    try:
                        parsed = json.loads(record['response'])
                    except json.JSONDecodeError:
                        parsed = {}
                items.append({
                    "image": record.get('image', ''),
                    "response": record.get('response', ''),
                    "subject": parsed.get('subject', ''),
                    "category": parsed.get('category', ''),
                    "suit": parsed.get('training_suitability') or parsed.get('suitability', 0),
                    "notes": parsed.get('notes', ''),
                    "timestamp": record.get('timestamp', ''),
                })
            except json.JSONDecodeError:
                continue
    return JSONResponse({"items": items, "total": len(items)})