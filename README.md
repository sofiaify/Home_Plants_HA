# Home Plants 🌿

A small self-hosted web app to keep track of the houseplants in your home, remind
you when to water them, and automatically adjust how often each plant needs water
based on the weather and temperature reported by Home Assistant.

It ships with your 12 plant photos and sensible default watering intervals, and
can run either as a **Home Assistant add-on** (recommended on HA OS/Supervised),
a **Docker container**, or directly with **Python** for development.

---

## Features

- **Plant library** — a photo, name, species, room/location and notes for every plant.
- **Pl@ntNet identification** — identify a species from a photo (either a new
  upload or the plant's stored photo) and pick from ranked candidates, or run
  identification across every plant in one click.
- **Watering schedule** — each plant has a base interval (e.g. "every 7 days").
- **Sick watch** — mark a plant as sick and get a **daily** check-up reminder
  (with optional symptom notes) until you mark it healthy again.
- **Fertilizing reminders** — a per-plant feeding cadence that only fires during
  spring/summer (configurable months), with a "mark as fed" action.
- **Weather-aware adjustments** — the effective interval is recalculated from the
  indoor/outdoor temperature, humidity, weather condition and (optionally) rain.
- **Reminders** — a daily check pushes a notification listing every plant that is
  due or overdue. Delivered through the Home Assistant notify service
  (mobile app, Telegram, etc.) and/or email (SMTP).
- **Mark as watered** — one tap records the event, reschedules the plant, and
  keeps a full watering history.
- **Undo** — accidental watering? The confirmation toast (and a `/water/undo`
  endpoint) reverses the last watering.
- **Manual control** — override a plant's status (Happy / Needs water / Overdue)
  or correct its *last watered* date from the editor.
- **Per-room sensors** — define rooms with their own temperature and humidity
  sensors; indoor plants use their room's sensors for scheduling.
- **Notifications** — Home Assistant push (`notify.mobile_app_*`), **ntfy**,
  **WhatsApp** (CallMeBot), Telegram or email.
- **Home Assistant sidebar panel** — installed as an add-on with **ingress**, the
  app appears as a **Plants** panel in the HA sidebar (leaf icon).
- **Entity autocomplete** — the Settings screen suggests matching weather /
  temperature / rain entities from Home Assistant as you type.
- **Status at a glance** — Overdue / Water today / Due soon / Happy badges.
- **No external services** — everything (including the database and photos) stays
  on your own device.

---

## Quick start

### 1. Home Assistant add-on (HA OS / Supervised)

**Scripted deploy** (from your computer, over SSH):

```bash
cp .deploy.env.example .deploy.env   # set HA_HOST / SSH user+port
./deploy.sh                          # copies ha-addon/ to <HA_HOST>:/addons/plants
```

`deploy.sh` refreshes the add-on build context from `app/`, copies it to the
device, and (optionally, if you set `HA_API_URL` + `HA_TOKEN`) asks Home Assistant
to reload the store and rebuild/restart the add-on. Nothing is uploaded that the
add-on doesn't need. Use `./deploy.sh --dry-run` to preview.

**Then, in Home Assistant:**

1. **Settings → Add-ons → Add-on Store → ⋮ → Check for updates**, then open
   **Local add-ons → Home Plants**.
2. **Install** (first time) or **Update**, fill in the Configuration tab (entity
   IDs, notify service, timezone), and **Start**.
3. Open `http://<your-ha-host>:8099`, or use the **Plants** entry that the add-on
   adds to the Home Assistant sidebar (via ingress).

> Tip: entity IDs are easier to set from inside the app's **Settings** screen,
> which autocompletes entities live from Home Assistant — the add-on's own
> Configuration tab does not offer autocomplete.

<details>
<summary>Manual alternative (Samba / File editor)</summary>

Copy the `ha-addon/` folder into Home Assistant's `/addons` share, then follow
steps 1–3 above. `ha-addon/` must contain `app/`, `seed_data/` and
`requirements.txt`; `deploy.sh` produces that layout automatically.
</details>


When running as an add-on the app talks to Home Assistant through the Supervisor
proxy automatically — **no long-lived access token is required** (`SUPERVISOR_TOKEN`
is used transparently).

### 2. Docker

```bash
cp .env.example .env     # then edit it
docker compose up -d --build
```

Open `http://localhost:8099`. Data is stored in `./data` and mounted into the
container.

### 3. Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env     # point HA_URL / HA_TOKEN at your instance
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8099 --reload
```

### 4. Simulation (no Home Assistant required)

To try the weather integration without a real Home Assistant, a mock HA lives in
`sim/mock_ha.py`. It implements the same REST endpoints the app calls, plus a
control panel where you can drag temperature/humidity/rain, switch the weather
condition, and see the app react (it's embedded next to the controls).

```bash
./sim/run-sim.sh
# mock HA control panel -> http://localhost:8123
# plants app            -> http://localhost:8099
```

`run-sim.sh` starts the mock on `:8123` and launches the app pointed at it
(`HA_URL=http://127.0.0.1:8123`, `HA_TOKEN=sim`, and the four entity IDs). Click
a preset (**Hot & dry**, **Cool & rainy**, …) and apply to watch each plant's
effective watering interval and reason change. Notifications are captured and
listed on the panel too.

---

## Configuration

Configuration has two layers, and the **Settings screen in the UI overrides the
environment variables** (values chosen in the UI are persisted in the database).

| Environment variable     | Setting in UI            | Purpose                                                        |
| ------------------------ | ------------------------ | -------------------------------------------------------------- |
| `HA_URL`                 | –                        | Home Assistant base URL (auto-set to the Supervisor in an add-on) |
| `HA_TOKEN`               | –                        | Long-lived access token (not needed as an add-on)              |
| `HA_WEATHER_ENTITY`      | Weather entity           | e.g. `weather.home` — condition, humidity and forecast         |
| `HA_OUTDOOR_TEMP_ENTITY` | Outdoor temperature      | e.g. `sensor.outdoor_temperature`                              |
| `HA_INDOOR_TEMP_ENTITY`  | Indoor temperature       | Temperature used for indoor plants                             |
| `HA_RAIN_ENTITY`         | Rain entity              | Optional rain gauge in mm                                      |
| `NOTIFY_SERVICES`        | Notify services          | Comma separated, e.g. `notify.mobile_app_phone, notify.telegram` |
| `NOTIFY_TIME`            | Daily reminder time      | `HH:MM` local time for the daily check                         |
| `FERTILIZE_MONTHS`       | Fertilize months         | Months (1-12) when feeding reminders are active, e.g. `3,4,5,6,7,8` |
| `TZ`                     | Timezone                 | e.g. `Europe/Madrid` — used for scheduling and display         |
| `EMAIL_TO`               | Email recipients         | Comma separated addresses for the email fallback               |
| `SMTP_HOST` … `SMTP_TLS` | –                        | SMTP server used for email notifications                       |
| `PLANTNET_API_KEY`       | Pl@ntNet API key         | Key from [my.plantnet.org](https://my.plantnet.org) — enables identification |
| `PLANTNET_PROJECT`       | Pl@ntNet project         | Flora to use, e.g. `all` or `k-southwestern-europe`           |
| `PLANTNET_LANG`          | Pl@ntNet language        | Language code for common names, e.g. `en`, `es`               |
| `PLANTS_DATA_DIR`        | –                        | Where the DB and photos live (defaults to `./data`)            |
| `HOST` / `PORT`          | –                        | Bind address/port (default `0.0.0.0:8099`)                     |

Find entity IDs in Home Assistant under **Developer Tools → States**.

---

## How watering frequency is calculated

Each plant has a **base interval** in days. On every request the app computes an
**effective interval** by scaling the base with an adjustment factor derived from
the current environment, then derives the next-due date from the last watering.

```
effective_interval = clamp(base * factor, 1 day, base * 1.6)
next_due           = last_watered + effective_interval
```

The factor starts at `1.0` and is built up from these rules:

| Condition                                             | Effect on factor |
| ----------------------------------------------------- | ---------------- |
| Temperature (indoor temp for indoor, outdoor for outdoor) | `1 - (temp − 21°C) * 0.03`, clamped to `0.6 … 1.5` |
| Humidity ≥ 70 %                                       | × 1.1            |
| Humidity ≤ 35 %                                       | × 0.92           |
| Outdoor + rainy / snowy condition                     | × 1.25           |
| Outdoor + sunny / windy condition                     | × 0.9            |
| Outdoor + ≥ 2 mm recent rain                          | × 1.3            |

The final factor is clamped to `0.5 … 1.6`. So a warm, dry day shortens the
interval (water sooner), while cool, humid or rainy weather lengthens it.

**Status thresholds** (based on days until due):

- `< 0` → **Overdue**
- `< 1` → **Water today**
- `≤ 2` → **Due soon**
- otherwise → **Happy**

A plant that has never been watered is treated as **Overdue** so it is not
forgotten. Each plant's card shows the reason contributing the most to the
adjustment (e.g. *"recent rain (4 mm)"*).

---

## Plant identification with Pl@ntNet

Species identification is powered by the [Pl@ntNet API](https://my.plantnet.org).
You need a free API key:

1. Create an account at <https://my.plantnet.org> and generate an API key.
2. Enter it in the app under **Settings → Pl@ntNet identification** (or set
   `PLANTNET_API_KEY`). Optionally choose a **project/flora** (default `all`) and
   a **language** for common names.

Then:

- **Per plant:** open a plant, choose which organ the photo shows (or leave
  *Auto-detect organ*), click **Identify**, and click a candidate to fill in the
  species (and the name, if it was empty). Works with a freshly chosen photo or
  the plant's already-stored photo.
- **All plants at once:** click **Identify all** in the header. This runs one
  request per plant and updates each plant's species. It asks for confirmation
  because it consumes API quota.

Notes:

- Pl@ntNet accepts **JPEG/PNG** images, up to **5 images** and **50 MB** per
  request (this app sends one image per request).
- The free tier has a **daily request quota**; the remaining allowance is shown
  under the results.
- Results should be reviewed — the top candidate is a best guess, and confidence
  scores are shown as percentages.
- Identification results are used for display/record only; the **watering
  interval still comes from the base interval you set per plant**.

## Reminders & notifications

- A scheduler job runs **once a day** at the configured time (in your timezone)
  and notifies for every active plant that is *Overdue* or *Water today*.
- Environment readings are refreshed every **30 minutes** so the schedules used
  throughout the day stay current.
- Delivery uses any Home Assistant `notify.*` services you list, plus optional
  email. Use the **Send test** button in Settings to verify your setup.

### Choosing a notification channel

Set any of these in **Settings**; the daily check sends to every configured channel.

- **Home Assistant mobile app (push):** install the HA companion app, then put its
  service (e.g. `notify.mobile_app_pixel`) in *Notify services*. The Settings field
  autocompletes the `notify.*` services your instance exposes.
- **ntfy (push, no account):** install the [ntfy](https://ntfy.sh) app, subscribe
  to a topic, and set that topic in *ntfy topic* (`ntfy server` defaults to
  `https://ntfy.sh`; point it at your own server if you self-host).
- **WhatsApp via CallMeBot (unofficial):** send
  `I allow callmebot to send me messages` on WhatsApp to `+34 644 51 95 23`, then
  set the returned API key and your number (with country code) in *WhatsApp* fields.
  You can also use Twilio's WhatsApp through a HA `notify.*` service instead.
- **Telegram:** add the Telegram integration in HA and use `notify.telegram`.
- **Email:** fill the `SMTP_*` variables and `EMAIL_TO`.

Use the **Send test** button to confirm delivery.

### Rooms & sensors

Open **Settings → Rooms & sensors** to add a room with its temperature and
humidity sensors (autocompleted from Home Assistant). Then set a plant's
**Location** to the room name (the editor suggests existing room names). Indoor
plants use their room's sensors; if a room has no sensors, the global indoor
temperature and weather humidity are used.

### Adding Telegram / email

- **Telegram:** set up the Telegram integration or a notify service in HA, then
  add `notify.telegram` (or your service) to *Notify services*.
- **Email:** fill in the `SMTP_*` variables and `EMAIL_TO`.

---

## Sick plants & fertilizing

### Sick watch

- Mark a plant sick from its card (the 🤒 button) or the editor. You can add a
  free-text symptom/treatment note.
- While a plant is marked sick, the **daily check-up notification** lists it
  (along with how many days it has been sick) so you remember to inspect it.
- Mark it healthy again with the 💚 button (or in the editor); the check-up stops.
- The **Sick** filter tab shows only the plants currently flagged.

### Fertilizing

- Each plant has a **fertilize interval** in days (default 30; set `0` to disable).
- Reminders only fire during the configured **growing months**
  (`FERTILIZE_MONTHS`, default March–August, i.e. northern spring/summer). Outside
  those months the card shows *"feeding off-season"*.
- When a feeding is due, the daily check includes it and the card shows
  *"🌱 feed in Nd"* / *"feed overdue"*. Use the 🌱 button to mark it as fed.
- Adjust the active months in **Settings → Fertilizing** (or `FERTILIZE_MONTHS`).

Both features reuse the same notification channels as watering reminders, so a
single daily check can send up to three messages (water, sick check-up, feed).

## Project layout

```
plants-app/
├── app/
│   ├── main.py            # FastAPI app, static mounts, startup/lifespan
│   ├── config.py          # environment-based configuration
│   ├── models.py          # SQLAlchemy models + engine/session
│   ├── schemas.py         # Pydantic request/response models
│   ├── store.py           # DB-backed settings that override env vars
│   ├── ha_client.py       # Home Assistant REST client (states + notify)
│   ├── plantnet.py        # Pl@ntNet identification client
│   ├── watering.py        # scheduling + weather-adjustment logic
│   ├── notifications.py   # message building, HA notify + SMTP email
│   ├── scheduler.py       # APScheduler jobs (daily check, env refresh)
│   ├── bootstrap.py       # first-run seeding from bundled photos
│   ├── routers/
│   │   ├── plants.py      # plant CRUD, watering, history, photo upload
│   │   ├── identify.py    # Pl@ntNet identification endpoints
│   │   └── system.py      # weather, status, settings, test notification
│   └── static/            # single-page web UI (HTML/CSS/vanilla JS)
├── seed_data/photos/      # bundled plant photos used on first run
├── data/                  # runtime DB + photos (created on first run)
├── ha-addon/              # Home Assistant add-on (config.yaml, Dockerfile, run.sh)
├── Dockerfile             # standalone container image
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

---

## API reference

All endpoints are under `/api`. Interactive docs are available at `/docs`
(FastAPI/Swagger UI).

| Method | Path                        | Description                          |
| ------ | --------------------------- | ------------------------------------ |
| GET    | `/api/plants`               | List plants with computed schedule   |
| POST   | `/api/plants`               | Create a plant                       |
| GET    | `/api/plants/{id}`          | Get one plant                        |
| PATCH  | `/api/plants/{id}`          | Update a plant                       |
| DELETE | `/api/plants/{id}`          | Delete a plant                       |
| POST   | `/api/plants/{id}/water`    | Record a watering (marks as watered) |
| POST   | `/api/plants/{id}/water/undo`| Undo the most recent watering       |
| POST   | `/api/plants/{id}/sick`     | Mark a plant sick (optional note)    |
| POST   | `/api/plants/{id}/healthy`  | Mark a plant healthy again           |
| POST   | `/api/plants/{id}/fertilize`| Mark a plant as fertilized           |
| GET/POST | `/api/rooms`              | List / create rooms (with sensors)   |
| PATCH/DELETE | `/api/rooms/{id}`     | Update / delete a room               |
| GET    | `/api/ha/notify-services`   | List HA notify.* services            |
| GET    | `/api/ha/suggest`           | Suggested entity IDs for settings    |
| GET    | `/api/plants/{id}/history`  | Watering history                     |
| POST   | `/api/plants/{id}/photo`    | Upload/replace a photo               |
| POST   | `/api/identify`             | Identify a plant from an uploaded image |
| POST   | `/api/plants/{id}/identify` | Identify a plant from its stored photo |
| POST   | `/api/identify/missing`     | Identify all photos (query `overwrite`) |
| GET    | `/api/weather`              | Current environment from HA          |
| GET    | `/api/ha/entities`          | List HA entities (settings autocomplete) |
| GET    | `/api/status`               | HA reachability + due plant count    |
| GET    | `/api/settings`             | Read settings                        |
| PUT    | `/api/settings`             | Update settings                      |
| POST   | `/api/notify/test`          | Send a test notification             |

---

## Data & persistence

- Everything lives in `PLANTS_DATA_DIR` (default `./data`):
  - `plants.db` — SQLite database (plants, watering events, settings, readings).
  - `photos/` — plant photos.
- On the very first start, if the database is empty, the app copies the bundled
  photos from `seed_data/photos` and creates one plant per photo. Later starts
  are a no-op.
- Photos uploaded from the UI are stored as-is on disk; the bundled seed photos
  were pre-shrunk to ~1280 px so the web UI stays fast.

---

## Key design decisions

- **Separate app rather than only HA helpers.** A standalone service gives a much
  nicer UI (photos, cards, one-tap watering) while still using HA as the source of
  truth for weather, temperature and notifications.
- **No tokens when possible.** As an add-on it uses `SUPERVISOR_TOKEN` and the
  `http://supervisor/core` proxy, so there is no secret to copy around.
- **Env vars with DB overrides.** Sane defaults come from the environment/add-on
  options, but anything you change in the UI is stored in the DB and wins — no
  restart or rebuild required.
- **Simple, transparent algorithm.** The adjustment is a small set of readable
  multipliers instead of a black box, so the "reason" shown on each card is
  always explainable and easy to tune.
- **Pl@ntNet for species, not scheduling.** Identification is a convenience for
  recording the right species; watering cadence remains under your control via
  the per-plant base interval, so a wrong ID can never silently change a
  schedule.
- **No build step for the frontend.** Plain HTML/CSS/vanilla JS keeps deployment
  trivial (one container) and avoids a Node toolchain.
- **SQLite.** Single-user, low-write workload — perfect fit, zero external
  dependencies, easy backups (just copy `data/`).

---

## Troubleshooting

- **"HA offline" badge / no weather bar** — check the entity IDs and, for
  non-add-on installs, `HA_URL`/`HA_TOKEN`. Verify the entities exist in
  Developer Tools → States.
- **No notifications** — confirm the `notify.*` service name(s), then use
  **Send test** in Settings.
- **Identification fails** — check the Pl@ntNet API key, the project name, and
  whether you've hit the daily quota (the error message says which).
- **Intervals look wrong** — the base interval lives on each plant; the displayed
  effective interval already includes weather adjustments.
- **Reset everything** — stop the app and delete `PLANTS_DATA_DIR` (or just
  `data/plants.db`); it will re-seed on next start.

---

## Possible next steps

- Rain-based delays using the `weather.*` forecast precipitation.
- Per-room temperature sensors mapped to plant locations.
- Per-plant moisture sensors for true soil-based scheduling.
- Snooze / skip-a-watering and seasonal profiles.
