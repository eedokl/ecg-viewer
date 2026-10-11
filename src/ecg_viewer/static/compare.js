// EKG Vergleich — stacked view with toggle switches
const state = {
  list: [],
  enabled: new Set(),   // ids that are rendered
  cache: new Map(),     // id → { meta, samples (Float32Array mV), fs }
};

const PX_PER_SECOND = 220;     // trace horizontal scale
const TRACE_HEIGHT = 200;      // px per row
const MV_RANGE = 1.5;          // visual clip ± mV

const $ = (q) => document.querySelector(q);
const fmtDE = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("de-DE", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
};

async function loadList() {
  const res = await fetch("/api/ecgs");
  state.list = await res.json();
  renderToggles();
}

function renderToggles() {
  const ul = $("#ecgToggleList");
  ul.innerHTML = "";
  for (const e of state.list) {
    const li = document.createElement("li");
    const checked = state.enabled.has(e.id) ? "checked" : "";
    li.innerHTML = `
      <span class="toggle-label">EKG am ${fmtDE(e.recorded_at)}</span>
      <label class="switch">
        <input type="checkbox" data-id="${e.id}" ${checked} />
        <span class="slider"></span>
      </label>
    `;
    li.querySelector("input").addEventListener("change", (ev) => {
      const id = Number(ev.target.dataset.id);
      if (ev.target.checked) state.enabled.add(id);
      else state.enabled.delete(id);
      renderStack();
    });
    ul.appendChild(li);
  }
}

async function ensureLoaded(id) {
  if (state.cache.has(id)) return state.cache.get(id);
  const res = await fetch(`/api/ecgs/${id}?downsample=1`);
  const data = await res.json();
  const entry = {
    meta: data,
    samples: Float32Array.from(data.samples_mv),
    fs: data.sample_rate,
  };
  state.cache.set(id, entry);
  return entry;
}

async function renderStack() {
  const stack = $("#stack");
  stack.innerHTML = "";
  if (state.enabled.size === 0) {
    const hint = document.createElement("div");
    hint.className = "empty-hint";
    hint.textContent = "Wähle links eine oder mehrere Aufzeichnungen aus, um sie hier zu vergleichen.";
    stack.appendChild(hint);
    return;
  }

  const ordered = state.list.filter(e => state.enabled.has(e.id));
  for (const e of ordered) {
    const row = document.createElement("div");
    row.className = "ecg-row";
    row.innerHTML = `
      <div class="ecg-meta-block">
        <div><span class="mk">Name:</span> <b>${e.name || "—"}</b></div>
        <div><span class="mk">Aufzeichnung am:</span> <b>${fmtDE(e.recorded_at)}</b></div>
        <div><span class="mk">Klassifizierung:</span> <b>${e.classification || "—"}</b></div>
        <div><span class="mk">Symptome:</span> <b>${e.symptoms || "keine"}</b></div>
        <div><span class="mk">⌀ Herzfrequenz:</span> <b>${e.avg_hr ? e.avg_hr + " BPM" : "—"}</b></div>
        <div><span class="mk">Gerät:</span> <b>${e.device || "—"}</b></div>
        <div><span class="mk">Messrate:</span> <b>${e.sample_rate ? e.sample_rate + " Hertz" : "—"}</b></div>
        <div><span class="mk">Ableitung:</span> <b>${e.lead || "—"}</b></div>
        <div><span class="mk">Einheit:</span> <b>µV</b></div>
      </div>
      <div class="ecg-trace-scroll">
        <canvas class="ecg-trace-canvas"></canvas>
        <div class="time-axis"></div>
      </div>
    `;
    stack.appendChild(row);

    ensureLoaded(e.id).then(entry => {
      drawTraceCanvas(row.querySelector(".ecg-trace-canvas"), entry);
      drawTimeAxis(row.querySelector(".time-axis"), entry);
    });
  }
}

function drawTraceCanvas(canvas, entry) {
  const { samples, fs } = entry;
  const durationS = samples.length / fs;
  const dpr = window.devicePixelRatio || 1;
  const cssW = Math.max(1, Math.floor(durationS * PX_PER_SECOND));
  const cssH = TRACE_HEIGHT;
  canvas.style.width = cssW + "px";
  canvas.style.height = cssH + "px";
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  // background
  ctx.fillStyle = "#0b0b0d";
  ctx.fillRect(0, 0, cssW, cssH);

  // subtle grid every 0.2s (minor) + 1s (major)
  ctx.strokeStyle = "rgba(255,255,255,0.05)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let t = 0; t <= durationS + 1e-6; t += 0.2) {
    const x = Math.round(t * PX_PER_SECOND) + 0.5;
    ctx.moveTo(x, 0); ctx.lineTo(x, cssH);
  }
  const rows = 4;
  for (let r = 1; r < rows; r++) {
    const y = Math.round((r / rows) * cssH) + 0.5;
    ctx.moveTo(0, y); ctx.lineTo(cssW, y);
  }
  ctx.stroke();

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.beginPath();
  for (let t = 0; t <= durationS + 1e-6; t += 1) {
    const x = Math.round(t * PX_PER_SECOND) + 0.5;
    ctx.moveTo(x, 0); ctx.lineTo(x, cssH);
  }
  ctx.stroke();

  // trace
  const mid = cssH / 2;
  const pxPerMv = (cssH * 0.45) / MV_RANGE;
  ctx.strokeStyle = "#ff3b30";
  ctx.lineWidth = 1.4;
  ctx.lineJoin = "round";
  ctx.beginPath();
  const step = Math.max(1, Math.floor(samples.length / cssW / 2));
  for (let i = 0; i < samples.length; i += step) {
    let mv = samples[i];
    if (mv > MV_RANGE) mv = MV_RANGE; else if (mv < -MV_RANGE) mv = -MV_RANGE;
    const x = (i / fs) * PX_PER_SECOND;
    const y = mid - mv * pxPerMv;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
}

function drawTimeAxis(el, entry) {
  const durationS = entry.samples.length / entry.fs;
  el.innerHTML = "";
  el.style.width = Math.floor(durationS * PX_PER_SECOND) + "px";
  for (let s = 0; s <= Math.floor(durationS); s++) {
    const tick = document.createElement("span");
    tick.className = "tick";
    tick.style.left = (s * PX_PER_SECOND) + "px";
    tick.textContent = s + "s";
    el.appendChild(tick);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  $("#refreshBtn").onclick = async () => {
    await fetch("/api/refresh", { method: "POST" });
    state.cache.clear();
    await loadList();
    renderStack();
  };
  loadList();
});
