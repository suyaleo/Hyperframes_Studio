const APP_BASE = (window.APP_BASE || (location.pathname.startsWith("/cards") ? "/cards" : "")).replace(/\/$/, "");
const state = {
  category: "rising", trends: [], selectedIssueId: null, project: null,
  selectedCardId: null, motion: "zoom", aspect: "9:16", engine: "hyperframes",
  templates: ["headline", "bullets", "chart", "quote", "cta"], meta: null,
  playing: false, previewTimer: null, renderTimer: null, editorDirty: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const decoder = document.createElement("textarea");

function withBase(path) {
  if (!path || /^https?:/i.test(path)) return path;
  return APP_BASE + (path.startsWith("/") ? path : `/${path}`);
}

function cleanText(value) {
  decoder.innerHTML = String(value || "");
  return decoder.value.replace(/<[^>]*>/g, " ").replace(/&nbs(?:p)?;?/gi, " ").replace(/\s+/g, " ").trim();
}

function escapeHtml(value) {
  return cleanText(value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
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
  const el = $("#toast");
  if (!el) return;
  el.textContent = message;
  el.className = bad ? "toast bad" : "toast";
  el.hidden = false;
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => { el.hidden = true; }, bad ? 5200 : 3000);
}

function setSaveState(label, mode = "") {
  const el = $("#saveState");
  if (!el) return;
  el.textContent = label;
  el.className = `save-state ${mode}`.trim();
}

function setWorkflow(step, hint) {
  const order = ["issue", "compose", "edit", "render"];
  const current = order.indexOf(step);
  $$(".workflow-step").forEach((el) => {
    const index = order.indexOf(el.dataset.step);
    el.classList.toggle("active", index === current);
    el.classList.toggle("done", index < current);
  });
  if (hint) $("#workflowHint").textContent = hint;
}

function currentCardIndex() {
  const cards = state.project?.cards || [];
  const found = cards.findIndex((card) => card.id === state.selectedCardId);
  return found >= 0 ? found : 0;
}

function cardLabel(kind) {
  return ({ headline: "표지", bullets: "핵심 요약", chart: "팩트", quote: "인용", cta: "마무리" })[kind] || "카드";
}

function cardPreviewHTML(card, index) {
  const kind = card?.kind || "headline";
  const number = String(index + 1).padStart(2, "0");
  if (kind === "bullets") {
    const items = (card.bullets || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    return `<div class="pv-card"><div class="pv-number">${number}</div><div class="pv-kicker">핵심 브리핑</div><h2>${escapeHtml(card.title)}</h2><ul>${items}</ul></div>`;
  }
  if (kind === "chart") {
    return `<div class="pv-card"><div class="pv-number">${number}</div><div class="pv-kicker">팩트 체크</div><h2>${escapeHtml(card.title)}</h2><div class="pv-facts"><div><span>${escapeHtml(card.left_label)}</span><b>${escapeHtml(card.left_value)}</b></div><div><span>${escapeHtml(card.right_label)}</span><b>${escapeHtml(card.right_value)}</b></div></div><p>${escapeHtml(card.unit)}</p></div>`;
  }
  if (kind === "quote") {
    return `<div class="pv-card"><div class="pv-number">${number}</div><div class="pv-kicker">맥락</div><blockquote>${escapeHtml(card.quote)}</blockquote><cite>${escapeHtml(card.attribution)}</cite></div>`;
  }
  if (kind === "cta") {
    return `<div class="pv-card"><div class="pv-number">${number}</div><div class="pv-kicker">다음 단계</div><h2>${escapeHtml(card.title)}</h2><p>${escapeHtml(card.body)}</p><div class="pv-cta">${escapeHtml(card.button || "원문 확인")}</div></div>`;
  }
  return `<div class="pv-card"><div class="pv-number">${number}</div><div class="pv-kicker">${escapeHtml(card.kicker || "ISSUE")}</div><h1>${escapeHtml(card.title)}</h1><p class="sub">${escapeHtml(card.subtitle)}</p></div>`;
}

function setStageMode() {
  const stage = $("#stage");
  if (!stage) return;
  stage.classList.toggle("phone-mode", state.aspect === "9:16");
  stage.classList.toggle("landscape-mode", state.aspect === "16:9");
  stage.classList.toggle("square-mode", state.aspect === "1:1");
  $("#previewAspect").textContent = state.aspect;
}

function paintPreview(index = currentCardIndex()) {
  const stage = $("#stage");
  const cards = state.project?.cards || [];
  setStageMode();
  if (!cards.length) return;
  const safeIndex = (index + cards.length) % cards.length;
  const card = cards[safeIndex];
  state.selectedCardId = card.id;
  const motion = state.project?.motion || state.motion;
  stage.innerHTML = `<div class="pv-shell motion-${escapeHtml(motion)}"><div class="pv-meta">${safeIndex + 1} / ${cards.length} · ${escapeHtml(state.aspect)}</div>${cardPreviewHTML(card, safeIndex)}<div class="pv-progress"><i style="width:${((safeIndex + 1) / cards.length) * 100}%"></i></div></div>`;
  $("#previewKind").textContent = cardLabel(card.kind);
  $("#playPosition").textContent = `${safeIndex + 1} / ${cards.length}`;
  $("#playProgress").style.width = `${((safeIndex + 1) / cards.length) * 100}%`;
}

function showVideo(url) {
  stopPlayback();
  setStageMode();
  $("#stage").innerHTML = `<video src="${escapeHtml(withBase(url))}?t=${Date.now()}" controls playsinline preload="metadata"></video>`;
  $("#previewKind").textContent = "렌더 결과";
}

function selectCard(id, { renderEditorToo = true } = {}) {
  if (!id) return;
  state.selectedCardId = id;
  renderSlides();
  if (renderEditorToo) renderEditor();
  paintPreview(currentCardIndex());
}

function stopPlayback() {
  state.playing = false;
  clearInterval(state.previewTimer);
  state.previewTimer = null;
  const btn = $("#btnPlay");
  if (btn) { btn.textContent = "▶"; btn.setAttribute("aria-label", "미리보기 재생"); }
}

function togglePlayback() {
  const cards = state.project?.cards || [];
  if (cards.length < 2) return;
  if (state.playing) return stopPlayback();
  state.playing = true;
  $("#btnPlay").textContent = "Ⅱ";
  $("#btnPlay").setAttribute("aria-label", "미리보기 일시정지");
  state.previewTimer = setInterval(() => {
    const next = (currentCardIndex() + 1) % cards.length;
    state.selectedCardId = cards[next].id;
    renderSlides();
    renderEditor();
    paintPreview(next);
  }, Math.max(1600, Number(state.project?.seconds_per_card || 3) * 1000));
}

function renderTrends() {
  const box = $("#issueList");
  if (!state.trends.length) {
    box.innerHTML = `<div class="recent-empty">불러온 이슈가 없습니다.<br/>새로고침을 다시 시도하세요.</div>`;
    $("#btnBuild").disabled = true;
    return;
  }
  box.innerHTML = state.trends.map((issue) => `
    <button class="issue ${state.selectedIssueId === issue.id ? "active" : ""}" data-issue-id="${escapeHtml(issue.id)}" type="button">
      <span class="issue-top"><span class="issue-category">${escapeHtml(issue.category || state.category)}</span><span class="issue-source">${escapeHtml(issue.source || "Issue feed")}</span></span>
      <strong>${escapeHtml(issue.title)}</strong>
      <p>${escapeHtml(issue.summary || "요약 정보가 없습니다.")}</p>
      ${state.selectedIssueId === issue.id ? '<span class="selected-tick">✓</span>' : ""}
    </button>`).join("");
  box.querySelectorAll("[data-issue-id]").forEach((button) => button.addEventListener("click", () => {
    state.selectedIssueId = button.dataset.issueId;
    renderTrends();
    setWorkflow("compose", "화면 비율과 카드 구성을 확인한 뒤 초안을 만드세요.");
  }));
  $("#btnBuild").disabled = !state.selectedIssueId;
}

function renderControls() {
  if (!state.meta) return;
  $("#catChips").innerHTML = (state.meta.issue_categories || []).map((item) => `<button class="chip ${state.category === item.id ? "active" : ""}" data-category="${escapeHtml(item.id)}" type="button">${escapeHtml(item.label)}</button>`).join("");
  $$("[data-category]").forEach((button) => button.addEventListener("click", async () => {
    state.category = button.dataset.category;
    state.selectedIssueId = null;
    renderControls();
    await loadTrends();
  }));
  $("#motionChips").innerHTML = (state.meta.motion_presets || []).map((item) => `<button class="motion-chip ${state.motion === item.id ? "active" : ""}" data-motion="${escapeHtml(item.id)}" type="button"><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.desc || "전환 효과")}</small></button>`).join("");
  $$("[data-motion]").forEach((button) => button.addEventListener("click", async () => {
    state.motion = button.dataset.motion;
    renderControls();
    if (state.project?.id) await persistSettings({ motion: state.motion }, "모션을 변경했습니다. 다시 렌더하세요.");
    else paintPreview();
  }));
  $("#tplChips").innerHTML = (state.meta.card_templates || []).map((item) => `<button class="template-chip ${state.templates.includes(item.id) ? "active" : ""}" data-template="${escapeHtml(item.id)}" type="button">${escapeHtml(item.label)}</button>`).join("");
  $$("[data-template]").forEach((button) => button.addEventListener("click", () => {
    const id = button.dataset.template;
    state.templates = state.templates.includes(id) ? state.templates.filter((value) => value !== id) : [...state.templates, id];
    if (!state.templates.length) { state.templates = ["headline", "bullets", "cta"]; toast("최소 구성 3장을 유지했습니다."); }
    renderControls();
  }));
  $$("[data-aspect]").forEach((button) => button.classList.toggle("active", button.dataset.aspect === state.aspect));
}

function renderSlides() {
  const cards = state.project?.cards || [];
  $("#cardCount").textContent = `${cards.length}장`;
  if (!cards.length) {
    $("#slides").innerHTML = `<div class="recent-empty">카드를 생성하면 순서가 표시됩니다.</div>`;
    return;
  }
  $("#slides").innerHTML = cards.map((card, index) => `
    <article class="slide ${state.selectedCardId === card.id ? "active" : ""}">
      <button class="slide-select" data-card-id="${escapeHtml(card.id)}" type="button">
        <span class="meta"><span>${String(index + 1).padStart(2, "0")}</span><span>${escapeHtml(cardLabel(card.kind))}</span></span>
        <h3>${escapeHtml(card.title || card.quote || card.kind)}</h3>
      </button>
      <span class="slide-actions">
        <button type="button" data-move="-1" data-card-id="${escapeHtml(card.id)}" aria-label="앞으로 이동">←</button>
        <button type="button" data-move="1" data-card-id="${escapeHtml(card.id)}" aria-label="뒤로 이동">→</button>
      </span>
    </article>`).join("");
  $("#slides").querySelectorAll(".slide-select").forEach((button) => button.addEventListener("click", () => {
    stopPlayback();
    selectCard(button.dataset.cardId);
  }));
  $("#slides").querySelectorAll("[data-move]").forEach((button) => button.addEventListener("click", async (event) => {
    event.stopPropagation();
    await moveCard(button.dataset.cardId, Number(button.dataset.move));
  }));
}

function field(label, id, value, { multiline = false, rows = 3, max = 160 } = {}) {
  const control = multiline
    ? `<textarea id="${id}" rows="${rows}" maxlength="${max}">${escapeHtml(value)}</textarea>`
    : `<input id="${id}" value="${escapeHtml(value)}" maxlength="${max}"/>`;
  return `<label>${label}${control}</label>`;
}

function renderEditor() {
  const editor = $("#editor");
  const card = (state.project?.cards || []).find((item) => item.id === state.selectedCardId);
  if (!card) {
    $("#inspectorTitle").textContent = "생성 설정";
    editor.innerHTML = `<div class="editor-empty"><span>편집할 카드 선택</span><p>카드가 만들어지면 선택한 슬라이드의 제목과 본문을 여기서 바로 수정합니다.</p></div>`;
    return;
  }
  $("#inspectorTitle").textContent = "카드 편집";
  let fields = "";
  if (card.kind === "headline") {
    fields = field("키커", "f_kicker", card.kicker, { max: 24 }) + field("제목", "f_title", card.title, { multiline: true, max: 90 }) + field("부제", "f_subtitle", card.subtitle, { max: 90 });
  } else if (card.kind === "bullets") {
    fields = field("제목", "f_title", card.title, { max: 50 }) + field("핵심 문장 · 한 줄에 하나", "f_bullets", (card.bullets || []).join("\n"), { multiline: true, rows: 6, max: 360 });
  } else if (card.kind === "chart") {
    fields = field("제목", "f_title", card.title, { max: 50 }) + `<div class="field-row">${field("왼쪽 항목", "f_left_label", card.left_label, { max: 30 })}${field("왼쪽 내용", "f_left_value", card.left_value, { max: 50 })}</div>` + `<div class="field-row">${field("오른쪽 항목", "f_right_label", card.right_label, { max: 30 })}${field("오른쪽 내용", "f_right_value", card.right_value, { max: 50 })}</div>` + field("설명", "f_unit", card.unit, { max: 80 });
  } else if (card.kind === "quote") {
    fields = field("인용 또는 핵심 문장", "f_quote", card.quote, { multiline: true, rows: 5, max: 180 }) + field("출처", "f_attr", card.attribution, { max: 60 });
  } else {
    fields = field("제목", "f_title", card.title, { max: 50 }) + field("본문", "f_body", card.body, { multiline: true, rows: 5, max: 220 }) + field("행동 문구", "f_button", card.button, { max: 32 });
  }
  const index = currentCardIndex() + 1;
  editor.innerHTML = `<div class="editor-head"><div><span>${String(index).padStart(2, "0")} / ${escapeHtml(cardLabel(card.kind))}</span><strong>선택한 카드 편집</strong></div></div><div class="editor-fields">${fields}</div><div class="editor-actions"><button class="btn btn-strong" id="btnSaveCard" type="button">변경사항 저장</button></div>`;
  $("#btnSaveCard").addEventListener("click", saveCard);
  editor.querySelectorAll("input, textarea").forEach((control) => control.addEventListener("input", () => {
    state.editorDirty = true;
    setSaveState("저장 필요", "dirty");
  }));
}

function collectCardPatch(card) {
  const value = (id) => cleanText(document.getElementById(id)?.value);
  if (card.kind === "headline") return { kicker: value("f_kicker"), title: value("f_title"), subtitle: value("f_subtitle") };
  if (card.kind === "bullets") return { title: value("f_title"), bullets: (document.getElementById("f_bullets")?.value || "").split(/\n+/).map(cleanText).filter(Boolean).slice(0, 5) };
  if (card.kind === "chart") return { title: value("f_title"), left_label: value("f_left_label"), left_value: value("f_left_value"), right_label: value("f_right_label"), right_value: value("f_right_value"), unit: value("f_unit") };
  if (card.kind === "quote") return { quote: value("f_quote"), attribution: value("f_attr") };
  return { title: value("f_title"), body: value("f_body"), button: value("f_button") };
}

async function saveCard() {
  const card = (state.project?.cards || []).find((item) => item.id === state.selectedCardId);
  if (!card) return;
  const button = $("#btnSaveCard");
  button.disabled = true;
  button.textContent = "저장 중…";
  try {
    const data = await api(`/api/projects/${state.project.id}/cards/update`, { method: "POST", body: JSON.stringify({ card_id: card.id, patch: collectCardPatch(card) }) });
    state.project = data.project;
    await invalidateRender();
    state.editorDirty = false;
    setSaveState("저장됨", "saved");
    renderSlides(); renderEditor(); paintPreview();
    setWorkflow("edit", "편집 내용이 미리보기에 반영됐습니다. 준비되면 렌더를 시작하세요.");
    toast("카드와 미리보기를 저장했습니다.");
  } catch (error) {
    setSaveState("저장 실패", "dirty");
    toast(error.message, true);
  } finally { button.disabled = false; button.textContent = "변경사항 저장"; }
}

async function moveCard(id, direction) {
  const cards = [...(state.project?.cards || [])];
  const from = cards.findIndex((card) => card.id === id);
  const to = Math.max(0, Math.min(cards.length - 1, from + direction));
  if (from < 0 || from === to) return;
  cards.splice(to, 0, cards.splice(from, 1)[0]);
  try {
    const data = await api(`/api/projects/${state.project.id}/cards/reorder`, { method: "POST", body: JSON.stringify({ order: cards.map((card) => card.id) }) });
    state.project = data.project;
    await invalidateRender();
    renderSlides(); paintPreview(currentCardIndex());
    setSaveState("저장됨", "saved");
  } catch (error) { toast(error.message, true); }
}

async function invalidateRender() {
  if (!state.project?.id || !state.project.render) return;
  const data = await api(`/api/projects/${state.project.id}/save`, { method: "POST", body: JSON.stringify({ status: "draft", render: null }) });
  state.project = data.project;
  hideOutput();
}

async function persistSettings(patch, message) {
  Object.assign(state.project || {}, patch);
  paintPreview();
  if (!state.project?.id) return;
  setSaveState("저장 중");
  try {
    const data = await api(`/api/projects/${state.project.id}/save`, { method: "POST", body: JSON.stringify({ ...patch, status: "draft", render: null }) });
    state.project = data.project;
    hideOutput();
    setSaveState("저장됨", "saved");
    if (message) toast(message);
  } catch (error) { setSaveState("저장 실패", "dirty"); toast(error.message, true); }
}

async function loadMeta() {
  state.meta = await api("/api/meta");
  renderControls();
}

async function loadTrends(force = false) {
  $("#trendStatus").textContent = "이슈를 불러오는 중…";
  $("#btnRefresh").disabled = true;
  try {
    const data = await api(`/api/trends?category=${encodeURIComponent(state.category)}${force ? "&force=true" : ""}`);
    state.trends = data.items || [];
    if (!state.selectedIssueId && state.trends[0]) state.selectedIssueId = state.trends[0].id;
    renderTrends();
    const time = new Date(data.updated_at || Date.now()).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
    $("#trendStatus").textContent = `${data.cached ? "캐시" : "최신"} ${state.trends.length}건 · ${time}`;
  } catch (error) {
    state.trends = []; renderTrends();
    $("#trendStatus").textContent = "피드 연결 실패";
    toast(`이슈를 불러오지 못했습니다: ${error.message}`, true);
  } finally { $("#btnRefresh").disabled = false; }
}

function syncProject(project) {
  state.project = project;
  state.aspect = project.aspect_ratio || "9:16";
  state.motion = project.motion || "zoom";
  state.engine = project.engine_hint === "remotion-adapter" ? "remotion" : (project.engine_hint || "hyperframes");
  state.selectedCardId = project.cards?.[0]?.id || null;
  $("#engine").value = state.engine;
  $("#projectTitle").textContent = cleanText(project.title) || "제목 없는 프로젝트";
  $("#btnRender").disabled = !(project.cards || []).length;
  history.replaceState({}, "", `${location.pathname}?project=${encodeURIComponent(project.id)}`);
  renderControls(); renderSlides(); renderEditor();
  if (project.render?.video_url) { showVideo(project.render.video_url); showOutput(project.render); setWorkflow("render", "렌더 결과가 준비되었습니다. 다운로드하거나 Timeline으로 전송할 수 있습니다."); }
  else { hideOutput(); paintPreview(0); setWorkflow("edit", "카드를 선택해 문구와 순서를 다듬은 뒤 렌더하세요."); }
  setSaveState("저장됨", "saved");
}

async function buildProject() {
  if (!state.selectedIssueId) return toast("먼저 이슈를 선택하세요.", true);
  const button = $("#btnBuild");
  button.disabled = true; button.textContent = "초안 만드는 중…";
  setWorkflow("compose", "이슈 내용을 카드 구성으로 정리하고 있습니다.");
  try {
    const data = await api("/api/projects/build", { method: "POST", body: JSON.stringify({ issue_id: state.selectedIssueId, category: state.category, template_ids: state.templates, motion: state.motion, aspect_ratio: state.aspect, seconds_per_card: 3 }) });
    syncProject(data.project);
    toast(`카드 ${data.project.cards.length}장 초안을 만들었습니다.`);
    await loadRecentProjects();
  } catch (error) {
    setWorkflow("compose", "카드 생성에 실패했습니다. 이슈를 다시 선택해 보세요.");
    toast(error.message, true);
  } finally { button.disabled = false; button.textContent = "선택한 이슈로 카드 만들기"; }
}

function formatElapsed(seconds) {
  const min = Math.floor(seconds / 60).toString().padStart(2, "0");
  const sec = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${min}:${sec}`;
}

function showRenderProgress() {
  const panel = $("#renderPanel");
  panel.hidden = false;
  $("#renderSpinner").hidden = false;
  $("#renderTitle").textContent = "영상 렌더링 중";
  $("#renderMessage").textContent = "창을 닫지 마세요. 세로 영상은 보통 1–3분 정도 걸립니다.";
  $("#renderTime").textContent = "00:00";
  $("#renderBar").style.width = "28%";
  $("#renderBar").style.animation = "";
  const started = Date.now();
  clearInterval(state.renderTimer);
  state.renderTimer = setInterval(() => { $("#renderTime").textContent = formatElapsed((Date.now() - started) / 1000); }, 1000);
}

function finishRenderProgress(ok, message) {
  clearInterval(state.renderTimer); state.renderTimer = null;
  $("#renderSpinner").hidden = true;
  $("#renderTitle").textContent = ok ? "렌더 완료" : "렌더 실패";
  $("#renderMessage").textContent = message;
  $("#renderBar").style.animation = "none";
  $("#renderBar").style.width = ok ? "100%" : "0";
}

async function renderProject() {
  if (!state.project?.id) return toast("먼저 카드를 생성하세요.", true);
  if (state.editorDirty && !confirm("저장하지 않은 편집 내용이 있습니다. 저장하지 않고 렌더할까요?")) return;
  stopPlayback(); hideOutput(); showRenderProgress();
  const button = $("#btnRender");
  button.disabled = true; button.querySelector(".btn-label").textContent = "렌더링 중";
  setWorkflow("render", "렌더 상태와 경과 시간을 아래에서 확인할 수 있습니다.");
  try {
    const data = await api(`/api/projects/${state.project.id}/render`, { method: "POST", body: JSON.stringify({ fps: 30, engine: state.engine }) });
    state.project = data.project;
    const render = data.render || {};
    finishRenderProgress(true, render.video_url ? "영상 파일과 미리보기가 준비되었습니다." : "HTML 미리보기가 준비되었습니다.");
    if (render.video_url) showVideo(render.video_url); else paintPreview();
    showOutput(render);
    setSaveState("렌더 완료", "saved");
    toast("렌더가 완료되었습니다. 바로 다운로드할 수 있습니다.");
  } catch (error) {
    finishRenderProgress(false, `${error.message} · 설정을 확인한 뒤 다시 시도하세요.`);
    setWorkflow("render", "렌더에 실패했습니다. 오류 내용을 확인하고 다시 시도하세요.");
    toast(error.message, true);
  } finally { button.disabled = false; button.querySelector(".btn-label").textContent = "다시 렌더"; }
}

function showOutput(render) {
  const url = render?.video_url || render?.preview_url || state.project?.preview_url;
  if (!url) return hideOutput();
  $("#outputPanel").hidden = false;
  $("#btnDownload").href = withBase(url);
  $("#btnOpen").href = withBase(url);
  $("#outputTitle").textContent = render?.video_url ? "영상 파일이 준비되었습니다" : "미리보기가 준비되었습니다";
}

function hideOutput() { $("#outputPanel").hidden = true; }

async function pushTimeline() {
  if (!state.project?.id) return;
  if (!confirm("현재 결과를 Timeline 초안으로 전송할까요?")) return;
  const button = $("#btnPush"); button.disabled = true; button.textContent = "전송 중…";
  try {
    const data = await api(`/api/projects/${state.project.id}/push-timeline`, { method: "POST", body: "{}" });
    toast(`Timeline에 등록했습니다: ${data.timeline?.name || data.timeline?.uid || "완료"}`);
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.textContent = "Timeline 전송"; }
}

async function loadRecentProjects() {
  const list = $("#recentList");
  try {
    const data = await api("/api/projects");
    const projects = data.items || [];
    list.innerHTML = projects.length ? projects.map((project) => `<button class="recent-item" data-project-id="${escapeHtml(project.id)}" type="button"><strong>${escapeHtml(project.title || "제목 없는 프로젝트")}</strong><span>${escapeHtml(project.aspect_ratio || "9:16")} · 카드 ${(project.cards || []).length}장 · ${project.status === "rendered" ? "렌더 완료" : "편집 중"}</span></button>`).join("") : `<div class="recent-empty">아직 저장된 프로젝트가 없습니다.</div>`;
    list.querySelectorAll("[data-project-id]").forEach((button) => button.addEventListener("click", () => openProject(button.dataset.projectId)));
  } catch (error) { list.innerHTML = `<div class="recent-empty">최근 작업을 불러오지 못했습니다.</div>`; }
}

async function openProject(id) {
  try {
    const data = await api(`/api/projects/${id}`);
    syncProject(data.project); closeRecent();
    toast("프로젝트를 이어서 편집합니다.");
  } catch (error) { toast(error.message, true); }
}

function openRecent() {
  $("#recentDrawer").classList.add("open");
  $("#recentDrawer").setAttribute("aria-hidden", "false");
  $("#drawerBackdrop").hidden = false;
  loadRecentProjects();
}

function closeRecent() {
  $("#recentDrawer").classList.remove("open");
  $("#recentDrawer").setAttribute("aria-hidden", "true");
  $("#drawerBackdrop").hidden = true;
  $("#sidebar").classList.remove("open");
}

function wire() {
  $("#btnRefresh").addEventListener("click", () => loadTrends(true));
  $("#btnBuild").addEventListener("click", buildProject);
  $("#btnRender").addEventListener("click", renderProject);
  $("#btnPlay").addEventListener("click", togglePlayback);
  $("#btnPrev").addEventListener("click", () => { stopPlayback(); const cards = state.project?.cards || []; if (cards.length) selectCard(cards[(currentCardIndex() - 1 + cards.length) % cards.length].id); });
  $("#btnNext").addEventListener("click", () => { stopPlayback(); const cards = state.project?.cards || []; if (cards.length) selectCard(cards[(currentCardIndex() + 1) % cards.length].id); });
  $("#btnCopy").addEventListener("click", async () => {
    const path = state.project?.render?.video_url || state.project?.preview_url;
    if (!path) return;
    try { await navigator.clipboard.writeText(new URL(withBase(path), location.origin).href); toast("결과 링크를 복사했습니다."); }
    catch { toast("링크 복사에 실패했습니다.", true); }
  });
  $("#btnPush").addEventListener("click", pushTimeline);
  $("#btnRecent").addEventListener("click", openRecent);
  $("#btnCloseRecent").addEventListener("click", closeRecent);
  $("#drawerBackdrop").addEventListener("click", closeRecent);
  $("#btnMenu").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
  $$("[data-aspect]").forEach((button) => button.addEventListener("click", async () => {
    if (state.aspect === button.dataset.aspect) return;
    state.aspect = button.dataset.aspect; renderControls(); setStageMode(); paintPreview();
    if (state.project?.id) await persistSettings({ aspect_ratio: state.aspect }, "화면 비율을 저장했습니다. 다시 렌더하세요.");
  }));
  $("#engine").addEventListener("change", async (event) => {
    state.engine = event.target.value;
    if (!state.project?.id) return;
    try {
      const data = await api(`/api/projects/${state.project.id}/engine`, { method: "POST", body: JSON.stringify({ engine: state.engine }) });
      state.project = data.project; await invalidateRender();
      setSaveState("저장됨", "saved"); toast(`렌더 엔진: ${event.target.selectedOptions[0].textContent}`);
    } catch (error) { toast(error.message, true); }
  });
  window.addEventListener("beforeunload", (event) => { if (state.editorDirty) { event.preventDefault(); event.returnValue = ""; } });
  window.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s" && state.editorDirty) { event.preventDefault(); saveCard(); }
    if (event.key === "Escape") closeRecent();
  });
}

async function init() {
  wire(); renderSlides();
  try { await Promise.all([loadMeta(), loadTrends(true), loadRecentProjects()]); }
  catch (error) { toast(`초기화 중 오류: ${error.message}`, true); }
  const projectId = new URLSearchParams(location.search).get("project");
  if (projectId) await openProject(projectId);
  try {
    const health = await api("/api/health");
    $("#healthDot").classList.toggle("ok", health.ok);
    $("#health").textContent = health.ok ? `v${health.version} · 연결됨` : "서버 확인 필요";
  } catch { $("#health").textContent = "서버 연결 실패"; }
}

init();
