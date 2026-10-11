# Development Log — Home Plants app

A recovery log for this project. It captures what was decided, what was built,
what is deployed, what is still open, and how to pick the work back up. For full
usage docs see [`README.md`](./README.md).

---

## 1. The idea

A small self-hosted web app that keeps a "base" of all the houseplants in the
home (each with a photo), reminds you when to water them, lets you mark a task
done, adjusts watering frequency from Home Assistant weather/temperature, and
lets you receive push notifications.

The user already had 12 plant photos uploaded into
`/path/to/Plants project/` (originals named
`PXL_20261011_*.MP.jpg`).

---

## 2. Key decisions (from the initial Q&A)

| Question | Decision |
| --- | --- |
| Architecture | **Self-hosted web app + Home Assistant REST API** (not an HA-only setup) |
| Notifications | **HA mobile app push** (and Telegram/email hooks were kept available) |
| Hosting | **Same device as Home Assistant** (Raspberry Pi on HA OS/Supervised) |
| Tech stack | Backend **Python / FastAPI**; frontend plain **HTML/CSS/vanilla JS**; storage **SQLite** |
| Plant ID | Later decided to use the **Pl@ntNet API** for species recognition |
| Deploy | **Local Home Assistant add-on**, uploaded over SSH via a deploy script |

Naming: the project folder is `plants-app`; the add-on is "Home Plants" with
slug `plants` → full slug **`local_plants`**.

---

## 3. What was built

### Backend (`app/`)

| File | Responsibility |
| --- | --- |
| `main.py` | FastAPI app, lifespan (restore data → init DB → seed → start scheduler), static/photo mounts |
| `config.py` | Environment-based settings (dataclass) |
| `models.py` | SQLAlchemy models (`Plant`, `WateringEvent`, `Room`, `Setting`, `Reading`) + lightweight `ALTER TABLE` migration |
| `schemas.py` | Pydantic request/response models |
| `store.py` | DB-backed settings that override env vars (`get_value`/`set_value`) |
| `ha_client.py` | Home Assistant REST client (states + `notify.*` service calls) |
| `watering.py` | Watering-interval weather adjustment + `compute_fertilize` + status override |
| `environment.py` | Resolves a plant's env, merging per-room temp/humidity sensors |
| `plantnet.py` | Pl@ntNet identification client |
| `notifications.py` | Message building + dispatch (HA notify, ntfy, WhatsApp, email) |
| `scheduler.py` | APScheduler jobs: daily check + 30-min env refresh |
| `bootstrap.py` | First-run seeding from bundled photos, and restore-from-bundled-DB |
| `routers/plants.py` | Plant CRUD, water/undo/sick/healthy/fertilize actions, history, photo upload |
| `routers/rooms.py` | Room CRUD (per-room temp/humidity sensors) |
| `routers/identify.py` | Pl@ntNet identify (upload / stored photo / bulk) |
| `routers/system.py` | weather, status, settings, entities/suggest/notify-services, test notification |
| `static/` | Single-page UI (`index.html`, `app.js`, `style.css`, `favicon.png`, `placeholder.svg`) |

### Features

- Plant library with photo, species, room, notes, indoor/outdoor placement.
- Watering schedule with **weather/temperature-adjusted** intervals and a visible reason.
- Status badges: Overdue / Water today / Due soon / Happy; filter tabs (Needs water / Sick / All / Happy).
- "Mark watered" + watering history.
- **Sick watch** — mark sick (with symptom note), get a **daily** check-up reminder until marked healthy.
- **Fertilizing reminders** — per-plant interval, only active in configured growing months.
- **Pl@ntNet identification** — per-plant and bulk.
- **Manual override** — force a plant's status, or correct its last-watered date.
- **Per-room sensors** — temperature + humidity sensors per room.
- **Undo** for accidental waterings.
- **Notifications** — HA push, ntfy, WhatsApp (CallMeBot), Telegram, email.
- **Sidebar panel** — embeds in the Home Assistant sidebar via ingress.
- **Simulator** — mock Home Assistant for testing without real HA.

---

## 4. Watering algorithm (design)

```
effective_interval = clamp(base_interval * factor, 1 day, base_interval * 1.6)
next_due           = last_watered + effective_interval
```

Factor starts at 1.0 and is built from:

| Condition | Effect |
| --- | --- |
| Temperature (indoor temp for indoor plants, outdoor for outdoor) | `1 - (temp − 21°C) × 0.03`, clamped `0.6…1.5` |
| Humidity ≥ 70% | × 1.1 |
| Humidity ≤ 35% | × 0.92 |
| Outdoor + rainy/snowy | × 1.25 |
| Outdoor + sunny/windy | × 0.9 |
| Outdoor + ≥ 2 mm recent rain | × 1.3 |

Final factor clamped `0.5…1.6`. Status: `<0` overdue, `<1` due today, `≤2` soon, else happy.
Never-watered plants show as Overdue so they aren't forgotten.

**Fertilizing** uses the same kind of computation but only between the configured
months (`FERTILIZE_MONTHS`, default `3,4,5,6,7,8` = northern spring/summer); off-season
shows "feeding off-season". Baseline for first feed is the plant's `created_at`.

---

## 5. Plant identification (Pl@ntNet)

- API: `POST https://my-api.plantnet.org/v2/identify/{project}?api-key=…`, multipart
  `images` + `organs` (`auto`/`leaf`/`flower`/`fruit`/`bark`). Free tier ~500 req/day.
- The API key is configured in `.env` (gitignored), the app's settings DB, and the
  add-on options. **The committed `ha-addon/config.yaml` has it blanked** — do not
  paste the key into LOG/README or commit it.
- `httpx` request logging is silenced so the key never lands in logs.
- Identification is **display-only**; it never changes a watering schedule.

**Identified species** (bulk run, Oct 2026). The user later renamed a couple of
plants to the common names Pl@ntNet returned:

| Photo / plant | Pl@ntNet species | Score |
| --- | --- | --- |
| Peace Lily | *Spathiphyllum floribundum* | 53% |
| Lipstick Plant | *Aeschynanthus radicans* | 80% |
| White Heather (×2) | *Calluna vulgaris* | 47/45% |
| Golden Pothos | *Epipremnum aureum* | 69% |
| Lavender (→ renamed **Curry plant**) | *Helichrysum italicum* | 14% (low) |
| Pink Heather | *Calluna vulgaris* | 86% |
| Dusty Miller | *Jacobaea maritima* | 42% |
| Ornamental Shrub (→ renamed **Winter savory**) | *Satureja montana* | 48% (low) |
| Coleus | *Coleus decurrens* | 58% |
| Nerve Plant | *Fittonia albivenis* | 82% |
| Alocasia | *Alocasia sanderiana* | 68% |

Note: the two `white-heather*.jpg` photos appear to be the **same plant** from
two angles (flagged, user kept both).

Low-confidence ones worth re-checking: Curry plant (use organ = **Flower**),
Winter savory, Dusty Miller.

---

## 6. Current plant data (as edited by the user)

The user filled in locations in the app. Current state (from the running DB):

| Plant | Placement | Room |
| --- | --- | --- |
| Peace Lily | indoor | Bathroom |
| Alocasia | indoor | Living Room |
| Golden Pothos | indoor | Living Room |
| Lipstick Plant | indoor | Living Room |
| Coleus | indoor | Kitchen |
| Curry plant | outdoor | Kitchen |
| Nerve Plant | indoor | Kitchen |
| Dusty Miller | outdoor | Balcon |
| Winter savory | outdoor | Balcon |
| Pink Heather | outdoor | Balcon |
| White Heather (×2) | outdoor | Balcon |

(The Mac preview's `data/plants.db` holds these edits and is bundled at deploy
time so the Pi starts with them.)

---

## 7. Simulation (mock Home Assistant)

- `sim/mock_ha.py` — a small FastAPI app implementing the HA endpoints the app
  uses (`GET /api/states/{entity}`, `POST /api/services/{domain}/{service}` for
  notify capture) plus a control panel at `/`.
- `sim/run-sim.sh` — starts the mock on `:8123` and the app on `:8099` pointed at it.
- Panel presets: Hot & dry / Cool & rainy / Cold / Mild. The plants app is embedded
  next to the controls; changing weather updates each card's interval + reason.
- Verified scenario effect (base 7/8/14/7d): Peace Lily 7.0→5.3→8.2→7.8d etc.

---

## 8. Deployment (Home Assistant add-on)

- `ha-addon/` is the add-on build context: `config.yaml`, `Dockerfile`, `run.sh`,
  plus a copy of `app/`, `seed_data/`, `requirements.txt` (regenerated by `deploy.sh`).
- `run.sh` reads `/data/options.json` (HA add-on options) and exports env vars,
  uses `HA_URL=http://supervisor/core` + `SUPERVISOR_TOKEN` (no long-lived token
  needed at runtime). `config.yaml` sets `homeassistant_api: true`.
- `deploy.sh` + `.deploy.env`: copies `ha-addon/` to `<HA_HOST>:/addons/plants`
  over SSH, optionally bundles the current `data/` (DB + photos) via `CARRY_DATA=1`,
  then optionally reloads the store and rebuilds/restarts via the HA API.
- `bootstrap.prepare_data_dir()` restores the bundled DB + photos on first `/data` start,
  so the Pi comes up with the Mac's exact plants/rooms/settings.

### Issues hit and fixed during deployment

1. **`mkdir /addons/plants: Permission denied`** — SSH user `hassio` wasn't root.
    - Fix: `deploy.sh` auto-detects UID and uses `sudo` (incl. `--rsync-path="sudo rsync"`)
      or prints exact instructions (set SSH add-on `username: root`, or `REMOTE_SUDO=1`).
2. **HA API returned 401 on reload/rebuild** — token problem.
    - Diagnosed with `curl -H "Authorization: Bearer $HA_TOKEN" "$HA_API_URL/api/"`.
    - Now returns `200 {"message":"API running."}` → token valid. The script now runs
      this auth check itself and reports 401/403/000 meaning clearly.
3. **Install extremely slow on the Pi** — `uvicorn[standard]` pulls `uvloop` + `httptools`,
   which have **no ARM wheels** → pip compiles from source (fails on 32-bit, slow on 64-bit).
    - Fix: `requirements.txt` now uses plain `uvicorn` (no extras). All deps then install
      from wheels on both aarch64 and armv7 (`pydantic-core` has wheels; `sqlalchemy`
      has a pure-python wheel and skips `greenlet` on armv7; `uvloop`/`httptools` removed).
    - Add-on bumped to `1.0.1`; `deploy.sh` prints device architecture.

### Environment reality

- Mac preview server had been bound to `0.0.0.0:8099`, reachable on the LAN at
  `http://<lan-ip>:8099` (and via Tailscale at `<tailscale-ip>`).
- The HA Pi also has an SSH add-on; the user connected as `<ssh-user>@<ha-host>:22`
  and then (with sudo/root) uploaded successfully.

---

### Post-review fixes (add-on v1.0.2)

Requested by the user after first look at the add-on:

1. **No sidebar panel** → added **ingress** support (`ingress: true`,
   `ingress_port: 8099`, `panel_icon: mdi:flower`, `panel_title: Plants`) so the
   app embeds in the HA sidebar. Frontend switched to **relative URLs** (an
   `asset()` helper computes the base from `location.pathname`) and a small
   middleware strips an `/api/hassio_ingress/<token>/` prefix so routes match.
2. **Add-on icon** → generated `ha-addon/icon.png` (128×128) and `logo.png` (leaf),
   plus `app/static/favicon.png`.
3. **No undo for watering** → added `POST /api/plants/{id}/water/undo` (deletes the
   latest `WateringEvent`, restores the previous `last_watered` or `None`) and a
   toast **Undo** button (toast now supports an action).
4. **No entity autocomplete** → added `GET /api/ha/entities` (from HA `/api/states`)
   and `<datalist>`-backed autocomplete on the Settings entity fields, filtered by
   domain/device_class/unit.

Add-on version bumped to **1.0.2**; `deploy.sh` refreshes the build context.

### Second round of fixes (add-on v1.0.3 / v1.0.4)

After installing on the Pi, the user reported: Settings did nothing, sensors
couldn't be added, and watering had no undo.

- **Root cause (Settings dead):** `GET /api/settings` returned **HTTP 500**.
  `store.get_value()` (changed earlier to prefer env values) treated an empty
  list env value as "unset" and returned `None`, so `notify_services`/`email_to`
  became `None` and `SettingsOut` validation failed. Fixed the precedence check
  to only fall back when the env value is genuinely `None`
  (`if env_value is not None: return env_value`). Verified 200 in both the sim and
  an empty-env instance. This is why the Settings button appeared to do nothing.
- **Misleading badge:** `ha_reachable` was `false` whenever no entities were
  configured. `/api/status` now reports real connectivity via `ha_state_count`,
  and the UI shows green "HA connected" / amber "Set sensors" / red "HA offline".
- **Auto-detect entities:** added `GET /api/ha/suggest` (weather = first
  `weather.*`; temp/rain by device_class/unit + name heuristics) and a
  "🪄 Auto-detect entities" button; Settings auto-fills empty fields on open.
- **Cache-busting:** added a `no-store` middleware and `?v=` query on static
  assets, because a stale cached `app.js` after an add-on update made the UI
  misbehave (e.g. absolute URLs under ingress).
- **Deploy troubleshooting learned:** local add-ons show a **Rebuild** button;
  a store reload (⋮ → Check for updates) is needed for HA to re-read
  `/addons` and offer an Update. The user's long-lived token was valid for
  `/api/` but **not admin**, so the Supervisor proxy (`/api/hassio/...`) returned
  401 — `deploy.sh` now detects and reports this.
- Added `/api/status` fields `ha_state_count` and `entities_configured`, plus
  `GET /api/ha/suggest`.

Add-on versions: **1.0.3** (auto-detect + badge) → **1.0.4** (settings 500 fix +
cache-busting).

### Third round — new features (add-on v1.0.5)

Requested by the user once the app was working:

1. **Manual plant status** — `Plant.status_override` (`""` = auto, `ok`/`due`/
   `overdue`/`soon`). `compute_watering` applies it and sets reason "manual
   override". The editor also got an editable **last watered** datetime
   (`PlantUpdate.last_watered`).
2. **Per-room sensors** — new `Room` model (`name`, `temp_entity`,
   `humidity_entity`) + `/api/rooms` CRUD. New `app/environment.py` (`collect` +
   `resolve`) merges a plant's room temp/humidity over the global env; used by
   both `routers/plants.py` and `/api/status`. Plants are matched to rooms by
   their `location` string. Verified: a room sensor of 34 °C changed a plant from
   7.0 → 4.3 days.
3. **Phone notifications** — `notifications.dispatch` now also sends to **ntfy**
   (`ntfy_topic`/`ntfy_server`) and **WhatsApp via CallMeBot**
   (`whatsapp_phone`/`whatsapp_apikey`), in addition to HA `notify.*` services and
   email. Added `GET /api/ha/notify-services` (from HA `/api/services`) to
   autocomplete the notify-service field. New settings/env: `NTFY_TOPIC`,
   `NTFY_SERVER`, `WHATSAPP_PHONE`, `WHATSAPP_APIKEY`.

UI: editor gained a Status select + Last-watered picker; Settings gained a
Push/WhatsApp section and a Rooms & sensors section (add/delete rooms with temp +
humidity entity pickers, names suggested in the plant Location field).

Simulator (`sim/mock_ha.py`) gained `/api/services` so the notify-service list can
be tested. Add-on version bumped to **1.0.5**.

**v1.0.6:** the humidity autocomplete was too strict — broadened all entity
filters to also match on the entity id / friendly name (`temp`, `hum`, `rain`),
and room→plant matching is now **case-insensitive/trimmed**
(`environment._norm`), since `location` and room names are free text.

**v1.0.7 / v1.0.8:** replaced `<datalist>` autocomplete with a custom dropdown and
then converted the sensor/room fields to real `<select>` dropdowns (reliable on
every browser):
- Settings entity fields (`set-weather/outdoor/indoor/rain`) are now `<select>`
  populated from HA: weather.*, all `device_class=temperature` sensors, and
  precipitation sensors. The saved value is kept as an "(not in HA)" option if
  it's ever missing.
- Rooms & sensors: the room, temperature and humidity fields are `<select>`s —
  room = **distinct plant Locations** (plus existing room names); temperature =
  all temperature sensors; humidity = all humidity sensors. The Rooms list shows
  plant rooms lacking sensors with a ＋ to configure, and saving upserts the room
  (PATCH if the name exists, else POST).

**v1.0.9:** added an on-screen diagnostic in Settings — the grey line now shows
`N entities from HA · X temperature · Y humidity` (or the load error) so empty
dropdowns can be diagnosed without the browser console. Removed a duplicate
auto-detect call and stopped clearing that message.

### Version control (git)

A git repository was initialised at `plants-app/` (branch `main`) and the work was
committed as **13 incremental, dependency-ordered commits**:
scaffold → core → HA/watering → rooms → notifications → Pl@ntNet → API/main →
UI → Docker → add-on → deploy → sim → docs.

- **Secret scrubbed:** the Pl@ntNet key was removed from `ha-addon/config.yaml`
  (a tracked file) before committing; it remains only in the gitignored `.env`
  and on the device. Verified absent from all git history
  (`git log -S <key>` finds nothing).
- **Ignored:** `.env`, `.deploy.env`, `data/`, `.venv/`, `__pycache__/`, and the
  generated add-on build copies (`ha-addon/app`, `ha-addon/seed_data`,
  `ha-addon/requirements.txt`).
- Because the repo had no prior history, each commit carries the **final** content
  of the files it introduces (no byte-perfect replay), so the history is a clean
  feature-by-feature progression rather than every intermediate edit.

---

## 9. Configuration reference

Runtime settings can come from environment **or** be overridden in the app's
Settings UI (persisted in the DB, DB wins). Key vars: `HA_URL`, `HA_TOKEN`,
`HA_WEATHER_ENTITY`, `HA_OUTDOOR_TEMP_ENTITY`, `HA_INDOOR_TEMP_ENTITY`,
`HA_RAIN_ENTITY`, `NOTIFY_SERVICES`, `EMAIL_TO`, `SMTP_*`, `NOTIFY_TIME`, `TZ`,
`FERTILIZE_MONTHS`, `PLANTNET_API_KEY`, `PLANTNET_PROJECT`, `PLANTNET_LANG`,
`PLANTS_DATA_DIR`, `HOST`, `PORT`. See `.env.example` and `README.md`.

---

## 10. Status — what works vs. what's open

**Working / verified**
- Full app + UI, weather-adjusted watering, sick watch, fertilizing, Pl@ntNet,
  manual status, per-room sensors, undo, simulator.
- Add-on deployed and running on the Pi (ingress sidebar panel, data carried over).
- `GET /api/settings` 500 fixed; Settings UI opens; git history committed (13 commits).

**Open / next steps**
1. **Entity dropdowns came back empty after v1.0.9, and rooms couldn't be added.**
   The app isn't receiving HA's entity list. Diagnose with the Settings grey
   diagnostic line (v1.0.9) and with `GET /api/ha/entities` +
   `/api/status` → `ha_state_count`:
   - `0` / `[]` → the add-on isn't reaching HA core (`homeassistant_api`/token).
   - non-zero → inspect the dropdown filters on the frontend.
2. **Configure sensors + notify service** from the app's **Settings** (the fields
   are dropdowns populated from HA): weather, outdoor/indoor temp, rain; add a
   room with its temp/humidity sensors; set the phone notify service. Then use
   **Send test**.
3. Optional: re-identify low-confidence plants (flower organ), verify the two
   White Heather entries, add SMTP email, rain-forecast-based delays.

---

## 11. Handy commands

```bash
# Run locally (Mac dev)
cd plants-app
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8099

# Simulation (mock HA + app pointed at it)
./sim/run-sim.sh

# Deploy to the Home Assistant Pi
cp .deploy.env.example .deploy.env   # fill HA_HOST / SSH / token
./deploy.sh                          # add --dry-run to preview, --no-reload to skip API

# HA token sanity check (won't print the token)
source .deploy.env
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $HA_TOKEN" "${HA_API_URL%/}/api/"

# Git
git log --oneline          # 13 incremental commits
```

Key files: `README.md` (docs), `LOG.md` (this file), `.env` (secrets, gitignored),
`.deploy.env` (deploy target, gitignored), `ha-addon/` (add-on), `sim/` (simulator),
`data/` (runtime DB + photos, gitignored).

---

## 12. Changelog (add-on versions)

Versions are the Home Assistant add-on `version` in `ha-addon/config.yaml`. The
app and add-on ship together, so each entry is the set of changes delivered in
that bump (1.0.0 is everything built up to the first deploy).

### 1.0.0 — Initial release
- Self-hosted **FastAPI + SQLite** app with a plain **HTML/CSS/JS** UI.
- **Plant library** with photos (12 bundled seed photos), species, room, notes,
  and indoor/outdoor placement.
- **Weather/temperature-adjusted watering** intervals with a visible reason;
  status badges (Overdue / Water today / Due soon / Happy) and filter tabs.
- **Mark watered** + watering history.
- **Sick watch** — mark sick (with a note) and get a daily check-up reminder.
- **Seasonal fertilizing reminders** (only during configured growing months).
- **Pl@ntNet identification** (per-plant and bulk).
- Notifications via HA `notify.*` services + optional **SMTP email**; daily
  **APScheduler** check + 30-min environment refresh.
- **Docker** packaging and a local **Home Assistant add-on** (`config.yaml`,
  `Dockerfile`, `run.sh`).
- **`deploy.sh` + `.deploy.env`** (SSH upload, optional data carry-over) and
  first-run **seeding / restore-from-bundle** (`bootstrap.py`).
- **Mock Home Assistant simulator** (`sim/`) for local testing.

### 1.0.1 — Raspberry Pi build reliability
- `requirements.txt`: `uvicorn[standard]` → plain **`uvicorn`** (drops `uvloop`,
  `httptools`, `watchfiles`, which have no ARM wheels and forced source builds /
  failures on the Pi). All deps now install from pure-Python or ARM wheels.
- `deploy.sh` prints the **device architecture** and warns on 32-bit ARM.

### 1.0.2 — Add-on polish
- **Ingress** support → a **Plants panel in the Home Assistant sidebar**
  (`ingress`, `ingress_port`, `panel_icon`, `panel_title`); frontend switched to
  **relative URLs**, plus a middleware that strips an
  `/api/hassio_ingress/<token>/` prefix.
- **Add-on icon** (`icon.png`, `logo.png`) and a browser `favicon.png`.
- **Watering undo** — `POST /api/plants/{id}/water/undo` and a toast **Undo** button.
- **Entity autocomplete** via `GET /api/ha/entities` (datalist-backed).

### 1.0.3 — Diagnostics & auto-detect
- `GET /api/ha/suggest` + a **"Auto-detect entities"** button; Settings pre-fills
  empty fields on open.
- `/api/status` gained `ha_state_count` and `entities_configured`; the badge now
  distinguishes **HA connected** / **Set sensors** / **HA offline**.

### 1.0.4 — Settings crash fix & cache-busting
- Fixed **`GET /api/settings` HTTP 500** (empty `notify_services`/`email_to` were
  returned as `None`); corrected `store.get_value` env precedence.
- Added a **`no-store`** middleware and `?v=` query on static assets so a stale
  `app.js` can't break the UI after an update.

### 1.0.5 — Manual control, rooms, notifications
- **Manual plant status override** (`status_override`) and an editable
  **last watered** date.
- **Per-room sensors**: `Room` model + `/api/rooms` CRUD; `app/environment.py`
  merges a plant's room temp/humidity; plants matched to rooms by `location`.
- **Notifications**: added **ntfy** and **WhatsApp (CallMeBot)** channels plus
  `GET /api/ha/notify-services`; new settings `ntfy_*`, `whatsapp_*`.
- UI: Status select + last-watered picker; Push/WhatsApp section; Rooms & sensors
  section.

### 1.0.6 — Robust matching
- Broadened entity filters to also match on entity id / friendly name
  (`temp`, `hum`, `rain`).
- Room→plant matching is now **case-insensitive / trimmed** (`environment._norm`).

### 1.0.7 — Reliable autocomplete
- Replaced `<datalist>` with a **custom dropdown** we control (works on every
  browser, Safari included).

### 1.0.8 — Dropdowns instead of typing
- Converted the sensor/room fields to real **`<select>`** dropdowns:
  - weather = all `weather.*`; outdoor/indoor temp = all temperature sensors;
    rain = precipitation sensors;
  - room = **distinct plant Locations** (+ existing room names); room temp = all
    temperature sensors; room humidity = all humidity sensors.
- Saving a room **upserts** (PATCH if the name exists, else POST).

### 1.0.9 — On-screen diagnostics
- Settings shows a grey diagnostic line (`N entities from HA · X temperature ·
  Y humidity`, or the load error) so empty dropdowns can be debugged without the
  browser console.
- Removed a duplicate auto-detect call and stopped clearing that message.

### 1.0.10 — Rooms come from Home Assistant
Replaced the app's own `Room` table / Settings rooms UI with HA **areas**:
- `ha_client.HAClient.get_rooms()` reads the **area / device / entity
  registries** over the **HA WebSocket API** (`websockets` dep added) and returns
  each room with its temperature/humidity sensors (entity linked to the area
  directly or via its device). Cached ~60 s. New `GET /api/ha/rooms`.
- `Plant` gained `room_id`, `room_name`, `temp_entity`, `humidity_entity`;
  `location` is kept in sync with the room name for display/notifications.
- The **plant editor** now picks a Room from a dropdown; the app then shows the
  room's sensors: one of each → names shown; several → choose from dropdowns;
  none → warning (still savable). `environment.resolve` uses the plant's chosen
  sensors (or the room's only sensor) instead of matching free-text locations.
- Plants whose room has no temperature **or** humidity sensor (or no room) show
  a **⚠️ badge** on their card (`PlantOut.sensor_warning`).
- Removed `app/routers/rooms.py`, the `Room` model and the Settings
  "Rooms & sensors" section. Simulator (`sim/mock_ha.py`) now serves a minimal
  HA **WebSocket** endpoint plus sample areas/sensors (Living Room with two temp
  + two humidity sensors, Bedroom with one, Bathroom with none) for testing all
  three cases.
- Filter room sensors by `device_class` first (only fall back to the unit when
  it is absent) so a **battery** (`unit "%"`, `device_class "battery"`) is not
  mistaken for a humidity sensor.

### 1.0.11 — Card & modal interactions
- Removed the ✎ edit button from plant cards; the **whole card** (photo + text)
  is now clickable and opens the editor. The action buttons (water / sick / feed)
  stop propagation so they still behave on their own.
- The plant editor (and Settings) now close on **Esc** or by clicking **outside**
  the card.
- Bumped static asset `?v=` query to 1.0.11 so browsers pick up the new files.

### 1.1.0 — Simpler notifications & working email
- **Removed the ntfy and WhatsApp (CallMeBot) channels** (`config`, `store`,
  `schemas`, `notifications`, Settings UI). Delivery is now Home Assistant
  mobile-app push and/or email.
- **Notify service** is a dropdown populated from `GET /api/ha/notify-services`,
  filtered to `notify.mobile_app_*` (no more typing service names).
- **Reminder months** is a multi-select of the twelve months of the year instead
  of a comma-separated text field.
- **Email (SMTP) fixed and configurable in-app.** `smtp_host/port/user/password/
  from/tls` are now stored settings (env fallback) with fields in Settings, and
  `_send_email` reads them from the DB. Gmail works with an **app password**
  (`smtp.gmail.com:587`, STARTTLS). Port 465 uses implicit TLS.
- **Send test** now reports the actual SMTP result/error (`email: no
  (<reason>)`) instead of a bare yes/no, so failures are diagnosable.
- Add-on options/schema gained `smtp_*` (and `run.sh` exports them); README
  documents the Gmail app-password setup. Version bumped to **1.1.0**.
