"use strict";

const $ = (sel) => document.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[m]));

const state = {
  defaults: null,
  settings: null,
  jobs: new Map(),
  filesDir: "",
  filesData: null,
  filesTabActive: false,
};

const STATUS_LABEL = {
  queued: "fila",
  running: "rodando",
  completed: "concluido",
  failed: "falhou",
  cancelled: "cancelado",
  downloading: "baixando",
  processing: "processando",
  finished: "ok",
};

const svg = (name) => `<svg class="icon"><use href="#${name}"></use></svg>`;

/* ---------------- Toasts ---------------- */

function showToast(msg, type = "success") {
  const wrap = $("#toast-wrap");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  const icon = type === "success" ? "i-check" : type === "error" ? "i-alert" : "i-zap";
  el.innerHTML = `${svg(icon)}<div>${esc(msg)}</div>`;
  wrap.appendChild(el);
  setTimeout(() => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 300);
  }, 3600);
}

/* ---------------- Formatadores ---------------- */

function fmtBytes(n) {
  if (!n) return "?";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(1)} ${u[i]}`;
}

function fmtTime(t) {
  if (!t) return "?";
  if (t < 60) return `${t.toFixed(0)}s`;
  const m = Math.floor(t / 60);
  return `${m}min${Math.floor(t % 60)}s`;
}

function fmtDate(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

/* ---------------- API ---------------- */

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

/* ---------------- Health ---------------- */

async function loadHealth() {
  try {
    const h = await api("/api/health");
    $("#ver").textContent = h.version;
    $("#health").innerHTML =
      `<span class="pill ${h.ffmpeg ? "ok" : "bad"}"><i></i>ffmpeg</span>` +
      `<span class="pill ${h.yt_dlp ? "ok" : "bad"}"><i></i>yt-dlp</span>`;
  } catch {
    $("#health").innerHTML = `<span class="pill bad"><i></i>servidor</span>`;
  }
}

/* ---------------- Jobs ---------------- */

function renderItems(job) {
  const items = job.items || [];
  if (!items.length) return "";
  const visible = items.slice(0, 8);
  const hidden = items.length - visible.length;
  const rows = visible.map((it) => {
    const st = it.status || "queued";
    const label = STATUS_LABEL[st] || st;
    const cls = st === "failed" ? "err" : st === "finished" ? "ok" : "";
    const mini = st === "downloading" && it.percent > 0
      ? `<div class="mini"><div style="width:${Math.min(100, it.percent)}%"></div></div>`
      : "";
    return `<div class="job-item ${cls}">
      <span class="dot ${st}"></span>
      <div class="item-main">
        <span class="item-text">${esc(it.title || it.url)}</span>
        ${mini}
      </div>
      <span class="item-status">${label}</span>
    </div>`;
  }).join("");
  return `<div class="job-items">${rows}${hidden ? `<div class="job-item dim">+${hidden} mais</div>` : ""}</div>`;
}

function jobSnapshot(job) {
  const cur = job.current || {};
  const items = (job.items || [])
    .map((it) => [it.url, it.status, it.percent, it.title, it.error].join("|"))
    .join("||");
  return [
    job.kind, job.status, Math.round(job.progress), job.message,
    cur.title, cur.speed, cur.eta, cur.downloaded, cur.total_bytes, cur.status,
    items,
    job.stats ? JSON.stringify(job.stats) : "",
    job.result ? JSON.stringify(job.result) : "",
  ].join("\u00a7");
}

function renderJob(job) {
  const prev = state.jobs.get(job.id);
  const snap = jobSnapshot(job);
  const changed = !prev || prev._snap !== snap;
  state.jobs.set(job.id, { ...prev, ...job, _snap: snap });

  let card = document.querySelector(`[data-job="${job.id}"]`);
  if (!card) {
    card = document.createElement("div");
    card.className = "job";
    card.dataset.job = job.id;
    $("#job-list").prepend(card);
    changed = true;
  }
  if (!changed) return;

  const cur = job.current || {};
  const pct = Math.min(100, Math.max(0, job.progress || 0));
  const speed = cur.speed ? `${fmtBytes(cur.speed)}/s` : "";
  const eta = cur.eta ? `ETA ${fmtTime(cur.eta)}` : "";
  const done = cur.downloaded ? fmtBytes(cur.downloaded) : "";
  const total = cur.total_bytes ? `/${fmtBytes(cur.total_bytes)}` : "";
  const detail = [speed, eta, done + total].filter(Boolean).join(" | ");

  let extra = "";
  if (job.kind === "download" && job.stats) {
    const s = job.stats;
    extra += `<div class="job-msg">${s.success} ok, ${s.failed} falhas, ${s.skipped} pulados — ${fmtBytes(s.total_bytes)} em ${fmtTime(s.total_time)}</div>`;
    const fails = s.results.filter((r) => !r.success);
    if (fails.length) {
      extra += `<div class="job-msg err">` + fails
        .map((f) => esc(f.url) + " — " + esc(f.error || ""))
        .join("<br>") + `</div>`;
    }
  }
  if (job.kind === "split" && job.result && job.result.tracks && job.result.tracks.length) {
    extra += `<div class="job-msg">${job.result.track_count} faixas em ${job.result.output_dir || ""}</div>`;
    extra += `<div>` + job.result.tracks
      .map((t) => {
        const rel = encodeURIComponent(t.replace(/\\/g, "/"));
        return `<a class="track-chip" href="/api/files/download?path=${rel}">${svg("i-download")}${esc(t.split(/[\\/]/).pop())}</a>`;
      })
      .join("") + `</div>`;
  }

  const id = job.id;

  const running = job.status === "running" || job.status === "queued";
  const kindIcon = job.kind === "download" ? "i-download" : "i-split";
  card.className = `job ${job.status}`;

  card.innerHTML = `
    <div class="job-head">
      <span class="job-kind">${svg(kindIcon)}${job.kind}</span>
      <div class="job-title">${esc(cur.title || job.message || "")}</div>
      <span class="status ${job.status}">${STATUS_LABEL[job.status] || job.status}</span>
    </div>
    ${running ? `
      <div class="bar"><div style="width:${pct}%"></div></div>
      <div class="job-msg">${pct.toFixed(0)}% ${detail ? "| " + esc(detail) : ""}</div>
    ` : ""}
    ${job.kind === "download" ? renderItems(job) : ""}
    <div class="job-msg">${esc(job.message || "")}</div>
    ${extra}
    <div class="job-actions">
      ${running
        ? `<button class="btn small danger" data-act="cancel">${svg("i-cancel")} Cancelar</button>`
        : `<button class="btn small ghost" data-act="delete">${svg("i-trash")} Remover</button>`}
    </div>
  `;

  card.querySelector("[data-act='cancel']")?.addEventListener("click", async () => {
    try {
      await api(`/api/jobs/${id}/cancel`, { method: "POST" });
      showToast("Cancelando processo...", "info");
    } catch (e) { console.error(e); }
  });
  card.querySelector("[data-act='delete']")?.addEventListener("click", async () => {
    try {
      await api(`/api/jobs/${id}`, { method: "DELETE" });
      state.jobs.delete(id);
      card.remove();
      updateJobsEmpty();
    } catch (e) { console.error(e); }
  });
}

function updateJobsEmpty() {
  $("#jobs-empty").hidden = state.jobs.size > 0;
  $("#clear-finished").hidden = ![...state.jobs.values()].some(
    (j) => !["queued", "running"].includes(j.status)
  );
}

async function pollJobs() {
  try {
    const data = await api("/api/jobs");
    data.jobs.forEach((job) => {
      const old = state.jobs.get(job.id);
      renderJob(job);
      if (old && old.status !== job.status && job.status === "completed") {
        showToast(job.kind === "download" ? "Download concluido" : "Faixas separadas", "success");
      }
    });
    state.jobs.forEach((j, id) => {
      if (!data.jobs.some((x) => x.id === id)) {
        const el = document.querySelector(`[data-job="${id}"]`);
        if (el) el.remove();
        state.jobs.delete(id);
      }
    });
    updateJobsEmpty();
    if (state.filesTabActive) loadFiles();
  } catch (e) { console.error(e); }
}

async function clearFinished() {
  const done = [...state.jobs.values()].filter((j) => !["queued", "running"].includes(j.status));
  await Promise.all(done.map((j) => api(`/api/jobs/${j.id}`, { method: "DELETE" }).catch(() => {})));
  await pollJobs();
}

/* ---------------- Settings ---------------- */

const INPUT_DEFAULTS = {
  output_dir: "output_dir",
  audio_format: "audio_format",
  video_quality: "video_quality",
  split_dir: "split-output",
  threshold: "split-threshold",
  min_silence: "split-min-silence",
  min_track: "split-min-track",
  split_fmt: "split-fmt",
  split_prefix: "split-prefix",
  lead_in: "split-lead-in",
  lead_out: "split-lead-out",
  digits: "split-digits",
};

async function loadDefaults() {
  try { state.defaults = await api("/api/defaults"); }
  catch { state.defaults = {}; }
  const d = state.defaults;
  $("#audio_format").innerHTML = (d.audio_formats || ["mp3", "m4a", "flac"])
    .map((f) => `<option>${f}</option>`).join("");
  $("#video_quality").innerHTML = (d.video_quals || ["best", "720", "1080"])
    .map((f) => `<option>${f}</option>`).join("");
  $("#split-fmt").innerHTML = (d.split_formats || ["mp3", "flac", "wav"])
    .map((f) => `<option>${f}</option>`).join("");
  applyDefaults();
}

function applyDefaults() {
  const d = state.defaults || {};
  for (const [key, sel] of Object.entries(INPUT_DEFAULTS)) {
    const el = $(`#${sel}`);
    if (el && !el.value && d[key] !== undefined) el.value = d[key];
  }
}

async function loadSettings() {
  try {
    const s = await api("/api/settings");
    state.settings = s;
    if (s.output_dir) $("#output_dir").value = s.output_dir;
    if (s.audio_format) $("#audio_format").value = s.audio_format;
    if (s.video_quality) $("#video_quality").value = s.video_quality;
    $("#playlist").checked = !!s.playlist;
    $("#sponsorblock").checked = !!s.sponsorblock;
    $("#embed_metadata").checked = s.embed_metadata !== false;
    $("#embed_thumbnail").checked = s.embed_thumbnail !== false;

    if (s.split_dir) $("#split-output").value = s.split_dir;
    if (s.threshold) $("#split-threshold").value = s.threshold;
    if (s.min_silence) $("#split-min-silence").value = s.min_silence;
    if (s.min_track) $("#split-min-track").value = s.min_track;
    if (s.split_fmt) $("#split-fmt").value = s.split_fmt;
    if (s.split_prefix) $("#split-prefix").value = s.split_prefix;
    $("#split-adaptive").checked = !!s.adaptive;
  } catch (e) { console.error(e); }
  applyDefaults();
}

const fallback = (sel, key) => {
  const raw = $(sel).value.trim();
  if (raw) return raw;
  const d = state.defaults || {};
  return d[key] !== undefined ? String(d[key]) : "";
};

function collectSettings() {
  return {
    output_dir: fallback("#output_dir", "output_dir") || "downloads",
    audio_format: $("#audio_format").value,
    video_quality: $("#video_quality").value,
    playlist: $("#playlist").checked,
    sponsorblock: $("#sponsorblock").checked,
    embed_metadata: $("#embed_metadata").checked,
    embed_thumbnail: $("#embed_thumbnail").checked,
    split_dir: fallback("#split-output", "split_dir") || "separado",
    threshold: fallback("#split-threshold", "threshold") || "-40dB",
    min_silence: parseFloat(fallback("#split-min-silence", "min_silence")) || 1.0,
    min_track: parseFloat(fallback("#split-min-track", "min_track")) || 5.0,
    split_fmt: $("#split-fmt").value,
    split_prefix: fallback("#split-prefix", "split_prefix") || "faixa",
    adaptive: $("#split-adaptive").checked,
  };
}

function saveSettings() {
  fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectSettings()),
  }).catch((e) => console.error(e));
}

/* ---------------- Arquivos ---------------- */

function renderFiles() {
  const data = state.filesData;
  if (!data) return;
  const rows = data.entries;
  const tbody = $("#file-rows");
  tbody.innerHTML = "";
  $("#files-empty").hidden = rows.length > 0;

  const parts = state.filesDir.split("/").filter(Boolean);
  $("#crumbs").innerHTML = `<a data-nav="">raiz</a>` +
    parts.map((p, i) => {
      const path = parts.slice(0, i + 1).join("/");
      return `<a data-nav="${path}">${esc(p)}</a>`;
    }).join(`<span>›</span>`);

  rows.forEach((e) => {
    const tr = document.createElement("tr");
    if (e.is_dir) {
      tr.className = "dir-row";
      tr.innerHTML = `
        <td><span class="fname" data-nav="${esc(e.path)}">${svg("i-folder")}${esc(e.name)}</span></td>
        <td class="size">-</td>
        <td class="size">${fmtDate(e.modified)}</td>
        <td></td>`;
      tr.querySelector("[data-nav]").addEventListener("click", () => {
        state.filesDir = e.path;
        loadFiles();
      });
    } else {
      const href = "/api/files/download?path=" + encodeURIComponent(e.path);
      tr.innerHTML = `
        <td><span class="fname">${svg("i-file")}${esc(e.name)}</span></td>
        <td class="size">${fmtBytes(e.size)}</td>
        <td class="size">${fmtDate(e.modified)}</td>
        <td class="td-actions">
          <a class="icon-btn green" href="${href}" title="Baixar">${svg("i-download")}</a>
          <button class="icon-btn purple" data-use="${esc(e.path)}" title="Usar no separador">${svg("i-split")}</button>
        </td>`;
      tr.querySelector("[data-use]").addEventListener("click", () => {
        $("#split-file").value = e.path;
        document.querySelector('[data-tab="separar"]').click();
        showToast("Arquivo selecionado no separador", "info");
      });
    }
    tbody.appendChild(tr);
  });
}

async function loadFiles() {
  try {
    const q = `?rel=${encodeURIComponent(state.filesDir)}`;
    state.filesData = await api("/api/files" + q);
    renderFiles();
  } catch (e) {
    $("#file-rows").innerHTML = "";
    $("#files-empty").hidden = false;
    $("#files-empty").querySelector("p").textContent = e.message;
  }
}

/* ---------------- Abas ---------------- */

function activateTab(btn) {
  document.querySelectorAll(".tabs button").forEach((b) => {
    b.classList.remove("active");
    b.setAttribute("aria-selected", "false");
  });
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  btn.classList.add("active");
  btn.setAttribute("aria-selected", "true");
  $("#tab-" + btn.dataset.tab).classList.add("active");
  state.filesTabActive = btn.dataset.tab === "arquivos";
  if (state.filesTabActive) loadFiles();
}

function initTabs() {
  const buttons = [...document.querySelectorAll(".tabs button")];
  buttons.forEach((btn, i) => {
    btn.addEventListener("click", () => activateTab(btn));
    btn.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      let next;
      if (e.key === "Home") next = buttons[0];
      else if (e.key === "End") next = buttons[buttons.length - 1];
      else next = buttons[(i + (e.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length];
      next.focus();
      activateTab(next);
    });
  });
}

/* ---------------- Dropzone ---------------- */

function setDropzoneUploading(on) {
  $("#dropzone").classList.toggle("uploading", on);
}

function setDropzoneFile(name, size) {
  $("#dz-name").textContent = name;
  $("#dz-size").textContent = fmtBytes(size);
  $("#dz-file").hidden = false;
  $("#dropzone").classList.add("has-file");
}

function clearDropzoneFile() {
  $("#dz-file").hidden = true;
  $("#dropzone").classList.remove("has-file", "uploading");
  $("#split-file").value = "";
  $("#file-picker").value = "";
}

async function uploadFile(file) {
  setDropzoneUploading(true);
  try {
    const form = new FormData();
    form.append("file", file);
    const res = await api("/api/files/upload", { method: "POST", body: form });
    $("#split-file").value = res.path;
    setDropzoneFile(res.name, res.size);
    showToast(`Arquivo "${res.name}" enviado`, "success");
  } catch (e) {
    showToast(e.message, "error");
  } finally {
    setDropzoneUploading(false);
  }
}

function initDropzone() {
  const dz = $("#dropzone");
  const picker = $("#file-picker");

  dz.addEventListener("click", () => picker.click());
  dz.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); picker.click(); }
  });
  picker.addEventListener("change", () => {
    if (picker.files[0]) uploadFile(picker.files[0]);
  });
  ["dragover", "dragenter"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("dragging"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("dragging"); })
  );
  dz.addEventListener("drop", (e) => {
    const file = e.dataTransfer?.files?.[0];
    if (file) uploadFile(file);
  });
  $("#dz-remove").addEventListener("click", (e) => {
    e.stopPropagation();
    clearDropzoneFile();
  });
}

/* ---------------- Formularios ---------------- */

function initModeSeg() {
  const segBtns = document.querySelectorAll(".seg-btn");
  const select = $("#mode");

  function setMode(value) {
    select.value = value;
    segBtns.forEach((b) => b.classList.toggle("active", b.dataset.mode === value));
    select.dispatchEvent(new Event("change"));
  }

  segBtns.forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));

  const video = select.value === "video";
  $("#fmt-field").hidden = video;
  $("#vq-field").hidden = !video;
}

function initForms() {
  $("#form-download").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const urls = $("#urls").value.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!urls.length) { showToast("Informe ao menos uma URL", "error"); return; }
    const body = {
      urls,
      mode: $("#mode").value,
      audio_format: $("#audio_format").value,
      video_quality: $("#video_quality").value,
      output_dir: fallback("#output_dir", "output_dir") || "downloads",
      playlist: $("#playlist").checked,
      sponsorblock: $("#sponsorblock").checked,
      embed_metadata: $("#embed_metadata").checked,
      embed_thumbnail: $("#embed_thumbnail").checked,
    };
    try {
      await api("/api/download", { method: "POST", body: JSON.stringify(body) });
      $("#urls").value = "";
      showToast(`${urls.length} URL(s) adicionada(s) a fila`, "success");
      saveSettings();
    } catch (e) { showToast(e.message, "error"); }
  });

  $("#form-split").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const file = $("#split-file").value.trim();
    if (!file) { showToast("Informe o arquivo de audio (ou arraste-o acima)", "error"); return; }
    const body = {
      file,
      output_dir: fallback("#split-output", "split_dir") || "separado",
      threshold: fallback("#split-threshold", "threshold") || "-40dB",
      min_silence: parseFloat(fallback("#split-min-silence", "min_silence")) || 1.0,
      min_track: parseFloat(fallback("#split-min-track", "min_track")) || 5.0,
      fmt: $("#split-fmt").value,
      bitrate: $("#split-bitrate").value.trim(),
      prefix: fallback("#split-prefix", "split_prefix") || "faixa",
      digits: parseInt($("#split-digits").value, 10) || 2,
      lead_in: parseFloat($("#split-lead-in").value) || 0.15,
      lead_out: parseFloat($("#split-lead-out").value) || 0.15,
      adaptive: $("#split-adaptive").checked,
    };
    try {
      await api("/api/split", { method: "POST", body: JSON.stringify(body) });
      showToast("Separacao iniciada", "success");
      saveSettings();
    } catch (e) { showToast(e.message, "error"); }
  });

  $("#mode").addEventListener("change", () => {
    const video = $("#mode").value === "video";
    $("#fmt-field").hidden = video;
    $("#vq-field").hidden = !video;
  });

  $("#refresh-files").addEventListener("click", loadFiles);
  $("#clear-finished").addEventListener("click", clearFinished);
}

/* ---------------- Init ---------------- */

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initModeSeg();
  initForms();
  initDropzone();
  loadDefaults();
  loadSettings();
  loadHealth();
  loadFiles();
  pollJobs();
  setInterval(pollJobs, 1000);
  setInterval(loadHealth, 15000);
});
