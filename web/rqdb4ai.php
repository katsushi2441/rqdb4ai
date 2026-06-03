<?php
require_once __DIR__ . '/config.php';

function h($s) {
    return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');
}

function rqdb_api($method, $path, $payload = null) {
    if (!defined('RQDB4AI_API_BASE') || trim(RQDB4AI_API_BASE) === '' || !defined('RQDB4AI_API_TOKEN') || trim(RQDB4AI_API_TOKEN) === '') {
        return array(
            'ok' => false,
            'error' => 'api_not_configured',
            'message' => 'RQDB4AI_API_BASE / RQDB4AI_API_TOKEN が未設定です。ジョブ実行サーバ側のAPI公開後、config.php を更新してください。',
        );
    }
    $base = rtrim(RQDB4AI_API_BASE, '/');
    $url = $base . '/' . ltrim($path, '/');
    $headers = array(
        'Authorization: Bearer ' . RQDB4AI_API_TOKEN,
        'Accept: application/json',
        'Content-Type: application/json',
        'User-Agent: KurageRQDashboard/0.1',
    );
    $body = $payload === null ? null : json_encode($payload);

    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
        curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 20);
        curl_setopt($ch, CURLOPT_HEADER, false);
        if ($body !== null) {
            curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
        }
        $raw = curl_exec($ch);
        $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $err = curl_error($ch);
        curl_close($ch);
        if ($raw === false) {
            return array('ok' => false, 'error' => $err ?: 'curl failed', 'http_code' => $code);
        }
    } else {
        $opts = array('http' => array(
            'method' => $method,
            'header' => implode("\r\n", $headers) . "\r\n",
            'timeout' => 20,
            'ignore_errors' => true,
        ));
        if ($body !== null) {
            $opts['http']['content'] = $body;
        }
        $raw = @file_get_contents($url, false, stream_context_create($opts));
        $code = 0;
        if (isset($http_response_header[0]) && preg_match('/\s(\d{3})\s/', $http_response_header[0], $m)) {
            $code = (int)$m[1];
        }
        if ($raw === false) {
            return array('ok' => false, 'error' => 'request failed', 'http_code' => $code);
        }
    }

    $json = json_decode($raw, true);
    if (!is_array($json)) {
        return array('ok' => false, 'error' => 'invalid_json', 'message' => 'API がJSON以外を返しました。API URL設定またはリバースプロキシを確認してください。', 'http_code' => isset($code) ? $code : 0, 'raw' => substr($raw, 0, 1000));
    }
    $json['_http_code'] = isset($code) ? $code : 0;
    return $json;
}

function rqdb_json_response($data, $code = 200) {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

if (isset($_GET['proxy'])) {
    $action = isset($_GET['action']) ? $_GET['action'] : 'summary';
    $method = $_SERVER['REQUEST_METHOD'];
    $raw = file_get_contents('php://input');
    $payload = $raw ? json_decode($raw, true) : null;

    if ($action === 'summary') {
        rqdb_json_response(rqdb_api('GET', '/api/summary'));
    }
    if ($action === 'queues') {
        rqdb_json_response(rqdb_api('GET', '/api/queues'));
    }
    if ($action === 'workers') {
        rqdb_json_response(rqdb_api('GET', '/api/workers'));
    }
    if ($action === 'jobs') {
        $qs = array();
        foreach (array('queue', 'status', 'limit', 'offset') as $key) {
            if (isset($_GET[$key]) && $_GET[$key] !== '') { $qs[$key] = $_GET[$key]; }
        }
        rqdb_json_response(rqdb_api('GET', '/api/jobs' . ($qs ? '?' . http_build_query($qs) : '')));
    }
    if ($action === 'job' && isset($_GET['id'])) {
        rqdb_json_response(rqdb_api('GET', '/api/jobs/' . rawurlencode($_GET['id'])));
    }
    if ($action === 'requeue' && isset($_GET['id'])) {
        rqdb_json_response(rqdb_api('POST', '/api/jobs/' . rawurlencode($_GET['id']) . '/requeue', $payload));
    }
    if ($action === 'cancel' && isset($_GET['id'])) {
        rqdb_json_response(rqdb_api('POST', '/api/jobs/' . rawurlencode($_GET['id']) . '/cancel', $payload));
    }
    if ($action === 'delete' && isset($_GET['id'])) {
        rqdb_json_response(rqdb_api('DELETE', '/api/jobs/' . rawurlencode($_GET['id']), $payload));
    }
    rqdb_json_response(array('ok' => false, 'error' => 'unknown action'), 400);
}
?>
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title><?php echo h(RQDB4AI_UI_TITLE); ?></title>
<style>
:root{--bg:#f6f7fb;--panel:#fff;--text:#162033;--muted:#64748b;--line:#e5e7eb;--accent:#2563eb;--ok:#059669;--warn:#d97706;--bad:#dc2626;--run:#7c3aed;--stop:#475569}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.55}.wrap{max-width:1180px;margin:0 auto;padding:18px}.top{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:14px}.brand h1{font-size:22px;margin:0}.brand p{margin:2px 0 0;color:var(--muted);font-size:13px}.btn{border:1px solid var(--line);background:#fff;border-radius:8px;padding:9px 12px;color:var(--text);font-weight:700;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px}.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}.btn.danger{color:var(--bad)}.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;box-shadow:0 1px 2px rgba(15,23,42,.04)}.metric{font-size:24px;font-weight:800}.label{font-size:12px;color:var(--muted)}.section{margin-top:14px}.queue-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.queue-name{font-weight:800;margin-bottom:8px}.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{border-radius:999px;background:#f1f5f9;color:#334155;padding:4px 8px;font-size:12px}.chip.bad{background:#fee2e2;color:#991b1b}.chip.run{background:#ede9fe;color:#5b21b6}.chip.resource{background:#dbeafe;color:#1e40af}.tabs{display:flex;gap:8px;overflow:auto;padding:2px 0 10px}.tab{white-space:nowrap}.tab.active{background:#111827;color:#fff}.jobs{display:grid;gap:10px}.job{display:grid;grid-template-columns:120px 1fr auto;gap:12px;align-items:center}.status{font-weight:800}.status.failed{color:var(--bad)}.status.started,.status.running{color:var(--run)}.status.finished,.status.complete{color:var(--ok)}.status.queued,.status.triggered,.status.warning{color:var(--warn)}.status.stopped,.status.canceled{color:var(--stop)}.mini{font-size:11px}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.muted{color:var(--muted)}.preview{font-size:13px;color:#334155;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.resource-line{margin-top:3px;font-size:12px;color:#1e40af;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.time-line{margin-top:3px;font-size:12px;color:#64748b;display:flex;gap:8px;flex-wrap:wrap}.actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.modal{position:fixed;inset:0;background:rgba(15,23,42,.45);display:none;align-items:flex-end;z-index:20}.modal.open{display:flex}.sheet{background:#fff;width:100%;max-height:88vh;overflow:auto;border-radius:16px 16px 0 0;padding:16px}.sheet-inner{max-width:1000px;margin:0 auto}.pre{background:#0f172a;color:#e5e7eb;border-radius:8px;padding:12px;white-space:pre-wrap;word-break:break-word;font-size:12px}.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:space-between;margin-bottom:10px}.select{border:1px solid var(--line);border-radius:8px;background:#fff;padding:9px 10px}.err{background:#fff1f2;border:1px solid #fecdd3;color:#9f1239;border-radius:8px;padding:10px;margin-bottom:10px;display:none}
@media(max-width:760px){.wrap{padding:12px}.top{align-items:flex-start}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.job{grid-template-columns:1fr}.actions{justify-content:flex-start}.brand h1{font-size:18px}.card{padding:12px}.sheet{max-height:92vh}.preview{white-space:normal}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="brand">
      <h1>Kurage RQ Dashboard for AI</h1>
      <p>RQ/Redis ジョブを日本語UIとAI APIで管理</p>
    </div>
    <button class="btn primary" onclick="reloadAll()">更新</button>
  </div>
  <div id="error" class="err"></div>
  <div class="grid">
    <div class="card"><div id="mWork" class="metric">-</div><div class="label">未完了ワーク</div></div>
    <div class="card"><div id="mQueues" class="metric">-</div><div class="label">RQ実行キュー</div></div>
    <div class="card"><div id="mWorkers" class="metric">-</div><div class="label">RQ Worker</div></div>
    <div class="card"><div id="mLive" class="metric">-</div><div class="label">RQ 待機/実行</div></div>
    <div class="card"><div id="mHistory" class="metric">-</div><div class="label">履歴 RQ完了/失敗</div></div>
  </div>

  <div class="section card">
    <div class="toolbar">
      <strong>未完了ワーク</strong><span class="muted">RQ実行中、または外部処理の完了確認が残っている仕事</span>
    </div>
    <div id="workItems" class="jobs"></div>
  </div>

  <div class="section card">
    <div class="toolbar">
      <strong>RQ実行キュー</strong><span class="muted">Redis/RQで現在処理対象になっているキュー。外部処理の完了状態ではありません</span>
    </div>
    <div id="queues" class="queue-grid"></div>
  </div>

  <div class="section card">
    <div class="toolbar">
      <strong>RQジョブ履歴キュー</strong><span class="muted">完了・失敗を含むRQ履歴の母集団</span>
    </div>
    <div id="historyQueues" class="queue-grid"></div>
  </div>

  <div class="section card">
    <div class="toolbar">
      <strong>ジョブ一覧</strong>
      <select id="queueFilter" class="select" onchange="loadJobs()"><option value="">全キュー</option></select>
    </div>
    <div class="tabs" id="tabs"></div>
    <div id="jobs" class="jobs"></div>
  </div>

  <div class="section card">
    <div class="toolbar"><strong>RQ Worker</strong><span class="muted">キューを監視してRQジョブを処理する常駐プロセス</span></div>
    <div id="workers" class="jobs"></div>
  </div>
</div>

<div id="modal" class="modal" onclick="closeModal(event)">
  <div class="sheet">
    <div class="sheet-inner">
      <div class="toolbar">
        <strong id="modalTitle">Job</strong>
        <button class="btn" onclick="hideModal()">閉じる</button>
      </div>
      <div id="modalBody"></div>
    </div>
  </div>
</div>

<script>
const statuses = [
  ['all','すべて'], ['queued','待機'], ['started','実行中'], ['failed','失敗'], ['stopped','停止'], ['finished','RQ完了'], ['deferred','保留'], ['scheduled','予定'], ['canceled','取消']
];
let currentStatus = 'all';
let lastQueues = [];

function esc(s){return String(s == null ? '' : s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function showError(msg){const e=document.getElementById('error'); e.textContent=msg; e.style.display='block';}
function clearError(){document.getElementById('error').style.display='none';}
async function api(action, params={}, opts={}){
  const qs = new URLSearchParams(Object.assign({proxy:1, action}, params));
  const res = await fetch('?' + qs.toString(), Object.assign({headers:{'Content-Type':'application/json'}}, opts));
  const data = await res.json().catch(()=>({ok:false,error:'JSON parse error'}));
  if(!data.ok) throw new Error(data.message || data.error || data.detail || 'API error');
  return data;
}
function statusLabel(s){return Object.fromEntries(statuses)[s] || s;}
function fmtTime(s){
  if(!s) return '-';
  const d = new Date(s);
  if(Number.isNaN(d.getTime())) return s;
  return d.toLocaleString('ja-JP', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
}
function resourceLabel(j){
  const t = j.task || {};
  if(t.resource_key) return t.resource_key;
  if(t.ollama_host || t.ollama_model) return ['ollama', t.ollama_host || '?', t.ollama_model || t.model || '?'].join(':');
  return '';
}
function renderTabs(){
  document.getElementById('tabs').innerHTML = statuses.map(([s,l]) => `<button class="btn tab ${s===currentStatus?'active':''}" onclick="currentStatus='${s}';renderTabs();loadJobs();">${l}</button>`).join('');
}
async function loadSummary(){
  const data = await api('summary');
  const qs = data.execution_queues || data.queues || [];
  const hqs = data.history_queues || [];
  const ws = data.workers || [];
  const workItems = data.work_items || [];
  lastQueues = qs;
  const live = (data.totals && data.totals.live) || {};
  const work = (data.totals && data.totals.work) || {};
  const history = (data.totals && data.totals.history) || {};
  document.getElementById('mWork').textContent = work.active == null ? workItems.length : work.active;
  document.getElementById('mQueues').textContent = qs.length;
  document.getElementById('mWorkers').textContent = ws.length;
  document.getElementById('mLive').textContent = `${live.queued||0}/${live.started||0}`;
  document.getElementById('mHistory').textContent = `${history.finished||0}/${(history.failed||0)+(history.stopped||0)}`;
  const select = document.getElementById('queueFilter');
  const cur = select.value;
  select.innerHTML = '<option value="">全履歴キュー</option>' + hqs.map(q=>`<option value="${esc(q.name)}">${esc(q.name)}</option>`).join('');
  select.value = cur;
  renderWorkItems(workItems);
  document.getElementById('queues').innerHTML = qs.map(q => `
    <div class="card">
      <div class="queue-name mono">${esc(q.name)}</div>
      <div class="chips">
        <span class="chip">待機 ${q.queued||0}</span>
        <span class="chip run">実行 ${q.started||0}</span>
        <span class="chip">予定 ${q.scheduled||0}</span>
        <span class="chip">保留 ${q.deferred||0}</span>
      </div>
    </div>`).join('') || '<div class="muted">実行キューがありません</div>';
  document.getElementById('historyQueues').innerHTML = hqs.map(q => `
    <div class="card">
      <div class="queue-name mono">${esc(q.name)}</div>
      <div class="chips">
        <span class="chip">待機 ${q.queued||0}</span>
        <span class="chip run">実行 ${q.started||0}</span>
        <span class="chip">RQ完了 ${q.finished||0}</span>
        <span class="chip bad">失敗 ${q.failed||0}</span>
        <span class="chip">停止 ${q.stopped||0}</span>
        <span class="chip">取消 ${q.canceled||0}</span>
      </div>
    </div>`).join('') || '<div class="muted">ジョブ履歴がありません</div>';
  renderWorkers(ws);
}
function renderWorkItems(items){
  document.getElementById('workItems').innerHTML = (items||[]).map(j => {
    const st = j.status || 'unknown';
    const lifecycle = j.lifecycle || {};
    const label = j.status_label || lifecycle.label || statusLabel(st);
    const state = lifecycle.state || st;
    const scope = j.work_scope === 'external_unconfirmed' ? '外部未確認' : 'RQ未完了';
    const resource = resourceLabel(j);
    const note = lifecycle.note ? `<div class="resource-line">${esc(lifecycle.note)}</div>` : '';
    return `<div class="job">
      <div><span class="status ${esc(state)}">${esc(label)}</span><div class="mono muted">${esc((j.id||'').slice(0,12))}</div><div class="muted mini">${esc(scope)}</div></div>
      <div><div><strong>${esc(j.queue||'-')}</strong> <span class="muted">${esc((j.task&&j.task.name)||'')}</span></div><div class="preview">${esc(j.input_preview || j.description || '')}</div>${resource?`<div class="resource-line mono">${esc(resource)}</div>`:''}${note}<div class="time-line"><span>RQ: ${esc(statusLabel(st))}</span><span>作成 ${esc(fmtTime(j.created_at))}</span><span>開始 ${esc(fmtTime(j.started_at))}</span><span>終了 ${esc(fmtTime(j.ended_at))}</span></div></div>
      <div class="actions"><button class="btn" onclick="showJob('${esc(j.id)}')">詳細</button></div>
    </div>`;
  }).join('') || '<div class="muted">未完了ワークはありません</div>';
}
function renderWorkers(ws){
  document.getElementById('workers').innerHTML = (ws||[]).map(w => `
    <div class="job">
      <div><span class="status">${esc(w.state)}</span><div class="mono muted">${esc(w.name)}</div></div>
      <div><div>${w.current_job_id ? esc((w.queues||[]).join(', ')) : '待機中'}</div><div class="preview">処理中ジョブ: ${esc(w.current_job_id || '-')}</div><div class="time-line"><span>起動 ${esc(fmtTime(w.birth_date))}</span><span>最終応答 ${esc(fmtTime(w.last_heartbeat))}</span></div></div>
      <div class="muted">RQ</div>
    </div>`).join('') || '<div class="muted">Worker が見つかりません</div>';
}
async function loadJobs(){
  const queue = document.getElementById('queueFilter').value;
  const params = {limit: 50};
  if(queue) params.queue = queue;
  if(currentStatus !== 'all') params.status = currentStatus;
  const data = await api('jobs', params);
  document.getElementById('jobs').innerHTML = (data.jobs||[]).map(j => {
    const st = j.status || 'unknown';
    const lifecycle = j.lifecycle || {};
    const displayLabel = j.status_label || lifecycle.label || statusLabel(st);
    const displayState = lifecycle.state || st;
    const err = j.error && j.error.label ? ` / ${j.error.label}` : '';
    const resource = resourceLabel(j);
    const task = j.task || {};
    const source = [task.source, task.queue_class, task.priority_class].filter(Boolean).join(' / ');
    const lifecycleNote = lifecycle.note ? `<div class="resource-line">${esc(lifecycle.note)}</div>` : '';
    return `<div class="job">
      <div><span class="status ${esc(displayState)}">${esc(displayLabel)}</span><div class="mono muted">${esc((j.id||'').slice(0,12))}</div><div class="muted mini">RQ: ${esc(statusLabel(st))}</div></div>
      <div><div><strong>${esc(j.queue||'-')}</strong> <span class="muted">${esc((j.task&&j.task.name)||'')}</span></div><div class="preview">${esc(j.input_preview || j.description || '')}${esc(err)}</div>${resource?`<div class="resource-line mono">${esc(resource)}</div>`:''}${lifecycleNote}<div class="time-line"><span>作成 ${esc(fmtTime(j.created_at))}</span><span>投入 ${esc(fmtTime(j.enqueued_at))}</span><span>開始 ${esc(fmtTime(j.started_at))}</span><span>終了 ${esc(fmtTime(j.ended_at))}</span>${source?`<span>${esc(source)}</span>`:''}</div></div>
      <div class="actions">
        <button class="btn" onclick="showJob('${esc(j.id)}')">詳細</button>
        ${st==='failed'?`<button class="btn" onclick="requeueJob('${esc(j.id)}')">再実行</button>`:''}
        ${j.actions&&j.actions.includes('delete')?`<button class="btn danger" onclick="deleteJob('${esc(j.id)}')">削除</button>`:''}
      </div>
    </div>`;
  }).join('') || '<div class="muted">ジョブがありません</div>';
}
async function showJob(id){
  const data = await api('job', {id});
  const j = data.job;
  document.getElementById('modalTitle').textContent = 'Job: ' + id;
  document.getElementById('modalBody').innerHTML = `
    <p><strong>${esc(j.status_label || (j.lifecycle&&j.lifecycle.label) || statusLabel(j.status))}</strong> / RQ: ${esc(statusLabel(j.status))} / ${esc(j.queue)} / ${esc((j.task&&j.task.name)||'')}</p>
    <h3>Lifecycle</h3><div class="pre">${esc(JSON.stringify(j.lifecycle || {}, null, 2))}</div>
    ${resourceLabel(j)?`<p><span class="chip resource mono">${esc(resourceLabel(j))}</span></p>`:''}
    <p class="muted">作成: ${esc(fmtTime(j.created_at))} / 投入: ${esc(fmtTime(j.enqueued_at))} / 開始: ${esc(fmtTime(j.started_at))} / 終了: ${esc(fmtTime(j.ended_at))}</p>
    <h3>Input</h3><div class="pre">${esc(JSON.stringify(j.args, null, 2))}</div>
    <h3>Kwargs</h3><div class="pre">${esc(JSON.stringify(j.kwargs, null, 2))}</div>
    <h3>Result</h3><div class="pre">${esc(JSON.stringify(j.result, null, 2))}</div>
    <h3>Error</h3><div class="pre">${esc(j.exc_info || '')}</div>
    <h3>Meta</h3><div class="pre">${esc(JSON.stringify(j.meta, null, 2))}</div>
    <p class="actions">${j.status==='failed'?`<button class="btn" onclick="requeueJob('${esc(id)}')">再実行</button>`:''}<button class="btn danger" onclick="deleteJob('${esc(id)}')">削除</button></p>
  `;
  document.getElementById('modal').classList.add('open');
}
function hideModal(){document.getElementById('modal').classList.remove('open');}
function closeModal(e){if(e.target.id==='modal') hideModal();}
async function requeueJob(id){if(!confirm('このジョブを再実行しますか？')) return; await api('requeue',{id},{method:'POST',body:'{}'}); await reloadAll();}
async function deleteJob(id){if(!confirm('このジョブを削除しますか？')) return; await api('delete',{id},{method:'POST',body:'{}'}); hideModal(); await reloadAll();}
async function reloadAll(){try{clearError(); await loadSummary(); await loadJobs();}catch(e){showError(e.message);}}
renderTabs();
reloadAll();
setInterval(reloadAll, 10000);
</script>
</body>
</html>
