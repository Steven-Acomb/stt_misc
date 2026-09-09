"use strict";

/* ==========================================================================
   STT phone app — browse audio, transcribe (async), review transcripts.
   Single-page, hash-routed, no framework. Views: transcripts / new / jobs / edit.
   ========================================================================== */

// ---- API helpers ---------------------------------------------------------
async function apiGet(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}
async function apiSend(url, method, body) {
  const r = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}
async function errText(r) {
  try { const j = await r.json(); return j.detail || j.error || r.statusText; }
  catch { return r.statusText; }
}
function encodePath(id) {
  return id.split("/").map(encodeURIComponent).join("/");
}

// ---- shared UI refs ------------------------------------------------------
const view = document.getElementById("view");
const crumbEl = document.getElementById("crumb");
const statusEl = document.getElementById("status");
const backBtn = document.getElementById("back-btn");
const offlineEl = document.getElementById("offline");

function setCrumb(text) { crumbEl.textContent = text; }
function setStatus(text, cls) { statusEl.textContent = text || ""; statusEl.className = "status" + (cls ? " " + cls : ""); }
function setBack(handler) {
  if (handler) { backBtn.hidden = false; backBtn.onclick = handler; }
  else { backBtn.hidden = true; backBtn.onclick = null; }
}
function fmtMs(ms) {
  const t = Math.floor(ms / 1000), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  const mm = String(m).padStart(2, "0"), ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// ---- router --------------------------------------------------------------
let cleanup = null;   // teardown for the current view

function route() {
  if (cleanup) { try { cleanup(); } catch (e) {} cleanup = null; }
  view.innerHTML = "";
  setBack(null);
  setStatus("");
  const hash = location.hash || "#/transcripts";
  const parts = hash.slice(2).split("/");   // strip "#/"
  const name = parts[0] || "transcripts";
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.route === name));
  if (name === "transcripts") viewTranscripts();
  else if (name === "new") viewNew();
  else if (name === "jobs") viewJobs();
  else if (name === "edit") viewEditor(decodeURIComponent(parts.slice(1).join("/")));
  else viewTranscripts();
}
window.addEventListener("hashchange", route);

// ==========================================================================
//  Transcripts list
// ==========================================================================
async function viewTranscripts() {
  setCrumb("Transcripts");
  view.append(el("div", "section-title", "Your transcripts"));
  let items;
  try { items = await apiGet("/api/transcripts"); }
  catch (e) { view.append(el("p", "empty", "Couldn't load: " + e.message)); return; }
  if (!items.length) { view.append(el("p", "empty", "No transcripts yet. Tap ＋ New to make one.")); return; }
  for (const it of items) {
    const card = el("a", "card");
    card.href = "#/edit/" + encodeURIComponent(it.id);
    card.append(el("div", "title", it.name));
    const mins = it.duration_ms ? (it.duration_ms / 60000).toFixed(1) + " min · " : "";
    card.append(el("div", "meta", `${mins}${it.speaker_count} speaker(s)`));
    view.append(card);
  }
}

// ==========================================================================
//  New — filesystem browser -> pick audio -> speaker sheet -> job
// ==========================================================================
let browsePath = null;

async function viewNew() {
  setCrumb("New transcription");
  // Upload-from-device button (iOS surfaces the Files app picker here).
  const upBtn = el("button", "btn block", "⬆ Upload audio from this device");
  const fi = document.createElement("input");
  fi.type = "file";
  fi.accept = "audio/*,.m4a,.m4b,.aac,.mp3,.wav,.flac,.ogg";
  fi.hidden = true;
  fi.onchange = () => { const f = fi.files && fi.files[0]; fi.value = ""; if (f) uploadFile(f); };
  upBtn.onclick = () => fi.click();
  view.append(upBtn, fi);
  view.append(el("div", "section-title", "or browse this desktop"));
  const browse = el("div"); browse.id = "browse";
  view.append(browse);
  await renderBrowse(browse);
}

async function renderBrowse(container) {
  container = container || document.getElementById("browse");
  if (!container) return;
  container.innerHTML = "";
  let listing;
  try {
    const url = browsePath == null ? "/api/fs" : "/api/fs?path=" + encodeURIComponent(browsePath);
    listing = await apiGet(url);
  } catch (e) {
    container.append(el("p", "empty", "Couldn't open folder: " + e.message));
    browsePath = null;
    container.append(makeBtn("Back to drives", "ghost block", () => { browsePath = null; renderBrowse(container); }));
    return;
  }
  browsePath = listing.path;
  container.append(el("div", "pathbar", listing.path || "This PC — pick a drive"));

  if (listing.parent != null || listing.path != null) {
    const up = el("button", "row dir");
    up.append(el("span", "glyph", "⬑"), el("span", "name", listing.parent != null ? "Up a level" : "Drives"));
    up.onclick = () => { browsePath = listing.parent; renderBrowse(container); };
    container.append(up);
  }
  for (const d of listing.dirs) {
    const row = el("button", "row dir");
    row.append(el("span", "glyph", "📁"), el("span", "name", d), el("span", "go", "›"));
    row.onclick = () => { browsePath = joinPath(listing.path, d); renderBrowse(container); };
    container.append(row);
  }
  const audio = (listing.files || []).filter((f) => f.kind === "audio");
  for (const f of audio) {
    const row = el("button", "row file");
    row.append(el("span", "glyph", "🎧"), el("span", "name", f.name), el("span", "go", "＋"));
    row.onclick = () => openSpeakerSheet(joinPath(listing.path, f.name), f.name);
    container.append(row);
  }
  if (!listing.dirs.length && !audio.length)
    container.append(el("p", "empty", "No sub-folders or audio files here."));
}

// Upload a picked file with a progress bar, then hand off to the speaker sheet.
function uploadFile(file) {
  const backdrop = el("div", "sheet-backdrop");
  const sheet = el("div", "sheet");
  sheet.append(el("h3", null, "Uploading"));
  sheet.append(el("div", "sub", file.name));
  const barWrap = el("div", "upbar");
  const bar = el("div", "upbar-fill");
  barWrap.append(bar);
  const pct = el("div", "sub", "0%");
  sheet.append(barWrap, pct);
  const cancel = makeBtn("Cancel", "ghost block", () => { xhr.abort(); backdrop.remove(); });
  sheet.append(cancel);
  backdrop.append(sheet);
  document.body.append(backdrop);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const p = Math.round((e.loaded / e.total) * 100);
    bar.style.width = p + "%";
    pct.textContent = p + "%" + (p >= 100 ? " — saving…" : "");
  };
  xhr.onload = () => {
    backdrop.remove();
    if (xhr.status >= 200 && xhr.status < 300) {
      const r = JSON.parse(xhr.responseText);
      openSpeakerSheet(r.path, r.name);
    } else {
      let msg = xhr.statusText;
      try { msg = JSON.parse(xhr.responseText).detail || msg; } catch (e) {}
      alert("Upload failed: " + msg);
    }
  };
  xhr.onerror = () => { backdrop.remove(); alert("Upload failed (network)."); };
  const fd = new FormData();
  fd.append("file", file, file.name);
  xhr.send(fd);
}

function joinPath(base, name) {
  if (!base) return name;
  const sep = base.includes("\\") ? "\\" : "/";
  return base.endsWith(sep) ? base + name : base + sep + name;
}
function makeBtn(text, cls, onclick) {
  const b = el("button", "btn " + (cls || ""), text);
  b.onclick = onclick;
  return b;
}

function openSpeakerSheet(audioPath, audioName) {
  let count = 2, auto = false;
  const backdrop = el("div", "sheet-backdrop");
  const sheet = el("div", "sheet");
  sheet.append(el("h3", null, "Transcribe"));
  sheet.append(el("div", "sub", audioName));

  const stepper = el("div", "stepper");
  const minus = el("button", null, "−");
  const val = el("div", "val", String(count));
  const plus = el("button", null, "+");
  const lbl = el("label", null, "speakers");
  const upd = () => { val.textContent = auto ? "auto" : String(count); minus.disabled = auto || count <= 1; plus.disabled = auto; };
  minus.onclick = () => { if (count > 1) count--; upd(); };
  plus.onclick = () => { if (count < 12) count++; upd(); };
  stepper.append(minus, el("div", null, ""), val, lbl, plus);
  // reorder for layout: minus, val, lbl, plus
  stepper.innerHTML = "";
  stepper.append(minus, val, lbl, plus);
  sheet.append(stepper);

  const autoWrap = el("label", "speed");
  const autoCb = document.createElement("input");
  autoCb.type = "checkbox";
  autoCb.onchange = () => { auto = autoCb.checked; upd(); };
  autoWrap.append(autoCb, document.createTextNode(" Auto-detect number of speakers"));
  autoWrap.style.display = "block";
  autoWrap.style.textAlign = "center";
  autoWrap.style.marginBottom = "16px";
  sheet.append(autoWrap);

  const start = makeBtn("Start transcription", "block", async () => {
    start.disabled = true; start.textContent = "Starting…";
    try {
      await apiSend("/api/jobs", "POST", { path: audioPath, speakers: auto ? 0 : count });
      close();
      location.hash = "#/jobs";
    } catch (e) { start.disabled = false; start.textContent = "Start transcription"; alert("Failed: " + e.message); }
  });
  const cancel = makeBtn("Cancel", "ghost block", () => close());
  cancel.style.marginTop = "8px";
  sheet.append(start, cancel);

  function close() { backdrop.remove(); }
  backdrop.onclick = (e) => { if (e.target === backdrop) close(); };
  backdrop.append(sheet);
  document.body.append(backdrop);
  upd();
}

// ==========================================================================
//  Jobs
// ==========================================================================
async function viewJobs() {
  setCrumb("Jobs");
  let timer = null;
  const container = el("div");
  view.append(el("div", "section-title", "Transcription jobs"), container);

  async function refresh() {
    let jobs;
    try { jobs = await apiGet("/api/jobs"); }
    catch (e) { return; }
    container.innerHTML = "";
    if (!jobs.length) { container.append(el("p", "empty", "No jobs this session. Pick a file under ＋ New.")); return; }
    let anyActive = false;
    for (const j of jobs) {
      if (j.status === "queued" || j.status === "running") anyActive = true;
      const done = j.status === "done" && j.transcript_id;
      const card = el(done ? "a" : "div", "card");
      if (done) card.href = "#/edit/" + encodeURIComponent(j.transcript_id);
      const head = el("div", "title");
      head.append(document.createTextNode(j.audio_name + "  "));
      const badge = el("span", "badge " + j.status, j.status);
      head.append(badge);
      card.append(head);
      let meta = "";
      if (j.status === "running") meta = "transcribing…";
      else if (j.status === "queued") meta = "waiting…";
      else if (j.status === "done") meta = `${(j.duration_ms / 60000).toFixed(1)} min · ${j.speaker_count} speaker(s) · tap to review`;
      else if (j.status === "error") meta = "error: " + j.error;
      card.append(el("div", "meta", meta));
      container.append(card);
    }
    if (anyActive && !timer) timer = setInterval(refresh, 2500);
    if (!anyActive && timer) { clearInterval(timer); timer = null; }
  }
  await refresh();
  cleanup = () => { if (timer) clearInterval(timer); };
}

// ==========================================================================
//  Editor (full parity, touch-adapted)
// ==========================================================================
async function viewEditor(id) {
  setCrumb("Loading…");
  setBack(() => { location.hash = "#/transcripts"; });

  let doc;
  try { doc = await apiGet("/api/transcript/" + encodePath(id)); }
  catch (e) { view.append(el("p", "empty", "Couldn't load transcript: " + e.message)); return; }
  if (!doc.speaker_names) doc.speaker_names = {};
  setCrumb(doc.audio_filename || "Transcript");

  const PALETTE = ["#5b8cff", "#e08a4c", "#4fd0a0", "#c07ce0", "#e06d8a", "#4fb8d0", "#d0b84f", "#8a90e0"];
  let dirty = false, saveTimer = null, playingId = null;
  const audioAvailable = !!doc.audio_available;

  // -- speaker helpers --
  const speakerKeys = () => {
    const keys = Object.keys(doc.speaker_names);
    for (const s of doc.segments) if (!keys.includes(s.speaker)) keys.push(s.speaker);
    return keys;
  };
  const speakerName = (k) => doc.speaker_names[k] || k;
  const speakerColor = (k) => { const i = speakerKeys().indexOf(k); return PALETTE[(i < 0 ? 0 : i) % PALETTE.length]; };
  const nextSpeakerKey = () => {
    const used = new Set(speakerKeys());
    for (let i = 0; i < 26; i++) { const c = String.fromCharCode(65 + i); if (!used.has(c)) return c; }
    return "S" + (speakerKeys().length + 1);
  };

  // -- save --
  function markDirty() {
    dirty = true;
    setStatus("unsaved", "dirty");
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 2000);
  }
  function flushSave() { if (dirty) save(); }
  async function save() {
    clearTimeout(saveTimer);
    if (!dirty) return;
    setStatus("saving…", "saving");
    try {
      await apiSend("/api/transcript/" + encodePath(id), "PUT", doc);
      dirty = false;
      setStatus("saved", "saved");
    } catch (e) { setStatus("save failed", "dirty"); }
  }

  // -- build DOM --
  const player = document.createElement("audio");
  player.preload = "metadata";

  const bar = el("div", "player-bar");
  bar.append(player);
  const transport = el("div", "transport");
  const btnBack = el("button", null, "« 5s");
  const btnPlay = el("button", null, "Play"); btnPlay.id = "play-pause";
  const btnFwd = el("button", null, "5s »");
  const timeReadout = el("span", "time-readout", "0:00 / 0:00");
  const scrubber = document.createElement("input");
  scrubber.type = "range"; scrubber.min = 0; scrubber.max = 1000; scrubber.value = 0; scrubber.className = "scrubber";
  const speedWrap = el("label", "speed"); speedWrap.append(document.createTextNode("Speed "));
  const speed = document.createElement("select");
  for (const v of ["0.5", "0.75", "1", "1.25", "1.5", "2"]) { const o = el("option", null, v + "×"); o.value = v; if (v === "1") o.selected = true; speed.append(o); }
  speedWrap.append(speed);
  transport.append(btnBack, btnPlay, btnFwd, timeReadout, speedWrap, scrubber);
  bar.append(transport);
  if (!audioAvailable) {
    bar.append(el("div", "meta", "⚠ audio file not found on disk — playback disabled"));
    [btnBack, btnPlay, btnFwd, scrubber, speed].forEach((e) => (e.disabled = true));
  }
  view.append(bar);

  const legend = el("div"); legend.id = "legend"; view.append(legend);
  const segWrap = el("div"); view.append(segWrap);

  // -- legend (rename globally) --
  function renderLegend() {
    legend.innerHTML = "";
    for (const key of speakerKeys()) {
      const item = el("div", "legend-item");
      const sw = el("span", "swatch"); sw.style.background = speakerColor(key);
      const input = document.createElement("input");
      input.type = "text"; input.value = speakerName(key);
      input.addEventListener("input", () => { markDirty(); doc.speaker_names[key] = input.value; refreshSelects(); });
      input.addEventListener("blur", flushSave);
      item.append(sw, input);
      legend.append(item);
    }
  }
  function buildSelect(select, current) {
    select.innerHTML = "";
    for (const k of speakerKeys()) { const o = el("option", null, speakerName(k)); o.value = k; select.append(o); }
    const nw = el("option", null, "+ New speaker…"); nw.value = "__new__"; select.append(nw);
    select.value = current;
  }
  function refreshSelects() {
    for (const row of segWrap.querySelectorAll(".segment")) {
      const sel = row.querySelector(".speaker-select");
      buildSelect(sel, sel.value);
      sel.style.borderLeft = `4px solid ${speakerColor(sel.value)}`;
    }
  }
  const autoGrow = (ta) => { ta.style.height = "auto"; ta.style.height = ta.scrollHeight + "px"; };

  const tmpl = document.getElementById("segment-template");
  function renderSegments() {
    segWrap.innerHTML = "";
    doc.segments.forEach((seg, index) => {
      const node = tmpl.content.firstElementChild.cloneNode(true);
      node.dataset.id = String(seg.id);
      if (seg.edited) node.classList.add("edited");
      const ts = node.querySelector(".timestamp");
      ts.textContent = fmtMs(seg.start);
      ts.onclick = () => { if (audioAvailable) player.currentTime = seg.start / 1000; };
      const sel = node.querySelector(".speaker-select");
      buildSelect(sel, seg.speaker);
      sel.style.borderLeft = `4px solid ${speakerColor(seg.speaker)}`;
      sel.onchange = () => onReassign(seg.id, sel);
      const ta = node.querySelector(".seg-text");
      ta.value = seg.text;
      ta.addEventListener("input", () => {
        markDirty(); seg.text = ta.value;
        if (!seg.edited) { seg.edited = true; node.classList.add("edited"); }
        autoGrow(ta);
      });
      ta.addEventListener("blur", flushSave);
      node.querySelector(".split-btn").onclick = () => onSplit(seg.id, ta);
      const mb = node.querySelector(".merge-btn");
      if (index === doc.segments.length - 1) mb.disabled = true;
      mb.onclick = () => onMerge(seg.id);
      segWrap.append(node);
      autoGrow(ta);
    });
  }

  const idxById = (id2) => doc.segments.findIndex((s) => s.id === id2);
  const renumber = () => doc.segments.forEach((s, i) => (s.id = i));

  function onReassign(id2, sel) {
    const i = idxById(id2); if (i < 0) return;
    let v = sel.value;
    if (v === "__new__") { const k = nextSpeakerKey(); doc.speaker_names[k] = `Speaker ${speakerKeys().length + 1}`; v = k; }
    doc.segments[i].speaker = v; doc.segments[i].edited = true;
    markDirty(); renderLegend(); renderSegments();
  }
  function onMerge(id2) {
    const i = idxById(id2); if (i < 0 || i >= doc.segments.length - 1) return;
    const a = doc.segments[i], b = doc.segments[i + 1];
    a.text = `${a.text.trim()} ${b.text.trim()}`.trim(); a.end = b.end;
    a.words = (a.words || []).concat(b.words || []); a.edited = true;
    doc.segments.splice(i + 1, 1); renumber();
    markDirty(); renderSegments();
  }
  function onSplit(id2, ta) {
    const i = idxById(id2); if (i < 0) return;
    const seg = doc.segments[i];
    const caret = ta.selectionStart != null ? ta.selectionStart : Math.floor(ta.value.length / 2);
    const before = ta.value.slice(0, caret).trim(), after = ta.value.slice(caret).trim();
    const playMs = Math.round((player.currentTime || 0) * 1000);
    const splitMs = (playMs > seg.start && playMs < seg.end) ? playMs : Math.round((seg.start + seg.end) / 2);
    const words = seg.words || [];
    const a = { id: seg.id, speaker: seg.speaker, start: seg.start, end: splitMs, text: before, words: words.filter((w) => w.start < splitMs), edited: true };
    const b = { id: seg.id + 1, speaker: seg.speaker, start: splitMs, end: seg.end, text: after, words: words.filter((w) => w.start >= splitMs), edited: true };
    doc.segments.splice(i, 1, a, b); renumber();
    markDirty(); renderSegments();
  }

  // -- playback --
  function updateHighlight() {
    const t = player.currentTime * 1000;
    let active = null;
    for (const s of doc.segments) if (t >= s.start && t < s.end) { active = s.id; break; }
    if (active === playingId) return;
    playingId = active;
    segWrap.querySelectorAll(".segment.playing").forEach((r) => r.classList.remove("playing"));
    if (active == null) return;
    const row = segWrap.querySelector(`.segment[data-id="${active}"]`);
    if (!row) return;
    row.classList.add("playing");
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") return;
    const rect = row.getBoundingClientRect();
    if (rect.top < 130 || rect.bottom > window.innerHeight) row.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  const nudge = (s) => { if (audioAvailable) player.currentTime = Math.max(0, Math.min(player.duration || 0, player.currentTime + s)); };
  const toggle = () => { if (!audioAvailable) return; player.paused ? player.play() : player.pause(); };

  player.addEventListener("timeupdate", () => {
    updateHighlight();
    const d = player.duration || 0;
    timeReadout.textContent = `${fmtMs(player.currentTime * 1000)} / ${fmtMs(d * 1000)}`;
    if (d > 0) scrubber.value = String(Math.round((player.currentTime / d) * 1000));
  });
  player.addEventListener("play", () => (btnPlay.textContent = "Pause"));
  player.addEventListener("pause", () => (btnPlay.textContent = "Play"));
  btnPlay.onclick = toggle; btnBack.onclick = () => nudge(-5); btnFwd.onclick = () => nudge(5);
  speed.onchange = () => (player.playbackRate = parseFloat(speed.value));
  scrubber.oninput = () => { const d = player.duration || 0; if (d > 0) player.currentTime = (parseInt(scrubber.value, 10) / 1000) * d; };

  function onKey(e) {
    const tag = (e.target && e.target.tagName) || "";
    const typing = tag === "TEXTAREA" || tag === "INPUT";
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); return; }
    if (e.altKey) { const k = e.key.toLowerCase(); if (k === "j") { e.preventDefault(); nudge(-5); } else if (k === "l") { e.preventDefault(); nudge(5); } else if (k === "k") { e.preventDefault(); toggle(); } return; }
    if (e.key === " " && !typing) { e.preventDefault(); toggle(); }
  }
  document.addEventListener("keydown", onKey);

  if (audioAvailable) {
    player.src = "/api/audio?path=" + encodeURIComponent(doc.audio_path);
    player.playbackRate = 1;
  }
  renderLegend();
  renderSegments();
  setStatus("");

  cleanup = () => {
    clearTimeout(saveTimer);
    if (dirty) { navigator.sendBeacon && navigator.sendBeacon("/api/transcript/" + encodePath(id), new Blob([JSON.stringify(doc)], { type: "application/json" })); }
    document.removeEventListener("keydown", onKey);
    try { player.pause(); player.src = ""; } catch (e) {}
  };
}

// ---- connectivity banner + boot -----------------------------------------
async function healthProbe() {
  try { await fetch("/api/health"); offlineEl.hidden = true; }
  catch { offlineEl.hidden = false; }
}
setInterval(healthProbe, 5000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) route(); });

route();
