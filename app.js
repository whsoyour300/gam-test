/* 감 테스트 — 주제 고르기 · 진행 · 채점 · 결과 · 공유
 *
 * 계산은 전부 여기서 끝난다. 서버는 촌평 한 줄을 받을 때만 부른다.
 * 원본 데이터는 이 앱에 들어오지 않는다 — topics/*.json 에 정답과 근거만 있다.
 */

const $ = (id) => document.getElementById(id);
const views = { home: $("view-home"), quiz: $("view-quiz"), result: $("view-result") };
// 첫 저장(11주제) 뒤에 더한 주제 — 시작 화면 오른쪽 칸에 놓는다
const NEW_TOPICS = new Set(["dram", "jpykrw", "seoul-apt"]);

let INDEX = null;     // topics.json
let PACK = null;      // 지금 푸는 주제
let idx = 0;
let answers = [];

const DONE_KEY = "gam-test-done";

/* 푼 주제를 기억한다. 이 브라우저 안에만 남고 서버로 가지 않는다.
   시크릿 창이나 저장소 차단 환경에서는 읽기·쓰기가 막히므로 감싼다. */
function doneMap() {
  try { return JSON.parse(localStorage.getItem(DONE_KEY) || "{}"); }
  catch { return {}; }
}
function markDone(id, score) {
  try {
    const m = doneMap();
    m[id] = Math.max(score, m[id] ?? 0);
    localStorage.setItem(DONE_KEY, JSON.stringify(m));
  } catch { /* 저장이 막혀 있어도 앱은 그대로 돈다 */ }
}

/* ── 채점 ────────────────────────────────────────────
 * 택1     맞으면 100, 틀리면 0
 * 슬라이더 오차율 × 200 만큼 깎는다 (10% 빗나가면 80점)
 */
function scoreOne(q, mine) {
  if (q.type === "choice") return mine === q.answer ? 100 : 0;
  const err = Math.abs(mine - q.answer) / Math.abs(q.answer);
  return Math.max(0, Math.round(100 - err * 200));
}
function errPct(q, mine) {
  if (q.type === "choice") return mine === q.answer ? 0 : 100;
  return Math.abs(mine - q.answer) / Math.abs(q.answer) * 100;
}
function gradeOf(s) {
  return INDEX.grades.find((g) => s >= g.min) || INDEX.grades.at(-1);
}
function reactionOf(q, mine, pct) {
  if (q.type === "choice") {
    return mine === q.answer ? INDEX.reactions_choice.hit
                             : INDEX.reactions_choice.miss;
  }
  return (INDEX.reactions.find((r) => pct <= r.max) || { text: "" }).text;
}
/* 받침이 있으면 을, 없으면 를 */
function josa(w) {
  const c = String(w).trim().slice(-1).charCodeAt(0);
  if (c < 0xac00 || c > 0xd7a3) return "을";
  return (c - 0xac00) % 28 ? "을" : "를";
}
/* Gemini 에게는 숫자가 아니라 방향만 보낸다 */
function directionOf(q, mine) {
  if (q.type === "choice") return mine === q.answer ? "맞힘" : "틀림";
  const d = (mine - q.answer) / Math.abs(q.answer);
  if (Math.abs(d) <= 0.08) return "비슷";
  return d > 0 ? "높게" : "낮게";
}

function show(name) {
  Object.entries(views).forEach(([k, el]) => (el.hidden = k !== name));
  $("app").classList.toggle("wide", name === "home");
  window.scrollTo({ top: 0 });
}

/* ── 시작 ────────────────────────────────────────── */
async function boot() {
  INDEX = await (await fetch("topics.json", { cache: "no-cache" })).json();
  $("title").textContent = INDEX.title;
  $("subtitle").textContent = INDEX.subtitle;

  const p = new URLSearchParams(location.search);
  if (p.has("s")) {
    const g = p.get("g") || "";
    const t = INDEX.topics.find((x) => x.id === p.get("t"));
    $("shared-banner").innerHTML =
      `친구가 ${t ? `<b>${t.emoji} ${t.title}</b> 에서 ` : ""}` +
      `<b>${Number(p.get("s"))}점 · ${g}</b>${josa(g || "점")} 받았습니다. 당신은요?`;
    $("shared-banner").hidden = false;
  }

  renderGrid();
  $("btn-next").onclick = next;
  $("btn-back").onclick = () => show("home");
  $("btn-more").onclick = () => { renderGrid(); show("home"); };
  $("btn-share").onclick = share;
  if (p.has("t")) {
    const t = INDEX.topics.find((x) => x.id === p.get("t"));
    if (t && !p.has("s")) start(t.id);
  }
}

function renderGrid() {
  const done = doneMap();
  const n = INDEX.topics.filter((t) => t.id in done).length;
  $("progress-note").textContent =
    n ? `${INDEX.topics.length}개 중 ${n}개 풀었습니다` : "";
  $("topic-grid").innerHTML = "";
  $("topic-grid-new").innerHTML = "";
  INDEX.topics.forEach((t) => {
    const b = document.createElement("button");
    b.className = "tcard" + (t.id in done ? " done" : "");
    b.innerHTML =
      `<span class="temoji">${t.emoji}</span>` +
      `<span class="ttitle">${t.title}</span>` +
      `<span class="tblurb">${t.blurb}</span>` +
      (t.id in done ? `<span class="tscore">${done[t.id]}점</span>` : "");
    b.onclick = () => start(t.id);
    $(NEW_TOPICS.has(t.id) ? "topic-grid-new" : "topic-grid").appendChild(b);
  });
}

async function start(id) {
  PACK = await (await fetch(`topics/${id}.json`)).json();
  idx = 0; answers = [];
  $("topic-name").textContent = `${PACK.emoji} ${PACK.title}`;
  renderQ();
  show("quiz");
}

/* ── 문항 ────────────────────────────────────────── */
function renderQ() {
  const q = PACK.questions[idx];
  $("progress-bar").style.width = `${(idx / PACK.questions.length) * 100}%`;
  $("q-count").textContent = `${idx + 1} / ${PACK.questions.length}`;
  $("q-text").textContent = q.text;
  $("btn-next").textContent =
    idx === PACK.questions.length - 1 ? "결과 보기" : "다음";

  const isChoice = q.type === "choice";
  $("q-choice").hidden = !isChoice;
  $("q-slider").hidden = isChoice;

  if (isChoice) {
    answers[idx] = null;
    $("btn-next").disabled = true;
    $("q-choice").innerHTML = "";
    q.options.forEach((opt) => {
      const b = document.createElement("button");
      b.className = "choice";
      b.type = "button";
      b.textContent = opt;
      b.setAttribute("aria-pressed", "false");
      b.onclick = () => {
        answers[idx] = opt;
        [...$("q-choice").children].forEach((c) =>
          c.setAttribute("aria-pressed", String(c === b)));
        $("btn-next").disabled = false;
      };
      $("q-choice").appendChild(b);
    });
  } else {
    const s = $("slider");
    s.min = q.min; s.max = q.max; s.step = q.step;
    // 기본값을 한가운데에서 한 칸 비켜 둔다 — 가운데면 생각 없이 맞는다
    s.value = Math.round(((q.min + q.max) / 2 + q.step) / q.step) * q.step;
    $("slider-min").textContent = `${q.min}${q.unit}`;
    $("slider-max").textContent = `${q.max}${q.unit}`;
    const paint = () => {
      answers[idx] = Number(s.value);
      $("slider-out").textContent = `${s.value}${q.unit}`;
    };
    s.oninput = paint;
    paint();
    $("btn-next").disabled = false;
  }
}

function next() {
  if (idx < PACK.questions.length - 1) { idx++; renderQ(); return; }
  renderResult();
  show("result");
}

/* ── 결과 ────────────────────────────────────────── */
function pos(q, v) {
  return Math.max(0, Math.min(100, ((v - q.min) / (q.max - q.min)) * 100));
}

function renderResult() {
  const total = Math.round(
    PACK.questions.map((q, i) => scoreOne(q, answers[i]))
      .reduce((a, b) => a + b, 0) / PACK.questions.length);
  const g = gradeOf(total);
  markDone(PACK.id, total);

  $("result-topic").textContent = `${PACK.emoji} ${PACK.title}`;
  $("score").innerHTML = `${total}<span>점</span>`;
  $("grade").textContent = g.name;
  $("grade-emoji").textContent = g.emoji || "";

  const box = $("cards");
  box.innerHTML = "";
  PACK.questions.forEach((q, i) => {
    const mine = answers[i];
    const pct = errPct(q, mine);
    const hit = q.type === "choice" ? mine === q.answer : pct <= 5;
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = `
      <h3>${q.text}</h3>
      <p class="react ${hit ? "hit" : pct > 40 ? "miss" : ""}">${reactionOf(q, mine, pct)}</p>
      ${q.type === "choice" ? choiceBody(q, mine) : sliderBody(q, mine)}
      ${q.chart ? chartBody(q.chart) : ""}
      ${q.insight ? `<p class="insight"><b>업계 배경</b>${q.insight}</p>` : ""}
      <p class="why">💡 ${q.why}</p>
      <details><summary>근거 보기</summary><p class="basis">${q.basis}</p></details>`;
    box.appendChild(el);
  });

  $("caveat").hidden = !PACK.caveat;
  if (PACK.caveat) $("caveat").innerHTML = `<b>이 데이터의 한계</b><br>${PACK.caveat}`;
  $("source").innerHTML =
    `출처 <a href="${PACK.source_url}" target="_blank" rel="noopener">${PACK.source}</a>`;

  requestAnimationFrame(() => setTimeout(animate, 60));
  askComment(total, g.name);
}

function choiceBody(q, mine) {
  const label = (o) => {
    const cls = o === q.answer && o === mine ? "both"
      : o === q.answer ? "real" : o === mine ? "mine" : "";
    const tag = o === q.answer && o === mine ? " 실제 · 내 답"
      : o === q.answer ? " 실제" : o === mine ? " 내 답" : "";
    return `<span class="pill ${cls}">${o}${tag}</span>`;
  };
  return `<div class="pills">${q.options.map(label).join("")}</div>`;
}

function sliderBody(q, mine) {
  const rows = [["내 답", mine, "mine"]];
  rows.push(["실제", q.answer, "real"]);
  const max = Math.max(...rows.map((r) => Math.abs(Number(r[1])))) || 1;
  const bars = rows.map(([k, v, cls]) => `
      <div class="row">
        <span class="k">${k}</span>
        <span class="bar ${cls}"><i data-w="${Math.abs(Number(v)) / max * 100}"></i></span>
        <span class="v">${v}${q.unit}</span>
      </div>`).join("");
  return `
    <div class="track">
      <span class="line"></span>
      <span class="ghost" style="left:${pos(q, mine)}%"></span>
      <span class="live" data-left="${pos(q, q.answer)}" style="left:${pos(q, mine)}%"></span>
    </div>
    <div class="rows">${bars}</div>`;
}

/* ── 문항 그래프 — 문항 파일의 chart 를 SVG 로 그린다 ──────── */
const CW = 400, CH = 180, PAD = { l: 34, r: 8, t: 16, b: 34 };

function chartBody(c) {
  return `<figure class="chart"><figcaption>${c.cap}</figcaption>` +
    (c.kind === "line" ? lineChart(c) : barChart(c)) + `</figure>`;
}

function scaleY(lo, hi) {
  return (v) => PAD.t + (hi - v) / (hi - lo) * (CH - PAD.t - PAD.b);
}

// 막대 — 바닥(0)에 붙은 쪽은 각지고, 값 쪽 끝만 둥글다
function barPath(x, y0, w, top, r) {
  r = Math.min(r, Math.abs(y0 - top));
  const s = top < y0 ? 1 : -1;
  return `M${x},${y0} V${top + s * r} Q${x},${top} ${x + r},${top} ` +
    `H${x + w - r} Q${x + w},${top} ${x + w},${top + s * r} V${y0} Z`;
}

function barChart(c) {
  const lo = Math.min(0, ...c.y), hi = Math.max(0, ...c.y, c.ref ?? 0);
  const y = scaleY(lo, hi), y0 = y(0), h = CH - PAD.t - PAD.b;
  const band = (CW - PAD.l - PAD.r) / c.x.length, w = Math.max(band - 2, 2);
  // 상승률은 +를 붙이고 %, 수준값(원 등)은 그대로 — 문항 파일의 unit · signed 를 따른다
  const unit = c.unit ?? "%", signed = c.signed ?? true;
  const sign = (v) => (signed && v > 0 ? "+" : "") + v.toLocaleString("ko-KR");
  const marks = c.x.map((yr, i) => {
    const v = c.y[i], x = PAD.l + i * band + (band - w) / 2, top = y(v);
    const on = c.hi.includes(yr), dim = c.hi.length && !on ? " dim" : "";
    const cx = x + w / 2, anchor = cx > CW - 50 ? "end" : cx < PAD.l + 40 ? "start" : "middle";
    const lbl = on ? `<text class="lbl" x="${cx}" y="${v >= 0 ? top - 5 : top + 13}"
      text-anchor="${anchor}">${yr}년 ${sign(v)}${unit}</text>` : "";
    return `<g><title>${yr}년 ${sign(v)}${unit}</title>
      <rect class="hit" x="${PAD.l + i * band}" y="${PAD.t}" width="${band}" height="${h}"/>
      <path class="${v >= 0 ? "up" : "down"}${dim}" d="${barPath(x, y0, w, top, Math.min(4, w / 2))}"/>${lbl}</g>`;
  }).join("");
  const ticks = [...new Set([hi, 0, lo])].map((v) =>
    `<line class="${v ? "axis" : "base"}" x1="${PAD.l}" x2="${CW - PAD.r}" y1="${y(v)}" y2="${y(v)}"/>
     <text x="${PAD.l - 5}" y="${y(v) + 4}" text-anchor="end">${Math.round(v)}</text>`).join("");
  const ref = c.ref == null ? "" :
    `<line class="ref" x1="${PAD.l}" x2="${CW - PAD.r}" y1="${y(c.ref)}" y2="${y(c.ref)}"/>
     <text class="lbl" x="${PAD.l + 4}" y="${y(c.ref) - 5}">${c.ref_label}</text>`;
  const xl = [0, c.x.length - 1].map((i) => `<text x="${PAD.l + (i + .5) * band}" y="${CH - 6}"
    text-anchor="${i ? "end" : "start"}">${c.x[i]}</text>`).join("");
  return `<svg viewBox="0 0 ${CW} ${CH}" role="img" aria-label="${c.cap}">${ticks}${marks}${ref}${xl}</svg>`;
}

function lineChart(c) {
  const lo = Math.min(...c.y), hi = Math.max(...c.y), pad = (hi - lo) * .08;
  const y = scaleY(lo - pad, hi + pad), h = CH - PAD.t - PAD.b;
  const step = (CW - PAD.l - PAD.r) / (c.x.length - 1), X = (i) => PAD.l + i * step;
  const ym = (k) => `${k.slice(0, 4)}년 ${+k.slice(5, 7)}월` + (k.length > 7 ? ` ${+k.slice(8)}일` : "");
  const hits = c.x.map((k, i) => `<rect class="hit" x="${X(i) - step / 2}" y="${PAD.t}"
    width="${step}" height="${h}"><title>${ym(k)} ${c.y[i]}</title></rect>`).join("");
  const pts = c.y.map((v, i) => `${X(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const marks = c.marks.map((m, j) => {
    const i = c.x.indexOf(m.x), cx = X(i), cy = y(c.y[i]);
    // above = 점 위 가운데, below = 점 아래 왼쪽, above-left = 점 위 왼쪽, below-right = 점 아래 오른쪽
    // 점 뒤로 다시 오르는 선이나 그래프 가장자리를 피해 글 자리를 고른다
    const pos = m.pos || (j ? "below" : "above");
    const left = pos === "below" || pos === "above-left", right = pos === "below-right";
    const low = (m.tone || (j ? "down" : "up")) === "down";
    const anchor = left ? "end" : right ? "start"
      : cx > CW - 90 ? "end" : cx < PAD.l + 60 ? "start" : "middle";
    const tx = left ? cx + 6 : right ? cx - 6 : cx;
    const ty = pos.startsWith("below") ? cy + 17 : cy - 10;
    return `<circle class="dot${low ? " low" : ""}" cx="${cx}" cy="${cy}" r="4.5"/>
      <text class="lbl" x="${tx}" y="${ty}" text-anchor="${anchor}">${m.label} ${c.y[i].toLocaleString("ko-KR")}</text>`;
  }).join("");
  const ticks = [hi, lo].map((v) =>
    `<line class="axis" x1="${PAD.l}" x2="${CW - PAD.r}" y1="${y(v)}" y2="${y(v)}"/>
     <text x="${PAD.l - 5}" y="${y(v) + 4}" text-anchor="end">${Math.round(v)}</text>`).join("");
  const xl = [0, c.x.length - 1].map((i) => `<text x="${X(i)}" y="${CH - 6}"
    text-anchor="${i ? "end" : "start"}">${c.x[i].slice(0, 4)}</text>`).join("");
  return `<svg viewBox="0 0 ${CW} ${CH}" role="img" aria-label="${c.cap}">${ticks}${hits}
    <polyline class="line" points="${pts}"/>${marks}${xl}</svg>`;
}

function animate() {
  document.querySelectorAll(".bar > i").forEach((b) => (b.style.width = b.dataset.w + "%"));
  document.querySelectorAll(".track .live").forEach((m) => (m.style.left = m.dataset.left + "%"));
}

/* ── 촌평 — 없어도 앱은 그대로 돈다 ──────────────── */
async function askComment(total, grade) {
  const el = $("ai-comment");
  el.hidden = false;
  el.innerHTML = `<span class="tag">촌평을 받아오는 중…</span>`;
  const directions = PACK.questions.map((q, i) => directionOf(q, answers[i]));
  try {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 3000);
    const r = await fetch("/api/comment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score: total, grade, directions, topic: PACK.title }),
      signal: ctl.signal,
    });
    clearTimeout(timer);
    const j = await r.json();
    if (!j || !j.comment) { el.hidden = true; return; }
    el.innerHTML = `<span class="tag">한 줄 촌평</span><br>${j.comment}` +
      (j.nickname ? `<br><span class="nick">${j.nickname}</span>` : "");
  } catch {
    el.hidden = true;
  }
}

/* ── 공유 ────────────────────────────────────────── */
async function share() {
  const total = $("score").textContent.replace(/[^0-9]/g, "");
  const grade = $("grade").textContent;
  const url = `${location.origin}${location.pathname}` +
    `?t=${encodeURIComponent(PACK.id)}&s=${total}&g=${encodeURIComponent(grade)}`;
  const text = `감 테스트 · ${PACK.title} ${total}점 · ${grade}`;
  try {
    if (navigator.share) { await navigator.share({ title: INDEX.title, text, url }); return; }
    await navigator.clipboard.writeText(`${text}\n${url}`);
    $("btn-share").textContent = "링크를 복사했습니다";
    setTimeout(() => ($("btn-share").textContent = "친구에게 보내기"), 1800);
  } catch { /* 사용자가 취소한 경우 */ }
}

boot();
