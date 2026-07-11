"use strict";

// ---- state ---------------------------------------------------------------
let doc = null;              // the transcript document (source of truth mirror)
let dirty = false;
let saveTimer = null;
let playingId = null;        // id of the currently highlighted segment
let audioAvailable = false;

const SPEAKER_PALETTE = [
  "#2f6feb", "#c2410c", "#0e8a6a", "#8b3fc9",
  "#b5153f", "#0a7ea4", "#a67c00", "#5661b3",
];

// ---- element refs --------------------------------------------------------
const els = {
  filename: document.getElementById("filename"),
  audioWarning: document.getElementById("audio-warning"),
  status: document.getElementById("status"),
  saveBtn: document.getElementById("save-btn"),
  player: document.getElementById("player"),
  playPause: document.getElementById("play-pause"),
  seekBack: document.getElementById("seek-back"),
  seekFwd: document.getElementById("seek-fwd"),
  timeReadout: document.getElementById("time-readout"),
  scrubber: document.getElementById("scrubber"),
  speed: document.getElementById("speed"),
  legend: document.getElementById("legend"),
  transcript: document.getElementById("transcript"),
  template: document.getElementById("segment-template"),
};

// ---- time helpers --------------------------------------------------------
function fmtMs(ms) {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

// ---- speaker helpers -----------------------------------------------------
function speakerKeys() {
  // Ordered: names map first (preserves insertion order), then any stray keys.
  const keys = Object.keys(doc.speaker_names);
  for (const seg of doc.segments) {
    if (!keys.includes(seg.speaker)) keys.push(seg.speaker);
  }
  return keys;
}

function speakerName(key) {
  return doc.speaker_names[key] || key;
}

function speakerColor(key) {
  const idx = speakerKeys().indexOf(key);
  return SPEAKER_PALETTE[(idx < 0 ? 0 : idx) % SPEAKER_PALETTE.length];
}

function nextSpeakerKey() {
  // Find an unused single letter A, B, C, ...
  const used = new Set(speakerKeys());
  for (let i = 0; i < 26; i++) {
    const k = String.fromCharCode(65 + i);
    if (!used.has(k)) return k;
  }
  return "S" + (speakerKeys().length + 1);
}

// ---- rendering -----------------------------------------------------------
function renderLegend() {
  els.legend.innerHTML = "";
  for (const key of speakerKeys()) {
    const item = document.createElement("div");
    item.className = "legend-item";

    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = speakerColor(key);

    const input = document.createElement("input");
    input.type = "text";
    input.value = speakerName(key);
    input.title = `Rename ${key} everywhere`;
    input.addEventListener("input", () => {
      markDirty();
      doc.speaker_names[key] = input.value;
      refreshSpeakerLabels();
    });
    // Flush the save the moment focus leaves the field, so a quick rename saves
    // immediately instead of waiting on the autosave debounce.
    input.addEventListener("blur", flushSave);

    item.append(swatch, input);
    els.legend.append(item);
  }
}

function buildSelect(select, currentKey) {
  select.innerHTML = "";
  for (const key of speakerKeys()) {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = speakerName(key);
    select.append(opt);
  }
  const newOpt = document.createElement("option");
  newOpt.value = "__new__";
  newOpt.textContent = "+ New speaker…";
  select.append(newOpt);
  select.value = currentKey;
}

function refreshSpeakerLabels() {
  // Update every reassignment <select> and colored left-border after a rename/add.
  for (const row of els.transcript.querySelectorAll(".segment")) {
    const select = row.querySelector(".speaker-select");
    const current = select.value;
    buildSelect(select, current);
    const key = current;
    select.style.borderLeft = `4px solid ${speakerColor(key)}`;
  }
}

function autoGrow(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = textarea.scrollHeight + "px";
}

function renderSegments() {
  els.transcript.innerHTML = "";
  if (!doc.segments.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No speech segments in this transcript.";
    els.transcript.append(empty);
    return;
  }

  doc.segments.forEach((seg, index) => {
    const node = els.template.content.firstElementChild.cloneNode(true);
    node.dataset.id = String(seg.id);
    if (seg.edited) node.classList.add("edited");

    const ts = node.querySelector(".timestamp");
    ts.textContent = fmtMs(seg.start);
    ts.addEventListener("click", () => seekToMs(seg.start));

    const select = node.querySelector(".speaker-select");
    buildSelect(select, seg.speaker);
    select.style.borderLeft = `4px solid ${speakerColor(seg.speaker)}`;
    select.addEventListener("change", () => onReassign(seg.id, select));

    const textarea = node.querySelector(".seg-text");
    textarea.value = seg.text;
    textarea.addEventListener("input", () => {
      seg.text = textarea.value;
      if (!seg.edited) {
        seg.edited = true;
        node.classList.add("edited");
      }
      autoGrow(textarea);
      markDirty();
    });
    textarea.addEventListener("focus", () => seekOnFocusHint(seg));
    textarea.addEventListener("blur", flushSave);

    node.querySelector(".split-btn").addEventListener("click", () => onSplit(seg.id));
    const mergeBtn = node.querySelector(".merge-btn");
    if (index === doc.segments.length - 1) mergeBtn.disabled = true;
    mergeBtn.addEventListener("click", () => onMerge(seg.id));

    els.transcript.append(node);
    autoGrow(textarea);
  });
}

// A gentle convenience: focusing a turn's text does NOT auto-seek (that would be
// disruptive); kept as a hook in case we want opt-in behavior later.
function seekOnFocusHint(_seg) {}

// ---- mutations -----------------------------------------------------------
function segIndexById(id) {
  return doc.segments.findIndex((s) => s.id === id);
}

function renumber() {
  doc.segments.forEach((s, i) => (s.id = i));
}

function onReassign(id, select) {
  const i = segIndexById(id);
  if (i < 0) return;
  let value = select.value;
  if (value === "__new__") {
    const key = nextSpeakerKey();
    doc.speaker_names[key] = `Speaker ${speakerKeys().length + 1}`;
    value = key;
  }
  doc.segments[i].speaker = value;
  doc.segments[i].edited = true;
  markDirty();
  renderLegend();
  renderSegments();
}

function onMerge(id) {
  const i = segIndexById(id);
  if (i < 0 || i >= doc.segments.length - 1) return;
  const a = doc.segments[i];
  const b = doc.segments[i + 1];
  a.text = `${a.text.trim()} ${b.text.trim()}`.trim();
  a.end = b.end;
  a.words = (a.words || []).concat(b.words || []);
  a.edited = true;
  doc.segments.splice(i + 1, 1);
  renumber();
  markDirty();
  renderSegments();
}

function onSplit(id) {
  const i = segIndexById(id);
  if (i < 0) return;
  const seg = doc.segments[i];
  const row = els.transcript.querySelector(`.segment[data-id="${id}"]`);
  const textarea = row.querySelector(".seg-text");
  const caret = textarea.selectionStart ?? Math.floor(textarea.value.length / 2);

  const full = textarea.value;
  const before = full.slice(0, caret).trim();
  const after = full.slice(caret).trim();

  // Split time: prefer the current playhead if it falls inside this turn,
  // otherwise fall back to the segment midpoint.
  const playMs = Math.round(els.player.currentTime * 1000);
  let splitMs;
  if (playMs > seg.start && playMs < seg.end) {
    splitMs = playMs;
  } else {
    splitMs = Math.round((seg.start + seg.end) / 2);
  }

  const words = seg.words || [];
  const wordsA = words.filter((w) => w.start < splitMs);
  const wordsB = words.filter((w) => w.start >= splitMs);

  const segA = {
    id: seg.id,
    speaker: seg.speaker,
    start: seg.start,
    end: splitMs,
    text: before,
    words: wordsA,
    edited: true,
  };
  const segB = {
    id: seg.id + 1,
    speaker: seg.speaker,
    start: splitMs,
    end: seg.end,
    text: after,
    words: wordsB,
    edited: true,
  };
  doc.segments.splice(i, 1, segA, segB);
  renumber();
  markDirty();
  renderSegments();
}

// ---- audio / transport ---------------------------------------------------
function seekToMs(ms) {
  if (!audioAvailable) return;
  els.player.currentTime = ms / 1000;
}

function togglePlay() {
  if (!audioAvailable) return;
  if (els.player.paused) els.player.play();
  else els.player.pause();
}

function nudge(seconds) {
  if (!audioAvailable) return;
  const dur = els.player.duration || 0;
  els.player.currentTime = Math.max(0, Math.min(dur, els.player.currentTime + seconds));
}

function updatePlayingHighlight() {
  const tMs = els.player.currentTime * 1000;
  let active = null;
  for (const seg of doc.segments) {
    if (tMs >= seg.start && tMs < seg.end) {
      active = seg.id;
      break;
    }
  }
  if (active === playingId) return;
  playingId = active;
  for (const row of els.transcript.querySelectorAll(".segment.playing")) {
    row.classList.remove("playing");
  }
  if (active === null) return;
  const row = els.transcript.querySelector(`.segment[data-id="${active}"]`);
  if (!row) return;
  row.classList.add("playing");

  // Auto-scroll to keep the playing line visible, but never while the user is
  // editing text (that would yank the caret out of view).
  const tag = (document.activeElement && document.activeElement.tagName) || "";
  if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") return;
  const rect = row.getBoundingClientRect();
  const topGuard = 160; // below the sticky header
  if (rect.top < topGuard || rect.bottom > window.innerHeight) {
    row.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

function wireAudio() {
  els.player.addEventListener("timeupdate", () => {
    updatePlayingHighlight();
    const dur = els.player.duration || 0;
    els.timeReadout.textContent = `${fmtMs(els.player.currentTime * 1000)} / ${fmtMs(dur * 1000)}`;
    if (dur > 0) els.scrubber.value = String(Math.round((els.player.currentTime / dur) * 1000));
  });
  els.player.addEventListener("play", () => (els.playPause.textContent = "Pause"));
  els.player.addEventListener("pause", () => (els.playPause.textContent = "Play"));
  els.player.addEventListener("loadedmetadata", () => {
    els.timeReadout.textContent = `0:00 / ${fmtMs((els.player.duration || 0) * 1000)}`;
  });

  els.playPause.addEventListener("click", togglePlay);
  els.seekBack.addEventListener("click", () => nudge(-3));
  els.seekFwd.addEventListener("click", () => nudge(3));
  els.speed.addEventListener("change", () => (els.player.playbackRate = parseFloat(els.speed.value)));
  els.scrubber.addEventListener("input", () => {
    const dur = els.player.duration || 0;
    if (dur > 0) els.player.currentTime = (parseInt(els.scrubber.value, 10) / 1000) * dur;
  });
}

function wireKeyboard() {
  document.addEventListener("keydown", (e) => {
    const tag = (e.target && e.target.tagName) || "";
    const typing = tag === "TEXTAREA" || tag === "INPUT";

    // Ctrl/Cmd+S -> save (always)
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      save();
      return;
    }
    // Alt-based transport works even while typing.
    if (e.altKey && !e.ctrlKey && !e.metaKey) {
      const k = e.key.toLowerCase();
      if (k === "j") { e.preventDefault(); nudge(-3); return; }
      if (k === "l") { e.preventDefault(); nudge(3); return; }
      if (k === "k") { e.preventDefault(); togglePlay(); return; }
    }
    // Space toggles play only when not typing in a field.
    if (e.key === " " && !typing) {
      e.preventDefault();
      togglePlay();
    }
  });
}

// ---- saving --------------------------------------------------------------
function setStatus(text, cls) {
  els.status.textContent = text;
  els.status.className = "status" + (cls ? " " + cls : "");
}

function markDirty() {
  dirty = true;
  els.saveBtn.disabled = false;
  setStatus("unsaved changes", "dirty");
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 2000); // debounced autosave
}

// Save right now if there's anything pending (used on blur, so leaving a field
// commits immediately rather than waiting on the debounce).
function flushSave() {
  if (dirty) save();
}

async function save() {
  clearTimeout(saveTimer);
  if (!dirty) return;
  setStatus("saving…", "saving");
  els.saveBtn.disabled = true;
  try {
    const res = await fetch("/api/transcript", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(doc),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || res.statusText);
    }
    dirty = false;
    setStatus("saved", "saved");
  } catch (err) {
    setStatus("save failed", "dirty");
    els.saveBtn.disabled = false;
    console.error("save failed:", err);
    alert("Save failed: " + err.message);
  }
}

// ---- init ----------------------------------------------------------------
async function init() {
  wireAudio();
  wireKeyboard();
  els.saveBtn.addEventListener("click", save);
  window.addEventListener("beforeunload", (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  let data;
  try {
    const res = await fetch("/api/transcript");
    data = await res.json();
  } catch (err) {
    setStatus("failed to load", "dirty");
    return;
  }

  doc = data;
  if (!doc.speaker_names) doc.speaker_names = {};
  audioAvailable = !!doc.audio_available;

  els.filename.textContent = doc.audio_filename || "transcript";
  if (audioAvailable) {
    els.player.src = "/api/audio";
    els.player.playbackRate = parseFloat(els.speed.value);
  } else {
    els.audioWarning.hidden = false;
    [els.playPause, els.seekBack, els.seekFwd, els.scrubber, els.speed].forEach(
      (el) => (el.disabled = true)
    );
  }

  renderLegend();
  renderSegments();
  setStatus("ready");
  els.saveBtn.disabled = true;
}

init();
