"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const state = { plan: null, day: 0, profile: null, meta: null };

function fmtQty(qty, unit) {
  if (unit === "") return String(Math.ceil(qty - 1e-9));
  if (qty >= 10) return `${Math.round(qty)} ${unit}`;
  return `${String(+qty.toFixed(2))} ${unit}`;
}

async function api(path, payload) {
  const res = await fetch(path, {
    method: payload ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function showError(msg) { const e = $("error"); e.textContent = msg || ""; e.hidden = !msg; }

function fillSelect(id, values, selected) {
  $(id).innerHTML = values.map((v) => `<option ${v === selected ? "selected" : ""}>${esc(v)}</option>`).join("");
}
function fillChips(id, values, name) {
  $(id).innerHTML = values.map((v) =>
    `<label class="chip"><input type="checkbox" name="${name}" value="${esc(v)}"><span>${esc(v)}</span></label>`).join("");
}
const checked = (name) => [...document.querySelectorAll(`input[name=${name}]:checked`)].map((i) => i.value);
const val = (id) => $(id).value.trim();

function readProfile() {
  return {
    name: val("name"), diet: $("diet").value, days: +$("days").value,
    calorie_goal: val("calorie_goal"), allergies: checked("allergy"), cuisines: checked("cuisine"),
    dislikes: val("dislikes"), pantry: val("pantry"),
    age: val("age"), sex: $("sex").value, weight_kg: val("weight_kg"), height_cm: val("height_cm"),
    activity: $("activity").value, goal: $("goal").value,
    low_carb: $("low_carb").checked, include_snacks: $("include_snacks").checked,
  };
}
function saveProfile(p) { try { localStorage.setItem("rmg-profile", JSON.stringify(p)); } catch (e) { /* storage unavailable */ } }
function restoreProfile() {
  let p; try { p = JSON.parse(localStorage.getItem("rmg-profile") || "null"); } catch (e) { p = null; }
  if (!p) return;
  ["name", "diet", "days", "calorie_goal", "dislikes", "pantry", "age", "sex", "weight_kg", "height_cm", "activity", "goal"]
    .forEach((k) => { if (p[k] !== undefined && p[k] !== null) $(k).value = Array.isArray(p[k]) ? p[k].join(", ") : p[k]; });
  $("low_carb").checked = !!p.low_carb;
  $("include_snacks").checked = p.include_snacks !== false;
  (p.allergies || []).forEach((v) => { const i = document.querySelector(`input[name=allergy][value="${v}"]`); if (i) i.checked = true; });
  (p.cuisines || []).forEach((v) => { const i = document.querySelector(`input[name=cuisine][value="${v}"]`); if (i) i.checked = true; });
}

function statBox(label, avg, target, unit) {
  const pct = Math.min(100, Math.round((avg / Math.max(target, 1)) * 100));
  return `<div class="stat"><div class="meta">${label}</div><b>${avg}</b> <span class="meta">/ ${target} ${unit}</span>
    <div class="bar"><span style="width:${pct}%"></span></div></div>`;
}

function renderSummary() {
  const s = state.plan.summary, a = s.average, m = s.macro_targets;
  $("summary").innerHTML = `<h2>Hello ${esc(state.profile.name || "Friend")}, here is your plan</h2>
    <p class="meta">Daily target: <b>${s.target_kcal} kcal</b> (${esc(s.target_source)}). Averages below are per day.</p>
    <div class="stats">${statBox("Calories", a.kcal, s.target_kcal, "kcal")}${statBox("Protein", a.protein, m.protein, "g")}
    ${statBox("Carbs", a.carbs, m.carbs, "g")}${statBox("Fat", a.fat, m.fat, "g")}</div>`;
  $("notes").innerHTML = state.plan.notes.map((n) => `<div class="note">${esc(n)}</div>`).join("");
}

function renderTabs() {
  $("tabs").innerHTML = state.plan.days.map((d, i) =>
    `<button class="tab" role="tab" aria-selected="${i === state.day}" data-day="${i}">${esc(d.day)}</button>`).join("");
  $("tabs").querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { state.day = +b.dataset.day; renderTabs(); renderMeals(); }));
}

function mealCard(m, dayIdx, idx) {
  const n = m.nutrition;
  const match = m.pantry_match >= 0.5 ? `<span class="meta">Uses ${Math.round(m.pantry_match * 100)}% of what you have</span>` : "";
  const warn = m.allergens.length ? `<span class="meta">Contains: ${m.allergens.map(esc).join(", ")}</span>` : "";
  return `<article class="card">
    <img src="${esc(m.image)}" alt="${esc(m.title)}" loading="lazy">
    <div class="body">
      <span class="slot">${esc(m.slot)}</span>
      <h3>${esc(m.title)}</h3>
      <div class="meta">${m.minutes} min | ${esc(m.cuisine)} | portion x${m.portion}</div>
      <div class="macros"><div><b>${n.kcal}</b>kcal</div><div><b>${n.protein}g</b>protein</div><div><b>${n.carbs}g</b>carbs</div><div><b>${n.fat}g</b>fat</div></div>
      ${match}${warn}
      <details><summary>Ingredients and steps</summary>
        <ul>${m.ingredients.map((i) => `<li>${esc(fmtQty(i.qty, i.unit))} ${esc(i.name)}</li>`).join("")}</ul>
        <ol>${m.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol></details>
      <div class="actions">
        <span class="stars" aria-label="Rate this recipe">${[1, 2, 3, 4, 5].map((r) => `<button data-rate="${r}" data-id="${esc(m.id)}" title="${r} star">&#9733;</button>`).join("")}</span>
        <button data-swap="${idx}" data-day="${dayIdx}">Swap</button>
      </div>
    </div></article>`;
}

function renderMeals(all) {
  const days = state.plan.days;
  const list = all ? days.map((d, i) => [d, i]) : [[days[state.day], state.day]];
  $("meals").innerHTML = list.map(([d, di]) =>
    (all ? `<h3 style="grid-column:1/-1">${esc(d.day)}</h3>` : "") +
    d.meals.map((m, i) => mealCard(m, di, i)).join("") +
    `<div class="meta" style="grid-column:1/-1">Day total: <b>${d.totals.kcal} kcal</b> | ${d.totals.protein}g protein | ${d.totals.carbs}g carbs | ${d.totals.fat}g fat</div>`
  ).join("");
}

function renderShopping() {
  const groups = {};
  state.plan.shopping.forEach((i) => (groups[i.category] = groups[i.category] || []).push(i));
  $("shopping").innerHTML = Object.keys(groups).map((cat) =>
    `<div class="shop-group"><h4>${esc(cat)}</h4>${groups[cat].map((i) =>
      `<label><input type="checkbox" ${i.have ? "checked" : ""}><span>${esc(i.quantity)} ${esc(i.name)}</span>${i.have ? '<span class="have">have</span>' : ""}</label>`).join("")}</div>`).join("");
}

function renderAll() {
  renderSummary(); renderTabs(); renderMeals(); renderShopping();
  $("results").hidden = false;
}

async function generate() {
  showError("");
  const btn = $("generate"); btn.disabled = true; btn.textContent = "Cooking up ideas...";
  try {
    state.profile = readProfile(); saveProfile(state.profile);
    state.plan = await api("/api/plan", { profile: state.profile });
    state.day = 0; renderAll();
    $("results").scrollIntoView({ behavior: "smooth" });
  } catch (e) { showError(e.message); }
  finally { btn.disabled = false; btn.textContent = "Generate my meal plan"; }
}

async function swap(day, index) {
  try {
    state.plan = await api("/api/swap", { profile: state.profile, spec: state.plan.spec, day, index });
    state.day = day; renderAll();
  } catch (e) { showError(e.message); window.scrollTo({ top: 0, behavior: "smooth" }); }
}

async function rate(id, rating) {
  try { await api("/api/feedback", { recipe_id: id, rating }); } catch (e) { showError(e.message); }
}

async function askAI() {
  showError("");
  const box = $("ai-result"); const btn = $("ai-btn"); btn.disabled = true;
  try {
    const profile = readProfile();
    const m = await api("/api/ai-recipe", { profile, slot: "dinner" });
    box.innerHTML = `<h2>AI chef suggestion</h2><div class="cards">${mealCard(m, -1, -1).replace(/<div class="actions">[\s\S]*?<\/div>\s*<\/div><\/article>/, "</div></article>")}</div>`;
    box.hidden = false; box.scrollIntoView({ behavior: "smooth" });
  } catch (e) { showError(e.message); }
  finally { btn.disabled = false; }
}

document.addEventListener("click", (ev) => {
  const t = ev.target.closest("button"); if (!t) return;
  if (t.dataset.swap !== undefined) swap(+t.dataset.day, +t.dataset.swap);
  if (t.dataset.rate) { rate(t.dataset.id, +t.dataset.rate); t.parentElement.querySelectorAll("button").forEach((b) => (b.style.opacity = +b.dataset.rate <= +t.dataset.rate ? 1 : 0.3)); }
});

$("generate").addEventListener("click", generate);
$("ai-btn").addEventListener("click", askAI);
$("print").addEventListener("click", () => { renderMeals(true); window.print(); });
window.addEventListener("afterprint", () => { if (state.plan) renderMeals(); });
$("copy-list").addEventListener("click", async () => {
  const text = state.plan.shopping.map((i) => `- ${i.quantity} ${i.name}`).join("\n");
  try { await navigator.clipboard.writeText(text); $("copy-list").textContent = "Copied!"; } catch (e) { $("copy-list").textContent = "Copy failed"; }
  setTimeout(() => ($("copy-list").textContent = "Copy"), 1500);
});

(async function init() {
  try {
    state.meta = await api("/api/meta");
    const m = state.meta;
    fillSelect("diet", m.diets, "vegetarian"); fillSelect("activity", m.activity, "light"); fillSelect("goal", m.goals, "maintain");
    fillSelect("days", [1, 2, 3, 4, 5, 6, 7].map(String), "7");
    fillChips("allergies", m.allergens, "allergy"); fillChips("cuisines", m.cuisines, "cuisine");
    restoreProfile();
    if (!m.ai_enabled) $("ai-btn").title = "AI chef is off: set ANTHROPIC_API_KEY on the server to enable it";
  } catch (e) { showError("Could not load the app data: " + e.message); }
})();
