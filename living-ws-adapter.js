// ============================================================================
// HOJAIGA // STEP 2: LIVING INTERFACE WEBSOCKET & EVENT SYSTEM ADAPTER
// File: living-ws-adapter.js
// Wires HojaigaLivingBus (living-interface.html) <-> server.py & hojaiga_agent.py
//   #46 Live Intent-to-Python Dispatch        (INTENT_IGNITED -> WS -> agent goal)
//   #47 Real-Time Telemetry-to-3D Mapper      (backend events -> 4 physical regions)
//   #48 Fault-Triggered Structural Destabil.  (POPUP/FAULT -> jitter + self-heal tube)
//   #49 Data Crystallization & SQLite Harvest (DATA_CRYSTALLIZED -> emerald shards)
//   #50 Interactive Crystal Vault Drawer      (CRYSTALLIZED chip -> glass vault UI)
// Connects to the real CNS bridge: ws://<host>:8765  (SSE fallback /api/stream)
// ============================================================================
(function () {
  'use strict';

  const WS_URL = 'ws://' + (window.location.hostname || 'localhost') + ':8765';
  const harvestedRecords = [];
  let ws = null;
  let transport = 'connecting'; // 'ws' | 'sse' | 'offline'
  let vaultHydrated = false;

  // Map Python backend sectors -> the 4 physical 3D Region indices
  // 0: Browser Swarm (-11, 1.5, -4) | 1: Directory Research (11, 2.0, -3)
  // 2: Entity Verifier (0, 3.5, -12) | 3: Portfolio Extractor (-6, -1.5, 9)
  const SECTOR_TO_REGION_IDX = { scanner: 0, llm: 1, verify: 2, execution: 3 };
  const SECTOR_TONES = {
    scanner: 'text-sky-300', llm: 'text-purple-300', verify: 'text-teal-300',
    execution: 'text-emerald-300', hub: 'text-amber-300', living: 'text-pink-300'
  };
  const HANDSHAKE_EVENTS = ['CNS_LINKED', 'WS_CONNECTED'];
  const CRYSTAL_EVENTS = ['LLAMA3_ACTION', 'PYAUTOGUI_MOVE', 'DATA_CRYSTALLIZED'];
  const FAULT_EVENTS = ['POPUP_INTERCEPTED', 'AGENT_FAILURE'];

  // ==========================================================================
  // Ability #50: CRYSTAL VAULT DRAWER (deep-space glass, injected into HUD)
  // ==========================================================================
  const VAULT_CSS = [
    '.vault-stage{',
    '  position:fixed; top:5.5rem; right:1.25rem; z-index:40; width:24rem; max-width:calc(100vw - 2rem);',
    '  max-height:70vh; opacity:0; transform:translateX(2.5rem) scale(.97); pointer-events:none;',
    '  transition:opacity .45s cubic-bezier(.16,1,.3,1), transform .45s cubic-bezier(.16,1,.3,1);',
    '}',
    '.vault-stage.open{opacity:1; transform:translateX(0) scale(1); pointer-events:auto;}',
    '.vault-glass{',
    '  position:relative; display:flex; flex-direction:column; height:100%; border-radius:1.5rem; overflow:hidden;',
    '  background:',
    '    radial-gradient(130% 80% at 8% -10%, rgba(16,185,129,.16), transparent 55%),',
    '    radial-gradient(100% 70% at 105% 105%, rgba(56,189,248,.12), transparent 60%),',
    '    radial-gradient(120% 90% at 50% -20%, rgba(167,139,250,.10), transparent 55%),',
    '    linear-gradient(165deg, rgba(5,9,18,.86), rgba(3,6,12,.94));',
    '  backdrop-filter:blur(16px) saturate(1.25); -webkit-backdrop-filter:blur(16px) saturate(1.25);',
    '  border:1px solid rgba(148,163,184,.16);',
    '  box-shadow:',
    '    0 34px 90px rgba(0,0,0,.78),',
    '    inset 0 1px 0 rgba(255,255,255,.10),',
    '    inset 0 -40px 70px rgba(2,5,11,.55),',
    '    0 0 60px rgba(16,185,129,.12);',
    '}',
    '.vault-glass::before{ /* star specks embedded in the glass */',
    '  content:""; position:absolute; inset:0; pointer-events:none; opacity:.55;',
    '  background-image:',
    '    radial-gradient(1.4px 1.4px at 12% 18%, rgba(255,255,255,.9), transparent 60%),',
    '    radial-gradient(1.1px 1.1px at 74% 8%,  rgba(167,243,208,.9), transparent 60%),',
    '    radial-gradient(1.6px 1.6px at 38% 62%, rgba(255,255,255,.7), transparent 60%),',
    '    radial-gradient(1.1px 1.1px at 88% 48%, rgba(125,211,252,.85), transparent 60%),',
    '    radial-gradient(1.3px 1.3px at 58% 86%, rgba(253,230,138,.75), transparent 60%),',
    '    radial-gradient(1px 1px at 24% 84%,   rgba(255,255,255,.65), transparent 60%);',
    '}',
    '.vault-glass::after{ /* top rim light */',
    '  content:""; position:absolute; left:8%; right:8%; top:0; height:1px; pointer-events:none;',
    '  background:linear-gradient(90deg, transparent, rgba(110,231,183,.75), rgba(56,189,248,.5), transparent);',
    '}',
    '.vault-head{position:relative; padding:1.1rem 1.15rem .85rem; border-bottom:1px solid rgba(148,163,184,.14);}',
    '.vault-eyebrow{font-size:9.5px; letter-spacing:.24em; color:#6ee7b7; text-transform:uppercase; opacity:.9;}',
    '.vault-title{font-size:.92rem; font-weight:600; color:#fff; margin-top:.2rem; letter-spacing:.02em;}',
    '.vault-live{',
    '  display:inline-flex; align-items:center; gap:6px; font-size:9px; letter-spacing:.16em;',
    '  color:#a7f3d0; padding:4px 9px; border-radius:999px;',
    '  background:rgba(16,185,129,.12); border:1px solid rgba(52,211,153,.35);',
    '}',
    '.vault-live i{width:6px; height:6px; border-radius:50%; background:#34d399; box-shadow:0 0 8px #34d399; animation:vaultPulse 1.6s ease-in-out infinite;}',
    '@keyframes vaultPulse{0%,100%{opacity:1; transform:scale(1);} 50%{opacity:.35; transform:scale(.7);}}',
    '.vault-close{',
    '  width:30px; height:30px; border-radius:10px; font-size:13px; color:#cbd5e1;',
    '  background:rgba(15,23,42,.8); border:1px solid rgba(100,116,139,.35); cursor:pointer; transition:.2s;',
    '}',
    '.vault-close:hover{color:#fff; border-color:rgba(52,211,153,.6); box-shadow:0 0 14px rgba(52,211,153,.25);}',
    '.vault-list{flex:1; overflow-y:auto; padding:.9rem 1rem; display:flex; flex-direction:column; gap:.55rem;}',
    '.vault-list::-webkit-scrollbar{width:6px;}',
    '.vault-list::-webkit-scrollbar-thumb{background:rgba(52,211,153,.35); border-radius:99px;}',
    '.vault-list::-webkit-scrollbar-track{background:transparent;}',
    '.vault-shard{',
    '  position:relative; padding:.65rem .75rem .6rem .8rem; border-radius:14px; overflow:hidden;',
    '  background:linear-gradient(135deg, rgba(9,15,28,.94), rgba(6,10,19,.8));',
    '  border:1px solid rgba(148,163,184,.14); border-left:3px solid var(--shard-c, #34d399);',
    '  box-shadow:inset 0 1px 0 rgba(255,255,255,.05), 0 10px 26px rgba(0,0,0,.45);',
    '  animation:shardIn .55s cubic-bezier(.16,1,.3,1) both;',
    '}',
    '.vault-shard::after{',
    '  content:""; position:absolute; top:0; bottom:0; width:45%; transform:skewX(-18deg) translateX(-160%);',
    '  background:linear-gradient(90deg, transparent, rgba(255,255,255,.07), transparent); transition:.7s;',
    '}',
    '.vault-shard:hover::after{transform:skewX(-18deg) translateX(320%);}',
    '.vault-shard:hover{border-color:rgba(148,163,184,.28); box-shadow:inset 0 1px 0 rgba(255,255,255,.06), 0 14px 34px rgba(0,0,0,.55), 0 0 22px var(--shard-g, rgba(52,211,153,.16));}',
    '@keyframes shardIn{from{opacity:0; transform:translateY(-10px) scale(.97); filter:brightness(2.2);} to{opacity:1; transform:none; filter:none;}}',
    '.shard-meta{display:flex; justify-content:space-between; align-items:center; font-size:9px; letter-spacing:.14em; color:var(--shard-c,#6ee7b7);}',
    '.shard-meta .t{color:#64748b; letter-spacing:.06em;}',
    '.shard-title{font-size:11.5px; font-weight:600; color:#f1f5f9; margin-top:.3rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}',
    '.shard-detail{font-size:10px; color:#94a3b8; margin-top:.15rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}',
    '.vault-empty{color:#64748b; font-size:11px; text-align:center; padding:2rem 1rem; line-height:1.7;}',
    '.vault-empty b{display:block; color:#94a3b8; font-size:11.5px; letter-spacing:.18em; text-transform:uppercase; margin-bottom:.4rem;}',
    '.vault-foot{',
    '  display:flex; align-items:center; justify-content:space-between; gap:.5rem;',
    '  padding:.6rem 1.1rem .75rem; border-top:1px solid rgba(148,163,184,.14);',
    '  font-size:9.5px; letter-spacing:.12em; color:#64748b;',
    '}',
    '.vault-foot .db{color:#6ee7b7;}',
    '.crystal-chip{',
    '  cursor:pointer; border-radius:12px; padding:4px 10px; margin:-4px -6px; transition:.25s;',
    '  border:1px solid transparent;',
    '}',
    '.crystal-chip:hover{',
    '  background:rgba(16,185,129,.12); border-color:rgba(52,211,153,.45);',
    '  box-shadow:0 0 22px rgba(52,211,153,.28), inset 0 0 12px rgba(52,211,153,.12);',
    '}',
    '.crystal-chip .gem{color:#34d399; text-shadow:0 0 10px rgba(52,211,153,.9); margin-right:2px;}'
  ].join('');

  function injectCrystalVaultUI() {
    const style = document.createElement('style');
    style.textContent = VAULT_CSS;
    document.head.appendChild(style);

    // Make the CRYSTALLIZED counter a real clickable gem chip (Ability #50)
    const chip = document.getElementById('crystal-count');
    if (chip && chip.parentElement) {
      const wrap = chip.parentElement;
      wrap.classList.add('crystal-chip');
      wrap.setAttribute('title', 'Open the Crystal Vault — inspect records harvested from the Python backend');
      wrap.addEventListener('click', toggleCrystalDrawer);
      if (!wrap.querySelector('.gem')) {
        const gem = document.createElement('span');
        gem.className = 'gem';
        gem.textContent = '\u25C6 ';
        wrap.insertBefore(gem, wrap.firstChild);
      }
    }

    const stage = document.createElement('div');
    stage.id = 'crystal-vault-drawer';
    stage.className = 'vault-stage';
    stage.innerHTML = [
      '<div class="vault-glass">',
      '  <div class="vault-head">',
      '    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:.6rem;">',
      '      <div>',
      '        <div class="vault-eyebrow font-mono-code">SQLITE WAL // HARVEST VAULT</div>',
      '        <div class="vault-title">Crystallized Intelligence Shards</div>',
      '      </div>',
      '      <button id="close-vault-btn" class="vault-close" title="Close vault">\u2715</button>',
      '    </div>',
      '    <div style="margin-top:.6rem; display:flex; align-items:center; justify-content:space-between;">',
      '      <span id="vault-link-badge" class="vault-live font-mono-code"><i></i> LINKING</span>',
      '      <span id="vault-shard-total" class="font-mono-code" style="font-size:9.5px; letter-spacing:.14em; color:#64748b;">0 SHARDS</span>',
      '    </div>',
      '  </div>',
      '  <div id="crystal-records-list" class="vault-list font-mono-code">',
      '    <div class="vault-empty"><b>Vault optics calibrating</b>Waiting for agents to crystallize records\u2026</div>',
      '  </div>',
      '  <div class="vault-foot font-mono-code">',
      '    <span class="db">\u25C8 hojaiga_harvest.db</span>',
      '    <span id="vault-transport">transport: \u2014</span>',
      '  </div>',
      '</div>'
    ].join('');
    document.body.appendChild(stage);
    document.getElementById('close-vault-btn').addEventListener('click', toggleCrystalDrawer);
  }

  function toggleCrystalDrawer() {
    const stage = document.getElementById('crystal-vault-drawer');
    if (!stage) return;
    const opening = !stage.classList.contains('open');
    stage.classList.toggle('open', opening);
    if (opening && !vaultHydrated) hydrateVaultFromSQLite();
  }

  const SHARD_PALETTE = {
    scanner: ['#38bdf8', 'rgba(56,189,248,.20)'],
    llm: ['#a855f7', 'rgba(168,85,247,.20)'],
    verify: ['#2dd4bf', 'rgba(45,212,191,.20)'],
    execution: ['#34d399', 'rgba(52,211,153,.20)'],
    hub: ['#fbbf24', 'rgba(251,191,36,.20)'],
    living: ['#f472b6', 'rgba(244,114,182,.20)']
  };

  function fmtTime(epoch) {
    if (!epoch) return 'LIVE';
    const d = typeof epoch === 'number' ? new Date(epoch * (epoch > 1e12 ? 1 : 1000)) : new Date(epoch);
    return d.toISOString().slice(11, 19);
  }

  function renderVault() {
    const listEl = document.getElementById('crystal-records-list');
    if (!listEl) return;
    if (harvestedRecords.length === 0) {
      listEl.innerHTML = '<div class="vault-empty"><b>Vault optics calibrating</b>Waiting for agents to crystallize records\u2026</div>';
    } else {
      listEl.innerHTML = harvestedRecords.slice(0, 25).map(function (r, i) {
        const pal = SHARD_PALETTE[r.sector] || SHARD_PALETTE.hub;
        return [
          '<div class="vault-shard" style="--shard-c:', pal[0], '; --shard-g:', pal[1], ';">',
          '  <div class="shard-meta"><span>SHARD #', (harvestedRecords.length - i),
          ' &bull; ', String(r.sector || 'hub').toUpperCase(), '</span>',
          '  <span class="t">', r.timestamp || 'LIVE', '</span></div>',
          '  <div class="shard-title">', escapeHtml(r.title || r.event_type || 'RECORD'), '</div>',
          '  <div class="shard-detail">', escapeHtml(r.detail || ''), '</div>',
          '</div>'
        ].join('');
      }).join('');
    }
    const total = document.getElementById('vault-shard-total');
    if (total) total.textContent = harvestedRecords.length + ' SHARD' + (harvestedRecords.length === 1 ? '' : 'S');
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function addRecordToVault(record) {
    if (!record) return;
    harvestedRecords.unshift({
      sector: record.sector || 'hub',
      event_type: record.event_type || 'EVENT',
      title: record.title || record.record_title || record.event_type || 'RECORD',
      detail: record.detail || record.log_line || '',
      timestamp: record.timestamp || fmtTime(record.ts)
    });
    if (harvestedRecords.length > 200) harvestedRecords.length = 200;
    renderVault();
  }

  // Ability #49: hydrate the drawer from the server's real SQLite harvest
  function hydrateVaultFromSQLite() {
    vaultHydrated = true;
    fetch('/api/vault?limit=25').then(function (r) { return r.json(); }).then(function (rows) {
      if (!Array.isArray(rows) || rows.length === 0) { vaultHydrated = false; return; }
      rows.reverse().forEach(function (row) {
        harvestedRecords.unshift({
          sector: row.sector || 'hub',
          event_type: row.event_type || 'EVENT',
          title: row.record_title || row.event_type || 'RECORD',
          detail: row.log_line || '',
          timestamp: fmtTime(row.ts)
        });
      });
      if (harvestedRecords.length > 200) harvestedRecords.length = 200;
      renderVault();
    }).catch(function () { vaultHydrated = false; });
  }

  // ==========================================================================
  // LINK STATE BADGES (HUD pulse dot + vault badge)
  // ==========================================================================
  function setLinkState(mode) {
    transport = mode;
    const dot = document.getElementById('core-pulse-dot');
    const badge = document.getElementById('vault-link-badge');
    const foot = document.getElementById('vault-transport');
    if (mode === 'ws') {
      if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping';
      if (badge) badge.innerHTML = '<i></i> WS LIVE';
      if (foot) foot.textContent = 'transport: ws://8765';
    } else if (mode === 'sse') {
      if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-sky-400 animate-ping';
      if (badge) badge.innerHTML = '<i></i> SSE LIVE';
      if (foot) foot.textContent = 'transport: /api/stream';
    } else {
      if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-rose-400/80';
      if (badge) badge.innerHTML = '<i style="animation:none; background:#fb7185; box-shadow:0 0 8px #fb7185;"></i> OFFLINE';
      if (foot) foot.textContent = 'transport: \u2014';
    }
  }

  // ==========================================================================
  // WEBSOCKET CONNECTION TO server.py (Ability #46/#47 transport)
  // ==========================================================================
  function handlePacket(pkt) {
    if (!pkt || typeof pkt !== 'object') return;
    try {
      HojaigaLivingBus.emit('BACKEND_PACKET', pkt);
    } catch (e) {
      console.warn('[LivingWS] packet dispatch error:', e);
    }
  }

  function connectLivingWebSocket() {
    try {
      ws = new WebSocket(WS_URL);
    } catch (e) {
      connectSSE();
      return;
    }
    let opened = false;

    ws.onopen = function () {
      opened = true;
      setLinkState('ws');
      logLivingEvent('[CNS_WS] Connected to live Hojaiga Python backend', 'text-emerald-300');
      if (!vaultHydrated && document.querySelector('#crystal-vault-drawer.open')) hydrateVaultFromSQLite();
    };

    ws.onmessage = function (event) {
      try {
        handlePacket(JSON.parse(event.data));
      } catch (err) {
        console.warn('[LivingWS] Parse error:', err);
      }
    };

    ws.onerror = function () {
      try { ws.close(); } catch (e) {}
    };

    ws.onclose = function () {
      if (!opened) {
        setLinkState('offline');
        connectSSE();
        return;
      }
      setLinkState('offline');
      logLivingEvent('[CNS_WS] Backend link dropped \u2014 reconnecting in 3s', 'text-amber-300');
      setTimeout(connectLivingWebSocket, 3000);
    };
  }

  function connectSSE() {
    if (!window.EventSource || transport === 'sse') return;
    const es = new EventSource('/api/stream');
    es.onopen = function () {
      setLinkState('sse');
      logLivingEvent('[CNS_SSE] Fallback stream linked to server.py', 'text-sky-300');
    };
    es.onmessage = function (e) {
      try { handlePacket(JSON.parse(e.data)); } catch (err) {}
    };
    es.onerror = function () {
      setLinkState('offline');
      try { es.close(); } catch (e) {}
      setTimeout(connectLivingWebSocket, 3000);
    };
  }

  function sendToBackend(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify(obj)); return true; } catch (e) {}
    }
    if (obj.action === 'SET_LIVING_INTENT') {
      // HTTP fallback (also implemented on server.py)
      try {
        fetch('/api/intent', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ intent: obj.intent })
        });
        return true;
      } catch (e) {}
    }
    return false;
  }

  // ==========================================================================
  // Ability #48: FAULT -> STRUCTURAL DESTABILIZATION + SELF-HEALING BYPASS
  // (real geometry: TubeGeometry reroute, same pipeline as the F-key handler)
  // ==========================================================================
  function destabilizeRegion(idx, reasonLine) {
    if (typeof regions === 'undefined' || idx == null || !regions[idx]) return;
    const reg = regions[idx];
    reg.destabilized = 1.15;
    reg.outerFrame.material.color.setHex(0xf43f5e);
    reg.heart.material.color.setHex(0xf43f5e);
    logLivingEvent('[ALERT] ' + reasonLine, 'text-rose-400 font-semibold');

    setTimeout(function () {
      if (!reg.group || !reg.group.parent) return; // structures rebuilt since
      if (reg.rerouteTube) livingWorld.remove(reg.rerouteTube);
      const bypassMid = reg.basePos.clone().multiplyScalar(0.55).add(new THREE.Vector3(3.5, -3.2, 2.5));
      const bypassCurve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(0, 0, 0), bypassMid, reg.basePos
      ]);
      const mat = makeConduitMat(0xfbbf24);
      const tube = new THREE.Mesh(new THREE.TubeGeometry(bypassCurve, 64, 0.1, 8, false), mat);
      livingWorld.add(tube);
      reg.rerouteTube = tube;
      reg.curve = bypassCurve;
      reg.tube = tube;
      reg.tubeMat = mat;
      reg.outerFrame.material.color.setHex(0xfbbf24);
      reg.heart.material.color.setHex(reg.def.color);
      logLivingEvent('[SELF-HEAL] Rerouted ' + reg.def.name + ' around obstacle', 'text-amber-300');
    }, 950);
  }

  function pulseRegion(idx) {
    if (typeof regions === 'undefined' || idx == null || !regions[idx]) return;
    const reg = regions[idx];
    reg.group.scale.setScalar(1.38);
    if (typeof agents !== 'undefined') {
      agents.forEach(function (a) {
        if (a.regionIndex !== idx) return;
        if (a._baseSpeed == null) a._baseSpeed = a.speed;
        a.speed = a._baseSpeed * 2.6;
        if (a._restoreTimer) clearTimeout(a._restoreTimer);
        a._restoreTimer = setTimeout(function () { a.speed = a._baseSpeed; }, 900);
      });
    }
  }

  function shardLauncher(idx) {
    if (typeof regions === 'undefined' || regions.length === 0) return null;
    if (idx != null && regions[idx]) return regions[idx];
    return regions[Math.floor(Math.random() * regions.length)];
  }

  // ==========================================================================
  // WIRE HojaigaLivingBus EVENTS <-> 3D LIVING ARCHITECTURE
  // ==========================================================================

  // A. Conductor intent -> Python orchestrator's live goal (Ability #46)
  HojaigaLivingBus.on('INTENT_IGNITED', function (payload) {
    const intentText = (payload && payload.intentText) || 'Autonomous Desktop Mission';
    const sent = sendToBackend({ action: 'SET_LIVING_INTENT', intent: intentText, world: 'living-interface' });
    if (sent) {
      logLivingEvent('[DISPATCH] Sent intent to Python Orchestrator: "' + intentText + '"', 'text-sky-300');
    } else {
      logLivingEvent('[DISPATCH] Backend offline \u2014 intent queued locally', 'text-amber-300');
    }
  });

  // B. Manual failure button -> notify Python (Ability #48)
  HojaigaLivingBus.on('FORCE_DESTABILIZE', function () {
    sendToBackend({ action: 'EMP_POPUP_PURGE', world: 'living-interface' });
  });

  // C. Backend telemetry -> 3D regions, reroutes, crystal shards, vault (Ability #47/#49)
  HojaigaLivingBus.on('BACKEND_PACKET', function (pkt) {
    // Auto-ignite if the backend streams while the void is still dormant
    if (!isIntentActive && HANDSHAKE_EVENTS.indexOf(pkt.event_type) === -1) {
      HojaigaLivingBus.emit('INTENT_IGNITED', {
        intentText: pkt.intent ||
          (document.getElementById('intent-input') || {}).value ||
          'Live Hojaiga Autonomous Stream'
      });
    }

    const regIdx = (pkt.sector in SECTOR_TO_REGION_IDX) ? SECTOR_TO_REGION_IDX[pkt.sector] : null;
    const isFault = FAULT_EVENTS.indexOf(pkt.event_type) !== -1;

    // 1. Popup interception / LLM or execution fault -> destabilize + self-heal
    if (isFault) {
      const name = (regIdx != null && regions[regIdx]) ? regions[regIdx].def.name : (pkt.sector || 'hub') + ' sector';
      destabilizeRegion(regIdx, (pkt.log_line || (pkt.event_type + ' on ' + name)));
      if (pkt.log_line && regIdx == null) logLivingEvent(pkt.log_line, 'text-rose-400 font-semibold');
      return;
    }

    // 2. Normal sector activity -> pulse region + boost its agents
    if (regIdx != null && isIntentActive) pulseRegion(regIdx);

    // 3. Successful action / sealed record -> returning emerald shard + vault entry
    if (CRYSTAL_EVENTS.indexOf(pkt.event_type) !== -1) {
      const launcher = shardLauncher(regIdx);
      if (launcher && typeof spawnCrystalShard === 'function') spawnCrystalShard(launcher);
      addRecordToVault({
        sector: pkt.sector || 'hub',
        event_type: pkt.event_type,
        title: pkt.record_title || (pkt.event_type + ' \u00B7 verified'),
        detail: pkt.log_line,
        timestamp: fmtTime(pkt.timestamp || pkt.ts)
      });
    }

    // 4. Stream line into the Living telemetry log
    if (pkt.log_line) {
      const tone = SECTOR_TONES[pkt.sector] || 'text-slate-300';
      logLivingEvent(pkt.log_line, isFault ? 'text-rose-400 font-semibold' : tone);
    }
  });

  // ==========================================================================
  // BOOT
  // ==========================================================================
  function boot() {
    injectCrystalVaultUI();
    renderVault();
    connectLivingWebSocket();
    window.__LWS_READY = true;
  }

  window.__LWS = {
    transport: function () { return transport; },
    records: harvestedRecords,
    openVault: function () {
      const s = document.getElementById('crystal-vault-drawer');
      if (s && !s.classList.contains('open')) toggleCrystalDrawer();
    },
    closeVault: function () {
      const s = document.getElementById('crystal-vault-drawer');
      if (s && s.classList.contains('open')) toggleCrystalDrawer();
    },
    isOpen: function () {
      const s = document.getElementById('crystal-vault-drawer');
      return !!(s && s.classList.contains('open'));
    },
    sendIntent: function (text) {
      return sendToBackend({ action: 'SET_LIVING_INTENT', intent: text });
    }
  };

  if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
