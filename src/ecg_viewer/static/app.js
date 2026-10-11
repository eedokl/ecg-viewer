// ECG Viewer — iPhone-style display
const state = {
  list: [],
  current: null,
  samples: null,
  fs: 512,
  selectSeq: 0,
  renderedAt: null,
};

const $ = (q) => document.querySelector(q);
const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric",
                                     hour: "2-digit", minute: "2-digit" });
};

async function loadList() {
  const from = $("#filterFrom").value;
  const to = $("#filterTo").value;
  const params = new URLSearchParams();
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  const res = await fetch("/api/ecgs?" + params.toString());
  state.list = await res.json();
  renderList();
  if (state.list.length && (!state.current || !state.list.find(e => e.id === state.current.id))) {
    selectEcg(state.list[0].id);
  } else if (!state.list.length) {
    state.current = null;
    state.samples = null;
    renderMeta();
    drawECG();
  }
}

function renderList() {
  const ul = $("#ecgList");
  ul.innerHTML = "";
  for (const e of state.list) {
    const li = document.createElement("li");
    if (state.current && state.current.id === e.id) li.classList.add("active");
    li.innerHTML = `
      <div class="date">${fmtDate(e.recorded_at)}</div>
      <div class="cls">${e.classification || "—"}</div>
      <div class="hr">${e.avg_hr ? e.avg_hr + " BPM" : ""}</div>
    `;
    li.onclick = () => selectEcg(e.id);
    ul.appendChild(li);
  }
}

async function selectEcg(id) {
  const seq = ++state.selectSeq;
  console.log("[ecg] selectEcg", id, "seq", seq);
  const res = await fetch(`/api/ecgs/${id}?downsample=2`);
  if (!res.ok) { console.warn("[ecg] fetch failed", res.status); return; }
  if (seq !== state.selectSeq) { console.log("[ecg] stale, drop seq", seq); return; }
  const data = await res.json();
  if (seq !== state.selectSeq) { console.log("[ecg] stale after json, drop seq", seq); return; }
  state.current = data;
  state.samples = new Float32Array(data.samples_mv);
  state.fs = data.sample_rate;
  state.renderedAt = new Date();
  console.log("[ecg] loaded id=", data.id, "n=", state.samples.length, "fs=", state.fs);
  renderList();
  renderMeta();
  requestAnimationFrame(() => drawECG());
}

function renderMeta() {
  const m = $("#meta");
  const c = state.current;
  if (!c) { m.innerHTML = '<div class="item"><span class="v">Keine Aufzeichnung ausgewählt</span></div>'; return; }
  const stamp = state.renderedAt ? state.renderedAt.toLocaleTimeString("de-DE") : "";
  m.innerHTML = `
    <div class="item"><span class="k">Aufgezeichnet</span><span class="v">${fmtDate(c.recorded_at)}</span></div>
    <div class="item"><span class="k">Klassifizierung</span><span class="v">${c.classification || "—"}</span></div>
    <div class="item hr"><span class="k">⌀ Herzfrequenz</span><span class="v">${c.avg_hr ? c.avg_hr + " BPM" : "—"}</span></div>
    <div class="item"><span class="k">Symptome</span><span class="v">${c.symptoms || "Keine"}</span></div>
    <div class="item"><span class="k">Dauer</span><span class="v">${c.duration_s ? c.duration_s.toFixed(1) + " s" : "—"}</span></div>
    <div class="item"><span class="k">Angezeigt</span><span class="v" style="font-size:12px;color:var(--muted)">${stamp}</span></div>
  `;
}

function drawECG() {
  const canvas = $("#ecgCanvas");
  const wrap = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const cssW = wrap.clientWidth;
  const cssH = wrap.clientHeight;
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  // ECG paper: 25mm/s horizontal, 10mm/mV vertical. Pick mm→px to fit width.
  const samples = state.samples;
  const fs = state.fs;
  const durationS = samples ? samples.length / fs : 30;
  const stripSeconds = 5;
  const rows = Math.ceil(durationS / stripSeconds);

  const padL = 38, padR = 14, padT = 10, padB = 22;
  const plotW = cssW - padL - padR;
  const mmPerPx = (stripSeconds * 25) / plotW;  // mm represented by 1px horizontally
  const pxPerMm = 1 / mmPerPx;

  const rowHeightMm = 22;   // ±1.1 mV range
  const rowGapMm = 3;
  const rowHeightPx = rowHeightMm * pxPerMm;
  const rowGapPx = rowGapMm * pxPerMm;
  const totalH = rows * rowHeightPx + (rows - 1) * rowGapPx;
  // scale down if too tall
  const availH = cssH - padT - padB;
  const scale = totalH > availH ? availH / totalH : 1;
  const rowH = rowHeightPx * scale;
  const rowGap = rowGapPx * scale;
  const pxPerMmScaled = pxPerMm * scale;

  // Draw each row
  ctx.lineWidth = 1;
  for (let r = 0; r < rows; r++) {
    const y = padT + r * (rowH + rowGap);
    drawGrid(ctx, padL, y, plotW, rowH, pxPerMmScaled);
    if (samples) drawTrace(ctx, samples, fs, r * stripSeconds, stripSeconds,
                           padL, y, plotW, rowH, pxPerMmScaled);
    // time label
    ctx.fillStyle = "#8a8f99";
    ctx.font = "11px -apple-system, Segoe UI, sans-serif";
    ctx.fillText(`${r * stripSeconds}s`, 4, y + 12);
  }
}

function drawGrid(ctx, x, y, w, h, pxPerMm) {
  const minorPx = pxPerMm;      // 1mm
  const majorPx = pxPerMm * 5;  // 5mm
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();

  ctx.strokeStyle = "rgba(255, 55, 95, 0.18)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let gx = x; gx <= x + w + 0.5; gx += minorPx) {
    ctx.moveTo(gx, y); ctx.lineTo(gx, y + h);
  }
  for (let gy = y; gy <= y + h + 0.5; gy += minorPx) {
    ctx.moveTo(x, gy); ctx.lineTo(x + w, gy);
  }
  ctx.stroke();

  ctx.strokeStyle = "rgba(255, 55, 95, 0.38)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let gx = x; gx <= x + w + 0.5; gx += majorPx) {
    ctx.moveTo(gx, y); ctx.lineTo(gx, y + h);
  }
  for (let gy = y; gy <= y + h + 0.5; gy += majorPx) {
    ctx.moveTo(x, gy); ctx.lineTo(x + w, gy);
  }
  ctx.stroke();

  ctx.restore();

  ctx.strokeStyle = "rgba(255, 55, 95, 0.5)";
  ctx.strokeRect(x, y, w, h);
}

function drawTrace(ctx, samples, fs, startS, secs, x, y, w, h, pxPerMm) {
  const start = Math.floor(startS * fs);
  const end = Math.min(samples.length, Math.floor((startS + secs) * fs));
  const n = end - start;
  if (n < 2) return;
  const mid = y + h / 2;
  const mmPerMv = 10;
  const maxMv = (h / 2) / pxPerMm / mmPerMv;

  ctx.strokeStyle = "#ff3b30";
  ctx.lineWidth = 1.6;
  ctx.lineJoin = "round";
  ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const px = x + (i / (secs * fs)) * w;
    let mv = samples[start + i];
    if (mv > maxMv) mv = maxMv; else if (mv < -maxMv) mv = -maxMv;
    const py = mid - mv * mmPerMv * pxPerMm;
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  }
  ctx.stroke();
}

function exportPdf() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const params = new URLSearchParams();
  if (mode === "single") {
    if (!state.current) { alert("Bitte zuerst eine Aufzeichnung auswählen."); return; }
    params.set("ecg_id", state.current.id);
  } else if (mode === "range") {
    const f = $("#exportFrom").value, t = $("#exportTo").value;
    if (f) params.set("date_from", f);
    if (t) params.set("date_to", t);
  }
  window.location.href = "/api/export.pdf?" + params.toString();
}

// wiring
window.addEventListener("DOMContentLoaded", () => {
  $("#refreshBtn").onclick = async () => {
    await fetch("/api/refresh", { method: "POST" });
    await loadList();
  };
  $("#filterFrom").onchange = loadList;
  $("#filterTo").onchange = loadList;
  $("#filterClear").onclick = () => {
    $("#filterFrom").value = ""; $("#filterTo").value = ""; loadList();
  };
  document.querySelectorAll('input[name="mode"]').forEach(r => {
    r.onchange = () => {
      $("#rangeInputs").classList.toggle("hidden", document.querySelector('input[name="mode"]:checked').value !== "range");
    };
  });
  $("#exportBtn").onclick = exportPdf;
  window.addEventListener("resize", () => drawECG());
  loadList();
});
