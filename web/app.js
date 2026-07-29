const APP_BASE = (window.APP_BASE || (location.pathname.startsWith("/cards") ? "/cards" : "")).replace(/\/$/, "");
function withBase(path) {
  if (!path) return path;
  if (/^https?:/i.test(path)) return path;
  const p = path.startsWith("/") ? path : "/" + path;
  return APP_BASE + p;
}

const state = {
  category: "rising",
  trends: [],
  selectedIssueId: null,
  project: null,
  selectedCardId: null,
  motion: "zoom",
  aspect: "9:16",
  engine: "hyperframes",
  templates: ["headline", "bullets", "chart", "quote", "cta"],
  meta: null,
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

async function api(path, opts = {}) {
  path = withBase(path);
  const res = await fetch(path, {
    headers: opts.body instanceof FormData ? undefined : { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const msg = typeof d === "string" ? d : d?.message || data.message || res.statusText;
    throw new Error(msg);
  }
  return data;
}

function toast(msg, bad = false) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = msg;
  el.className = bad ? "toast bad" : "toast";
  el.hidden = false;
  clearTimeout(window.__tt);
  window.__tt = setTimeout(() => (el.hidden = true), 2800);
}


let previewTimer = null;
let previewIdx = 0;

function cardPreviewHTML(card) {
  const kind = card?.kind || "headline";
  if (kind === "bullets") {
    const lis = (card.bullets || []).map((b) => `<li>${escapeHtml(b)}</li>`).join("");
    return `<div class="pv-card"><div class="pv-kicker">브리핑</div><h2>${escapeHtml(card.title || "")}</h2><ul>${lis}</ul></div>`;
  }
  if (kind === "chart") {
    return `<div class="pv-card"><div class="pv-kicker">비교</div><h2>${escapeHtml(card.title || "")}</h2>
      <div class="pv-bars"><div><span>${escapeHtml(card.left_label || "")}</span><b>${escapeHtml(card.left_value || "")}</b></div>
      <div class="hi"><span>${escapeHtml(card.right_label || "")}</span><b>${escapeHtml(card.right_value || "")}</b></div></div>
      <p>${escapeHtml(card.unit || "")}</p></div>`;
  }
  if (kind === "quote") {
    return `<div class="pv-card"><div class="pv-kicker">인용</div><blockquote>“${escapeHtml(card.quote || "")}”</blockquote><cite>— ${escapeHtml(card.attribution || "")}</cite></div>`;
  }
  if (kind === "cta") {
    return `<div class="pv-card"><div class="pv-kicker">정리</div><h2>${escapeHtml(card.title || "")}</h2><p>${escapeHtml(card.body || "")}</p><div class="pv-cta">${escapeHtml(card.button || "더보기")}</div></div>`;
  }
  return `<div class="pv-card"><div class="pv-kicker">${escapeHtml(card.kicker || "ISSUE")}</div><h1>${escapeHtml(card.title || "")}</h1><p>${escapeHtml(card.subtitle || "")}</p></div>`;
}

function paintInPagePreview(cards, idx = 0) {
  const stage = $("#stage");
  if (!stage) return;
  const list = cards || [];
  if (!list.length) {
    stage.classList.remove("phone-mode");
    stage.innerHTML = `<div class="empty">카드를 생성하면 여기에 미리보기가 뜹니다</div>`;
    return;
  }
  const phone = state.aspect === "9:16";
  stage.classList.toggle("phone-mode", !!phone);
  const i = ((idx % list.length) + list.length) % list.length;
  previewIdx = i;
  const card = list[i];
  const motion = state.project?.motion || state.motion || "zoom";
  stage.innerHTML = `
    <div class="pv-shell motion-${escapeHtml(motion)}">
      <div class="pv-meta">${i + 1}/${list.length} · ${escapeHtml(card.kind || "card")} · ${escapeHtml(motion)}</div>
      ${cardPreviewHTML(card)}
      <div class="pv-progress"><i style="width:${((i + 1) / list.length) * 100}%"></i></div>
    </div>`;
}

function startPreviewRotation() {
  if (previewTimer) clearInterval(previewTimer);
  previewTimer = setInterval(() => {
    const cards = state.project?.cards || [];
    if (cards.length < 2) return;
    paintInPagePreview(cards, previewIdx + 1);
  }, 2800);
}

function setPreview(_url) {
  // Always prefer in-page card preview so user never sees a black iframe.
  const cards = state.project?.cards || [];
  if (!cards.length) {
    paintInPagePreview([]);
    return;
  }
  // If a slide is selected, show that; else first
  let idx = 0;
  if (state.selectedCardId) {
    const found = cards.findIndex((c) => c.id === state.selectedCardId);
    if (found >= 0) idx = found;
  }
  paintInPagePreview(cards, idx);
  startPreviewRotation();
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderTrends() {
  const box = $("#issueList");
  if (!box) return;
  box.innerHTML =
    (state.trends || [])
      .map(
        (t) => `<button class="issue ${state.selectedIssueId === t.id ? "active" : ""}" data-id="${t.id}" type="button">
      <strong>${escapeHtml(t.title)}</strong>
      <span>${escapeHtml((t.summary || "").slice(0, 90))}</span>
    </button>`
      )
      .join("") || `<div class="status">이슈를 불러오는 중…</div>`;
  box.querySelectorAll("[data-id]").forEach((b) =>
    b.addEventListener("click", () => {
      state.selectedIssueId = b.dataset.id;
      renderTrends();
    })
  );
  const ticker = $("#ticker");
  if (ticker) {
    ticker.innerHTML = (state.trends || [])
      .slice(0, 8)
      .map((t) => `<span>🔥 <b>${escapeHtml(t.title.slice(0, 28))}</b></span>`)
      .join("");
  }
}

function renderSlides() {
  const cards = state.project?.cards || [];
  const box = $("#slides");
  if (!box) return;
  box.innerHTML =
    cards
      .map(
        (c, i) => `<article class="slide ${state.selectedCardId === c.id ? "active" : ""}" data-id="${c.id}" draggable="true">
      <div class="meta"><span>${String(i + 1).padStart(2, "0")}</span><span>${escapeHtml(c.kind)}</span></div>
      <h3>${escapeHtml(c.title || c.quote || c.kind)}</h3>
      <p>${escapeHtml((c.subtitle || c.body || (c.bullets || []).join(" · ") || "").slice(0, 80))}</p>
    </article>`
      )
      .join("") || `<div class="status">이슈를 고르고 카드 생성 버튼을 누르세요.</div>`;

  box.querySelectorAll(".slide").forEach((el) => {
    el.addEventListener("click", () => {
      state.selectedCardId = el.dataset.id;
      renderSlides();
      renderEditor();
      const cards = state.project?.cards || [];
      const idx = cards.findIndex((c) => c.id === state.selectedCardId);
      paintInPagePreview(cards, idx >= 0 ? idx : 0);
      startPreviewRotation();
    });
    el.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", el.dataset.id);
    });
    el.addEventListener("dragover", (e) => e.preventDefault());
    el.addEventListener("drop", async (e) => {
      e.preventDefault();
      const from = e.dataTransfer.getData("text/plain");
      const to = el.dataset.id;
      if (!from || !to || !state.project) return;
      const ids = state.project.cards.map((c) => c.id);
      const fi = ids.indexOf(from);
      const ti = ids.indexOf(to);
      if (fi < 0 || ti < 0) return;
      ids.splice(ti, 0, ids.splice(fi, 1)[0]);
      try {
        const data = await api(`/api/projects/${state.project.id}/cards/reorder`, {
          method: "POST",
          body: JSON.stringify({ order: ids }),
        });
        state.project = data.project;
        renderSlides();
        setPreview(state.project.preview_url);
        toast("슬라이드 순서 변경");
      } catch (err) {
        toast(err.message, true);
      }
    });
  });
}

function renderEditor() {
  const ed = $("#editor");
  if (!ed) return;
  const card = (state.project?.cards || []).find((c) => c.id === state.selectedCardId);
  if (!card) {
    ed.innerHTML = `<div class="status">슬라이드를 선택하면 여기서 편집합니다.</div>`;
    return;
  }
  const kind = card.kind || "headline";
  let fields = "";
  if (kind === "headline") {
    fields = `
      <label>키커</label><input id="f_kicker" value="${escapeHtml(card.kicker || "")}"/>
      <label>제목</label><textarea id="f_title">${escapeHtml(card.title || "")}</textarea>
      <label>부제</label><input id="f_subtitle" value="${escapeHtml(card.subtitle || "")}"/>`;
  } else if (kind === "bullets") {
    fields = `
      <label>제목</label><input id="f_title" value="${escapeHtml(card.title || "")}"/>
      <label>불릿 (줄바꿈)</label><textarea id="f_bullets" rows="5">${escapeHtml((card.bullets || []).join("\n"))}</textarea>`;
  } else if (kind === "chart") {
    fields = `
      <label>제목</label><input id="f_title" value="${escapeHtml(card.title || "")}"/>
      <label>왼쪽 라벨/값</label><div class="row"><input id="f_left_label" value="${escapeHtml(card.left_label || "")}"/><input id="f_left_value" value="${escapeHtml(card.left_value || "")}"/></div>
      <label>오른쪽 라벨/값</label><div class="row"><input id="f_right_label" value="${escapeHtml(card.right_label || "")}"/><input id="f_right_value" value="${escapeHtml(card.right_value || "")}"/></div>
      <label>단위</label><input id="f_unit" value="${escapeHtml(card.unit || "")}"/>`;
  } else if (kind === "quote") {
    fields = `
      <label>인용</label><textarea id="f_quote" rows="4">${escapeHtml(card.quote || "")}</textarea>
      <label>출처</label><input id="f_attr" value="${escapeHtml(card.attribution || "")}"/>`;
  } else {
    fields = `
      <label>제목</label><input id="f_title" value="${escapeHtml(card.title || "")}"/>
      <label>본문</label><textarea id="f_body" rows="4">${escapeHtml(card.body || "")}</textarea>
      <label>버튼</label><input id="f_button" value="${escapeHtml(card.button || "")}"/>`;
  }
  ed.innerHTML = `
    <div class="kicker">슬라이드 편집 · ${escapeHtml(kind)}</div>
    <div class="editor-fields">${fields}</div>
    <div class="row" style="margin-top:10px">
      <button class="btn primary" id="btnSaveCard" type="button">카드 저장</button>
    </div>`;
  $("#btnSaveCard")?.addEventListener("click", saveCard);
}

async function saveCard() {
  if (!state.project?.id || !state.selectedCardId) return;
  const card = (state.project.cards || []).find((c) => c.id === state.selectedCardId);
  if (!card) return;
  const patch = {};
  const val = (id) => document.getElementById(id)?.value;
  if (card.kind === "headline") {
    patch.kicker = val("f_kicker");
    patch.title = val("f_title");
    patch.subtitle = val("f_subtitle");
  } else if (card.kind === "bullets") {
    patch.title = val("f_title");
    patch.bullets = (val("f_bullets") || "").split(/\n+/).map((s) => s.trim()).filter(Boolean);
  } else if (card.kind === "chart") {
    patch.title = val("f_title");
    patch.left_label = val("f_left_label");
    patch.left_value = val("f_left_value");
    patch.right_label = val("f_right_label");
    patch.right_value = val("f_right_value");
    patch.unit = val("f_unit");
  } else if (card.kind === "quote") {
    patch.quote = val("f_quote");
    patch.attribution = val("f_attr");
  } else {
    patch.title = val("f_title");
    patch.body = val("f_body");
    patch.button = val("f_button");
  }
  try {
    const data = await api(`/api/projects/${state.project.id}/cards/update`, {
      method: "POST",
      body: JSON.stringify({ card_id: state.selectedCardId, patch }),
    });
    state.project = data.project;
    renderSlides();
    renderEditor();
    setPreview(state.project.preview_url);
    const st = $("#stage");
    if (st) st.scrollIntoView({behavior:"smooth", block:"center"});
    toast("카드 저장됨 · 미리보기 갱신");
  } catch (e) {
    toast(e.message, true);
  }
}

/* setPreview replaced below */

async function loadMeta() {
  state.meta = await api("/api/meta");
  const cat = $("#catChips");
  cat.innerHTML = (state.meta.issue_categories || [])
    .map((c) => `<button class="chip ${state.category === c.id ? "active" : ""}" data-cat="${c.id}" type="button">${c.label}</button>`)
    .join("");
  cat.querySelectorAll("[data-cat]").forEach((b) =>
    b.addEventListener("click", async () => {
      state.category = b.dataset.cat;
      await loadTrends(true);
      loadMeta();
    })
  );
  const motion = $("#motionChips");
  const motions = state.meta.motion_presets || [];
  motion.innerHTML = motions
    .map((m) => `<button class="chip ${state.motion === m.id ? "active" : ""}" data-motion="${m.id}" type="button" title="${escapeHtml(m.desc || "")}">${escapeHtml(m.label)}${m.desc ? `<small>${escapeHtml(m.desc)}</small>` : ""}</button>`)
    .join("");
  motion.querySelectorAll("[data-motion]").forEach((b) =>
    b.addEventListener("click", async () => {
      state.motion = b.dataset.motion;
      if (state.motion === "remotion") state.engine = "remotion";
      else if (state.engine === "remotion") state.engine = "hyperframes";
      const engSel = $("#engine");
      if (engSel) engSel.value = state.engine;
      if (state.project?.id) {
        try {
          // persist motion on project + refresh composition theme
          const data = await api(`/api/projects/${state.project.id}/save`, {
            method: "POST",
            body: JSON.stringify({ motion: state.motion, engine_hint: state.motion === "remotion" ? "remotion" : state.engine }),
          });
          state.project = data.project;
          if (state.motion === "remotion") {
            await api(`/api/projects/${state.project.id}/engine`, { method: "POST", body: JSON.stringify({ engine: "remotion" }) });
          }
          setPreview();
        } catch (e) {
          toast(e.message || String(e), true);
        }
      } else {
        setPreview();
      }
      loadMeta();
    })
  );
  const tpl = $("#tplChips");
  tpl.innerHTML = (state.meta.card_templates || [])
    .map((t) => `<button class="chip ${state.templates.includes(t.id) ? "active" : ""}" data-tpl="${t.id}" type="button">${t.label}</button>`)
    .join("");
  tpl.querySelectorAll("[data-tpl]").forEach((b) =>
    b.addEventListener("click", () => {
      const id = b.dataset.tpl;
      if (state.templates.includes(id)) state.templates = state.templates.filter((x) => x !== id);
      else state.templates = [...state.templates, id];
      if (!state.templates.length) state.templates = ["headline", "bullets", "cta"];
      loadMeta();
    })
  );
}

async function loadTrends(force = false) {
  $("#trendStatus").textContent = "실시간 피드 갱신 중…";
  try {
    const data = await api(`/api/trends?category=${encodeURIComponent(state.category)}${force ? "&force=true" : ""}`);
    state.trends = data.items || [];
    if (!state.selectedIssueId && state.trends[0]) state.selectedIssueId = state.trends[0].id;
    renderTrends();
    $("#trendStatus").textContent = `${data.cached ? "캐시" : "최신"} · ${state.trends.length}건 · ${new Date(data.updated_at || Date.now()).toLocaleTimeString()}`;
  } catch (e) {
    $("#trendStatus").textContent = e.message;
    toast(e.message, true);
  }
}

async function buildProject() {
  try {
    $("#btnBuild").disabled = true;
    const body = {
      issue_id: state.selectedIssueId,
      category: state.category,
      template_ids: state.templates,
      motion: state.motion,
      aspect_ratio: state.aspect,
      seconds_per_card: 3,
    };
    const data = await api("/api/projects/build", { method: "POST", body: JSON.stringify(body) });
    state.project = data.project;
    if (state.motion === "remotion") {
      state.engine = "remotion";
      const engSel = $("#engine"); if (engSel) engSel.value = "remotion";
      await api(`/api/projects/${state.project.id}/engine`, { method: "POST", body: JSON.stringify({ engine: "remotion" }) });
      const p2 = await api(`/api/projects/${state.project.id}`);
      state.project = p2.project;
    }
    state.selectedCardId = state.project.cards?.[0]?.id || null;
    renderSlides();
    renderEditor();
    setPreview(data.project.preview_url || `/preview/${data.project.id}`);
    $("#projStatus").textContent = `프로젝트 ${data.project.id} · 카드 ${data.project.cards.length} · 미리보기 표시 중`;
    const st = $("#stage");
    if (st) st.scrollIntoView({behavior:"smooth", block:"center"});
    toast("카드 " + data.project.cards.length + "장 생성 · 미리보기 확인");
  } catch (e) {
    toast(e.message, true);
  } finally {
    $("#btnBuild").disabled = false;
  }
}

async function renderProject() {
  if (!state.project?.id) return toast("먼저 카드를 생성하세요", true);
  try {
    $("#btnRender").disabled = true;
    toast("렌더 중… (" + (state.engine||"hyperframes") + ")");
    const data = await api(`/api/projects/${state.project.id}/render`, {
      method: "POST",
      body: JSON.stringify({ fps: 30, engine: state.engine || "hyperframes" }),
    });
    state.project = data.project;
    const r = data.render || {};
    $("#projStatus").textContent = `렌더: ${r.engine || "-"} · ${r.video_url ? "영상 준비" : "HTML 프리뷰"}`;
    if (r.video_url) {
      if (previewTimer) clearInterval(previewTimer);
      const st=$("#stage");
      if(st){
        st.classList.toggle("phone-mode", state.aspect==="9:16");
        st.innerHTML = `<video src="${withBase(r.video_url)}?t=${Date.now()}" controls playsinline style="width:100%;height:100%;object-fit:contain;background:#000"></video>`;
      }
    } else {
      setPreview(r.preview_url || state.project.preview_url);
    }
    toast(r.video_url ? `렌더 완료 (${r.engine})` : "프리뷰 준비");
  } catch (e) {
    toast(e.message, true);
  } finally {
    $("#btnRender").disabled = false;
  }
}

function wire() {
  $("#btnRefresh")?.addEventListener("click", () => loadTrends(true));
  $("#btnBuild")?.addEventListener("click", buildProject);
  $("#btnRender")?.addEventListener("click", renderProject);
  $("#btnPush")?.addEventListener("click", async () => {
    if (!state.project?.id) return toast("먼저 카드를 생성하세요", true);
    try {
      const data = await api(`/api/projects/${state.project.id}/push-timeline`, { method: "POST", body: "{}" });
      toast("Timeline 등록: " + (data.timeline?.uid || data.timeline?.name || "ok"));
    } catch (e) {
      toast(e.message, true);
    }
  });
  $("#aspect")?.addEventListener("change", (e) => {
    state.aspect = e.target.value;
    if (state.project?.preview_url) setPreview(state.project.preview_url);
  });
  $("#engine")?.addEventListener("change", async (e) => {
    state.engine = e.target.value;
    if (!state.project?.id) return;
    try {
      const data = await api(`/api/projects/${state.project.id}/engine`, {
        method: "POST",
        body: JSON.stringify({ engine: state.engine }),
      });
      state.project = data.project;
      setPreview(state.project.preview_url);
      toast("엔진: " + state.engine);
    } catch (err) {
      toast(err.message, true);
    }
  });
}

(async function init() {
  // deep link ?project=
  const qs = new URLSearchParams(location.search);
  const pid = qs.get("project");
  wire();
  await loadMeta();
  await loadTrends(true);
  if (pid) {
    try {
      const data = await api(`/api/projects/${pid}`);
      state.project = data.project;
      state.selectedCardId = state.project.cards?.[0]?.id || null;
      renderSlides();
      renderEditor();
      const v = state.project.render?.video_url;
      if (v) {
        $("#stage").innerHTML = `<video src="${withBase(v)}?t=${Date.now()}" controls playsinline style="width:100%;height:100%;background:#000;object-fit:contain"></video>`;
      } else setPreview(state.project.preview_url || `/preview/${pid}`);
      $("#projStatus").textContent = `프로젝트 ${pid}`;
    } catch (e) {
      setPreview(null);
      toast(e.message, true);
    }
  } else setPreview(null);
  const h = await api("/api/health");
  $("#health").textContent = `${h.service} v${h.version} · pw ${h.playwright ? "on" : "off"} · ff ${h.ffmpeg ? "on" : "off"}`;
})();
