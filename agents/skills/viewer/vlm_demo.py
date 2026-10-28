#!/usr/bin/env python3
"""VLM camera demo page (served by server.py at /vlm).

The page is kept in a Python module so `agents/` stays schema + workers
(no loose HTML files). It talks to the server's /api/vlm proxy.
"""

DEFAULT_PROMPT = """Analyze this Hokusai manga illustration for LoRA training. Return ONLY a JSON object:
{
  "subject": "brief description of what is depicted",
  "category": "landscape|figure|yokai|daily_life|nature|calligraphy|action|narrative|animals",
  "style_notes": "linework quality, composition, period indicators",
  "lora_quality": {"linework": 1-10, "contrast": 1-10, "composition": 1-10, "artifact_free": 1-10},
  "training_suitability": 1-10,
  "notes": "any issues for training (artifacts, blur, text boxes, busy composition)"
}"""

PAGE_HTML = r"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hokusai VLM Camera Demo</title>
<style>
  :root {
    --bg:#f0f2f5; --panel:#fff; --text:#243044; --muted:#7b8794; --line:#e3e7ee;
    --brand:#3949ab; --brand2:#1a237e; --ok:#2e7d32; --warn:#f57f17; --err:#c62828;
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif; }
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
  main { max-width:1280px; margin:0 auto; padding:18px; display:grid; gap:16px;
         grid-template-columns: minmax(320px, 1fr) minmax(320px, 1fr); }
  .result { grid-column: 1 / -1; }
  @media (max-width: 860px) { main { grid-template-columns: 1fr; } }
  .panel { background:var(--panel); border-radius:14px; padding:16px; box-shadow:0 1px 6px rgba(0,0,0,.08); min-width:0; }
  .panel h2 { font-size:13px; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); margin:0 0 10px; }
  .videoWrap { position:relative; background:#0d1117; border-radius:12px; overflow:hidden;
               aspect-ratio:4/3; display:flex; align-items:center; justify-content:center; }
  video, #preview { width:100%; height:100%; object-fit:contain; display:block; }
  #preview { position:absolute; inset:0; z-index:2; background:#0d1117; }
  video[hidden], #preview[hidden] { display:none; }
  #placeholder { color:#8b949e; font-size:13px; text-align:center; padding:20px; }
  .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:10px; }
  .spacer { flex:1; }
  button, select, textarea, input[type=file] { font:inherit; }
  button { padding:8px 14px; border:1px solid var(--brand); background:#fff; color:var(--brand);
           border-radius:9px; cursor:pointer; font-weight:600; font-size:12px; }
  button:hover:not(:disabled) { background:var(--brand); color:#fff; }
  button:disabled { opacity:.45; cursor:not-allowed; }
  button.primary { background:var(--brand); color:#fff; }
  button.primary:hover:not(:disabled) { background:var(--brand2); border-color:var(--brand2); }
  select { padding:7px 10px; border:1px solid var(--line); border-radius:8px; background:#fafbfc; }
  textarea { width:100%; padding:10px 12px; border:1px solid var(--line); border-radius:10px;
             resize:vertical; font-family:ui-monospace, "Cascadia Code", Consolas, monospace; font-size:12px; line-height:1.5; }
  .file { display:inline-flex; align-items:center; gap:6px; padding:7px 12px; border:1px dashed var(--line);
          border-radius:9px; cursor:pointer; font-size:12px; color:var(--brand); font-weight:600; }
  .file input { display:none; }
  .muted { color:var(--muted); font-size:11px; }
  pre#textView { margin:0; min-height:220px; max-height:520px; overflow:auto; background:#0f172a; color:#e2e8f0;
                 border-radius:12px; padding:14px; font:12px/1.55 ui-monospace, "Cascadia Code", Consolas, monospace;
                 white-space:pre-wrap; word-break:break-word; }
  .error { margin-top:10px; padding:10px 12px; border-radius:10px; background:#fdecea; color:var(--err);
           border:1px solid #f5c6c0; font-size:12px; white-space:pre-wrap; }
  .error[hidden] { display:none; }
  details { margin-top:10px; font-size:12px; color:var(--muted); }
  summary { cursor:pointer; }
  .hint { font-size:12px; color:var(--muted); margin-top:6px; }
</style>
</head>
<body>
<header>
  <div style="flex:1">
    <a href="/">← Dashboard</a>
    <h1>📷 VLM Camera Demo</h1>
    <p>カメラで撮影（または画像を選択）→ VLM に送信 → テキストで確認</p>
  </div>
  <span id="health" class="badge">VLM 状態を確認中…</span>
</header>

<main>
  <section class="panel">
    <h2>Camera</h2>
    <div class="videoWrap">
      <video id="video" autoplay playsinline muted hidden></video>
      <img id="preview" alt="captured preview" hidden>
      <div id="placeholder">カメラを開始するか、画像を選択してください</div>
    </div>
    <div class="row">
      <button id="startBtn" class="primary">▶ カメラ開始</button>
      <button id="stopBtn" disabled>■ 停止</button>
      <button id="captureBtn" class="primary" disabled>📸 撮影</button>
      <select id="camSelect" title="カメラを選択">
        <option value="">既定のカメラ</option>
      </select>
    </div>
    <div class="row">
      <label class="file">🖼 画像を選択<input type="file" id="fileInput" accept="image/*"></label>
      <span id="imgInfo" class="muted"></span>
      <span class="spacer"></span>
      <button id="resetBtn" disabled>やり直す</button>
    </div>
    <details>
      <summary>カメラが使えない場合</summary>
      <p>ブラウザのカメラ許可が必要です。ページは <code>localhost</code> または HTTPS で開いてください。
      カメラが無い環境では「画像を選択」からアップロードできます。</p>
    </details>
  </section>

  <section class="panel">
    <h2>Prompt</h2>
    <div class="row">
      <select id="preset">
        <option value="lora">LoRA review (JSON)</option>
        <option value="describe">Describe (日本語)</option>
        <option value="ocr">OCR / text</option>
        <option value="custom">Custom</option>
      </select>
      <span class="muted">画像は 1024px に縮小して送信</span>
    </div>
    <textarea id="prompt" rows="9"></textarea>
    <div class="row">
      <button id="analyzeBtn" class="primary" disabled>🤖 VLMで解析</button>
      <button id="clearBtn">クリア</button>
      <span id="elapsed" class="muted"></span>
    </div>
    <p class="hint">解析はサーバー経由で LM Studio / OpenAI 互換 API に送られます。</p>
  </section>

  <section class="panel result">
    <div class="row" style="margin-top:0">
      <h2 style="margin:0">Text output</h2>
      <span class="spacer"></span>
      <button id="prettyBtn">JSON整形</button>
      <button id="copyBtn">コピー</button>
      <button id="downloadBtn">.txt保存</button>
    </div>
    <pre id="textView">まだ結果がありません。</pre>
    <div id="error" class="error" hidden></div>
  </section>
</main>

<script>
const $ = id => document.getElementById(id);
const video = $('video'), preview = $('preview'), placeholder = $('placeholder');
const startBtn = $('startBtn'), stopBtn = $('stopBtn'), captureBtn = $('captureBtn');
const camSelect = $('camSelect'), fileInput = $('fileInput'), resetBtn = $('resetBtn');
const imgInfo = $('imgInfo'), preset = $('preset'), promptEl = $('prompt');
const analyzeBtn = $('analyzeBtn'), clearBtn = $('clearBtn'), elapsed = $('elapsed');
const textView = $('textView'), errorBox = $('error'), healthEl = $('health');
const prettyBtn = $('prettyBtn'), copyBtn = $('copyBtn'), downloadBtn = $('downloadBtn');

const PROMPTS = {
  lora: `__DEFAULT_PROMPT__`,
  describe: `この画像に描かれている内容を、日本語で具体的に説明してください。
人物・動物・風景・文字・構図など、見える要素を整理して出力してください。`,
  ocr: `画像内の文字を読み取り、そのままテキストで出力してください。
読み取れない文字は「?」としてください。`,
  custom: ''
};

let stream = null;
let imageData = '';
let rawText = '';
let pretty = false;
let vlmModel = '';
const canvas = document.createElement('canvas');
const ctx = canvas.getContext('2d');

function setError(message) {
  if (!message) { errorBox.hidden = true; errorBox.textContent = ''; return; }
  errorBox.hidden = false;
  errorBox.textContent = message;
}

function setImage(dataUrl, label) {
  imageData = dataUrl;
  preview.src = dataUrl;
  preview.hidden = false;
  placeholder.hidden = true;
  analyzeBtn.disabled = false;
  resetBtn.disabled = false;
  imgInfo.textContent = label || '';
  setError('');
}

function resetImage() {
  imageData = '';
  preview.removeAttribute('src');
  preview.hidden = true;
  placeholder.hidden = !!stream;
  analyzeBtn.disabled = true;
  resetBtn.disabled = true;
  imgInfo.textContent = '';
  textView.textContent = 'まだ結果がありません。';
  rawText = '';
  elapsed.textContent = '';
  setError('');
}

async function refreshDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) return;
  const devices = await navigator.mediaDevices.enumerateDevices();
  const cams = devices.filter(d => d.kind === 'videoinput');
  const current = camSelect.value;
  camSelect.replaceChildren(new Option('既定のカメラ', ''));
  cams.forEach((d, i) => camSelect.appendChild(new Option(d.label || ('カメラ ' + (i + 1)), d.deviceId)));
  if (current) camSelect.value = current;
}

async function startCamera(deviceId) {
  stopCamera();
  imageData = '';
  preview.hidden = true;
  analyzeBtn.disabled = true;
  resetBtn.disabled = true;
  imgInfo.textContent = '';
  placeholder.hidden = false;
  setError('');
  try {
    const videoConstraints = deviceId
      ? { deviceId: { exact: deviceId } }
      : { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } };
    stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: videoConstraints });
    video.srcObject = stream;
    video.hidden = false;
    await video.play();
    placeholder.hidden = true;
    startBtn.disabled = true;
    stopBtn.disabled = false;
    captureBtn.disabled = false;
    await refreshDevices();
    if (deviceId) camSelect.value = deviceId;
  } catch (err) {
    stopCamera();
    setError('カメラを開始できません: ' + (err.message || err));
  }
}

function stopCamera() {
  if (stream) stream.getTracks().forEach(t => t.stop());
  stream = null;
  video.srcObject = null;
  video.hidden = true;
  startBtn.disabled = false;
  stopBtn.disabled = true;
  captureBtn.disabled = true;
  if (!imageData) placeholder.hidden = false;
}

function capture() {
  const vw = video.videoWidth, vh = video.videoHeight;
  if (!vw || !vh) { setError('カメラ映像の準備ができていません。少し待ってから撮影してください。'); return; }
  const max = 1024;
  const scale = Math.min(1, max / Math.max(vw, vh));
  canvas.width = Math.round(vw * scale);
  canvas.height = Math.round(vh * scale);
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  setImage(canvas.toDataURL('image/jpeg', 0.9), `撮影: ${canvas.width}×${canvas.height}px`);
}

function renderText() {
  if (!rawText) { textView.textContent = 'まだ結果がありません。'; return; }
  if (pretty) {
    try { textView.textContent = JSON.stringify(JSON.parse(rawText), null, 2); return; }
    catch (_) { pretty = false; prettyBtn.textContent = 'JSON整形'; }
  }
  textView.textContent = rawText;
}

async function analyze() {
  if (!imageData) return;
  setError('');
  elapsed.textContent = '';
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = '解析中…';
  textView.textContent = 'VLM が考えています…';
  const started = performance.now();
  try {
    const res = await fetch('/api/vlm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: imageData, prompt: promptEl.value, model: vlmModel || undefined })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ('HTTP ' + res.status));
    rawText = data.text || '(empty response)';
    pretty = false;
    prettyBtn.textContent = 'JSON整形';
    renderText();
    elapsed.textContent = ((performance.now() - started) / 1000).toFixed(1) + 's · ' + (data.model || '');
    checkHealth();
  } catch (err) {
    setError('解析に失敗しました: ' + (err.message || err));
    textView.textContent = '';
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = '🤖 VLMで解析';
  }
}

async function checkHealth() {
  try {
    const res = await fetch('/api/vlm/health', { cache: 'no-store' });
    const data = await res.json();
    if (data.vlm) {
      vlmModel = data.model || '';
      healthEl.className = 'badge ok';
      healthEl.textContent = 'VLM 接続OK' + (data.model ? ' · ' + data.model : '');
      healthEl.title = data.base_url || '';
    } else {
      vlmModel = '';
      healthEl.className = 'badge warn';
      healthEl.textContent = 'サーバーOK / VLM未接続';
      healthEl.title = data.error || data.base_url || '';
    }
  } catch (err) {
    vlmModel = '';
    healthEl.className = 'badge bad';
    healthEl.textContent = 'サーバー未接続';
    healthEl.title = String(err);
  }
}

startBtn.onclick = () => startCamera(camSelect.value || undefined);
stopBtn.onclick = stopCamera;
captureBtn.onclick = capture;
resetBtn.onclick = resetImage;
camSelect.onchange = () => { if (stream) startCamera(camSelect.value); };
analyzeBtn.onclick = analyze;
clearBtn.onclick = () => {
  textView.textContent = 'まだ結果がありません。';
  rawText = '';
  elapsed.textContent = '';
  setError('');
};
prettyBtn.onclick = () => {
  pretty = !pretty;
  prettyBtn.textContent = pretty ? '生テキスト' : 'JSON整形';
  renderText();
};
downloadBtn.onclick = () => {
  if (!rawText) return;
  const blob = new Blob([textView.textContent], { type: 'text/plain;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'vlm-result.txt';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
copyBtn.onclick = async () => {
  try {
    await navigator.clipboard.writeText(textView.textContent);
    copyBtn.textContent = 'コピー済み';
    setTimeout(() => { copyBtn.textContent = 'コピー'; }, 1200);
  } catch (_) { setError('クリップボードにコピーできませんでした'); }
};
fileInput.onchange = () => {
  const file = fileInput.files && fileInput.files[0];
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) { setError('画像が大きすぎます（20MBまで）'); return; }
  const reader = new FileReader();
  reader.onload = () => setImage(String(reader.result), `${file.name} (${Math.round(file.size / 1024)}KB)`);
  reader.onerror = () => setError('画像を読み込めませんでした');
  reader.readAsDataURL(file);
};
document.addEventListener('keydown', e => {
  if (e.code === 'Space' && document.activeElement?.tagName !== 'TEXTAREA' && document.activeElement?.tagName !== 'INPUT') {
    e.preventDefault();
    if (!captureBtn.disabled) capture();
  }
});

promptEl.value = PROMPTS.lora;
preset.onchange = () => {
  promptEl.value = PROMPTS[preset.value] || '';
};
resetImage();
checkHealth();
setInterval(checkHealth, 15000);
</script>
</body>
</html>
"""

PAGE_HTML = PAGE_HTML.replace("__DEFAULT_PROMPT__", DEFAULT_PROMPT)
