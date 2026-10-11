const state = {
  plants: [],
  filter: "due",
  env: {},
  editingPhotoFile: null,
  identifyCandidates: [],
  rooms: [],
  editTemp: "",
  editHum: "",
  editRoomName: "",
};

const BASE = location.pathname.endsWith("/") ? location.pathname : location.pathname + "/";
const $ = (id) => document.getElementById(id);

function asset(path) {
  return BASE + String(path).replace(/^\//, "");
}

function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function fromLocalInput(val) {
  return val ? new Date(val).toISOString() : null;
}

function toast(message, ms = 2600, action = null) {
  const el = $("toast");
  el.innerHTML = "";
  el.append(document.createTextNode(message));
  if (action) {
    const btn = document.createElement("button");
    btn.className = "toast-btn";
    btn.textContent = action.label;
    btn.addEventListener("click", () => {
      el.classList.add("hidden");
      action.onClick();
    });
    el.appendChild(btn);
    ms = Math.max(ms, 6000);
  }
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), ms);
}

async function api(path, options = {}) {
  const res = await fetch(asset(path), {
    headers: options.body && !(options.body instanceof FormData)
      ? { "Content-Type": "application/json" }
      : undefined,
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function statusLabel(status) {
  return {
    overdue: "Overdue",
    due: "Water today",
    soon: "Due soon",
    ok: "Happy",
    inactive: "Paused",
    unknown: "New",
  }[status] || status;
}

function relativeDays(days) {
  if (days === null || days === undefined) return "never watered";
  const rounded = Math.round(days);
  if (rounded < 0) return `overdue ${Math.abs(rounded)}d`;
  if (rounded === 0) return "due today";
  if (rounded === 1) return "due tomorrow";
  return `in ${rounded}d`;
}

function lastWateredText(iso) {
  if (!iso) return "not watered yet";
  const then = new Date(iso);
  const days = Math.floor((Date.now() - then.getTime()) / 86400000);
  if (days <= 0) return "watered today";
  if (days === 1) return "watered yesterday";
  return `watered ${days}d ago`;
}

function fertilizeText(plant) {
  if (!plant.fertilize_in_season) return "feeding off-season";
  const d = plant.fertilize_days_until;
  if (d === null || d === undefined) return "feed due";
  if (d < 0) return `feed overdue ${Math.abs(Math.round(d))}d`;
  if (d < 1) return "feed today";
  return `feed in ${Math.round(d)}d`;
}

function cardHTML(plant) {
  const photo = plant.photo ? asset(`photos/${plant.photo}`) : asset("static/placeholder.svg");
  const showOk = plant.status === "ok" || plant.status === "soon";
  const reason = plant.adjustment_reason && plant.adjustment_reason !== "season baseline"
    ? `<div class="reason">⤵ ${plant.adjustment_reason} · every ${plant.effective_interval_days}d</div>`
    : `<div class="reason">every ${plant.effective_interval_days}d</div>`;
  const sickBadge = plant.is_sick ? `<span class="badge sick">🤒 Sick</span>` : "";
  const warnBadge = plant.sensor_warning
    ? `<span class="badge warn" title="No temperature or humidity sensors linked to this plant's room">⚠️</span>`
    : "";
  const fertLine = plant.fertilize_interval_days > 0
    ? `<div class="fert ${plant.fertilize_status === "overdue" || plant.fertilize_status === "due" ? "due" : ""}">🌱 ${fertilizeText(plant)}</div>`
    : "";
  const sickNote = plant.is_sick && plant.sick_note ? `<div class="sick-note">${escapeHTML(plant.sick_note)}</div>` : "";
  const feedBtn = plant.fertilize_interval_days > 0
    ? `<button class="ghost icon-btn feed-btn" title="Mark as fed">🌱</button>`
    : "";
  return `
    <div class="card ${plant.is_sick ? "is-sick" : ""}" data-id="${plant.id}">
      <img class="photo" src="${photo}" alt="${plant.name}" loading="lazy" />
      <div class="body">
        <div class="badges"><span class="badge ${plant.status}">${statusLabel(plant.status)}</span>${sickBadge}${warnBadge}</div>
        <h3>${escapeHTML(plant.name)}</h3>
        ${plant.species ? `<div class="species">${escapeHTML(plant.species)}</div>` : ""}
        <div class="loc">${plant.placement === "outdoor" ? "🌤" : "🏠"} ${escapeHTML(plant.location || "Unplaced")}</div>
        <div class="meta"><span>${lastWateredText(plant.last_watered)}</span><span>${relativeDays(plant.days_until_due)}</span></div>
        ${reason}
        ${fertLine}
        ${sickNote}
        <div class="row">
          <button class="primary water-btn">${showOk ? "💧 Water" : "💧 Mark watered"}</button>
          <button class="ghost icon-btn sick-btn" title="${plant.is_sick ? "Mark healthy" : "Mark sick"}">${plant.is_sick ? "💚" : "🤒"}</button>
          ${feedBtn}
        </div>
      </div>
    </div>`;
}

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function renderPlants() {
  const grid = $("grid");
  let list = state.plants;
  if (state.filter === "due") list = list.filter((p) => ["overdue", "due"].includes(p.status));
  if (state.filter === "ok") list = list.filter((p) => ["ok", "soon"].includes(p.status) && !p.is_sick);
  if (state.filter === "sick") list = list.filter((p) => p.is_sick);

  grid.innerHTML = list.map(cardHTML).join("");
  $("empty").classList.toggle("hidden", list.length > 0);

  grid.querySelectorAll(".card").forEach((card) => {
    const id = Number(card.dataset.id);
    const plant = state.plants.find((p) => p.id === id);
    card.addEventListener("click", () => openPlantModal(id));
    const act = (selector, handler) => {
      const el = card.querySelector(selector);
      if (el) el.addEventListener("click", (e) => {
        e.stopPropagation();
        handler();
      });
    };
    act(".water-btn", () => waterPlant(id));
    act(".sick-btn", () => (plant.is_sick ? markHealthy(id) : markSick(id)));
    act(".feed-btn", () => fertilizePlant(id));
  });
}

function renderWeather() {
  const env = state.env;
  const bar = $("weather");
  if (!env || !env.available) {
    bar.classList.add("hidden");
    return;
  }
  const parts = [];
  if (env.condition) parts.push(`<strong>${escapeHTML(env.condition)}</strong>`);
  if (env.outdoor_temp_c != null) parts.push(`🌡 ${env.outdoor_temp_c.toFixed(1)}°C outside`);
  if (env.humidity != null) parts.push(`💧 ${env.humidity}% humidity`);
  if (env.rain_mm != null) parts.push(`🌧 ${env.rain_mm} mm rain`);
  const forecast = (env.forecast || []).map((d) =>
    `<span>${new Date(d.datetime).toLocaleDateString(undefined, { weekday: "short" })} ${d.temperature ?? "–"}° / ${d.templow ?? "–"}°</span>`
  ).join("");
  bar.innerHTML = parts.join("") + (forecast ? `<div class="forecast">${forecast}</div>` : "");
  bar.classList.remove("hidden");
}

async function loadHaRooms(force = false) {
  if (!force && state.rooms.length) return state.rooms;
  try {
    state.rooms = (await api("/api/ha/rooms")) || [];
  } catch (err) {
    state.rooms = [];
  }
  return state.rooms;
}

function roomById(id) {
  return state.rooms.find((r) => r.area_id === id) || null;
}

function fillRoomSelect(selectedId) {
  const sel = $("plant-room");
  const rooms = state.rooms;
  sel.innerHTML =
    `<option value="">No room</option>` +
    rooms.map((r) => `<option value="${escapeHTML(r.area_id)}">${escapeHTML(r.name)}</option>`).join("");
  if (selectedId && !rooms.some((r) => r.area_id === selectedId)) {
    sel.innerHTML += `<option value="${escapeHTML(selectedId)}">${escapeHTML(selectedId)} (not in HA)</option>`;
  }
  sel.value = selectedId || "";
  renderRoomSensors();
}

function sensorOptions(sensors, selected, selectId) {
  const chosen = sensors.some((s) => s.entity_id === selected) ? selected : sensors[0]?.entity_id;
  const opts = sensors
    .map(
      (s) =>
        `<option value="${escapeHTML(s.entity_id)}"${s.entity_id === chosen ? " selected" : ""}>${escapeHTML(
          s.name || s.entity_id
        )}</option>`
    )
    .join("");
  return `<select id="${selectId}">${opts}</select>`;
}

function renderRoomSensors() {
  const box = $("room-sensors");
  const roomId = $("plant-room").value;
  const room = roomById(roomId);
  if (!roomId) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  if (!room) {
    box.innerHTML = `<div class="sensor-warning">⚠️ This room isn't available in Home Assistant, so no sensors could be looked up. You can still save.</div>`;
    return;
  }
  const temps = room.temperature_sensors || [];
  const hums = room.humidity_sensors || [];
  if (!temps.length && !hums.length) {
    box.innerHTML = `<div class="sensor-warning">⚠️ No temperature or humidity sensors are linked to <strong>${escapeHTML(
      room.name
    )}</strong>. You can still save — the plant will show a warning until sensors are added in Home Assistant.</div>`;
    return;
  }
  const tempField = temps.length
    ? temps.length === 1
      ? `<div class="sensor-note">🌡 <strong>${escapeHTML(temps[0].name)}</strong></div>`
      : `<label>Temperature sensor${sensorOptions(temps, state.editTemp, "plant-temp-entity")}</label>`
    : `<div class="sensor-note muted">🌡 No temperature sensor in this room.</div>`;
  const humField = hums.length
    ? hums.length === 1
      ? `<div class="sensor-note">💧 <strong>${escapeHTML(hums[0].name)}</strong></div>`
      : `<label>Humidity sensor${sensorOptions(hums, state.editHum, "plant-hum-entity")}</label>`
    : `<div class="sensor-note muted">💧 No humidity sensor in this room.</div>`;
  box.innerHTML = tempField + humField;
}

function pickSensorEntity(sensors, selectId) {
  if (!sensors || !sensors.length) return "";
  if (sensors.length === 1) return sensors[0].entity_id;
  const sel = $(selectId);
  return sel ? sel.value : "";
}

async function loadAll() {
  try {
    const [plants, weather, status] = await Promise.all([
      api("/api/plants"),
      api("/api/weather"),
      api("/api/status"),
    ]);
    state.plants = plants;
    state.env = weather;
    const pill = $("ha-status");
    let pillClass = "bad";
    let pillLabel = "HA offline";
    if (status.ha_reachable) {
      if (status.entities_configured) {
        pillClass = "ok";
        pillLabel = "HA connected";
      } else {
        pillClass = "warn";
        pillLabel = "Set sensors";
      }
    }
    pill.className = "status-pill " + pillClass;
    pill.textContent = pillLabel;
    renderPlants();
    renderWeather();
  } catch (err) {
    toast("Load failed: " + err.message);
  }
}

async function waterPlant(id) {
  try {
    const plant = await api(`/api/plants/${id}/water`, { method: "POST", body: JSON.stringify({}) });
    toast(`Watered ${plant.name} 💧`, 5000, { label: "Undo", onClick: () => undoWater(id) });
    loadAll();
  } catch (err) {
    toast("Failed: " + err.message);
  }
}

async function undoWater(id) {
  try {
    await api(`/api/plants/${id}/water/undo`, { method: "POST" });
    toast("Watering undone");
    loadAll();
  } catch (err) {
    toast("Undo failed: " + err.message);
  }
}

async function markSick(id) {
  const note = prompt("Symptoms / note (optional):") ?? "";
  try {
    await api(`/api/plants/${id}/sick`, { method: "POST", body: JSON.stringify({ note }) });
    toast("Marked as sick — you'll get a daily check-up 🤒");
    loadAll();
  } catch (err) {
    toast("Failed: " + err.message);
  }
}

async function markHealthy(id) {
  try {
    await api(`/api/plants/${id}/healthy`, { method: "POST" });
    toast("Marked as healthy 💚");
    loadAll();
  } catch (err) {
    toast("Failed: " + err.message);
  }
}

async function fertilizePlant(id) {
  try {
    await api(`/api/plants/${id}/fertilize`, { method: "POST" });
    toast("Marked as fed 🌱");
    loadAll();
  } catch (err) {
    toast("Failed: " + err.message);
  }
}

async function openPlantModal(id = null) {
  state.editingPhotoFile = null;
  state.identifyCandidates = [];
  const plant = id ? state.plants.find((p) => p.id === id) : null;
  state.editTemp = plant?.temp_entity || "";
  state.editHum = plant?.humidity_entity || "";
  state.editRoomName = plant?.room_name || plant?.location || "";
  await loadHaRooms(true);
  let roomId = plant?.room_id || "";
  if (!roomId && plant?.location) {
    const match = state.rooms.find(
      (r) => (r.name || "").trim().toLowerCase() === plant.location.trim().toLowerCase()
    );
    if (match) roomId = match.area_id;
  }
  $("plant-modal-title").textContent = plant ? "Edit plant" : "Add plant";
  $("plant-id").value = plant ? plant.id : "";
  $("plant-name").value = plant ? plant.name : "";
  $("plant-species").value = plant?.species || "";
  $("plant-placement").value = plant?.placement || "indoor";
  fillRoomSelect(roomId);
  $("plant-interval").value = plant?.base_interval_days || 7;
  $("plant-fert-interval").value = plant ? plant.fertilize_interval_days ?? 30 : 30;
  $("plant-sick").checked = plant ? !!plant.is_sick : false;
  $("plant-sick-note").value = plant?.sick_note || "";
  $("plant-status").value = plant?.status_override || "";
  $("plant-last-watered").value = toLocalInput(plant?.last_watered);
  $("plant-notes").value = plant?.notes || "";
  $("plant-active").checked = plant ? plant.active : true;
  $("plant-photo").value = "";
  const preview = $("photo-preview");
  preview.src = plant?.photo ? asset(`photos/${plant.photo}`) : asset("static/placeholder.svg");
  $("identify-results").innerHTML = "";
  $("plant-modal").classList.remove("hidden");
}

async function savePlant(event) {
  event.preventDefault();
  const id = $("plant-id").value;
  const room = roomById($("plant-room").value);
  const payload = {
    name: $("plant-name").value.trim(),
    species: $("plant-species").value.trim() || null,
    location: room ? room.name : state.editRoomName,
    placement: $("plant-placement").value,
    room_id: $("plant-room").value,
    room_name: room ? room.name : state.editRoomName,
    temp_entity: room ? pickSensorEntity(room.temperature_sensors, "plant-temp-entity") : state.editTemp,
    humidity_entity: room ? pickSensorEntity(room.humidity_sensors, "plant-hum-entity") : state.editHum,
    base_interval_days: Number($("plant-interval").value) || 7,
    fertilize_interval_days: Math.max(0, Number($("plant-fert-interval").value) || 0),
    is_sick: $("plant-sick").checked,
    sick_note: $("plant-sick-note").value.trim(),
    status_override: $("plant-status").value,
    last_watered: fromLocalInput($("plant-last-watered").value),
    notes: $("plant-notes").value.trim(),
    active: $("plant-active").checked,
  };
  try {
    const plant = id
      ? await api(`/api/plants/${id}`, { method: "PATCH", body: JSON.stringify(payload) })
      : await api("/api/plants", { method: "POST", body: JSON.stringify(payload) });

    if (state.editingPhotoFile) {
      const form = new FormData();
      form.append("file", state.editingPhotoFile);
      await api(`/api/plants/${plant.id}/photo`, { method: "POST", body: form });
    }
    $("plant-modal").classList.add("hidden");
    toast("Saved");
    loadAll();
  } catch (err) {
    toast("Save failed: " + err.message);
  }
}

async function identifyPlant() {
  const id = $("plant-id").value;
  const organ = $("identify-organ").value;
  const box = $("identify-results");
  box.innerHTML = `<span class="hint">Identifying…</span>`;
  try {
    let result;
    if (state.editingPhotoFile) {
      const form = new FormData();
      form.append("file", state.editingPhotoFile);
      result = await api(`/api/identify?organ=${encodeURIComponent(organ)}`, { method: "POST", body: form });
    } else if (id) {
      result = await api(`/api/plants/${id}/identify?organ=${encodeURIComponent(organ)}`, { method: "POST" });
    } else {
      box.innerHTML = `<span class="hint">Choose a photo first, then identify.</span>`;
      return;
    }
    renderCandidates(result);
  } catch (err) {
    box.innerHTML = `<span class="hint">${escapeHTML(err.message)}</span>`;
  }
}

function renderCandidates(result) {
  const box = $("identify-results");
  const list = result.candidates || [];
  state.identifyCandidates = list;
  if (!list.length) {
    box.innerHTML = `<span class="hint">No match found for this photo.</span>`;
    return;
  }
  const attribution = `<span class="attribution">Powered by Pl@ntNet${result.remaining_requests != null ? ` · ${result.remaining_requests} requests left today` : ""}</span>`;
  box.innerHTML = list.map((c, i) => {
    const common = c.common_names[0] || c.scientific_name;
    const pct = Math.round(c.score * 100);
    const family = c.family ? ` · ${escapeHTML(c.family)}` : "";
    return `<button type="button" class="candidate" data-index="${i}">
      <span class="names"><span>${escapeHTML(common)}</span><span class="sci">${escapeHTML(c.scientific_name)}${family}</span></span>
      <span class="score">${pct}%</span>
    </button>`;
  }).join("") + attribution;
  box.querySelectorAll(".candidate").forEach((btn) =>
    btn.addEventListener("click", () => applyCandidate(Number(btn.dataset.index)))
  );
}

function applyCandidate(index) {
  const c = (state.identifyCandidates || [])[index];
  if (!c) return;
  $("plant-species").value = c.scientific_name;
  if (c.common_names[0] && !$("plant-name").value.trim()) {
    $("plant-name").value = c.common_names[0];
  }
  toast("Applied: " + (c.common_names[0] || c.scientific_name));
}

async function identifyAll() {
  if (!confirm("Run Pl@ntNet on every plant photo and update the species?\n\nThis uses one API request per plant.")) return;
  toast("Identifying all plants… this can take a moment", 8000);
  try {
    const res = await api("/api/identify/missing?overwrite=true", { method: "POST" });
    const failed = res.results.filter((r) => r.error).length;
    toast(`Updated ${res.updated} plant(s)${failed ? `, ${failed} failed` : ""}`);
    loadAll();
  } catch (err) {
    toast("Failed: " + err.message);
  }
}

async function detectEntities(silent = false) {
  try {
    const s = await api("/api/ha/suggest");
    if (!s.state_count) {
      if (!silent) toast("Can't reach Home Assistant — no entities returned");
      return;
    }
    let filled = 0;
    const setIfEmpty = (id, val) => {
      if (val && !$(id).value.trim()) {
        $(id).value = val;
        filled++;
      }
    };
    setIfEmpty("set-weather", s.weather);
    setIfEmpty("set-outdoor", s.outdoor_temp);
    setIfEmpty("set-indoor", s.indoor_temp);
    setIfEmpty("set-rain", s.rain);
    if (!silent) toast(filled ? "Filled detected entities — review and Save" : "Nothing new to fill");
  } catch (err) {
    if (!silent) toast("Detect failed: " + err.message);
  }
}

let entityItems = null;

async function getEntityItems() {
  if (entityItems) return entityItems;
  const entities = await api("/api/ha/entities");
  entityItems = entities.map((e) => ({
    ...e,
    hay: `${e.entity_id} ${e.name || ""}`.toLowerCase(),
  }));
  return entityItems;
}

const isWeatherEnt = (e) => e.domain === "weather";
const isTempEnt = (e) => e.device_class === "temperature" || (!e.device_class && ["°C", "°F", "K"].includes(e.unit)) || /temp|temperature/.test(e.hay);
const isHumEnt = (e) => e.device_class === "humidity" || (!e.device_class && (e.unit === "%" || /humid|humidity|\bhum\b/.test(e.hay)));
const isRainEnt = (e) => String(e.device_class || "").startsWith("precipitation") || ["mm", "in"].includes(e.unit) || /rain|precip/.test(e.hay);

function fillSelect(id, items, selected) {
  const sel = $(id);
  if (!sel) return;
  let html =
    `<option value="">— none —</option>` +
    items.map((it) => `<option value="${escapeHTML(it.value)}">${escapeHTML(it.label)}</option>`).join("");
  if (selected && !items.some((it) => it.value === selected)) {
    html += `<option value="${escapeHTML(selected)}">${escapeHTML(selected)} (not in HA)</option>`;
  }
  sel.innerHTML = html;
  sel.value = selected || "";
}

async function loadEntityPickers(settings) {
  let items = [];
  let error = "";
  try {
    items = await getEntityItems();
  } catch (err) {
    error = err.message;
  }
  const pick = (pred) => items.filter(pred).map((e) => ({ value: e.entity_id, label: e.name || e.entity_id }));
  fillSelect("set-weather", pick(isWeatherEnt), settings?.ha_weather_entity);
  fillSelect("set-outdoor", pick(isTempEnt), settings?.ha_outdoor_temp_entity);
  fillSelect("set-indoor", pick(isTempEnt), settings?.ha_indoor_temp_entity);
  fillSelect("set-rain", pick(isRainEnt), settings?.ha_rain_entity);
  const tempN = items.filter(isTempEnt).length;
  const humN = items.filter(isHumEnt).length;
  $("settings-msg").textContent = error
    ? `Could not load entities: ${error}`
    : `${items.length} entities from HA · ${tempN} temperature · ${humN} humidity`;
}

async function openSettings() {
  try {
    const s = await api("/api/settings");
    await loadEntityPickers(s);
    $("set-notify-time").value = s.notify_time || "08:00";
    $("set-timezone").value = s.timezone || "";
    $("set-fert-months").value = (s.fertilize_months || []).join(", ");
    $("set-notify-services").value = (s.notify_services || []).join(", ");
    $("set-email-to").value = (s.email_to || []).join(", ");
    $("set-weather").value = s.ha_weather_entity || "";
    $("set-outdoor").value = s.ha_outdoor_temp_entity || "";
    $("set-indoor").value = s.ha_indoor_temp_entity || "";
    $("set-rain").value = s.ha_rain_entity || "";
    $("set-plantnet-key").value = s.plantnet_api_key || "";
    $("set-plantnet-project").value = s.plantnet_project || "all";
    $("set-plantnet-lang").value = s.plantnet_lang || "en";
    $("set-ntfy-topic").value = s.ntfy_topic || "";
    $("set-ntfy-server").value = s.ntfy_server || "";
    $("set-wa-phone").value = s.whatsapp_phone || "";
    $("set-wa-apikey").value = s.whatsapp_apikey || "";
    $("settings-modal").classList.remove("hidden");
    if (!$("set-weather").value && !$("set-outdoor").value && !$("set-indoor").value) {
      detectEntities(true);
    }
  } catch (err) {
    toast("Could not open settings: " + err.message);
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const splitList = (v) => v.split(",").map((s) => s.trim()).filter(Boolean);
  const payload = {
    notify_time: $("set-notify-time").value,
    timezone: $("set-timezone").value.trim(),
    fertilize_months: splitList($("set-fert-months").value).map(Number).filter((n) => n >= 1 && n <= 12),
    notify_services: splitList($("set-notify-services").value),
    email_to: splitList($("set-email-to").value),
    ha_weather_entity: $("set-weather").value.trim(),
    ha_outdoor_temp_entity: $("set-outdoor").value.trim(),
    ha_indoor_temp_entity: $("set-indoor").value.trim(),
    ha_rain_entity: $("set-rain").value.trim(),
    plantnet_api_key: $("set-plantnet-key").value.trim(),
    plantnet_project: $("set-plantnet-project").value.trim() || "all",
    plantnet_lang: $("set-plantnet-lang").value.trim() || "en",
    ntfy_topic: $("set-ntfy-topic").value.trim(),
    ntfy_server: $("set-ntfy-server").value.trim() || "https://ntfy.sh",
    whatsapp_phone: $("set-wa-phone").value.trim(),
    whatsapp_apikey: $("set-wa-apikey").value.trim(),
  };
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
    $("settings-msg").textContent = "Saved.";
    loadAll();
  } catch (err) {
    $("settings-msg").textContent = "Failed: " + err.message;
  }
}

async function testNotification() {
  $("settings-msg").textContent = "Sending…";
  try {
    const result = await api("/api/notify/test", { method: "POST" });
    $("settings-msg").textContent = `Sent. HA: ${result.ha.length}, email: ${result.email ? "yes" : "no"}`;
  } catch (err) {
    $("settings-msg").textContent = "Failed: " + err.message;
  }
}

function init() {
  $("btn-add").addEventListener("click", () => openPlantModal());
  $("btn-settings").addEventListener("click", openSettings);
  $("btn-identify").addEventListener("click", identifyPlant);
  $("btn-identify-all").addEventListener("click", identifyAll);
  $("btn-detect").addEventListener("click", () => detectEntities(false));
  $("plant-room").addEventListener("change", renderRoomSensors);
  $("plant-form").addEventListener("submit", savePlant);
  $("settings-form").addEventListener("submit", saveSettings);
  $("btn-test").addEventListener("click", testNotification);
  $("plant-photo").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    state.editingPhotoFile = file;
    $("photo-preview").src = URL.createObjectURL(file);
  });
  document.querySelectorAll("[data-close]").forEach((btn) =>
    btn.addEventListener("click", (e) => e.target.closest(".modal").classList.add("hidden"))
  );
  document.querySelectorAll(".modal").forEach((modal) =>
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.add("hidden");
    })
  );
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".modal:not(.hidden)").forEach((modal) => modal.classList.add("hidden"));
  });
  document.querySelectorAll(".filters button").forEach((btn) =>
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filters button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.filter = btn.dataset.filter;
      renderPlants();
    })
  );
  loadAll();
  setInterval(loadAll, 5 * 60 * 1000);
}

document.addEventListener("DOMContentLoaded", init);
