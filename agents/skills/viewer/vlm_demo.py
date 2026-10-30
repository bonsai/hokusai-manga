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
        <option value="age">Age estimation (年齢推定)</option>
        <option value="simple">Simple: 年齢・動作・場所 (日本語)</option>
        <option value="simple_en">Simple: Age/Action/Location (English)</option>
        <option value="dance">💃 Dance detection (踊り判定)</option>
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
      <button id="translateBtn">🇯🇵 日本語化</button>
      <button id="speakBtn">🔊 読み上げ</button>
      <button id="stopSpeakBtn" disabled>⏹ 停止</button>
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
const prettyBtn = $('prettyBtn'), translateBtn = $('translateBtn'), speakBtn = $('speakBtn'), stopSpeakBtn = $('stopSpeakBtn'), copyBtn = $('copyBtn'), downloadBtn = $('downloadBtn');

const PROMPTS = {
  lora: `__DEFAULT_PROMPT__`,
  describe: `この画像に描かれている内容を、日本語で具体的に説明してください。
人物・動物・風景・文字・構図など、見える要素を整理して出力してください。`,
  ocr: `画像内の文字を読み取り、そのままテキストで出力してください。
読み取れない文字は「?」としてください。`,
  age: `この画像に写っている人物の年齢を推定してください。
出力形式は以下の JSON のみで返してください：
{
  "age_estimate": "推定年齢（例: 25歳前後、10代後半〜20代前半など）",
  "confidence": "高/中/低",
  "reasoning": "判断根拠（顔の特徴、肌の質感、髪型、服装、背景など）"
}
人物が複数いる場合は、最も目立つ人物（中央にいる、大きく写っている等）を対象としてください。
人物が写っていない場合は age_estimate を "人物なし" としてください。`,
  simple: `この画像に写っている人物について、以下の3点のみ JSON で答えてください（出力は日本語のみ）：
{
  "age": "推定年齢（例: 25歳前後）",
  "action": "何をしているか（例: 手を振っている、本を読んでいる）",
  "location": "どこにいるか（例: 屋内の部屋、公園、駅のホーム）"
}
人物がいない場合は age を "人物なし"、action と location を "" としてください。
キー名（age/action/location）はそのまま、値だけ日本語にしてください。`,
  simple_en: `Answer ONLY a JSON object with these 3 fields about the person in the image:
{
  "age": "estimated age (e.g., around 25 years old)",
  "action": "what they are doing (e.g., waving hand, reading a book)",
  "location": "where they are (e.g., indoor room, park, train platform)"
}
If no person, set age to "No person" and action/location to "".`,
  dance: `この画像に踊り・舞踊のシーンが含まれているか判定してください。
出力は以下の JSON のみ：
{
  "is_dance": true/false,
  "dance_type": "日本舞踊/民謡/盆踊り/神楽/能楽/その他/該当なし",
  "confidence": "高/中/低",
  "description": "何が描かれているか簡潔に（例: 扇子を持って舞う女性、太鼓に合わせて踊る群衆）"
}
踊りでない場合は is_dance: false, dance_type: "該当なし" としてください。`,
  custom: ''
};

let stream = null;
let imageData = '';
let rawText = '';
let pretty = false;
let translated = false;
let vlmModel = '';
const canvas = document.createElement('canvas');
const ctx = canvas.getContext('2d');

function setError(message) {
  if (!message) { errorBox.hidden = true; errorBox.textContent = ''; return; }
  errorBox.hidden = false;
  errorBox.textContent = message;
}

function getJapaneseText(text) {
  if (!text) return '';
  
  // Simple English to Japanese translation for common VLM responses
  const translations = [
    [/^A person is waving their hand in an indoor setting\./, '人が屋内で手を振っています。'],
    [/^A person is ([^.]+)\./, '人が$1しています。'],
    [/^There is a person ([^.]+)\./, '人が$1います。'],
    [/^The image shows ([^.]+)\./, '画像には$1が写っています。'],
    [/^This image depicts ([^.]+)\./, 'この画像は$1を描いています。'],
    [/^An? ([^.]+) is ([^.]+)\./, '$1が$2しています。'],
    [/^An? ([^.]+) in ([^.]+)\./, '$2の中に$1があります。'],
    [/indoor setting/, '屋内'],
    [/outdoor setting/, '屋外'],
    [/waving (?:their |his |her )?hand/, '手を振る'],
    [/standing/, '立っている'],
    [/sitting/, '座っている'],
    [/walking/, '歩いている'],
    [/running/, '走っている'],
    [/smiling/, '笑っている'],
    [/looking at (?:the |)(?:camera|lens)/, 'カメラを見ている'],
    [/holding ([^.]+)/, '$1を持っている'],
    [/wearing ([^.]+)/, '$1を着ている'],
    [/in (?:an? |the )?([^.]+) (?:room|setting|area)/, '$1な部屋で'],
    [/with ([^.]+)/, '$1とともに'],
    [/person/gi, '人'],
    [/man/gi, '男性'],
    [/woman/gi, '女性'],
    [/child/gi, '子供'],
    [/boy/gi, '男の子'],
    [/girl/gi, '女の子'],
    [/hand/gi, '手'],
    [/face/gi, '顔'],
  ];
  
  let result = text;
  for (const [pattern, replacement] of translations) {
    result = result.replace(pattern, replacement);
  }
  
  // If no translation applied, return original with a note
  if (result === text && /^[A-Z]/.test(text.trim())) {
    return text + ' （日本語訳未対応）';
  }
  return result;
}

function renderText() {
  if (!rawText) { textView.textContent = 'まだ結果がありません。'; return; }
  if (pretty) {
    try { textView.textContent = JSON.stringify(JSON.parse(rawText), null, 2); return; }
    catch (_) { pretty = false; prettyBtn.textContent = 'JSON整形'; }
  }
  textView.textContent = translated ? getJapaneseText(rawText) : rawText;
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

// Play notification sounds using Web Audio API
let analysisSoundInterval = null;
let analysisAudioCtx = null;

function startAnalysisSound() {
  // Play initial notification
  playTone([660, 880], 0.15, 0.1);
  
  // Start looping thinking sound every 2 seconds
  analysisAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  analysisSoundInterval = setInterval(() => {
    playThinkingPulse(analysisAudioCtx);
  }, 2000);
}

function stopAnalysisSound() {
  if (analysisSoundInterval) {
    clearInterval(analysisSoundInterval);
    analysisSoundInterval = null;
  }
  if (analysisAudioCtx) {
    analysisAudioCtx.close().catch(() => {});
    analysisAudioCtx = null;
  }
}

function playThinkingPulse(ctx) {
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    // Soft pulsing tone
    osc.frequency.setValueAtTime(440, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(550, ctx.currentTime + 0.3);
    osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.6);
    gain.gain.setValueAtTime(0, ctx.currentTime);
    gain.gain.linearRampToValueAtTime(0.05, ctx.currentTime + 0.05);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.6);
  } catch (_) {}
}

function playDoneSound() {
  // Elaborate success fanfare: ascending arpeggio + chord
  playFanfare([
    { freq: 523.25, delay: 0.00, dur: 0.3 },   // C5
    { freq: 659.25, delay: 0.10, dur: 0.3 },   // E5
    { freq: 783.99, delay: 0.20, dur: 0.3 },   // G5
    { freq: 1046.5, delay: 0.30, dur: 0.5 },   // C6
    { freq: 1318.5, delay: 0.40, dur: 0.6 },   // E6
    { freq: 1568.0, delay: 0.50, dur: 0.8 },   // G6
  ]);
  // Final major chord
  setTimeout(() => playChord([1046.5, 1318.5, 1568.0, 2093.0], 1.0), 600);
}

function playErrorSound() {
  // Descending minor chord for error
  playFanfare([
    { freq: 440, delay: 0.00, dur: 0.4 },     // A4
    { freq: 370, delay: 0.15, dur: 0.4 },     // F#4
    { freq: 311, delay: 0.30, dur: 0.6 },     // D#4
  ]);
  setTimeout(() => playChord([311, 370, 440], 1.0), 500);
}

function playFanfare(notes) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    notes.forEach(note => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(note.freq, ctx.currentTime + note.delay);
      gain.gain.setValueAtTime(0, ctx.currentTime + note.delay);
      gain.gain.linearRampToValueAtTime(0.08, ctx.currentTime + note.delay + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + note.delay + note.dur);
      osc.start(ctx.currentTime + note.delay);
      osc.stop(ctx.currentTime + note.delay + note.dur);
    });
  } catch (_) {}
}

function playChord(freqs, duration) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    freqs.forEach(freq => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, ctx.currentTime);
      gain.gain.setValueAtTime(0, ctx.currentTime);
      gain.gain.linearRampToValueAtTime(0.06, ctx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + duration);
    });
  } catch (_) {}
}

function playTone(freqs, dur, gap) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    freqs.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sine';
      const t = ctx.currentTime + i * gap;
      osc.frequency.setValueAtTime(freq, t);
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(0.1, t + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
      osc.start(t);
      osc.stop(t + dur);
    });
  } catch (_) {}
}

async function analyze() {
  if (!imageData) return;
  setError('');
  elapsed.textContent = '';
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = '解析中…';
  textView.textContent = 'VLM が考えています…';
  startAnalysisSound();
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
    stopAnalysisSound();
    playDoneSound();
    checkHealth();
  } catch (err) {
    setError('解析に失敗しました: ' + (err.message || err));
    textView.textContent = '';
    stopAnalysisSound();
    playErrorSound();
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

translateBtn.onclick = () => {
  translated = !translated;
  translateBtn.textContent = translated ? '🇬🇧 英語に戻す' : '🇯🇵 日本語化';
  renderText();
};

let speechUtterance = null;
speakBtn.onclick = () => {
  const text = translated ? getJapaneseText(rawText) : rawText;
  if (!text || text === 'まだ結果がありません。') return;
  speechUtterance = new SpeechSynthesisUtterance(text);
  speechUtterance.lang = 'ja-JP';
  speechUtterance.rate = 1.0;
  speechUtterance.pitch = 1.0;
  speechSynthesis.speak(speechUtterance);
  speakBtn.disabled = true;
  stopSpeakBtn.disabled = false;
  speechUtterance.onend = () => {
    speakBtn.disabled = false;
    stopSpeakBtn.disabled = true;
  };
};

stopSpeakBtn.onclick = () => {
  speechSynthesis.cancel();
  speakBtn.disabled = false;
  stopSpeakBtn.disabled = true;
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
