(() => {
  "use strict";

  const state = {
    view: "dashboard",
    tuiPane: "f1",
    defaultViewApplied: false,
    actuators: [],
    actStates: {},
    lastStoreSig: "",
    storeItems: [],
    conceptsRaw: "",
    linksRaw: "",
    pendingRetractId: null,
    visStreaming: true,
    visTimer: null,
    streamSrc: null,
    streamPollTimer: null,
    visInFlight: false,
    visFrameCount: 0,
    visLastClassAt: 0,
    visScene: "auto",
    visBboxesEnabled: true,
    visBoxes: [],
    visCustomSource: null,
    webcamActive: false,
    webcamStream: null,
    webcamRaf: null,
    graph: {
      nodes: [],
      edges: [],
      selectedId: null,
      paused: false,
      animId: null,
    },
    txLines: [],
  };

  const TIER_COLORS = {
    sensory: "#38bdf8",
    episodic: "#f59e0b",
    semantic: "#22c55e",
    concept: "#a855f7",
    retracted: "#ef4444",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function nowTs() {
    return new Date().toLocaleTimeString([], { hour12: false });
  }

  function addTx(msg) {
    state.txLines.unshift(`[${nowTs()}] ${msg}`);
    if (state.txLines.length > 60) state.txLines.length = 60;
    const el = $("cortex-tx-log");
    if (el) el.textContent = state.txLines.join("\n");
  }

  function addVisLog(msg) {
    const el = $("vis-event-log");
    if (!el) return;
    const prev = el.textContent ? el.textContent.split("\n") : [];
    prev.unshift(`[${nowTs()}] ${msg}`);
    if (prev.length > 24) prev.length = 24;
    el.textContent = prev.join("\n");
  }

  function getBootToken() {
    const meta = document.querySelector('meta[name="n8-boot-token"]');
    return meta ? meta.getAttribute("content") || "" : "";
  }

  async function apiGet(url) {
    const tok = getBootToken();
    const headers = tok ? { "X-Na8ve-Token": tok } : {};
    const res = await fetch(url, { cache: "no-store", headers });
    return await res.json();
  }

  async function apiPost(url, payload) {
    const headers = { "Content-Type": "application/json" };
    const tok = getBootToken();
    if (tok) headers["X-Na8ve-Token"] = tok;
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload || {}),
    });
    return await res.json();
  }

  function resolveInitialView() {
    const path = (window.location.pathname || "").toLowerCase();
    const hash = (window.location.hash || "").replace(/^#/, "").toLowerCase();
    for (const cand of [hash, path]) {
      if (cand.includes("vision")) return "vision";
      if (cand.includes("tui") || cand.includes("cortex")) return "tui";
      if (cand.includes("dashboard")) return "dashboard";
    }
    return null;
  }

  function setView(viewName, updateHash = true) {
    if (!["dashboard", "tui", "vision"].includes(viewName)) viewName = "dashboard";
    state.view = viewName;
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.view === viewName);
    });
    document.querySelectorAll(".view-panel").forEach((p) => {
      p.classList.toggle("active", p.id === `view-${viewName}`);
    });
    if (updateHash && window.location.hash !== `#${viewName}`) {
      history.replaceState(null, "", `#${viewName}`);
    }
    if (viewName === "tui") {
      loadStoreSnapshot().then(() => {
        if (state.tuiPane === "f4") ensureGraphLoop();
      });
    }
    if (viewName === "vision") {
      startVisionLoop();
    } else {
      stopVisionLoop();
    }
  }

  function setTuiPane(pane) {
    if (!["f1", "f2", "f3", "f4"].includes(pane)) return;
    state.tuiPane = pane;
    document.querySelectorAll(".tui-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.tui === pane);
    });
    document.querySelectorAll(".tui-pane").forEach((p) => {
      p.classList.toggle("active", p.id === `tui-pane-${pane}`);
    });
    if (pane === "f2" || pane === "f4") {
      loadStoreSnapshot().then(() => {
        if (pane === "f4") ensureGraphLoop();
      });
    }
    if (pane === "f3") {
      refreshSnapshot();
    }
  }

  /* ===================== SNAPSHOT & DASHBOARD ===================== */

  function applySnapshot(data) {
    if (!state.defaultViewApplied) {
      state.defaultViewApplied = true;
      const explicit = resolveInitialView();
      if (explicit) setView(explicit, false);
      else if (data.default_view) setView(data.default_view, false);
    }
    $("hdr-app-name").textContent = data.app_name || "na8ve-os App";

    if (!data.ok) {
      $("pill-link").textContent = `enclave: ${data.err || "error"}`;
      $("pill-link").className = "pill pill-err";
      return;
    }

    const t = data.telemetry || {};
    const linkEl = $("pill-link");
    linkEl.textContent = state.streamSrc ? "enclave: live stream" : "enclave: online";
    linkEl.className = "pill pill-ok";

    $("pill-model").textContent = `model: ${t.model || "bx-1m-l2-t036"}`;
    $("pill-mode").textContent = `mode: ${t.mode || "recurrent"} · int${t.width || 32}`;
    const shortSha = (t.state_sha256 || "").slice(0, 12) || "--";
    $("pill-sha").textContent = `sha: ${shortSha}`;
    $("tui-chat-sha").textContent = `state: ${shortSha}`;

    // Telemetry KPIs
    const periphs = t.peripherals || [];
    const chip = periphs.find((p) => p.name === "chip") || {};
    $("kpi-soc").textContent = `${chip.soc || "QRB2210"} · ${chip.temp_c || "--"} °C`;
    $("kpi-soc-sub").textContent = `${chip.arch || "aarch64"} · ${chip.cores || "4"} cores @ ${chip.freq_mhz || "2000"} MHz`;

    const st = t.store || {};
    $("kpi-store-live").textContent = `${st.live || 0} live (${st.retracted || 0} ret)`;
    $("kpi-store-sub").textContent = `sensory: ${st.sensory || 0} · episodic: ${st.episodic || 0} · semantic: ${st.semantic || 0}`;

    const doms = t.domains || [];
    $("kpi-domains").textContent = `${doms.length} pVM domain${doms.length === 1 ? "" : "s"}`;
    $("kpi-audit").textContent = `audit seq: ${t.audit_seq || 0}`;

    const camP = periphs.find((p) => p.name === "camera") || {};
    $("kpi-cam").textContent = `${camP.view || 72}x${camP.view || 72} view`;
    $("kpi-cam-sub").textContent = t.cam_probe || `${camP.sensor || "UnoQ-QRB2210-Cam"} · metadata-only`;

    // Readings
    renderReadings(t.readings || []);

    // Peripherals table
    renderPeripherals(periphs);

    // Actuators (merge live states from enclave telemetry)
    state.actStates = t.act_states || {};
    state.actuators = data.actuators || [];
    $("dash-reserved-pins").textContent = `reserved: ${data.reserved_pins || "7..21,26..42,47..48"}`;
    renderActuators($("dash-act-grid"));
    renderActuators($("f3-act-grid"));

    // Raw os-info + F3 dump
    const infoText = (t.os_info_lines || []).join("\n") || "No os-info reported";
    $("dash-os-info").textContent = infoText;
    $("f3-device-dump").textContent = [
      "=== os-info ===",
      infoText,
      "",
      "=== live sensory readings ===",
      ...(t.readings || []).map((r) => `${r.kind || r.subject || "sensor"}: ${Object.entries(r).filter(([k]) => k !== "kind" && k !== "subject").map(([k, v]) => `${k}=${v}`).join(" ")}`),
      "",
      "=== peripherals ===",
      ...periphs.map((p) => `${p.name}: ok=${p.ok || "1"} ${Object.entries(p).filter(([k]) => k !== "name" && k !== "ok").map(([k, v]) => `${k}=${v}`).join(" ")}`),
      "",
      "=== acts ===",
      ...(t.acts_lines || []),
    ].join("\n");

    const storeSig = `${st.total || 0}:${st.live || 0}:${st.retracted || 0}:${shortSha}:${t.audit_seq || 0}`;
    if (state.lastStoreSig && state.lastStoreSig !== storeSig) {
      loadStoreSnapshot();
    }
    state.lastStoreSig = storeSig;
  }

  async function refreshSnapshot() {
    try {
      const data = await apiGet("/api/snapshot");
      applySnapshot(data);
    } catch (err) {
      $("pill-link").textContent = "enclave: unreachable";
      $("pill-link").className = "pill pill-err";
    }
  }

  function renderReadings(readings) {
    const el = $("dash-readings");
    el.innerHTML = "";
    if (!readings.length) {
      const note = document.createElement("div");
      note.className = "empty-note";
      note.textContent = "No active sensor readings reported.";
      el.appendChild(note);
      return;
    }
    for (const r of readings) {
      const tile = document.createElement("div");
      tile.className = "reading-tile";
      const k = document.createElement("div");
      k.className = "reading-kind";
      k.textContent = r.kind || r.subject || "sensor";
      const v = document.createElement("div");
      v.className = "reading-vals";
      v.textContent = Object.entries(r)
        .filter(([key]) => key !== "kind" && key !== "subject")
        .map(([key, val]) => `${key}=${val}`)
        .join("  ");
      tile.appendChild(k);
      tile.appendChild(v);
      el.appendChild(tile);
    }
  }

  function renderPeripherals(periphs) {
    const tbody = $("dash-periph-table").querySelector("tbody");
    tbody.innerHTML = "";
    for (const p of periphs) {
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.className = "mono";
      tdName.textContent = p.name || "--";
      const tdOk = document.createElement("td");
      tdOk.textContent = p.ok === "1" || p.ok === "true" ? "OK" : String(p.ok || "--");
      tdOk.className = tdOk.textContent === "OK" ? "status-ok-text" : "status-err-text";
      const tdDet = document.createElement("td");
      tdDet.className = "mono";
      tdDet.textContent = Object.entries(p)
        .filter(([k]) => k !== "name" && k !== "ok")
        .map(([k, v]) => `${k}=${v}`)
        .join(" ");
      tr.appendChild(tdName);
      tr.appendChild(tdOk);
      tr.appendChild(tdDet);
      tbody.appendChild(tr);
    }
  }

  function renderActuators(container) {
    if (!container) return;
    container.innerHTML = "";
    for (const act of state.actuators) {
      const curState = act.state || state.actStates[act.name] || (act.states && act.states[0]) || "off";
      const card = document.createElement("div");
      card.className = "act-card";
      const head = document.createElement("div");
      head.className = "act-head";
      const nameSpan = document.createElement("span");
      nameSpan.className = "mono";
      nameSpan.textContent = act.name;
      const metaSpan = document.createElement("span");
      metaSpan.className = "status-inline";
      metaSpan.textContent = `${act.kind} pin:${act.pin} · ${curState}`;
      head.appendChild(nameSpan);
      head.appendChild(metaSpan);

      const btns = document.createElement("div");
      btns.className = "act-btns";
      for (const stVal of act.states || []) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn-ghost btn-xs" + (curState === stVal ? " btn-act-active" : "");
        b.textContent = stVal;
        b.addEventListener("click", () => proposeAct(act.name, [stVal]));
        btns.appendChild(b);
      }
      card.appendChild(head);
      card.appendChild(btns);
      container.appendChild(card);
    }
  }

  async function proposeAct(actId, args) {
    const res = await apiPost("/api/act/propose", { act_id: actId, args });
    const msg = res.approved
      ? `APPROVED ${res.act_id} (${args.join(",")}) · audit #${res.audit_seq}`
      : `REFUSED ${actId}: ${res.err || res.reason}`;
    $("dash-act-status").textContent = msg;
    $("dash-act-status").className = "status-inline " + (res.approved ? "status-ok-text" : "status-err-text");
    const f3Log = $("f3-act-log");
    if (f3Log) {
      f3Log.textContent = `[${nowTs()}] ${msg}\n` + f3Log.textContent;
    }
    addTx(`cx_act: ${msg}`);
    refreshSnapshot();
  }

  /* ===================== TURNS & CONSOLE ===================== */

  async function runTurnRequest(prompt, source = "dash") {
    const model = $("dash-model-select").value;
    const width = $("dash-width-select").value;
    const mode = $("dash-mode-select").value;
    const outBox = $("dash-turn-output");
    if (source === "dash") outBox.textContent = "Executing turn inside enclave...";

    const res = await apiPost("/api/turn", { prompt, model, width, mode, max_bytes: 160 });
    if (!res.ok) {
      const errMsg = `Turn failed: ${res.err}`;
      if (source === "dash") outBox.textContent = errMsg;
      appendChatMsg("sys", errMsg);
      return;
    }

    const actNote = res.proposed_act && res.proposed_act !== "none" ? ` · act=${res.proposed_act}` : "";
    const summary = `[${res.model} · ${res.mode} · int${res.width} · ${res.latency_ms}ms${actNote}]\n${res.reply}\nworking_state=${res.state_sha256}`;
    if (source === "dash") outBox.textContent = summary;

    appendChatMsg("bot", `${res.reply}\n(${res.model} int${res.width}, ${res.latency_ms} ms${actNote}, state=${String(res.state_sha256).slice(0, 12)})`);
    if (actNote) {
      $("dash-act-status").textContent = `ENCLAVE TURN: ${res.proposed_act}`;
      $("dash-act-status").className = "status-inline status-ok-text";
      const f3Log = $("f3-act-log");
      if (f3Log) {
        f3Log.textContent = `[${nowTs()}] F1 TURN -> ${res.proposed_act}\n` + f3Log.textContent;
      }
    }
    $("pill-sha").textContent = `sha: ${String(res.state_sha256).slice(0, 12)}`;
    $("tui-chat-sha").textContent = `state: ${String(res.state_sha256).slice(0, 12)}`;
    $("trace-ms").textContent = `${res.latency_ms} ms`;
    $("cortex-turn-trace").textContent = [
      `prompt: ${prompt}`,
      `model: ${res.model} (${res.mode}, int${res.width})`,
      `latency_ms: ${res.latency_ms}`,
      `state_sha256: ${res.state_sha256}`,
      `proposed_act: ${res.proposed_act || "none"}`,
      `reply: ${res.reply}`,
    ].join("\n");
    addTx(`turn: ${res.model} int${res.width} (${res.latency_ms}ms) sha=${String(res.state_sha256).slice(0, 10)}`);
    await Promise.all([refreshSnapshot(), loadStoreSnapshot()]);
  }

  function appendChatMsg(role, text) {
    const feed = $("tui-chat-feed");
    if (!feed) return;
    const div = document.createElement("div");
    div.className = `chat-msg ${role}`;
    div.textContent = text;
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
  }

  async function execTuiCommand(cmd) {
    const term = $("tui-term-out");
    term.textContent = `$ ${cmd}\n...`;
    const res = await apiPost("/api/tui/exec", { cmd });
    if (res.ok) {
      term.textContent = `$ ${cmd}\n${res.output || "(empty)"}`;
      addTx(`tui: ${cmd}`);
      await Promise.all([refreshSnapshot(), loadStoreSnapshot()]);
    } else {
      term.textContent = `$ ${cmd}\nERR: ${res.err || "refused"} ${res.detail || ""}`;
    }
  }

  /* ===================== MEMORY STORE & <dialog> RETRACTION ===================== */

  async function loadStoreSnapshot() {
    const tier = $("mem-filter-tier") ? $("mem-filter-tier").value : "";
    const res = await apiGet(`/api/store?limit=64&include_retracted=1&tier=${encodeURIComponent(tier)}`);
    if (!res.ok) return;

    state.storeItems = res.items || [];
    state.conceptsRaw = res.concepts_raw || "";
    state.linksRaw = res.links_raw || "";

    const tbody = $("mem-store-table").querySelector("tbody");
    tbody.innerHTML = "";
    for (const item of state.storeItems) {
      const tr = document.createElement("tr");
      if (!item.live) tr.className = "tr-retracted";

      const tdId = document.createElement("td");
      tdId.className = "mono";
      tdId.textContent = `#${item.id}`;

      const tdTier = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = `tier-pill tier-${item.tier}`;
      badge.textContent = item.tier;
      tdTier.appendChild(badge);

      const tdImp = document.createElement("td");
      tdImp.className = "mono";
      tdImp.textContent = Number(item.importance).toFixed(2);

      const tdStatus = document.createElement("td");
      tdStatus.className = "mono " + (item.live ? "status-ok-text" : "status-err-text");
      tdStatus.textContent = item.live ? "LIVE" : "RETRACTED";

      const tdText = document.createElement("td");
      tdText.textContent = item.text;

      const tdAct = document.createElement("td");
      if (item.live) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn-danger-outline btn-xs";
        b.textContent = "Retract";
        b.addEventListener("click", () => openRetractDialog(item.id, item.text));
        tdAct.appendChild(b);
      } else {
        tdAct.textContent = "--";
      }

      tr.append(tdId, tdTier, tdImp, tdStatus, tdText, tdAct);
      tbody.appendChild(tr);
    }

    rebuildGraphModel();
  }

  function openRetractDialog(memoryId, previewText) {
    state.pendingRetractId = memoryId;
    const dlg = $("retract-dialog");
    $("retract-dialog-desc").textContent =
      `Unconditionally retract memory #${memoryId} ("${String(previewText || "").slice(0, 80)}")? ` +
      `Superseded memories remain excluded from active recall and working state.`;
    if (typeof dlg.showModal === "function") dlg.showModal();
    else if (window.confirm($("retract-dialog-desc").textContent)) confirmRetract();
  }

  async function confirmRetract() {
    const memoryId = state.pendingRetractId;
    if (!memoryId) return;
    const cls = $("retract-class-select").value;
    const res = await apiPost("/api/memory/retract", {
      memory_id: memoryId,
      retraction_class: cls,
    });
    const dlg = $("retract-dialog");
    if (dlg.open) dlg.close();
    state.pendingRetractId = null;

    if (res.ok) {
      addTx(`retract #${memoryId} (${cls}) sha=${String(res.state_sha256).slice(0, 10)}`);
      $("insp-actions").style.display = "none";
      await Promise.all([loadStoreSnapshot(), refreshSnapshot()]);
    }
  }

  /* ===================== F4 CORTEX FORCE GRAPH ===================== */

  function rebuildGraphModel() {
    const prevPos = new Map();
    for (const n of state.graph.nodes) prevPos.set(n.id, { x: n.x, y: n.y, vx: n.vx, vy: n.vy });

    const canvas = $("cortex-canvas");
    const w = canvas.width || 760;
    const h = canvas.height || 430;
    const nodes = [];
    const edges = [];

    state.storeItems.forEach((item, idx) => {
      const nid = `mem:${item.id}`;
      const old = prevPos.get(nid);
      const angle = (idx / Math.max(1, state.storeItems.length)) * Math.PI * 2;
      nodes.push({
        id: nid,
        rawId: item.id,
        kind: item.live ? item.tier : "retracted",
        tier: item.tier,
        live: Boolean(item.live),
        label: `#${item.id} ${String(item.text).slice(0, 18)}`,
        fullText: item.text,
        importance: item.importance,
        x: old ? old.x : w * 0.5 + Math.cos(angle) * (90 + (idx % 3) * 45),
        y: old ? old.y : h * 0.5 + Math.sin(angle) * (70 + (idx % 3) * 35),
        vx: old ? old.vx : 0,
        vy: old ? old.vy : 0,
      });
    });

    // Parse enclave concept nodes (`c <id> <name>` or `concept ...`) if exported
    const cLines = state.conceptsRaw.split("\n").map((s) => s.trim()).filter(Boolean);
    const conceptIds = new Set();
    cLines.forEach((ln, idx) => {
      if (ln.startsWith("OK ") || ln.startsWith("ERR ")) return;
      const m = ln.match(/c\s+(\d+)\s+(.+)/);
      if (m) {
        const cid = `con:${m[1]}`;
        conceptIds.add(cid);
        const old = prevPos.get(cid);
        nodes.push({
          id: cid,
          rawId: Number(m[1]),
          kind: "concept",
          tier: "concept",
          live: true,
          label: m[2].slice(0, 20),
          fullText: ln,
          importance: 0.7,
          x: old ? old.x : w * 0.5 + Math.cos(idx * 1.1) * 140,
          y: old ? old.y : h * 0.5 + Math.sin(idx * 1.1) * 110,
          vx: old ? old.vx : 0,
          vy: old ? old.vy : 0,
        });
      }
    });

    // Parse links (`l <src> <dst>`) or synthesize tier clusters between adjacent live nodes
    const lLines = state.linksRaw.split("\n").map((s) => s.trim()).filter(Boolean);
    for (const ln of lLines) {
      const m = ln.match(/(\d+)\s*->\s*(\d+)|l\s+(\d+)\s+(\d+)/);
      if (m) {
        const a = m[1] || m[3];
        const b = m[2] || m[4];
        const src = conceptIds.has(`con:${a}`) ? `con:${a}` : `mem:${a}`;
        const dst = conceptIds.has(`con:${b}`) ? `con:${b}` : `mem:${b}`;
        edges.push({ src, dst });
      }
    }
    if (edges.length === 0 && nodes.length > 1) {
      const byTier = {};
      for (const n of nodes) {
        if (!byTier[n.tier]) byTier[n.tier] = [];
        byTier[n.tier].push(n.id);
      }
      for (const list of Object.values(byTier)) {
        for (let i = 1; i < list.length; i++) edges.push({ src: list[i - 1], dst: list[i] });
      }
    }

    state.graph.nodes = nodes;
    state.graph.edges = edges;
  }

  function stepAndDrawGraph() {
    const canvas = $("cortex-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    const nodes = state.graph.nodes;
    const edges = state.graph.edges;
    const byId = new Map(nodes.map((n) => [n.id, n]));

    if (!state.graph.paused && nodes.length > 0) {
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        a.vx += (w * 0.5 - a.x) * 0.0025;
        a.vy += (h * 0.5 - a.y) * 0.0025;
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let d2 = dx * dx + dy * dy + 25;
          if (d2 < 24000) {
            const f = 520 / d2;
            const d = Math.sqrt(d2);
            dx /= d; dy /= d;
            a.vx += dx * f; a.vy += dy * f;
            b.vx -= dx * f; b.vy -= dy * f;
          }
        }
      }
      for (const e of edges) {
        const a = byId.get(e.src);
        const b = byId.get(e.dst);
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 88) * 0.015;
        a.vx += (dx / dist) * force;
        a.vy += (dy / dist) * force;
        b.vx -= (dx / dist) * force;
        b.vy -= (dy / dist) * force;
      }
      for (const n of nodes) {
        n.vx *= 0.84;
        n.vy *= 0.84;
        n.x = Math.max(24, Math.min(w - 24, n.x + n.vx));
        n.y = Math.max(24, Math.min(h - 24, n.y + n.vy));
      }
    }

    const cs = getComputedStyle(document.documentElement);
    const colBg = (cs.getPropertyValue("--surface-console") || "#f4f7fb").trim();
    const colRule = (cs.getPropertyValue("--rule") || "#cddae6").trim();
    const colInk = (cs.getPropertyValue("--ink") || "#0b1a24").trim();
    const colMuted = (cs.getPropertyValue("--muted") || "#5b7284").trim();

    ctx.fillStyle = colBg;
    ctx.fillRect(0, 0, w, h);

    // Subtle reticle grid matching Cortex instrument aesthetic
    ctx.strokeStyle = colRule;
    ctx.globalAlpha = 0.45;
    ctx.lineWidth = 1;
    for (let x = 40; x < w; x += 40) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    }
    for (let y = 40; y < h; y += 40) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    ctx.globalAlpha = 1.0;

    // Edges
    ctx.strokeStyle = colMuted;
    ctx.globalAlpha = 0.45;
    ctx.lineWidth = 1.4;
    for (const e of edges) {
      const a = byId.get(e.src);
      const b = byId.get(e.dst);
      if (!a || !b) continue;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    ctx.globalAlpha = 1.0;

    if (nodes.length === 0) {
      ctx.fillStyle = colMuted;
      ctx.font = "13px ui-monospace, monospace";
      ctx.fillText("No memories in store yet. Add memories in F2 or run a turn.", 28, h * 0.5);
    }

    // Nodes
    ctx.font = "11px ui-monospace, monospace";
    for (const n of nodes) {
      const color = TIER_COLORS[n.kind] || "#0d7ea6";
      const radius = n.id === state.graph.selectedId ? 11 : 8;
      ctx.beginPath();
      ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      if (n.id === state.graph.selectedId) {
        ctx.strokeStyle = "#ffd400";
        ctx.lineWidth = 2.5;
        ctx.stroke();
      }
      ctx.fillStyle = n.live ? colInk : colMuted;
      ctx.fillText(n.label, n.x + 12, n.y + 4);
    }

    if (state.view === "tui" && state.tuiPane === "f4") {
      state.graph.animId = requestAnimationFrame(stepAndDrawGraph);
    } else {
      state.graph.animId = null;
    }
  }

  function ensureGraphLoop() {
    if (!state.graph.animId) {
      state.graph.animId = requestAnimationFrame(stepAndDrawGraph);
    }
  }

  function selectGraphNode(node) {
    state.graph.selectedId = node.id;
    $("insp-id").textContent = node.id;
    $("insp-body").textContent = [
      `id: ${node.id}`,
      `tier: ${node.tier}`,
      `liveness: ${node.live ? "LIVE" : "RETRACTED"}`,
      `importance: ${Number(node.importance).toFixed(2)}`,
      `text: ${node.fullText}`,
    ].join("\n");
    const actBox = $("insp-actions");
    if (node.id.startsWith("mem:") && node.live) {
      actBox.style.display = "block";
      $("btn-insp-retract").onclick = () => openRetractDialog(node.rawId, node.fullText);
    } else {
      actBox.style.display = "none";
    }
  }

  /* ===================== VISION LIVE VIEW & WEBCAM BOUNDING BOXES ===================== */

  function drawBoundingBoxes(ctx, W, H, boxes) {
    if (!state.visBboxesEnabled || !Array.isArray(boxes) || !boxes.length) return;
    ctx.save();
    for (let idx = boxes.length - 1; idx >= 0; idx--) {
      const box = boxes[idx];
      if (!box) continue;
      const x = Math.max(2, Math.min(W - 8, Number(box.x || 0) * W));
      const y = Math.max(2, Math.min(H - 8, Number(box.y || 0) * H));
      const w = Math.max(12, Math.min(W - x - 2, Number(box.w || 0.2) * W));
      const h = Math.max(12, Math.min(H - y - 2, Number(box.h || 0.2) * H));
      const isPrimary = idx === 0;
      const col = isPrimary ? "#10b981" : idx === 1 ? "#f59e0b" : "#38bdf8";

      ctx.strokeStyle = col;
      ctx.lineWidth = isPrimary ? 2.5 : 1.5;
      ctx.setLineDash(isPrimary ? [] : [5, 4]);
      ctx.strokeRect(x, y, w, h);

      if (isPrimary) {
        const arm = Math.min(14, w * 0.28, h * 0.28);
        ctx.setLineDash([]);
        ctx.lineWidth = 3.5;
        ctx.beginPath();
        ctx.moveTo(x, y + arm); ctx.lineTo(x, y); ctx.lineTo(x + arm, y);
        ctx.moveTo(x + w - arm, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + arm);
        ctx.moveTo(x, y + h - arm); ctx.lineTo(x, y + h); ctx.lineTo(x + arm, y + h);
        ctx.moveTo(x + w - arm, y + h); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w, y + h - arm);
        ctx.stroke();
      }

      const pct = Math.round(Number(box.prob || 0) * 100);
      const tagText = `${String(box.label || "object")} ${pct}%`;
      ctx.font = isPrimary ? "600 12px ui-monospace, monospace" : "500 10.5px ui-monospace, monospace";
      const tw = ctx.measureText(tagText).width + 10;
      const th = isPrimary ? 20 : 16;
      const ty = y - th >= 2 ? y - th : Math.min(H - th - 2, y + 2);
      const tx = Math.min(W - tw - 2, Math.max(2, x));

      ctx.fillStyle = isPrimary ? "rgba(6, 78, 59, 0.88)" : "rgba(15, 23, 42, 0.78)";
      ctx.fillRect(tx, ty, tw, th);
      ctx.fillStyle = "#ffffff";
      ctx.fillText(tagText, tx + 5, ty + (isPrimary ? 14 : 11.5));
    }
    ctx.restore();
  }

  function encodeSourceToRgb565B64(sourceEl) {
    if (!sourceEl) return null;
    const sw = sourceEl.videoWidth || sourceEl.naturalWidth || sourceEl.width || 0;
    const sh = sourceEl.videoHeight || sourceEl.naturalHeight || sourceEl.height || 0;
    if (!sw || !sh) return null;
    const sSize = Math.min(sw, sh);
    const sx = Math.floor((sw - sSize) * 0.5);
    const sy = Math.floor((sh - sSize) * 0.5);

    const W = 72;
    const H = 72;
    const off = document.createElement("canvas");
    off.width = W;
    off.height = H;
    const octx = off.getContext("2d");
    octx.drawImage(sourceEl, sx, sy, sSize, sSize, 0, 0, W, H);
    const data = octx.getImageData(0, 0, W, H).data;
    const buf = new Uint8Array(W * H * 2);
    for (let i = 0, p = 0; i < W * H; i++, p += 4) {
      const r5 = (data[p] >> 3) & 0x1f;
      const g6 = (data[p + 1] >> 2) & 0x3f;
      const b5 = (data[p + 2] >> 3) & 0x1f;
      const c = (r5 << 11) | (g6 << 5) | b5;
      buf[i * 2] = (c >> 8) & 0xff;
      buf[i * 2 + 1] = c & 0xff;
    }
    let bin = "";
    for (let i = 0; i < buf.length; i += 0x2000) {
      bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x2000));
    }
    return btoa(bin);
  }

  function drawCustomSourceFrame(sourceEl) {
    if (!sourceEl) return;
    const sw = sourceEl.videoWidth || sourceEl.naturalWidth || sourceEl.width || 0;
    const sh = sourceEl.videoHeight || sourceEl.naturalHeight || sourceEl.height || 0;
    if (!sw || !sh) return;
    const sSize = Math.min(sw, sh);
    const sx = Math.floor((sw - sSize) * 0.5);
    const sy = Math.floor((sh - sSize) * 0.5);
    const canvas = $("vision-canvas");
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(sourceEl, sx, sy, sSize, sSize, 0, 0, canvas.width, canvas.height);

    const S = 6;
    ctx.save();
    ctx.strokeStyle = "rgba(255, 212, 0, 0.72)";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([7, 5]);
    ctx.strokeRect(4 * S, 4 * S, 64 * S, 64 * S);
    ctx.restore();
    drawBoundingBoxes(ctx, canvas.width, canvas.height, state.visBoxes);
  }

  async function startWebcam() {
    if (state.webcamActive) return true;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      $("vis-frame-meta").textContent = "webcam unavailable — use localhost or Classify Image";
      addVisLog("Browser webcam API unavailable (requires localhost/HTTPS); use 'Classify Image' or scenes 0..5.");
      return false;
    }
    try {
      let stream = null;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment", width: { ideal: 640 }, height: { ideal: 480 } },
          audio: false,
        });
      } catch (_) {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      }
      const vid = $("vis-webcam-video");
      vid.srcObject = stream;
      await vid.play();
      state.webcamStream = stream;
      state.webcamActive = true;
      state.visCustomSource = vid;
      state.visScene = "webcam";
      $("vis-scene-select").value = "webcam";
      $("btn-vis-webcam").textContent = "Stop Webcam";
      $("vis-frame-meta").textContent = "source: live webcam · transient 72x72";
      addVisLog("Live webcam active (frames stay transient; only classifications leave enclave).");

      const tick = () => {
        if (!state.webcamActive) return;
        drawCustomSourceFrame(vid);
        if (state.visStreaming && state.view === "vision" && !state.visInFlight) {
          const now = Date.now();
          if (now - state.visLastClassAt > 650) {
            state.visLastClassAt = now;
            state.visInFlight = true;
            runVisionLook(true).finally(() => { state.visInFlight = false; });
          }
        }
        state.webcamRaf = requestAnimationFrame(tick);
      };
      state.webcamRaf = requestAnimationFrame(tick);
      return true;
    } catch (err) {
      $("vis-frame-meta").textContent = "webcam denied/no device — use Classify Image or scenes 0..5";
      addVisLog(`Webcam denied or unavailable (${err && err.message ? err.message : "no device"}).`);
      return false;
    }
  }

  function stopWebcam() {
    state.webcamActive = false;
    if (state.webcamRaf) {
      cancelAnimationFrame(state.webcamRaf);
      state.webcamRaf = null;
    }
    if (state.webcamStream) {
      try {
        state.webcamStream.getTracks().forEach((tr) => tr.stop());
      } catch (_) {}
      state.webcamStream = null;
    }
    const vid = $("vis-webcam-video");
    if (vid) vid.srcObject = null;
    const btn = $("btn-vis-webcam");
    if (btn) btn.textContent = "Use Webcam";
    if (state.visCustomSource === vid) state.visCustomSource = null;
  }

  function drawPv565Frame(b64, seqNum) {
    const binStr = atob(b64);
    const w = 72;
    const h = 72;
    if (binStr.length < w * h * 2) return;

    const canvas = $("vision-canvas");
    const ctx = canvas.getContext("2d");
    const off = document.createElement("canvas");
    off.width = w;
    off.height = h;
    const octx = off.getContext("2d");
    const img = octx.createImageData(w, h);
    const dst = img.data;

    for (let i = 0, p = 0; i < w * h; i++, p += 2) {
      const c = (binStr.charCodeAt(p) << 8) | binStr.charCodeAt(p + 1);
      const r = ((c >> 11) & 0x1f) * 255 / 31;
      const g = ((c >> 5) & 0x3f) * 255 / 63;
      const b = (c & 0x1f) * 255 / 31;
      const di = i * 4;
      dst[di] = r;
      dst[di + 1] = g;
      dst[di + 2] = b;
      dst[di + 3] = 255;
    }
    octx.putImageData(img, 0, 0);

    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, 0, 0, canvas.width, canvas.height);

    // Draw the #ffd400 dashed 64x64 saccade window (scaled 6x: offset 24, size 384)
    const S = 6;
    ctx.save();
    ctx.strokeStyle = "#ffd400";
    ctx.lineWidth = 2;
    ctx.setLineDash([7, 5]);
    ctx.strokeRect(4 * S, 4 * S, 64 * S, 64 * S);

    // Saccade fixation crosshairs
    ctx.setLineDash([]);
    ctx.lineWidth = 1.5;
    const cx = canvas.width * 0.5 + Math.cos((seqNum || 1) * 0.55) * 32;
    const cy = canvas.height * 0.5 + Math.sin((seqNum || 1) * 0.72) * 32;
    ctx.beginPath();
    ctx.arc(cx, cy, 10, 0, Math.PI * 2);
    ctx.moveTo(cx - 16, cy); ctx.lineTo(cx + 16, cy);
    ctx.moveTo(cx, cy - 16); ctx.lineTo(cx, cy + 16);
    ctx.stroke();
    ctx.restore();

    drawBoundingBoxes(ctx, canvas.width, canvas.height, state.visBoxes);
  }

  async function pullVisionFrame() {
    if (state.visInFlight || state.view !== "vision") return;
    if (state.webcamActive || state.visScene === "webcam") {
      if (state.visCustomSource) drawCustomSourceFrame(state.visCustomSource);
      return;
    }
    state.visInFlight = true;
    try {
      const sceneParam = state.visScene === "auto" ? "" : state.visScene;
      const data = await apiGet(`/api/vision/frame?scene=${encodeURIComponent(sceneParam)}`);
      if (data.ok && data.pv565_b64) {
        drawPv565Frame(data.pv565_b64, data.seq);
        $("vis-frame-meta").textContent = `scene: ${data.scene} · mode: ${data.mode < 0 ? "auto" : "fixed"} · seq: ${data.seq}`;
        state.visFrameCount++;
        const now = Date.now();
        if (now - state.visLastClassAt > 3500) {
          state.visLastClassAt = now;
          runVisionLook(true);
        }
      }
    } finally {
      state.visInFlight = false;
    }
  }

  async function runVisionLook(quiet = false) {
    const model = $("vis-model-select").value;
    const saccades = Number($("vis-saccades-input").value || 8);
    const scene = $("vis-scene-select").value;
    const payload = { model, saccades, scene };
    if (state.webcamActive || (scene === "webcam" && state.visCustomSource)) {
      const b64 = encodeSourceToRgb565B64(state.visCustomSource || $("vis-webcam-video"));
      if (b64) payload.frame_b64 = b64;
    }
    const res = await apiPost("/api/vision/look", payload);
    if (!res.ok) {
      if (!quiet) addVisLog(`look failed: ${res.err}`);
      return;
    }

    const precLabel = res.precision || (Number(res.width) === 32 ? "float32" : `int${res.width}`);
    $("vis-model-pill").textContent = `${res.model} · ${res.mode} · ${precLabel}`;
    $("vis-top1-class").textContent = res.class_name || "--";
    $("vis-top1-conf").textContent = `conf: ${(Number(res.confidence || 0) * 100).toFixed(1)}%`;
    $("vis-top1-lat").textContent = `latency: ${Number(res.latency_ms || 0).toFixed(1)} ms`;
    $("vis-top1-sac").textContent = `saccades: ${res.saccades}`;

    state.visBoxes = Array.isArray(res.boxes) && res.boxes.length
      ? res.boxes
      : (res.bbox ? [{ label: res.class_name, prob: res.confidence, ...res.bbox }] : []);
    if (res.bbox) {
      $("vis-top1-bbox").textContent = `bbox: [${Number(res.bbox.x).toFixed(2)}, ${Number(res.bbox.y).toFixed(2)}, ${Number(res.bbox.w).toFixed(2)}, ${Number(res.bbox.h).toFixed(2)}]`;
    } else {
      $("vis-top1-bbox").textContent = "bbox: --";
    }
    if (state.visCustomSource && (state.webcamActive || scene === "webcam")) {
      drawCustomSourceFrame(state.visCustomSource);
    } else if (!state.webcamActive) {
      const canvas = $("vision-canvas");
      drawBoundingBoxes(canvas.getContext("2d"), canvas.width, canvas.height, state.visBoxes);
    }

    const bars = $("vis-top5-bars");
    bars.innerHTML = "";
    for (const [label, prob] of res.top5 || []) {
      const pct = Math.max(0, Math.min(100, Number(prob) * 100));
      const row = document.createElement("div");
      row.className = "bar-row";
      const lbl = document.createElement("div");
      lbl.className = "bar-label";
      lbl.textContent = label;
      const track = document.createElement("div");
      track.className = "bar-track";
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = `${pct.toFixed(1)}%`;
      track.appendChild(fill);
      const pctEl = document.createElement("div");
      pctEl.className = "bar-pct";
      pctEl.textContent = `${pct.toFixed(1)}%`;
      row.append(lbl, track, pctEl);
      bars.appendChild(row);
    }
    const odom = (res.vx !== null && res.vx !== undefined && res.wz !== null && res.wz !== undefined)
      ? ` vx=${Number(res.vx).toFixed(3)}m/s wz=${Number(res.wz).toFixed(3)}rad/s`
      : "";
    const boxNote = res.bbox ? ` box=(${Number(res.bbox.x).toFixed(2)},${Number(res.bbox.y).toFixed(2)},${Number(res.bbox.w).toFixed(2)},${Number(res.bbox.h).toFixed(2)})` : "";
    addVisLog(`${res.model} ${precLabel} sac=${res.saccades} class=${res.class_name} conf=${(res.confidence * 100).toFixed(1)}%${odom}${boxNote} (${res.latency_ms}ms)`);
  }

  function startVisionLoop() {
    stopVisionLoop();
    if (!state.visStreaming) return;
    pullVisionFrame();
    state.visTimer = setInterval(pullVisionFrame, 260);
  }

  function stopVisionLoop() {
    if (state.visTimer) {
      clearInterval(state.visTimer);
      state.visTimer = null;
    }
  }

  /* ===================== THEME & EXPANDABLE WINDOWS ===================== */

  function applyTheme(theme) {
    const mode = theme === "dark" ? "dark" : "light";
    if (mode === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    const btn = $("btn-theme-toggle");
    if (btn) btn.textContent = mode === "dark" ? "Light Mode" : "Dark Mode";
    try { localStorage.setItem("n8-ui-theme", mode); } catch (_) {}
    if (state.view === "tui" && state.tuiPane === "f4") {
      requestAnimationFrame(stepAndDrawGraph);
    }
  }

  function syncGraphCanvasSize() {
    const wrap = $("cortex-canvas-wrap");
    const canvas = $("cortex-canvas");
    if (!wrap || !canvas) return;
    const rect = wrap.getBoundingClientRect();
    if (rect.width >= 240 && rect.height >= 200) {
      const targetW = Math.round(rect.width);
      const targetH = Math.round(rect.height);
      if (Math.abs(canvas.width - targetW) > 12 || Math.abs(canvas.height - targetH) > 12) {
        canvas.width = targetW;
        canvas.height = targetH;
      }
    }
  }

  function closeAllExpandedWindows() {
    document.querySelectorAll(".card.card-expanded").forEach((c) => {
      c.classList.remove("card-expanded");
      const btn = c.querySelector(".win-expand-btn");
      if (btn) {
        btn.textContent = "\u2922";
        btn.title = "Expand window";
        btn.setAttribute("aria-expanded", "false");
      }
    });
    const bd = $("win-backdrop");
    if (bd) bd.classList.add("hidden");
    requestAnimationFrame(syncGraphCanvasSize);
  }

  function initExpandableWindows() {
    document.querySelectorAll(".card:not(.kpi-card)").forEach((card) => {
      const head = card.querySelector(".card-head");
      if (!head || head.querySelector(".win-expand-btn")) return;

      const tools = document.createElement("div");
      tools.className = "card-head-tools";
      while (head.children.length > 1) {
        tools.appendChild(head.children[1]);
      }

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "win-expand-btn";
      btn.textContent = "\u2922";
      btn.title = "Expand window";
      btn.setAttribute("aria-expanded", "false");
      btn.addEventListener("click", () => {
        const expanding = !card.classList.contains("card-expanded");
        closeAllExpandedWindows();
        if (expanding) {
          card.classList.add("card-expanded");
          btn.textContent = "\u2921";
          btn.title = "Restore window";
          btn.setAttribute("aria-expanded", "true");
          const bd = $("win-backdrop");
          if (bd) bd.classList.remove("hidden");
        }
        requestAnimationFrame(() => {
          syncGraphCanvasSize();
          if (state.view === "tui" && state.tuiPane === "f4") ensureGraphLoop();
        });
      });

      tools.appendChild(btn);
      head.appendChild(tools);
    });

    const bd = $("win-backdrop");
    if (bd) bd.addEventListener("click", closeAllExpandedWindows);

    if (typeof ResizeObserver !== "undefined" && $("cortex-canvas-wrap")) {
      const ro = new ResizeObserver(() => {
        if (state.view === "tui" && state.tuiPane === "f4") syncGraphCanvasSize();
      });
      ro.observe($("cortex-canvas-wrap"));
    }
  }

  /* ===================== WIRE EVENTS ===================== */

  function init() {
    let savedTheme = "light";
    try {
      savedTheme = localStorage.getItem("n8-ui-theme") || "light";
    } catch (_) {}
    applyTheme(savedTheme);
    initExpandableWindows();

    const themeBtn = $("btn-theme-toggle");
    if (themeBtn) {
      themeBtn.addEventListener("click", () => {
        const isDark = document.documentElement.getAttribute("data-theme") === "dark";
        applyTheme(isDark ? "light" : "dark");
      });
    }

    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => setView(btn.dataset.view));
    });

    document.querySelectorAll(".tui-tab").forEach((btn) => {
      btn.addEventListener("click", () => setTuiPane(btn.dataset.tui));
    });

    window.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") {
        closeAllExpandedWindows();
        return;
      }
      if (state.view !== "tui") return;
      if (ev.key === "F1") { ev.preventDefault(); setTuiPane("f1"); }
      else if (ev.key === "F2") { ev.preventDefault(); setTuiPane("f2"); }
      else if (ev.key === "F3") { ev.preventDefault(); setTuiPane("f3"); }
      else if (ev.key === "F4") { ev.preventDefault(); setTuiPane("f4"); }
    });

    $("btn-refresh-all").addEventListener("click", () => {
      refreshSnapshot();
      loadStoreSnapshot();
    });

    $("dash-turn-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const inp = $("dash-turn-prompt");
      const val = inp.value.trim();
      if (!val) return;
      runTurnRequest(val, "dash");
    });

    $("btn-test-reserved-pin").addEventListener("click", () => {
      proposeAct("gpio21", ["on"]);
    });

    $("tui-chat-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const inp = $("tui-chat-input");
      const val = inp.value.trim();
      if (!val) return;
      inp.value = "";
      appendChatMsg("user", val);
      runTurnRequest(val, "tui");
    });

    $("tui-term-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const inp = $("tui-term-input");
      const cmd = inp.value.trim();
      if (cmd) execTuiCommand(cmd);
    });

    document.querySelectorAll("#tui-cmd-chips .chip").forEach((ch) => {
      ch.addEventListener("click", () => {
        $("tui-term-input").value = ch.dataset.cmd;
        execTuiCommand(ch.dataset.cmd);
      });
    });

    $("mem-add-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const text = $("mem-add-text").value.trim();
      const tier = $("mem-add-tier").value;
      const importance = Number($("mem-add-imp").value || 0.5);
      if (!text) return;
      const res = await apiPost("/api/memory/remember", { text, tier, importance });
      if (res.ok) {
        $("mem-add-text").value = "";
        addTx(`remember #${res.memory_id} [${tier}] "${text.slice(0, 40)}"`);
        await Promise.all([loadStoreSnapshot(), refreshSnapshot()]);
      }
    });

    $("mem-recall-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const query = $("mem-recall-query").value.trim();
      const max_hops = Number($("mem-recall-hops").value || 2);
      const res = await apiPost("/api/memory/recall", { query, limit: 12, max_hops });
      const fTrunc = $("flag-truncated");
      const fHop = $("flag-hop");
      const fFan = $("flag-fan");
      fTrunc.textContent = `truncated: ${Boolean(res.truncated)}`;
      fHop.textContent = `hopCapped: ${Boolean(res.hopCapped)}`;
      fFan.textContent = `fanOutClipped: ${Boolean(res.fanOutClipped)}`;
      fTrunc.classList.toggle("tripped", Boolean(res.truncated));
      fHop.classList.toggle("tripped", Boolean(res.hopCapped));
      fFan.classList.toggle("tripped", Boolean(res.fanOutClipped));

      const box = $("mem-recall-results");
      box.innerHTML = "";
      for (const item of res.items || []) {
        const div = document.createElement("div");
        div.className = "reading-tile mt-12";
        div.textContent = `#${item.id} [${item.tier}] (imp=${Number(item.importance).toFixed(2)}): ${item.text}`;
        box.appendChild(div);
      }
      addTx(`recall q="${query}" hits=${(res.items || []).length}`);
    });

    $("mem-filter-tier").addEventListener("change", loadStoreSnapshot);
    $("btn-reload-store").addEventListener("click", loadStoreSnapshot);
    $("btn-f3-refresh").addEventListener("click", refreshSnapshot);

    $("btn-retract-cancel").addEventListener("click", () => {
      $("retract-dialog").close();
      state.pendingRetractId = null;
    });
    $("btn-retract-confirm").addEventListener("click", confirmRetract);

    $("btn-graph-pause").addEventListener("click", () => {
      state.graph.paused = !state.graph.paused;
      $("btn-graph-pause").textContent = state.graph.paused ? "Resume Physics" : "Pause Physics";
    });
    $("btn-graph-reset").addEventListener("click", () => {
      state.graph.nodes = [];
      rebuildGraphModel();
      ensureGraphLoop();
    });
    $("btn-graph-sync").addEventListener("click", loadStoreSnapshot);

    $("cortex-canvas").addEventListener("click", (ev) => {
      const canvas = $("cortex-canvas");
      const rect = canvas.getBoundingClientRect();
      const x = ((ev.clientX - rect.left) / rect.width) * canvas.width;
      const y = ((ev.clientY - rect.top) / rect.height) * canvas.height;
      let hit = null;
      let best = 24 * 24;
      for (const n of state.graph.nodes) {
        const dx = n.x - x;
        const dy = n.y - y;
        const d2 = dx * dx + dy * dy;
        if (d2 < best) { best = d2; hit = n; }
      }
      if (hit) selectGraphNode(hit);
    });

    $("btn-vis-look").addEventListener("click", () => runVisionLook(false));
    $("btn-vis-webcam").addEventListener("click", async () => {
      if (state.webcamActive) {
        stopWebcam();
        state.visCustomSource = null;
        state.visScene = "auto";
        $("vis-scene-select").value = "auto";
        await pullVisionFrame();
      } else {
        await startWebcam();
      }
    });
    $("btn-vis-upload").addEventListener("click", () => {
      $("vis-file-input").click();
    });
    $("vis-file-input").addEventListener("change", (ev) => {
      const file = ev.target.files && ev.target.files[0];
      if (!file) return;
      stopWebcam();
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = async () => {
        state.visCustomSource = img;
        state.visScene = "webcam";
        $("vis-scene-select").value = "webcam";
        $("vis-frame-meta").textContent = `image: ${file.name} · transient 72x72`;
        drawCustomSourceFrame(img);
        await runVisionLook(false);
        URL.revokeObjectURL(url);
      };
      img.src = url;
    });
    $("chk-vis-bboxes").addEventListener("change", () => {
      state.visBboxesEnabled = Boolean($("chk-vis-bboxes").checked);
      if (state.visCustomSource && (state.webcamActive || state.visScene === "webcam")) {
        drawCustomSourceFrame(state.visCustomSource);
      } else {
        pullVisionFrame();
      }
    });
    $("btn-vis-stream").addEventListener("click", () => {
      state.visStreaming = !state.visStreaming;
      $("btn-vis-stream").textContent = state.visStreaming ? "Pause Live Stream" : "Resume Live Stream";
      if (state.visStreaming) startVisionLoop();
      else stopVisionLoop();
    });
    $("vis-scene-select").addEventListener("change", async () => {
      state.visScene = $("vis-scene-select").value;
      if (state.visScene === "webcam") {
        await startWebcam();
      } else {
        stopWebcam();
        state.visCustomSource = null;
        await apiGet(`/api/vision/frame?scene=${encodeURIComponent(state.visScene)}`);
        await pullVisionFrame();
        await runVisionLook(false);
      }
    });

    const initial = resolveInitialView();
    if (initial) setView(initial, false);

    function startTelemetryStream() {
      if (state.streamSrc) {
        try { state.streamSrc.close(); } catch (_) {}
        state.streamSrc = null;
      }
      if (typeof EventSource !== "undefined") {
        const tok = getBootToken();
        const url = tok ? `/api/stream?token=${encodeURIComponent(tok)}` : "/api/stream";
        const es = new EventSource(url);
        state.streamSrc = es;
        es.addEventListener("telemetry", (ev) => {
          if (document.hidden) return;
          try {
            const payload = JSON.parse(ev.data);
            applySnapshot(payload);
          } catch (_) {}
        });
        es.onerror = () => {
          try { es.close(); } catch (_) {}
          state.streamSrc = null;
          setTimeout(() => {
            if (!state.streamSrc) startTelemetryStream();
          }, 3000);
        };
      }
    }

    refreshSnapshot();
    loadStoreSnapshot();
    startTelemetryStream();
    state.streamPollTimer = setInterval(() => {
      if (!document.hidden && !state.streamSrc) refreshSnapshot();
    }, 1500);
  }

  document.addEventListener("DOMContentLoaded", init);
})();

