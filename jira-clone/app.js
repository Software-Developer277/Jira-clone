/* SprintFlow — Jira Clone frontend (vanilla JS SPA) */
"use strict";

const $ = (s) => document.querySelector(s);

const STATUSES = ["BACKLOG", "IN_PROGRESS", "IN_REVIEW", "DONE"];
const STATUS_LABEL = {
  BACKLOG: "Backlog",
  IN_PROGRESS: "In Progress",
  IN_REVIEW: "In Review",
  DONE: "Done",
};
const TYPE_LABEL = { BUG: "🐞 Bug", FEATURE: "✨ Feature", TASK: "📋 Task" };
const PRIORITY_CLASS = { LOW: "p-low", MEDIUM: "p-medium", HIGH: "p-high", CRITICAL: "p-critical" };
const ACT_ICON = {
  created: "🆕",
  status_changed: "🔀",
  assignee_changed: "👤",
  priority_changed: "🔺",
  commented: "💬",
};

const state = {
  token: localStorage.getItem("sf_token") || null,
  user: null,
  workspaces: [],
  wsId: null,
  projects: [],
  projectId: null,
  issues: [],
  members: [],
  filters: { q: "", assignee_id: "", priority: "" },
  current: null, // { issue, comments, activity }
  authMode: "login",
  debounce: null,
};

/* ================= API ================= */

async function api(path, opts = {}) {
  opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (state.token) opts.headers["Authorization"] = "Bearer " + state.token;
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (res.status === 402 && data && data.code === "quota_exceeded") {
    showUpgrade(data);
    throw Object.assign(new Error(data.error), { quota: true });
  }
  if (!res.ok) {
    throw Object.assign(new Error((data && data.error) || "HTTP " + res.status), {
      status: res.status,
      data,
    });
  }
  return data;
}

/* ================= Helpers ================= */

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

const renderMd = (s) => DOMPurify.sanitize(marked.parse(s || ""));
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString() : "");
const currentWs = () => state.workspaces.find((w) => w.id === state.wsId);

function toast(msg, kind = "info") {
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.textContent = msg;
  $("#toast").appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

function memberOptions(selectedId, withUnassigned) {
  let html = withUnassigned ? '<option value="">— Təyin edilməyib —</option>' : "";
  for (const m of state.members) {
    html += `<option value="${m.id}" ${m.id === selectedId ? "selected" : ""}>${esc(m.name)}</option>`;
  }
  return html;
}

/* ================= Auth ================= */

function showAuth() {
  $("#auth-view").classList.remove("hidden");
  $("#app-view").classList.add("hidden");
}

function showApp() {
  $("#auth-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
  $("#user-name").textContent = state.user.name;
  loadWorkspaces();
}

async function submitAuth(e) {
  e.preventDefault();
  const body = {
    email: $("#auth-email").value.trim(),
    password: $("#auth-password").value,
  };
  const path = state.authMode === "register" ? "/api/auth/register" : "/api/auth/login";
  if (state.authMode === "register") body.name = $("#auth-name").value.trim();
  try {
    const data = await api(path, { method: "POST", body: JSON.stringify(body) });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("sf_token", data.token);
    showApp();
  } catch (err) {
    toast(err.message, "error");
  }
}

function setAuthMode(mode) {
  state.authMode = mode;
  $("#tab-login").classList.toggle("active", mode === "login");
  $("#tab-register").classList.toggle("active", mode === "register");
  $("#auth-name").classList.toggle("hidden", mode === "login");
}

async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (e) { /* ignore */ }
  localStorage.removeItem("sf_token");
  state.token = null;
  state.user = null;
  showAuth();
}

/* ================= Workspaces / projects ================= */

async function loadWorkspaces() {
  try {
    state.workspaces = await api("/api/workspaces");
    const sel = $("#ws-select");
    sel.innerHTML = state.workspaces
      .map((w) => `<option value="${w.id}">${esc(w.name)} (${esc(w.plan_tier)})</option>`)
      .join("");
    if (!state.workspaces.length) {
      sel.innerHTML = '<option value="">— workspace yoxdur —</option>';
      return;
    }
    state.wsId = state.workspaces[0].id;
    sel.value = state.wsId;
    updatePlanBadge();
    await Promise.all([loadProjects(), loadMembers()]);
    loadBoard();
  } catch (e) {
    toast(e.message, "error");
  }
}

function updatePlanBadge() {
  const ws = currentWs();
  const badge = $("#plan-badge");
  if (!ws) { badge.textContent = ""; return; }
  const pro = ws.plan_tier === "pro";
  badge.textContent = pro ? "⭐ PRO" : "FREE plan";
  badge.classList.toggle("pro", pro);
}

async function createWorkspace() {
  const name = prompt("Workspace adı:");
  if (!name) return;
  const slug = prompt("Slug (nümunə: my-team):", name.toLowerCase().replace(/[^a-z0-9]+/g, "-"));
  if (!slug) return;
  try {
    const ws = await api("/api/workspaces", { method: "POST", body: JSON.stringify({ name, slug }) });
    toast("Workspace yaradıldı", "success");
    await loadWorkspaces();
    $("#ws-select").value = String(ws.id);
    selectWorkspace(ws.id);
  } catch (e) {
    toast(e.message, "error");
  }
}

async function selectWorkspace(id) {
  state.wsId = id;
  updatePlanBadge();
  await Promise.all([loadProjects(), loadMembers()]);
  loadBoard();
}

async function loadProjects() {
  try {
    state.projects = await api(`/api/workspaces/${state.wsId}/projects`);
    const sel = $("#project-select");
    sel.innerHTML = state.projects.length
      ? state.projects.map((p) => `<option value="${p.id}">${esc(p.key)} — ${esc(p.name)}</option>`).join("")
      : '<option value="">— layihə yoxdur —</option>';
    state.projectId = state.projects.length ? state.projects[0].id : null;
    if (state.projects.length) sel.value = state.projectId;
  } catch (e) {
    toast(e.message, "error");
  }
}

async function createProject() {
  const name = prompt("Layihə adı:");
  if (!name) return;
  const key = prompt("Açar (2-10 hərf/rəqəm, nümunə: WEB):", name.slice(0, 4).toUpperCase());
  if (!key) return;
  try {
    const p = await api(`/api/workspaces/${state.wsId}/projects`, {
      method: "POST",
      body: JSON.stringify({ name, key }),
    });
    toast(`Layihə ${p.key} yaradıldı`, "success");
    await loadProjects();
    state.projectId = p.id;
    $("#project-select").value = String(p.id);
    loadBoard();
  } catch (e) {
    toast(e.message, "error"); // 402-də upgrade modal artıq göstərilib
  }
}

async function deleteProject() {
  if (!state.projectId) return;
  if (!confirm("Layihə silinsin? Aktiv ticket-lər varsa, soft delete təklif olunacaq.")) return;
  try {
    await api(`/api/projects/${state.projectId}?force=1`, { method: "DELETE" });
    toast("Layihə soft-delete edildi (ticket-lər saxlanılıb)", "success");
    await loadProjects();
    loadBoard();
  } catch (e) {
    toast(e.message, "error");
  }
}

async function loadMembers() {
  try {
    state.members = await api(`/api/workspaces/${state.wsId}/members`);
    $("#f-assignee").innerHTML =
      '<option value="">Məsul: hamısı</option>' +
      state.members.map((m) => `<option value="${m.id}">${esc(m.name)}</option>`).join("");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function inviteMember() {
  const email = prompt("Dəvət olunacaq istifadəçinin email-i (sistemdə qeydiyyatlı olmalıdır):");
  if (!email) return;
  try {
    await api(`/api/workspaces/${state.wsId}/invite`, {
      method: "POST",
      body: JSON.stringify({ email, role: "member" }),
    });
    toast("Üzv əlavə edildi", "success");
    await loadMembers();
  } catch (e) {
    toast(e.message, "error");
  }
}

/* ================= Board ================= */

function loadBoard() {
  if (!state.projectId) {
    state.issues = [];
    renderBoard();
    return;
  }
  const p = new URLSearchParams();
  if (state.filters.q) p.set("q", state.filters.q);
  if (state.filters.assignee_id) p.set("assignee_id", state.filters.assignee_id);
  if (state.filters.priority) p.set("priority", state.filters.priority);
  api(`/api/projects/${state.projectId}/issues?` + p.toString())
    .then((issues) => {
      state.issues = issues;
      renderBoard();
    })
    .catch((e) => toast(e.message, "error"));
}

function renderBoard() {
  const board = $("#board");
  board.innerHTML = "";
  $("#board-empty").classList.toggle("hidden", state.issues.length > 0);
  for (const st of STATUSES) {
    const col = document.createElement("div");
    col.className = "column";
    col.dataset.status = st;
    const items = state.issues.filter((i) => i.status === st);
    col.innerHTML =
      `<div class="col-header"><span>${STATUS_LABEL[st]}</span>` +
      `<span class="count">${items.length}</span></div><div class="col-body"></div>`;
    const body = col.querySelector(".col-body");
    items.forEach((issue) => body.appendChild(cardEl(issue)));
    col.addEventListener("dragover", (e) => {
      e.preventDefault();
      col.classList.add("drag-over");
    });
    col.addEventListener("dragleave", () => col.classList.remove("drag-over"));
    col.addEventListener("drop", (e) => {
      e.preventDefault();
      col.classList.remove("drag-over");
      const id = +e.dataTransfer.getData("text/plain");
      if (id) moveIssue(id, st);
    });
    board.appendChild(col);
  }
}

function cardEl(issue) {
  const el = document.createElement("div");
  el.className = "card";
  el.draggable = true;
  el.innerHTML =
    `<div class="card-top"><span class="key">${esc(issue.issue_key)}</span>` +
    `<span class="priority ${PRIORITY_CLASS[issue.priority] || ""}">${issue.priority}</span></div>` +
    `<div class="card-title">${esc(issue.title)}</div>` +
    `<div class="card-bottom"><span>${TYPE_LABEL[issue.issue_type] || issue.issue_type}</span>` +
    (issue.story_points != null ? `<span class="points">${issue.story_points}</span>` : "") +
    `<span class="spacer"></span>` +
    `<span class="avatar" title="${esc(issue.assignee_name || "Təyin edilməyib")}">` +
    esc((issue.assignee_name || "?").slice(0, 1).toUpperCase()) + "</span></div>";
  el.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", String(issue.id));
    el.classList.add("dragging");
  });
  el.addEventListener("dragend", () => el.classList.remove("dragging"));
  el.addEventListener("click", () => openIssue(issue.id));
  return el;
}

/* Optimistic UI drag-and-drop: kart dərhal köçür, xəta olarsa geri qayıdır. */
function moveIssue(id, status) {
  const issue = state.issues.find((i) => i.id === id);
  if (!issue || issue.status === status) return;
  const prevStatus = issue.status;
  issue.status = status;
  renderBoard();
  api(`/api/issues/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status, version: issue.version }),
  })
    .then((updated) => {
      Object.assign(issue, updated);
      renderBoard();
    })
    .catch((err) => {
      issue.status = prevStatus;
      renderBoard();
      if (err.status === 409) {
        toast("⚠️ Konflikt: başqa istifadəçi bu kartı dəyişdi — yenilənir...", "warn");
        refreshIssueQuiet(id);
      } else {
        toast(err.message, "error");
      }
    });
}

function refreshIssueQuiet(id) {
  api(`/api/issues/${id}`)
    .then((fresh) => {
      const idx = state.issues.findIndex((i) => i.id === id);
      if (idx >= 0) state.issues[idx] = fresh;
      renderBoard();
    })
    .catch(() => {});
}

/* ================= Issue detail modal ================= */

async function openIssue(id) {
  try {
    const [issue, comments, activity] = await Promise.all([
      api(`/api/issues/${id}`),
      api(`/api/issues/${id}/comments`),
      api(`/api/issues/${id}/activity`),
    ]);
    state.current = { issue, comments, activity };
    renderIssueModal();
    $("#issue-modal").classList.remove("hidden");
  } catch (e) {
    toast(e.message, "error");
  }
}

function renderIssueModal() {
  const { issue, comments, activity } = state.current;
  $("#im-key").textContent = issue.issue_key + " · " + (TYPE_LABEL[issue.issue_type] || "");
  $("#im-title").value = issue.title;
  $("#im-description").value = issue.description || "";
  $("#im-desc-preview").classList.add("hidden");
  $("#im-description").classList.remove("hidden");
  $("#tab-desc-write").classList.add("active");
  $("#tab-desc-preview").classList.remove("active");

  $("#im-status").value = issue.status;
  $("#im-assignee").innerHTML = memberOptions(issue.assignee_id, true);
  $("#im-priority").value = issue.priority;
  $("#im-type").value = issue.issue_type;
  $("#im-points").value = issue.story_points ?? "";

  $("#im-meta").innerHTML =
    `Yaradan: <b>${esc(issue.reporter_name || "—")}</b><br>` +
    `Yaradılıb: ${fmtDate(issue.created_at)}<br>` +
    `Yenilənib: ${fmtDate(issue.updated_at)}<br>` +
    `Versiya: v${issue.version}`;

  $("#im-comments").innerHTML = comments.length
    ? comments
        .map(
          (c) =>
            `<div class="comment"><div class="comment-head">` +
            `<b>${esc(c.author_name || "—")}</b><span>${fmtDate(c.created_at)}</span></div>` +
            `<div class="md-body">${renderMd(c.content)}</div></div>`
        )
        .join("")
    : '<p class="muted small">Hələ şərh yoxdur.</p>';
  $("#im-new-comment").value = "";

  $("#im-activity").innerHTML = activity
    .map(
      (a) =>
        `<div class="act">${ACT_ICON[a.action] || "•"} <b>${esc(a.actor_name || "—")}</b>` +
        ` — ${esc(a.detail)}<br><span class="small">${fmtDate(a.created_at)}</span></div>`
    )
    .join("");
}

async function patchIssue(patch) {
  const cur = state.current;
  if (!cur) return;
  try {
    const updated = await api(`/api/issues/${cur.issue.id}`, {
      method: "PATCH",
      body: JSON.stringify(Object.assign({ version: cur.issue.version }, patch)),
    });
    cur.issue = updated;
    const idx = state.issues.findIndex((i) => i.id === updated.id);
    if (idx >= 0) state.issues[idx] = updated;
    renderBoard();
    renderIssueModal();
  } catch (e) {
    if (e.status === 409) {
      toast("⚠️ Konflikt: başqa istifadəçi dəyişdi — son məlumat yüklənir...", "warn");
      await openIssue(cur.issue.id); // modalı son state ilə yenilə
    } else {
      toast(e.message, "error");
    }
  }
}

async function saveDescription() {
  const cur = state.current;
  if (!cur) return;
  const value = $("#im-description").value;
  if (value === (cur.issue.description || "")) return;
  await patchIssue({ description: value });
}

async function addComment() {
  const cur = state.current;
  const content = $("#im-new-comment").value.trim();
  if (!cur || !content) return;
  try {
    await api(`/api/issues/${cur.issue.id}/comments`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    const [comments, activity] = await Promise.all([
      api(`/api/issues/${cur.issue.id}/comments`),
      api(`/api/issues/${cur.issue.id}/activity`),
    ]);
    cur.comments = comments;
    cur.activity = activity;
    renderIssueModal();
  } catch (e) {
    toast(e.message, "error");
  }
}

/* ================= New issue / upgrade ================= */

function openNewIssue() {
  if (!state.projectId) {
    toast("Əvvəlcə layihə yaradın", "warn");
    return;
  }
  $("#ni-title").value = "";
  $("#ni-description").value = "";
  $("#ni-points").value = "";
  $("#ni-assignee").innerHTML = memberOptions(null, true);
  $("#new-issue-modal").classList.remove("hidden");
  setTimeout(() => $("#ni-title").focus(), 50);
}

async function createIssue() {
  const title = $("#ni-title").value.trim();
  if (!title) {
    toast("Başlıq boş ola bilməz", "error");
    return;
  }
  const assigneeRaw = $("#ni-assignee").value;
  const body = {
    title,
    issue_type: $("#ni-type").value,
    priority: $("#ni-priority").value,
    description: $("#ni-description").value,
    assignee_id: assigneeRaw ? +assigneeRaw : null,
    story_points: $("#ni-points").value === "" ? null : +$("#ni-points").value,
  };
  try {
    await api(`/api/projects/${state.projectId}/issues`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    $("#new-issue-modal").classList.add("hidden");
    toast("Ticket yaradıldı", "success");
    loadBoard();
  } catch (e) {
    if (e.quota) {
      $("#new-issue-modal").classList.add("hidden"); // upgrade modal artıq açıqdır
    } else {
      toast(e.message, "error");
    }
  }
}

function showUpgrade(data) {
  $("#upgrade-msg").textContent =
    (data && data.error) || "Free plan limitinə çatdınız.";
  $("#upgrade-modal").classList.remove("hidden");
}

async function upgradePlan() {
  try {
    await api(`/api/workspaces/${state.wsId}/upgrade`, { method: "POST" });
    const ws = currentWs();
    if (ws) ws.plan_tier = "pro";
    updatePlanBadge();
    $("#upgrade-modal").classList.add("hidden");
    toast("⭐ Pro plan aktivdir! İndi yenidən cəhd edin.", "success");
  } catch (e) {
    toast(e.message, "error");
  }
}

/* ================= Filters ================= */

function onSearch() {
  clearTimeout(state.debounce);
  state.debounce = setTimeout(() => {
    state.filters.q = $("#f-search").value.trim();
    loadBoard();
  }, 300);
}

/* ================= Wiring ================= */

function bindStatic() {
  $("#tab-login").addEventListener("click", () => setAuthMode("login"));
  $("#tab-register").addEventListener("click", () => setAuthMode("register"));
  $("#auth-form").addEventListener("submit", submitAuth);
  $("#btn-logout").addEventListener("click", logout);

  $("#ws-select").addEventListener("change", (e) => selectWorkspace(+e.target.value));
  $("#btn-new-ws").addEventListener("click", createWorkspace);
  $("#project-select").addEventListener("change", (e) => {
    state.projectId = +e.target.value || null;
    loadBoard();
  });
  $("#btn-new-project").addEventListener("click", createProject);
  $("#btn-del-project").addEventListener("click", deleteProject);
  $("#btn-invite").addEventListener("click", inviteMember);

  $("#f-search").addEventListener("input", onSearch);
  $("#f-assignee").addEventListener("change", (e) => {
    state.filters.assignee_id = e.target.value;
    loadBoard();
  });
  $("#f-priority").addEventListener("change", (e) => {
    state.filters.priority = e.target.value;
    loadBoard();
  });
  $("#btn-new-issue").addEventListener("click", openNewIssue);
  $("#btn-create-issue").addEventListener("click", createIssue);

  // Issue modal
  $("#im-status").addEventListener("change", (e) => patchIssue({ status: e.target.value }));
  $("#im-assignee").addEventListener("change", (e) =>
    patchIssue({ assignee_id: e.target.value ? +e.target.value : null })
  );
  $("#im-priority").addEventListener("change", (e) => patchIssue({ priority: e.target.value }));
  $("#im-type").addEventListener("change", (e) => patchIssue({ issue_type: e.target.value }));
  $("#im-points").addEventListener("change", (e) =>
    patchIssue({ story_points: e.target.value === "" ? null : +e.target.value })
  );
  $("#im-title").addEventListener("change", (e) => {
    if (state.current && e.target.value.trim() && e.target.value !== state.current.issue.title) {
      patchIssue({ title: e.target.value.trim() });
    }
  });
  $("#btn-save-desc").addEventListener("click", saveDescription);
  $("#btn-add-comment").addEventListener("click", addComment);

  $("#tab-desc-write").addEventListener("click", () => {
    $("#im-description").classList.remove("hidden");
    $("#im-desc-preview").classList.add("hidden");
    $("#tab-desc-write").classList.add("active");
    $("#tab-desc-preview").classList.remove("active");
  });
  $("#tab-desc-preview").addEventListener("click", () => {
    $("#im-desc-preview").innerHTML = renderMd($("#im-description").value);
    $("#im-description").classList.add("hidden");
    $("#im-desc-preview").classList.remove("hidden");
    $("#tab-desc-preview").classList.add("active");
    $("#tab-desc-write").classList.remove("active");
  });

  // Upgrade modal
  $("#btn-upgrade").addEventListener("click", upgradePlan);

  // Close buttons
  document.querySelectorAll("[data-close]").forEach((btn) =>
    btn.addEventListener("click", () => $("#" + btn.dataset.close).classList.add("hidden"))
  );
  document.querySelectorAll(".overlay").forEach((ov) =>
    ov.addEventListener("click", (e) => {
      if (e.target === ov) ov.classList.add("hidden");
    })
  );
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.querySelectorAll(".overlay").forEach((ov) => ov.classList.add("hidden"));
  });
}

async function init() {
  bindStatic();
  if (state.token) {
    try {
      state.user = await api("/api/auth/me");
      showApp();
      return;
    } catch (e) {
      localStorage.removeItem("sf_token");
      state.token = null;
    }
  }
  showAuth();
}

init();
