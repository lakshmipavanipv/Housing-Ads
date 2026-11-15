'use strict';
// ---------- helpers ----------
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const S = {st: null, tab: 'home', sig: '', profile: null};
const TABS = [['home', 'Home'], ['connection', 'Connection'], ['bluetooth', 'Bluetooth'], ['battery', 'Ring Battery'],
  ['time', 'Time'], ['modes', 'Modes'], ['count', 'Count'], ['steps', 'Steps'], ['hr', 'HR'], ['spo2', 'SpO2'],
  ['hrv', 'HRV'], ['sleep', 'Sleep']];
const LIVE = {count: 'Count', steps: 'Steps', hr: 'Heart rate (bpm)', spo2: 'SpO2 (%)', hrv: 'HRV (ms)', sleep: 'Sleep (min)'};
const MODES = [['time', 'Time'], ['counter', 'Counter'], ['steps', 'Steps'], ['hr', 'HR'], ['spo2', 'SpO2'],
  ['sleep', 'Sleep'], ['battery', 'Battery'], ['off', 'Switch Off'], ['on', 'Switch On']];
const PARSERS = ['uint8', 'int8', 'uint16_le', 'int16_le', 'uint32_le', 'int32_le', 'unix_time_le', 'hr_measurement', 'ascii', 'raw_hex'];
const OPS = ['read', 'write', 'read_write', 'notify'];

async function api(path, body, method) {
  const opt = {method: method || (body === undefined ? 'GET' : 'POST'), headers: {'Content-Type': 'application/json'}};
  if (body !== undefined) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}
function toast(msg, bad) {
  const t = $('#toast'); t.textContent = msg; t.className = 'show' + (bad ? ' bad' : '');
  clearTimeout(toast.h); toast.h = setTimeout(() => { t.className = ''; }, 4000);
}
const fmtT = ts => ts ? new Date(ts * 1000).toLocaleTimeString() : '—';
const fmtDT = ts => ts ? new Date(ts * 1000).toLocaleString() : '—';
const fmtMin = m => m == null ? '—' : `${(+m).toFixed(1)} min`;
function fmtTz(m) {
  if (m == null) return '';
  const s = m < 0 ? '-' : '+'; m = Math.abs(m);
  return `UTC${s}${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}
function fmtRingTime(unix, tz) {
  if (unix == null) return '—';
  return new Date((unix + (tz || 0) * 60) * 1000).toISOString().slice(0, 19).replace('T', ' ') + ' ' + fmtTz(tz);
}
function parseTz(s) {
  const m = /^(?:UTC)?\s*([+-])?(\d{1,2})(?::?(\d{2}))?$/i.exec(String(s).trim());
  if (!m) throw new Error('Time zone format must be like +05:30 or -04:00');
  return (m[1] === '-' ? -1 : 1) * (parseInt(m[2], 10) * 60 + parseInt(m[3] || '0', 10));
}
const badge = s => { s = s || 'PENDING'; return `<span class="badge b-${esc(s.split(/[ :]/)[0])}" title="${esc(s)}">${esc(s)}</span>`; };
const rows = () => (S.st?.rings || []);
const stage = k => S.st?.stages?.[k] || {};
const srow = (k, addr) => stage(k).rows?.[addr] || {};
const ringCell = r => `<span class="dot ${r.connected ? 'on' : ''}"></span><b>${esc(r.unit_id)}</b> ${esc(r.name || '(no name)')}<div class="mac">${esc(r.addr)}</div>`;
const buzzCell = r => `<button class="buzz ${r.buzzing ? 'on' : ''}" data-act="buzz" data-addr="${esc(r.addr)}">${r.buzzing ? 'Buzzing…' : 'Buzz'}</button><button data-act="stop" data-addr="${esc(r.addr)}">Stop</button>`;
const isFail = s => (s || '').startsWith('FAIL');

// ---------- sparkline (live line chart) ----------
let CC = null;
function drawSpark(cv, pts) {
  if (!CC) { const cs = getComputedStyle(document.documentElement); CC = {line: cs.getPropertyValue('--chart').trim(), mut: cs.getPropertyValue('--muted').trim()}; }
  const dpr = window.devicePixelRatio || 1, W = 220, H = 46;
  if (cv.width !== W * dpr) { cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + 'px'; cv.style.height = H + 'px'; }
  const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  const p = (pts || []).filter(x => typeof x[1] === 'number');
  g.fillStyle = CC.mut; g.font = '10px system-ui';
  if (p.length < 2) { g.fillText(p.length ? 'collecting…' : 'no data', 4, H / 2 + 3); return; }
  const t0 = p[0][0], t1 = p[p.length - 1][0] || t0 + 1;
  let lo = Math.min(...p.map(x => x[1])), hi = Math.max(...p.map(x => x[1]));
  if (hi === lo) { hi += 1; lo -= 1; }
  const X = t => 30 + (t - t0) / ((t1 - t0) || 1) * (W - 34), Y = v => 4 + (hi - v) / (hi - lo) * (H - 8);
  g.fillText(String(Math.round(hi)), 0, 10); g.fillText(String(Math.round(lo)), 0, H - 2);
  g.strokeStyle = CC.line; g.lineWidth = 1.5; g.beginPath();
  p.forEach(([t, v], i) => i ? g.lineTo(X(t), Y(v)) : g.moveTo(X(t), Y(v))); g.stroke();
}

// ---------- generic keyed table: rebuilt only when rings/columns change ----------
function table(cols, list, rowFail) {
  const host = $('#tbl'); if (!host) return;
  const sig = S.tab + '|' + cols.map(c => c.h).join('|') + '|' + list.map(r => r.addr).join(',');
  if (sig !== S.sig) {
    S.sig = sig;
    host.innerHTML = list.length
      ? `<div class="tblwrap"><table><thead><tr>${cols.map(c => `<th>${c.h}</th>`).join('')}</tr></thead><tbody>${
        list.map((r, i) => `<tr id="r${i}">${cols.map((c, j) => `<td id="c${i}_${j}" class="${c.cls || ''}">${c.chart ? '<canvas></canvas>' : ''}</td>`).join('')}</tr>`).join('')
      }</tbody></table></div>`
      : `<div class="tblwrap"><p class="empty">No rings yet. Open the <b>Bluetooth</b> tab, click <b>Search</b>, then <b>Connect All</b>.</p></div>`;
  }
  list.forEach((r, i) => {
    const tr = document.getElementById('r' + i); if (!tr) return;
    tr.className = rowFail && rowFail(r) ? 'fail' : '';
    cols.forEach((c, j) => {
      const td = document.getElementById(`c${i}_${j}`);
      if (c.chart) { drawSpark(td.firstChild, c.chart(r)); return; }
      const h = c.v(r);
      if (td._h !== h) { td.innerHTML = h; td._h = h; }
    });
  });
}

function shell(title, bar, help) {
  return `<h2>${title}</h2>${help ? `<div class="info">${help}</div>` : ''}
  <div class="bar">${bar || ''}<span class="sp"></span><button data-act="buzzAll">Buzz All</button><button data-act="stopAll">Stop All</button></div>
  <div id="info" class="info"></div><div id="tbl"></div>
  <div class="footer"><span>Saves every ring's result with a timestamp under batch <b class="fb"></b> · tester <b class="ft"></b></span>
  <button class="primary" data-act="save" data-stage="${S.tab}">Save Results</button></div>`;
}
const runBar = k => `<button class="primary" data-act="stageStart" data-stage="${k}">Run Stage</button><button data-act="stageStop" data-stage="${k}">Stop Stage</button>`;
function setInfo(h) { const el = $('#info'); if (el && el._h !== h) { el.innerHTML = h; el._h = h; } }
function stageInfo(k, extra) {
  const st = stage(k);
  if (!st.started_at) return 'Stage not started. Click <b>Run Stage</b>.';
  return `Run stage started: <b>${fmtDT(st.started_at)}</b> · ${st.running ? '<b>RUNNING</b>' : 'finished ' + fmtT(st.finished_at)}`
    + (st.last_poll ? ` · last ping ${fmtT(st.last_poll)}` : '') + (extra ? ' · ' + extra : '');
}
function counts(k) {
  const rs = Object.values(stage(k).rows || {}); const p = rs.filter(r => r.status === 'PASS').length;
  const f = rs.filter(r => isFail(r.status)).length; return `PASS <b>${p}</b> · FAIL <b>${f}</b> · of ${rs.length}`;
}

// ---------- views ----------
const V = {};

V.home = {
  build: () => `<h2>Batch reports</h2><div class="bar"><button data-act="refreshHome">Refresh</button></div>
    <div id="homeList"></div><div id="homeDetail"></div>`,
  show: loadHome,
};
async function loadHome() {
  const list = await api('/api/batches');
  const stg = ['bluetooth', 'battery', 'time', 'modes', 'count', 'steps', 'hr', 'spo2', 'hrv', 'sleep'];
  $('#homeList').innerHTML = list.length ? `<div class="tblwrap"><table><thead><tr><th>Batch</th><th>Created</th><th>Tester</th><th>Rings</th>${
    stg.map(s => `<th>${s}</th>`).join('')}<th></th></tr></thead><tbody>${list.map(b => `<tr><td><b>${esc(b.name)}</b></td><td>${fmtDT(b.created_at)}</td><td>${esc(b.tester)}</td><td class="num">${b.rings} / ${b.ring_target}</td>${
    stg.map(s => { const c = b.stages[s]; return `<td class="num">${c ? `<span class="badge b-PASS">${c.pass}</span> <span class="badge b-FAIL">${c.fail}</span>` : '—'}</td>`; }).join('')
    }<td><button data-act="viewBatch" data-id="${b.id}">View</button><a href="/api/batches/${b.id}/csv"><button>CSV</button></a></td></tr>`).join('')}</tbody></table></div>`
    : '<div class="card">No saved batches yet. Run a stage on any tab and click <b>Save Results</b>.</div>';
}
async function loadBatch(id) {
  const d = await api('/api/batches/' + id);
  $('#homeDetail').innerHTML = `<h3>${esc(d.batch.name)}: results per ring</h3><div class="tblwrap"><table><thead><tr><th>Ring</th>${
    d.stages.map(s => `<th>${s}</th>`).join('')}</tr></thead><tbody>${d.rings.map(r => `<tr class="${Object.values(r.results).some(x => isFail(x.status)) ? 'fail' : ''}"><td><b>${esc(r.unit_id)}</b> ${esc(r.ble_name)}<div class="mac">${esc(r.mac)}</div></td>${
    d.stages.map(s => { const x = r.results[s]; return `<td title="${esc(x ? JSON.stringify(x.values) + ' · saved ' + fmtDT(x.saved_at) + ' by ' + x.tester : '')}">${x ? badge(x.status) : '—'}</td>`; }).join('')
    }</tr>`).join('')}</tbody></table></div>`;
}

V.connection = {
  build: () => `<h2>Connection</h2>
    <div class="card"><h3 style="margin-top:0">Bluetooth adapter</h3>
      <label class="radio"><input type="radio" name="adapter" value="local"> <b>Local laptop Bluetooth</b> (default)</label>
      <label class="radio"><input type="radio" name="adapter" value="mock"> Simulator: virtual rings for training and demo</label>
      <label class="radio"><input type="radio" name="adapter" value="dongles" disabled> USB dongles (3 slots below, not enabled yet)</label>
      <div id="adStatus"></div>
      <div class="tblwrap" style="margin-top:8px"><table><thead><tr><th>Dongle</th><th>Serial number / COM port</th><th></th><th>Status</th></tr></thead><tbody>
      ${[1, 2, 3].map(i => `<tr><td>USB dongle ${i}</td><td><input disabled placeholder="e.g. COM${i + 2} / serial"></td><td><button disabled>Connect</button></td><td><span class="badge">Not used: local Bluetooth selected</span></td></tr>`).join('')}
      </tbody></table></div></div>
    <div class="card"><h3 style="margin-top:0">Batch</h3>
      <label>Rings to test in this batch <input id="target" type="number" min="1" style="width:90px"></label>
      <button data-act="saveTarget">Set</button></div>
    <div class="card"><h3 style="margin-top:0">Ring model: UUID variables</h3>
      <div class="bar"><label>Model <select id="profSel"></select></label><button data-act="loadProfile">Load</button>
      <span class="sp"></span><button data-act="saveProfile" class="primary">Save</button><button data-act="saveAsProfile">Save as new model…</button></div>
      <div id="profForm">Loading…</div></div>`,
  show: async () => {
    const st = S.st || {};
    document.querySelectorAll('input[name=adapter]').forEach(x => { x.checked = x.value === (st.backend || 'local'); });
    $('#target').value = st.ring_target || 30;
    await loadProfileForm();
  },
  update: st => {
    const el = $('#adStatus'); if (!el) return;
    const h = st.backend_error ? `<div class="err">Adapter error: ${esc(st.backend_error)}</div>`
      : `<div class="info">Active: <b>${st.backend === 'mock' ? 'Simulator' : 'Local laptop Bluetooth'}</b> · rings known ${st.rings.length} · connected ${st.rings.filter(r => r.connected).length} / ${st.ring_target}</div>`;
    if (el._h !== h) { el.innerHTML = h; el._h = h; }
  },
};
async function loadProfileForm() {
  const d = await api('/api/profile'); S.profile = d;
  $('#profSel').innerHTML = d.profiles.map(p => `<option ${p === d.name ? 'selected' : ''}>${esc(p)}</option>`).join('');
  const p = d.profile, vars = p.vars || {};
  const anyPh = Object.values(vars).some(v => v.placeholder);
  $('#profForm').innerHTML = `${anyPh ? '<div class="warn">Rows marked in yellow still have PLACEHOLDER UUIDs. Enter the values from the Body &amp; Soul app, untick "placeholder" and Save.</div>' : ''}
    <div class="bar"><label>Model name <input id="pModel" value="${esc(p.model)}"></label>
    <label>BLE name prefix filter <input id="pPrefix" value="${esc(p.name_prefix)}" placeholder="(all devices)"></label>
    <label>Default service UUID <input id="pSvc" size="38" value="${esc(p.service_uuid)}"></label></div>
    <div class="tblwrap"><table><thead><tr><th>Variable</th><th>Service UUID (blank = default)</th><th>Characteristic UUID</th><th>Op</th><th>Parser</th><th>Commands (name=hex, …)</th><th>Placeholder</th></tr></thead><tbody>
    ${Object.entries(vars).map(([k, v]) => `<tr class="${v.placeholder ? 'ph' : ''}" data-var="${esc(k)}">
      <td><b>${esc(k)}</b></td>
      <td><input data-f="service" size="36" value="${esc(v.service || '')}"></td>
      <td><input data-f="char" size="36" value="${esc(v.char || '')}"></td>
      <td><select data-f="op">${OPS.map(o => `<option ${o === v.op ? 'selected' : ''}>${o}</option>`).join('')}</select></td>
      <td><select data-f="parser">${PARSERS.map(o => `<option ${o === v.parser ? 'selected' : ''}>${o}</option>`).join('')}</select></td>
      <td><input data-f="commands" size="40" value="${esc(Object.entries(v.commands || {}).map(([a, b]) => `${a}=${b}`).join(', '))}"></td>
      <td><input type="checkbox" data-f="placeholder" ${v.placeholder ? 'checked' : ''}></td></tr>`).join('')}
    </tbody></table></div>
    <h3>Pass/fail rules and timings</h3><textarea id="pRules" rows="9">${esc(JSON.stringify(p.rules || {}, null, 2))}</textarea>`;
}
function collectProfile() {
  const p = structuredClone(S.profile.profile);
  p.model = $('#pModel').value.trim(); p.name_prefix = $('#pPrefix').value.trim(); p.service_uuid = $('#pSvc').value.trim();
  document.querySelectorAll('#profForm tr[data-var]').forEach(tr => {
    const v = p.vars[tr.dataset.var], f = n => tr.querySelector(`[data-f=${n}]`);
    v.service = f('service').value.trim() || undefined; v.char = f('char').value.trim();
    v.op = f('op').value; v.parser = f('parser').value; v.placeholder = f('placeholder').checked;
    const cmds = f('commands').value.split(',').map(s => s.trim()).filter(Boolean);
    if (cmds.length) {
      v.commands = {};
      cmds.forEach(c => { const [a, b] = c.split('=').map(s => (s || '').trim()); if (!a || !/^([0-9a-fA-F]{2})+$/.test(b || '')) throw new Error(`Command "${c}" on ${tr.dataset.var} must look like name=01`); v.commands[a] = b.toLowerCase(); });
    } else delete v.commands;
  });
  try { p.rules = JSON.parse($('#pRules').value); } catch (e) { throw new Error('Rules box is not valid JSON: ' + e.message); }
  return p;
}

V.bluetooth = {
  build: () => shell('Bluetooth: find, connect and identify rings',
    `<button class="primary" data-act="scan">Search</button><button data-act="connectAll">Connect All</button><button data-act="disconnectAll">Disconnect All</button>`,
    'Open the charge-case lids, click <b>Search</b>, then <b>Connect All</b>. Use <b>Buzz</b> on a row to make that ring vibrate and blink until <b>Stop</b>, then mark whether you saw it.'),
  update: st => {
    const rs = rows(), f = rs.filter(r => r.found).length, c = rs.filter(r => r.connected).length;
    setInfo(`${st.scanning ? '<b>Searching…</b> · ' : ''}Found <b>${f}</b> · Connected <b>${c}</b> / target <b>${st.ring_target}</b>${c >= st.ring_target ? ' · <b>batch complete</b>' : ''} · ${counts('bluetooth')}`);
    table([
      {h: 'Bluetooth ring', v: ringCell},
      {h: 'RSSI', cls: 'num', v: r => r.rssi != null ? `${r.rssi} dBm` : '—'},
      {h: '<button data-act="scan">Search</button>', v: r => st.scanning ? 'Searching…' : badge(r.found ? 'Found' : 'FAIL: not found')},
      {h: '<button data-act="connectAll">Connect All</button>', v: r => r.connected ? badge('Connected') : `<button data-act="connect" data-addr="${esc(r.addr)}">Connect</button>${r.error ? ' ' + badge('FAIL: ' + r.error) : ''}`},
      {h: '<button data-act="buzzAll">Buzz All</button><button data-act="stopAll">Stop</button>', v: buzzCell},
      {h: 'Buzz seen? <button data-act="seenAll">✓ All seen</button>', v: r => { const s = srow('bluetooth', r.addr).seen; return `<button data-act="seen" data-ok="1" data-addr="${esc(r.addr)}" class="${s === true ? 'primary' : ''}">✓ Yes</button><button data-act="seen" data-ok="0" data-addr="${esc(r.addr)}" class="${s === false ? 'primary' : ''}">✗ No</button>`; }},
      {h: 'Result', v: r => badge(srow('bluetooth', r.addr).status) + (r.buzz_error ? ' ' + badge('FAIL: buzz ' + r.buzz_error) : '')},
    ], rs, r => isFail(srow('bluetooth', r.addr).status));
  },
};

V.battery = {
  build: () => shell('Ring battery: charge time test', runBar('battery'),
    'Put rings on charge, then click <b>Run Stage</b>. The portal pings every ring every minute, estimates the time to 100 %, records when each ring reaches 100 % and compares that with the estimate.'),
  update: st => {
    const s = stage('battery');
    setInfo(stageInfo('battery', `ping every ${s.interval_s ? Math.round(s.interval_s) + ' s' : '60 s'} · ${counts('battery')}`));
    table([
      {h: 'Bluetooth ring', v: ringCell},
      {h: 'Current battery', cls: 'num', v: r => { const x = srow('battery', r.addr); return x.current != null ? `<b>${x.current}%</b>` : (x.error ? badge('FAIL: ' + x.error) : '—'); }},
      {h: 'Est. time to 100%', cls: 'num', v: r => { const x = srow('battery', r.addr); return x.current == null ? '—' : x.current >= 100 ? 'Full' : fmtMin(x.eta_min); }},
      {h: 'Reached 100% at', cls: 'num', v: r => fmtT(srow('battery', r.addr).full_at)},
      {h: 'Estimated vs actual', cls: 'num', v: r => { const x = srow('battery', r.addr); return x.est_total_min == null ? '—' : `${fmtMin(x.est_total_min)} vs ${x.actual_min != null ? fmtMin(x.actual_min) : fmtMin(x.elapsed_min) + ' so far'}`; }},
      {h: 'Variance', cls: 'num', v: r => { const x = srow('battery', r.addr); return x.variance_min == null ? '—' : `${x.variance_min > 0 ? '+' : ''}${x.variance_min} min (${x.variance_pct}%)`; }},
      {h: 'Trend', chart: r => srow('battery', r.addr).samples},
      {h: 'Buzz', v: buzzCell},
      {h: 'Result', v: r => badge(srow('battery', r.addr).status)},
    ], rows(), r => isFail(srow('battery', r.addr).status));
  },
};

V.time = {
  build: () => shell('Time and time zone test',
    `<label>Time zone <input id="tz" value="+05:30" size="7"></label><label>Time shift (min) <input id="shift" type="number" value="0" style="width:80px"></label>
     <button class="primary" data-act="timeRun">Apply to all rings &amp; verify</button><button data-act="timeRead">Read current only</button>`,
    'Sets the time zone and the shifted time on every connected ring, then reads them back. PASS = time within the tolerance and time zone applied.'),
  update: st => {
    const s = stage('time'), p = s.params || {};
    setInfo(stageInfo('time', p.read_only ? 'read only' : (p.tz_min != null ? `applied <b>${fmtTz(p.tz_min)}</b>, shift <b>${p.shift_min || 0} min</b>` : '')) + ' · ' + counts('time'));
    table([
      {h: 'Bluetooth ring', v: ringCell},
      {h: 'Current time zone / time on ring', cls: 'num', v: r => { const x = srow('time', r.addr); return x.before_time != null ? fmtRingTime(x.before_time, x.before_tz) : '—'; }},
      {h: `Target ${p.tz_min != null ? fmtTz(p.tz_min) : ''} ${p.shift_min ? `(shift ${p.shift_min} min)` : ''}`, cls: 'num', v: r => { const x = srow('time', r.addr); return x.target ? fmtRingTime(x.target, p.tz_min) : '—'; }},
      {h: 'Read-back after set', cls: 'num', v: r => { const x = srow('time', r.addr); return x.after_time != null ? fmtRingTime(x.after_time, x.after_tz) : '—'; }},
      {h: 'Drift', cls: 'num', v: r => { const x = srow('time', r.addr); return x.drift_s != null ? `${x.drift_s} s` : '—'; }},
      {h: 'Buzz', v: buzzCell},
      {h: 'Result', v: r => badge(srow('time', r.addr).status)},
    ], rows(), r => isFail(srow('time', r.addr).status));
  },
};

V.modes = {
  build: () => shell('Mode test', '', 'Click a mode in the column header to switch <b>all</b> connected rings to that mode. Each cell shows whether that ring accepted it. PASS = all 9 modes OK.'),
  update: st => {
    const s = stage('modes');
    setInfo((s.last_mode ? `Last applied: <b>${esc(s.last_mode)}</b> at ${fmtT(s.last_at)} · ` : 'No mode applied yet · ') + counts('modes'));
    table([
      {h: 'Bluetooth ring', v: ringCell},
      ...MODES.map(([k, label]) => ({h: `<button data-act="mode" data-mode="${k}">${label}</button>`, v: r => { const m = (srow('modes', r.addr).modes || {})[k]; return m ? badge(m) : '—'; }})),
      {h: 'Buzz', v: buzzCell},
      {h: 'Result', v: r => badge(srow('modes', r.addr).status)},
    ], rows(), r => isFail(srow('modes', r.addr).status));
  },
};

for (const [k, label] of Object.entries(LIVE)) {
  V[k] = {
    build: () => shell(`${label}: live data test`, runBar(k),
      `Click <b>Run Stage</b>. The portal pings every ring every 10 s and draws a live trend line. ${k === 'steps' || k === 'count' ? 'Move or tap the rings during the stage: the value must increase.' : 'Keep the rings worn or on a finger simulator.'}`),
    update: st => {
      const s = stage(k);
      setInfo(stageInfo(k, `ping every ${s.interval_s || 10} s for ${s.duration_s || 120} s · ${counts(k)}`));
      table([
        {h: 'Bluetooth ring', v: ringCell},
        {h: 'Live value', cls: 'num', v: r => { const x = srow(k, r.addr); return x.current != null ? `<b>${x.current}</b>` : (x.error ? badge('FAIL: ' + x.error) : '—'); }},
        {h: 'Live trend', chart: r => srow(k, r.addr).samples},
        {h: 'Min / Max', cls: 'num', v: r => { const x = srow(k, r.addr); return x.min != null ? `${x.min} / ${x.max}` : '—'; }},
        {h: 'Samples', cls: 'num', v: r => String((srow(k, r.addr).samples || []).length)},
        {h: 'Buzz', v: buzzCell},
        {h: 'Average', cls: 'num', v: r => { const x = srow(k, r.addr); return x.avg != null ? `<b>${x.avg}</b>` : '—'; }},
        {h: 'Result', v: r => badge(srow(k, r.addr).status)},
      ], rows(), r => isFail(srow(k, r.addr).status));
    },
  };
}

// ---------- actions ----------
const who = () => ({batch: $('#batch').value.trim(), tester: $('#tester').value.trim()});
const A = {
  tab: d => go(d.tab),
  scan: async () => { const r = await api('/api/scan', {}); toast(`Found ${r.found} ring(s)`); },
  connect: d => api('/api/connect', {addr: d.addr}),
  connectAll: async () => { const r = await api('/api/connect_all', {}); toast(`Connected ${r.connected} / ${r.total}`); },
  disconnectAll: () => api('/api/disconnect_all', {}),
  buzz: d => api('/api/buzz', {addr: d.addr, on: true}),
  stop: d => api('/api/buzz', {addr: d.addr, on: false}),
  buzzAll: () => api('/api/buzz', {all: true, on: true}),
  stopAll: () => api('/api/buzz', {all: true, on: false}),
  seen: d => api('/api/bt/seen', {addr: d.addr, ok: d.ok === '1'}),
  seenAll: async () => { const c = rows().filter(r => r.connected); if (!c.length || !confirm(`Mark all ${c.length} connected rings as buzz seen?`)) return; await Promise.all(c.map(r => api('/api/bt/seen', {addr: r.addr, ok: true}))); },
  stageStart: async d => { await api(`/api/stage/${d.stage}/start`, {}); toast('Stage started'); },
  stageStop: d => api(`/api/stage/${d.stage}/stop`, {}),
  timeRun: () => api('/api/stage/time/start', {tz_min: parseTz($('#tz').value), shift_min: +$('#shift').value || 0}),
  timeRead: () => api('/api/stage/time/start', {read_only: true}),
  mode: async d => { const r = await api('/api/mode', {mode: d.mode}); toast(`${d.mode}: ${r.ok} / ${r.total} rings OK`, r.ok < r.total); },
  save: async d => { const r = await api('/api/save', {stage: d.stage, ...who()}); toast(`Saved ${r.saved} ring results to batch "${who().batch}"`); },
  refreshHome: loadHome,
  viewBatch: d => loadBatch(d.id),
  saveTarget: async () => { await api('/api/ring_target', {n: +$('#target').value}); toast('Batch ring count set'); },
  loadProfile: async () => { await api('/api/profile/load', {name: $('#profSel').value}); await loadProfileForm(); toast('Model loaded'); },
  saveProfile: async () => { await api('/api/profile', {profile: collectProfile()}, 'PUT'); await loadProfileForm(); toast('Model saved'); },
  saveAsProfile: async () => { const n = prompt('New model name (e.g. ring_v2)'); if (!n) return; await api('/api/profile', {profile: collectProfile(), name: n}, 'PUT'); await loadProfileForm(); toast('Saved as ' + n); },
};
document.addEventListener('click', async e => {
  const b = e.target.closest('button[data-act]'); if (!b) return;
  e.preventDefault();
  try { b.disabled = true; await A[b.dataset.act](b.dataset, b); } catch (err) { toast(err.message, true); } finally { b.disabled = false; }
});
document.addEventListener('change', async e => {
  if (e.target.name === 'adapter') {
    try { const r = await api('/api/backend', {mode: e.target.value}); toast(r.error ? 'Adapter error: ' + r.error : 'Adapter switched', !!r.error); } catch (err) { toast(err.message, true); }
  }
});
for (const id of ['batch', 'tester']) {
  try { $('#' + id).value = localStorage.getItem('rqa_' + id) || ''; } catch (e) { /* storage unavailable */ }
  $('#' + id).addEventListener('input', e => { try { localStorage.setItem('rqa_' + id, e.target.value); } catch (x) { /* ignore */ } update(); });
}

// ---------- navigation + live updates ----------
function go(tab) {
  S.tab = tab; S.sig = '';
  $('#tabs').innerHTML = TABS.map(([k, l]) => `<button data-act="tab" data-tab="${k}" class="${k === tab ? 'active' : ''}">${l}</button>`).join('');
  $('#view').innerHTML = V[tab].build();
  if (V[tab].show) V[tab].show().catch(err => toast(err.message, true));
  update();
}
function update() {
  const st = S.st; if (!st) return;
  const c = st.rings.filter(r => r.connected).length;
  $('#chip').textContent = `${st.backend === 'mock' ? 'Simulator' : 'Local Bluetooth'}${st.backend_error ? ' (error)' : ''} · ${c} / ${st.ring_target} connected`;
  document.querySelectorAll('.fb').forEach(x => { x.textContent = $('#batch').value || '(set at top)'; });
  document.querySelectorAll('.ft').forEach(x => { x.textContent = $('#tester').value || '(set at top)'; });
  if (V[S.tab].update) V[S.tab].update(st);
}
function connectWs() {
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  ws.onmessage = m => { S.st = JSON.parse(m.data); update(); };
  ws.onclose = () => { $('#chip').textContent = 'Server offline, retrying…'; setTimeout(connectWs, 2000); };
}
go('home');
connectWs();
