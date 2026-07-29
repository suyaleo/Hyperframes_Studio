const APP_BASE = (window.APP_BASE || "").replace(/\/$/, "");
const THEME_KEY = "hyperframes-studio-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

const state = {
  category: "rising",
  trends: [],
  selectedIssueId: null,
  manualTopic: "",
  project: null,
  selectedCardId: null,
  motion: "zoom",
  aspect: "9:16",
  engine: "hyperframes",
  templates: ["headline", "bullets", "chart", "quote", "cta"],
  meta: null,
  health: null,
  previewIndex: 0,
  previewPlaying: false,
  renderRunning: false,
};

const $ = (selector) => document.querySelector(selector);
let previewTimer = null;
let toastTimer = null;
let modalOpener = null;
let themeMediaCleanup = null;

function withBase(path) {
  if (!path || /^https?:/i.test(path)) return path;
  return APP_BASE + (path.startsWith("/") ? path : `/${path}`);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(withBase(path), {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || data.message || response.statusText);
  }
  return data;
}

function toast(message, bad = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = bad ? "toast bad" : "toast";
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { element.hidden = true; }, 3200);
}

function readThemePreference() {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return ["light", "dark", "system"].includes(value) ? value : "system";
  } catch (_) {
    return "system";
  }
}

function resolveTheme(preference) {
  return preference === "system"
    ? (matchMedia(DARK_QUERY).matches ? "dark" : "light")
    : preference;
}

function applyTheme(preference) {
  const resolved = resolveTheme(preference);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
  const themeMeta = document.querySelector('meta[name="theme-color"]');
  if (themeMeta) themeMeta.content = resolved === "dark" ? "#16191b" : "#fbfaf7";
  return resolved;
}

function subscribeTheme(preference) {
  if (themeMediaCleanup) themeMediaCleanup();
  const media = matchMedia(DARK_QUERY);
  const update = () => applyTheme(preference);
  update();
  if (preference !== "system") {
    themeMediaCleanup = null;
    return;
  }
  media.addEventListener("change", update);
  themeMediaCleanup = () => media.removeEventListener("change", update);
}

function chooseTheme(preference) {
  try { localStorage.setItem(THEME_KEY, preference); } catch (_) { /* theme still applies */ }
  subscribeTheme(preference);
}

function setupTheme() {
  const preference = readThemePreference();
  $("#themePreference").value = preference;
  subscribeTheme(preference);
  $("#themePreference").addEventListener("change", (event) => chooseTheme(event.target.value));
}

function sourceLabel(item) {
  if (item.source_kind === "catalog") return "카탈로그";
  return "뉴스";
}

function renderTrends() {
  const list = $("#issueList");
  const rows = state.trends.map((item, index) => {
    const selected = !state.manualTopic && state.selectedIssueId === item.id;
    const metric = item.stars ? `${Number(item.stars).toLocaleString("ko-KR")} stars` : item.published || "출처 확인";
    return `<article class="issue-row" data-selected="${selected}" data-issue-row="${escapeHtml(item.id)}">
      <button class="issue-select" type="button" data-issue-id="${escapeHtml(item.id)}" aria-label="${escapeHtml(item.title)} 선택"></button>
      <span class="issue-index">${String(index + 1).padStart(2, "0")}</span>
      <div class="issue-content">
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.summary || "요약 정보가 없습니다.")}</p>
        <div class="issue-meta"><span class="source-kind">${sourceLabel(item)}</span><span>${escapeHtml(item.source || "알 수 없는 출처")}</span><span>·</span><span>${escapeHtml(metric)}</span></div>
      </div>
      ${item.url ? `<a class="issue-source-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" aria-label="원문 열기" title="원문 열기"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M14 5h5v5M10 14 19 5M19 14v5H5V5h5"/></svg></a>` : ""}
    </article>`;
  });

  list.innerHTML = rows.join("") || `<div class="empty-state compact"><strong>표시할 이슈가 없습니다</strong><span>새로고침하거나 다른 카테고리를 선택하세요.</span></div>`;
  list.querySelectorAll("[data-issue-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedIssueId = button.dataset.issueId;
      state.manualTopic = "";
      $("#topicInput").value = "";
      renderTrends();
      updateProjectReadiness();
    });
  });
  $("#issueCount").textContent = `${state.trends.length}개 항목 · 1개 선택`;
}

function renderCategories() {
  const box = $("#catChips");
  box.innerHTML = (state.meta?.issue_categories || []).map((category) => `
    <button class="category-tab" type="button" role="tab" aria-selected="${state.category === category.id}" data-category="${escapeHtml(category.id)}">${escapeHtml(category.label)}</button>`).join("");
  box.querySelectorAll("[data-category]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.dataset.category === state.category) return;
      state.category = button.dataset.category;
      state.selectedIssueId = null;
      state.manualTopic = "";
      $("#topicInput").value = "";
      renderCategories();
      await loadTrends(true);
    });
  });
}

function renderTemplateOptions() {
  const box = $("#tplChips");
  box.innerHTML = (state.meta?.card_templates || []).map((template) => `
    <button class="option-button" type="button" aria-pressed="${state.templates.includes(template.id)}" data-template="${escapeHtml(template.id)}">${escapeHtml(template.label)}</button>`).join("");
  box.querySelectorAll("[data-template]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.template;
      state.templates = state.templates.includes(id)
        ? state.templates.filter((value) => value !== id)
        : [...state.templates, id];
      if (!state.templates.length) {
        state.templates = ["headline"];
        toast("최소 한 개의 카드 템플릿이 필요합니다.", true);
      }
      renderTemplateOptions();
    });
  });
}

function renderMotionOptions() {
  const box = $("#motionChips");
  box.innerHTML = (state.meta?.motion_presets || []).map((motion) => `
    <button class="option-button" type="button" aria-pressed="${state.motion === motion.id}" data-motion="${escapeHtml(motion.id)}" title="${escapeHtml(motion.desc || "")}">${escapeHtml(motion.label)}<small>${escapeHtml(motion.desc || "")}</small></button>`).join("");
  box.querySelectorAll("[data-motion]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.motion = button.dataset.motion;
      if (state.motion === "remotion") state.engine = "remotion";
      else if (state.engine === "remotion") state.engine = "hyperframes";
      $("#engine").value = state.engine;
      renderMotionOptions();
      if (!state.project?.id) {
        paintPreview();
        return;
      }
      try {
        const data = await api(`/api/projects/${state.project.id}/save`, {
          method: "POST",
          body: JSON.stringify({ motion: state.motion, engine_hint: state.engine }),
        });
        state.project = data.project;
        paintPreview();
        toast(`모션 변경 · ${button.textContent.trim()}`);
      } catch (error) {
        toast(error.message, true);
      }
    });
  });
}

function cardPreviewHtml(card) {
  const kind = card?.kind || "headline";
  if (kind === "bullets") {
    return `<div class="pv-card"><div class="pv-kicker">브리핑</div><h2>${escapeHtml(card.title)}</h2><ul>${(card.bullets || []).map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("")}</ul></div>`;
  }
  if (kind === "chart") {
    return `<div class="pv-card"><div class="pv-kicker">비교</div><h2>${escapeHtml(card.title)}</h2><div class="pv-bars"><div><span>${escapeHtml(card.left_label)}</span><b>${escapeHtml(card.left_value)}</b></div><div class="hi"><span>${escapeHtml(card.right_label)}</span><b>${escapeHtml(card.right_value)}</b></div></div><p>${escapeHtml(card.unit)}</p></div>`;
  }
  if (kind === "quote") {
    return `<div class="pv-card"><div class="pv-kicker">인용</div><blockquote>“${escapeHtml(card.quote)}”</blockquote><cite>— ${escapeHtml(card.attribution)}</cite></div>`;
  }
  if (kind === "cta") {
    return `<div class="pv-card"><div class="pv-kicker">정리</div><h2>${escapeHtml(card.title)}</h2><p>${escapeHtml(card.body)}</p><span class="pv-cta">${escapeHtml(card.button || "더보기")}</span></div>`;
  }
  return `<div class="pv-card"><div class="pv-kicker">${escapeHtml(card.kicker || "ISSUE")}</div><h1>${escapeHtml(card.title)}</h1><p>${escapeHtml(card.subtitle)}</p></div>`;
}

function updateTransport() {
  const cards = state.project?.cards || [];
  const current = cards.length ? state.previewIndex + 1 : 0;
  const seconds = Number(state.project?.seconds_per_card || 3);
  const elapsed = current ? (current - 1) * seconds : 0;
  const total = cards.length * seconds;
  $("#transportTime").textContent = `00:${String(elapsed).padStart(2, "0")} / 00:${String(total).padStart(2, "0")}`;
  $("#transportProgress").style.width = cards.length ? `${(current / cards.length) * 100}%` : "0%";
  $(".canvas-transport").dataset.playing = String(state.previewPlaying);
  $("#btnPlay").setAttribute("aria-label", state.previewPlaying ? "카드 미리보기 일시정지" : "카드 미리보기 재생");
}

function paintPreview() {
  const cards = state.project?.cards || [];
  const stage = $("#stage");
  if (!cards.length) {
    stage.innerHTML = `<div class="empty-state"><svg aria-hidden="true" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m8 14 2.5-2.5L14 15l2-2 3 3M8 8h.01"/></svg><strong>이슈를 선택해 카드를 생성하세요</strong><span>생성된 HTML 카드와 영상이 이 캔버스에서 재생됩니다.</span></div>`;
    updateTransport();
    return;
  }
  state.previewIndex = ((state.previewIndex % cards.length) + cards.length) % cards.length;
  const card = cards[state.previewIndex];
  stage.innerHTML = `<div class="pv-shell motion-${escapeHtml(state.project.motion || state.motion)}"><div class="pv-meta">${String(state.previewIndex + 1).padStart(2, "0")}/${String(cards.length).padStart(2, "0")} · ${escapeHtml(card.kind)}</div>${cardPreviewHtml(card)}<div class="pv-progress"><i style="width:${((state.previewIndex + 1) / cards.length) * 100}%"></i></div></div>`;
  updateTransport();
}

function setPreviewPlaying(playing) {
  const cards = state.project?.cards || [];
  state.previewPlaying = Boolean(playing && cards.length > 1);
  clearInterval(previewTimer);
  previewTimer = null;
  if (state.previewPlaying) {
    previewTimer = window.setInterval(() => {
      state.previewIndex = (state.previewIndex + 1) % cards.length;
      paintPreview();
    }, Number(state.project?.seconds_per_card || 3) * 1000);
  }
  updateTransport();
}

function selectCard(cardId) {
  const cards = state.project?.cards || [];
  const index = cards.findIndex((card) => card.id === cardId);
  if (index < 0) return;
  state.selectedCardId = cardId;
  state.previewIndex = index;
  setPreviewPlaying(false);
  paintPreview();
  renderSlides();
  renderEditor();
  updateSummary();
}

function renderSlides() {
  const cards = state.project?.cards || [];
  const box = $("#slides");
  if (!cards.length) {
    box.innerHTML = `<div class="timeline-empty"><strong>생성된 카드가 없습니다</strong><span>왼쪽에서 이슈를 고른 뒤 ‘카드 생성’을 실행하세요.</span></div>`;
    return;
  }
  box.innerHTML = cards.map((card, index) => `<article class="slide" role="button" tabindex="0" aria-selected="${state.selectedCardId === card.id}" data-card-id="${escapeHtml(card.id)}" draggable="true"><div class="meta"><span>${String(index + 1).padStart(2, "0")}</span><span>${escapeHtml(card.kind)}</span></div><h3>${escapeHtml(card.title || card.quote || card.kind)}</h3><p>${escapeHtml(card.subtitle || card.body || (card.bullets || []).join(" · ") || card.attribution || "")}</p></article>`).join("");
  box.querySelectorAll("[data-card-id]").forEach((element) => {
    const activate = () => selectCard(element.dataset.cardId);
    element.addEventListener("click", activate);
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(); }
    });
    element.addEventListener("dragstart", (event) => event.dataTransfer.setData("text/plain", element.dataset.cardId));
    element.addEventListener("dragover", (event) => event.preventDefault());
    element.addEventListener("drop", async (event) => {
      event.preventDefault();
      const from = event.dataTransfer.getData("text/plain");
      const to = element.dataset.cardId;
      const ids = cards.map((card) => card.id);
      const fromIndex = ids.indexOf(from);
      const toIndex = ids.indexOf(to);
      if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return;
      ids.splice(toIndex, 0, ids.splice(fromIndex, 1)[0]);
      try {
        const data = await api(`/api/projects/${state.project.id}/cards/reorder`, { method: "POST", body: JSON.stringify({ order: ids }) });
        state.project = data.project;
        renderSlides();
        state.previewIndex = state.project.cards.findIndex((card) => card.id === state.selectedCardId);
        paintPreview();
        toast("카드 순서를 저장했습니다.");
      } catch (error) {
        toast(error.message, true);
      }
    });
  });
}

function renderEditor() {
  const editor = $("#editor");
  const card = (state.project?.cards || []).find((item) => item.id === state.selectedCardId);
  if (!card) {
    editor.innerHTML = `<div class="empty-state compact"><strong>편집할 카드를 선택하세요</strong><span>아래 시퀀스에서 카드를 선택할 수 있습니다.</span></div>`;
    return;
  }

  let fields = "";
  if (card.kind === "headline") {
    fields = `<label>키커<input id="f_kicker" value="${escapeHtml(card.kicker)}"/></label><label>제목<textarea id="f_title">${escapeHtml(card.title)}</textarea></label><label>부제<input id="f_subtitle" value="${escapeHtml(card.subtitle)}"/></label>`;
  } else if (card.kind === "bullets") {
    fields = `<label>제목<input id="f_title" value="${escapeHtml(card.title)}"/></label><label>불릿 · 한 줄에 하나<textarea id="f_bullets" rows="5">${escapeHtml((card.bullets || []).join("\n"))}</textarea></label>`;
  } else if (card.kind === "chart") {
    fields = `<label>제목<input id="f_title" value="${escapeHtml(card.title)}"/></label><div class="field-row"><label>왼쪽 라벨<input id="f_left_label" value="${escapeHtml(card.left_label)}"/></label><label>왼쪽 값<input id="f_left_value" value="${escapeHtml(card.left_value)}"/></label></div><div class="field-row"><label>오른쪽 라벨<input id="f_right_label" value="${escapeHtml(card.right_label)}"/></label><label>오른쪽 값<input id="f_right_value" value="${escapeHtml(card.right_value)}"/></label></div><label>단위<input id="f_unit" value="${escapeHtml(card.unit)}"/></label>`;
  } else if (card.kind === "quote") {
    fields = `<label>인용<textarea id="f_quote">${escapeHtml(card.quote)}</textarea></label><label>출처<input id="f_attr" value="${escapeHtml(card.attribution)}"/></label>`;
  } else {
    fields = `<label>제목<input id="f_title" value="${escapeHtml(card.title)}"/></label><label>본문<textarea id="f_body">${escapeHtml(card.body)}</textarea></label><label>버튼 문구<input id="f_button" value="${escapeHtml(card.button)}"/></label>`;
  }

  editor.innerHTML = `<div class="editor-heading"><h3>선택 카드 편집</h3><span class="source-kind">${escapeHtml(card.kind)}</span></div><div class="editor-fields">${fields}</div><div class="save-row"><button class="studio-button" id="btnSaveCard" type="button">변경 저장</button></div>`;
  editor.querySelectorAll("input, textarea").forEach((field) => field.addEventListener("input", () => { $("#unsavedMark").hidden = false; }));
  $("#btnSaveCard").addEventListener("click", saveCard);
}

async function saveCard() {
  if (!state.project?.id || !state.selectedCardId) return;
  const card = state.project.cards.find((item) => item.id === state.selectedCardId);
  const value = (id) => document.getElementById(id)?.value || "";
  const patch = {};
  if (card.kind === "headline") Object.assign(patch, { kicker: value("f_kicker"), title: value("f_title"), subtitle: value("f_subtitle") });
  else if (card.kind === "bullets") Object.assign(patch, { title: value("f_title"), bullets: value("f_bullets").split(/\n+/).map((text) => text.trim()).filter(Boolean) });
  else if (card.kind === "chart") Object.assign(patch, { title: value("f_title"), left_label: value("f_left_label"), left_value: value("f_left_value"), right_label: value("f_right_label"), right_value: value("f_right_value"), unit: value("f_unit") });
  else if (card.kind === "quote") Object.assign(patch, { quote: value("f_quote"), attribution: value("f_attr") });
  else Object.assign(patch, { title: value("f_title"), body: value("f_body"), button: value("f_button") });

  try {
    const data = await api(`/api/projects/${state.project.id}/cards/update`, { method: "POST", body: JSON.stringify({ card_id: state.selectedCardId, patch }) });
    state.project = data.project;
    $("#unsavedMark").hidden = true;
    renderSlides();
    renderEditor();
    paintPreview();
    toast("카드 변경사항을 저장했습니다.");
  } catch (error) {
    toast(error.message, true);
  }
}

function updateAspect() {
  const frame = $("#stageFrame");
  frame.className = `studio-canvas__frame aspect-${state.aspect.replace(":", "-")}`;
  $("#summaryResolution").textContent = state.aspect === "9:16" ? "1080 × 1920" : state.aspect === "16:9" ? "1920 × 1080" : "1080 × 1080";
}

function updateSummary() {
  const cards = state.project?.cards || [];
  const duration = cards.length * Number(state.project?.seconds_per_card || 3);
  $("#summaryDuration").textContent = cards.length ? `${duration}s` : "—";
  $("#summarySlides").textContent = String(cards.length);
  $("#compositionId").textContent = state.project?.id || "선택 없음";
  $("#canvasHeading").textContent = state.project?.title || state.manualTopic || "새 프로젝트";
  $("#activeCardLabel").textContent = state.selectedCardId ? `SELECTED · ${state.selectedCardId}` : "NO SELECTION";
  $("#btnPrev").disabled = cards.length < 2;
  $("#btnNext").disabled = cards.length < 2;
  $("#btnPlay").disabled = cards.length < 2;
  $("#btnRender").disabled = !state.project?.id;
  updateAspect();
  updateTransport();
}

function updateProjectReadiness() {
  $("#btnBuild").disabled = !(state.selectedIssueId || state.manualTopic);
}

async function loadMeta() {
  state.meta = await api("/api/meta");
  renderCategories();
  renderTemplateOptions();
  renderMotionOptions();
}

async function loadTrends(force = false) {
  $("#sourceMode").textContent = state.category === "ai" ? "NEWS + CATALOG" : "LIVE";
  $("#trendStatus").textContent = "피드 갱신 중…";
  $("#issueList").innerHTML = `<div class="empty-state compact"><span class="spinner" aria-hidden="true"></span><strong>이슈를 수집하고 있습니다</strong></div>`;
  try {
    const data = await api(`/api/trends?category=${encodeURIComponent(state.category)}${force ? "&force=true" : ""}`);
    state.trends = data.items || [];
    if (!state.selectedIssueId && state.trends[0]) state.selectedIssueId = state.trends[0].id;
    renderTrends();
    const time = new Date(data.updated_at || Date.now()).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
    $("#trendStatus").textContent = `${data.cached ? "캐시" : "최신"} · ${state.trends.length}건 · ${time}`;
    updateProjectReadiness();
  } catch (error) {
    state.trends = [];
    $("#issueList").innerHTML = `<div class="empty-state compact"><strong>이슈를 불러오지 못했습니다</strong><span>${escapeHtml(error.message)}</span></div>`;
    $("#trendStatus").textContent = "피드 오류 · 다시 시도하세요";
    toast(error.message, true);
  }
}

async function loadHealth() {
  const element = $("#health");
  try {
    state.health = await api("/api/health");
    const ready = state.health.hyperframes && state.health.ffmpeg;
    element.dataset.state = ready ? "ready" : "error";
    element.innerHTML = `<span class="status-dot" aria-hidden="true"></span> ${ready ? "로컬 렌더 준비" : "렌더 의존성 확인 필요"}`;
    $("#btnPush").disabled = !state.health.timeline_configured;
    $("#pushHint").textContent = state.health.timeline_configured
      ? "현재 프로젝트를 연결된 Timeline으로 전송합니다."
      : "Timeline 연결 정보가 없어 비활성화되었습니다.";
    renderDependencies();
  } catch (error) {
    element.dataset.state = "error";
    element.innerHTML = `<span class="status-dot" aria-hidden="true"></span> API 연결 실패`;
    toast(error.message, true);
  }
}

function renderDependencies() {
  const health = state.health || {};
  const dependencies = [
    ["Hyperframes", Boolean(health.hyperframes)],
    ["FFmpeg", Boolean(health.ffmpeg)],
    ["Playwright", Boolean(health.playwright)],
    ["oMLX", Boolean(health.omlx_configured)],
  ];
  $("#dependencyGrid").innerHTML = dependencies.map(([name, ready]) => `<div class="dependency" data-ready="${ready}"><span>${name}</span><b>${ready ? "READY" : name === "oMLX" ? "NOT SET" : "CHECK"}</b></div>`).join("");
}

async function buildProject() {
  if (!(state.selectedIssueId || state.manualTopic)) return;
  const button = $("#btnBuild");
  const original = button.innerHTML;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = "카드 구성 중…";
  try {
    const body = {
      category: state.category,
      template_ids: state.templates,
      motion: state.motion,
      aspect_ratio: state.aspect,
      seconds_per_card: 3,
    };
    if (state.manualTopic) {
      body.title = state.manualTopic;
      body.summary = "사용자가 직접 입력한 주제로 만든 카드 초안입니다. AI 기반 근거 수집은 다음 개발 단계에서 연결됩니다.";
    } else {
      body.issue_id = state.selectedIssueId;
    }
    const data = await api("/api/projects/build", { method: "POST", body: JSON.stringify(body) });
    state.project = data.project;
    state.selectedCardId = state.project.cards?.[0]?.id || null;
    state.previewIndex = 0;
    state.previewPlaying = false;
    renderSlides();
    renderEditor();
    paintPreview();
    updateSummary();
    $("#projStatus").textContent = `프로젝트 ${state.project.id} · 카드 ${state.project.cards.length}장`;
    toast(`카드 ${state.project.cards.length}장을 생성했습니다.`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.innerHTML = original;
    button.removeAttribute("aria-busy");
    updateProjectReadiness();
  }
}

function setRenderState(kind, phase, percent, message, error = "") {
  const panel = $("#renderProgress");
  panel.dataset.state = kind;
  $("#renderPhase").textContent = phase;
  $("#renderPercent").textContent = `${percent}%`;
  $("#renderBar").style.width = `${percent}%`;
  $("#renderMessage").textContent = message;
  $("#renderError").hidden = !error;
  $("#renderError").textContent = error;
}

function openRenderModal() {
  if (!state.project?.id) return;
  modalOpener = document.activeElement;
  $("#renderModal").hidden = false;
  $("#renderComposition").textContent = state.project.id;
  $("#renderEngine").textContent = $("#engine").selectedOptions[0].textContent;
  setRenderState("idle", "준비", 0, "의존성과 출력 설정을 확인한 뒤 렌더를 시작하세요.");
  renderDependencies();
  $("#btnRunRender").focus();
}

function closeRenderModal() {
  if (state.renderRunning) return;
  $("#renderModal").hidden = true;
  modalOpener?.focus();
}

async function runRender() {
  if (!state.project?.id || state.renderRunning) return;
  state.renderRunning = true;
  $("#btnRunRender").disabled = true;
  $("#btnCancelRender").disabled = true;
  $("#btnCloseRender").disabled = true;
  setRenderState("running", "프레임 생성", 18, `${state.engine} 엔진이 카드 프레임을 구성하고 있습니다.`);
  try {
    const data = await api(`/api/projects/${state.project.id}/render`, {
      method: "POST",
      body: JSON.stringify({ fps: 30, engine: state.engine }),
    });
    state.project = data.project;
    const render = data.render || {};
    if (render.video_url) {
      setPreviewPlaying(false);
      $("#stage").innerHTML = `<video src="${withBase(render.video_url)}?t=${Date.now()}" controls playsinline aria-label="렌더된 Hyperframes 영상"></video>`;
    }
    $("#renderOutput").textContent = render.video_url ? `MP4 · ${render.engine}` : "HTML preview";
    $("#projStatus").textContent = `렌더 완료 · ${render.engine || state.engine}`;
    setRenderState("success", "완료", 100, `영상 출력이 완료되었습니다 · ${render.engine || state.engine}`);
    $("#btnRunRender").textContent = "다시 렌더";
    toast(`영상 렌더 완료 · ${render.engine || state.engine}`);
  } catch (error) {
    setRenderState("error", "실패", 100, "렌더를 완료하지 못했습니다. 아래 오류를 확인하세요.", error.message);
    toast(error.message, true);
  } finally {
    state.renderRunning = false;
    $("#btnRunRender").disabled = false;
    $("#btnCancelRender").disabled = false;
    $("#btnCloseRender").disabled = false;
  }
}

async function pushTimeline() {
  if (!state.project?.id || !state.health?.timeline_configured) return;
  try {
    const data = await api(`/api/projects/${state.project.id}/push-timeline`, { method: "POST", body: "{}" });
    toast(`Timeline 등록 완료 · ${data.timeline?.uid || data.timeline?.name || "ok"}`);
  } catch (error) {
    toast(error.message, true);
  }
}

function wireControls() {
  $("#btnRefresh").addEventListener("click", () => loadTrends(true));
  $("#btnBuild").addEventListener("click", buildProject);
  $("#btnRender").addEventListener("click", openRenderModal);
  $("#btnRunRender").addEventListener("click", runRender);
  $("#btnCancelRender").addEventListener("click", closeRenderModal);
  $("#btnCloseRender").addEventListener("click", closeRenderModal);
  $("#btnPush").addEventListener("click", pushTimeline);
  $("#topicForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const topic = $("#topicInput").value.trim();
    if (!topic) return toast("직접 만들 주제를 입력하세요.", true);
    state.manualTopic = topic;
    state.selectedIssueId = null;
    renderTrends();
    updateSummary();
    updateProjectReadiness();
    toast("직접 주제를 선택했습니다.");
  });
  $("#aspect").addEventListener("change", (event) => {
    state.aspect = event.target.value;
    updateAspect();
  });
  $("#engine").addEventListener("change", async (event) => {
    state.engine = event.target.value;
    if (!state.project?.id) return;
    try {
      const data = await api(`/api/projects/${state.project.id}/engine`, { method: "POST", body: JSON.stringify({ engine: state.engine }) });
      state.project = data.project;
      paintPreview();
      toast(`렌더 엔진 · ${event.target.selectedOptions[0].textContent}`);
    } catch (error) {
      toast(error.message, true);
    }
  });
  $("#btnPrev").addEventListener("click", () => {
    const cards = state.project?.cards || [];
    if (!cards.length) return;
    state.previewIndex = (state.previewIndex - 1 + cards.length) % cards.length;
    selectCard(cards[state.previewIndex].id);
  });
  $("#btnNext").addEventListener("click", () => {
    const cards = state.project?.cards || [];
    if (!cards.length) return;
    state.previewIndex = (state.previewIndex + 1) % cards.length;
    selectCard(cards[state.previewIndex].id);
  });
  $("#btnPlay").addEventListener("click", () => setPreviewPlaying(!state.previewPlaying));
  $("#timelineZoom").addEventListener("input", (event) => $("#slides").style.setProperty("--timeline-card-width", `${event.target.value}px`));
  $("#renderModal").addEventListener("mousedown", (event) => {
    if (event.target === $("#renderModal")) closeRenderModal();
  });
  document.addEventListener("keydown", (event) => {
    const modal = $("#renderModal");
    if (modal.hidden) return;
    if (event.key === "Escape") { event.preventDefault(); closeRenderModal(); return; }
    if (event.key !== "Tab") return;
    const focusable = [...modal.querySelectorAll("button:not(:disabled), select, input, [tabindex]:not([tabindex='-1'])")];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
}

async function loadProject(projectId) {
  const data = await api(`/api/projects/${projectId}`);
  state.project = data.project;
  state.motion = state.project.motion || state.motion;
  state.aspect = state.project.aspect_ratio || state.aspect;
  state.engine = state.project.engine_hint === "remotion-adapter" ? "remotion" : state.project.engine_hint || state.engine;
  state.selectedCardId = state.project.cards?.[0]?.id || null;
  $("#aspect").value = state.aspect;
  $("#engine").value = state.engine;
  renderMotionOptions();
  renderSlides();
  renderEditor();
  updateSummary();
  if (state.project.render?.video_url) {
    $("#stage").innerHTML = `<video src="${withBase(state.project.render.video_url)}?t=${Date.now()}" controls playsinline aria-label="렌더된 Hyperframes 영상"></video>`;
  } else {
    paintPreview();
  }
  $("#projStatus").textContent = `프로젝트 ${state.project.id}`;
}

(async function init() {
  setupTheme();
  wireControls();
  updateSummary();
  try {
    await Promise.all([loadMeta(), loadHealth()]);
    await loadTrends(true);
    const projectId = new URLSearchParams(location.search).get("project");
    if (projectId) await loadProject(projectId);
  } catch (error) {
    toast(error.message, true);
  }
})();
