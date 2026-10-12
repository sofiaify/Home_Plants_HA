#!/usr/bin/env bash
#
# Deploy the Home Plants add-on to a Home Assistant OS / Supervised device.
#
# It copies this folder's `ha-addon/` build context to <HA_HOST>:/addons/plants
# over SSH. After that, Home Assistant installs/updates it as a local add-on.
#
# Usage:
#   cp .deploy.env.example .deploy.env   # then edit it
#   ./deploy.sh
#
# or pass everything inline:
#   HA_HOST=homeassistant.local HA_SSH_USER=root ./deploy.sh
#
# Flags:
#   --dry-run     show what would happen without touching the device
#   --no-reload   skip the optional Home Assistant API reload/rebuild step
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DRY_RUN=0
DO_RELOAD=1
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --no-reload) DO_RELOAD=0 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

# --- Load configuration -------------------------------------------------------
if [ -f .deploy.env ]; then
  # shellcheck disable=SC1091
  source .deploy.env
fi

: "${HA_HOST:?Set HA_HOST in .deploy.env (e.g. homeassistant.local or the Pi IP)}"
HA_SSH_PORT="${HA_SSH_PORT:-22}"
HA_SSH_USER="${HA_SSH_USER:-root}"
ADDONS_PATH="${ADDONS_PATH:-/addons}"
ADDON_DIR_NAME="${ADDON_DIR_NAME:-plants}"
ADDON_SLUG="${ADDON_SLUG:-local_plants}"
HA_API_URL="${HA_API_URL:-}"
HA_TOKEN="${HA_TOKEN:-}"

SRC_DIR="$SCRIPT_DIR/ha-addon"
REMOTE="${HA_SSH_USER}@${HA_HOST}"
DEST="${ADDONS_PATH}/${ADDON_DIR_NAME}"
SSH_OPTS=(-p "$HA_SSH_PORT" -o StrictHostKeyChecking=accept-new)

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

# --- 1. Refresh the add-on build context from the app source ------------------
say "Refreshing add-on build context (app/, requirements.txt)"
mkdir -p "$SRC_DIR"
rm -rf "$SRC_DIR/app" "$SRC_DIR/requirements.txt"
cp -R app "$SRC_DIR/app"
cp requirements.txt "$SRC_DIR/requirements.txt"
find "$SRC_DIR/app" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

if [ ! -f "$SRC_DIR/config.yaml" ]; then
  echo "ha-addon/config.yaml is missing" >&2
  exit 1
fi

# --- 2. Preflight: can we reach the device over SSH? --------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  warn "DRY RUN — skipping SSH and copy."
  say "Would sync: $SRC_DIR/  ->  ${REMOTE}:${DEST}/"
  say "Files:"
  (cd "$SRC_DIR" && find . -type f -not -path './app/__pycache__/*' | sed 's/^/    /')
else
  say "Checking SSH connection to ${REMOTE}:${HA_SSH_PORT}"
  if ! ssh "${SSH_OPTS[@]}" "$REMOTE" "echo connected" >/dev/null 2>&1; then
    echo "Could not SSH to $REMOTE on port $HA_SSH_PORT." >&2
    echo "Make sure the 'Advanced SSH & Web Terminal' add-on is running and HA_SSH_USER/HA_SSH_PORT are correct." >&2
    exit 1
  fi

  remote_arch="$(ssh "${SSH_OPTS[@]}" "$REMOTE" 'uname -m' 2>/dev/null || echo unknown)"
  say "Device architecture: ${remote_arch}"
  case "$remote_arch" in
    armv7l|armv6l) warn "32-bit ARM detected — dependencies install from pure-Python wheels; first build may take a few minutes." ;;
  esac

  # ADDONS_PATH is owned by root. Figure out if we can write: as root, or via sudo.
  REMOTE_SUDO="${REMOTE_SUDO:-auto}"
  SUDO_PREFIX=""
  case "$REMOTE_SUDO" in
    1|yes|true) SUDO_PREFIX="sudo " ;;
    0|no|false) SUDO_PREFIX="" ;;
    *)
      remote_uid="$(ssh "${SSH_OPTS[@]}" "$REMOTE" 'id -u' 2>/dev/null || echo '')"
      if [ "$remote_uid" = "0" ]; then
        SUDO_PREFIX=""
      elif ssh "${SSH_OPTS[@]}" "$REMOTE" "sudo -n true" >/dev/null 2>&1; then
        SUDO_PREFIX="sudo "
      else
        SUDO_PREFIX="__none__"
      fi ;;
  esac

  if [ "$SUDO_PREFIX" = "__none__" ]; then
    cat >&2 <<ERR
Cannot write to ${ADDONS_PATH} as '${HA_SSH_USER}' (needs root, and passwordless sudo is unavailable).

Fix one of these and re-run:
  * set the SSH add-on username to 'root'
    (Advanced SSH & Web Terminal -> Configuration -> username: root), or
  * set HA_SSH_USER=root in .deploy.env, or
  * set REMOTE_SUDO=1 in .deploy.env if '${HA_SSH_USER}' has passwordless sudo.
ERR
    exit 1
  fi

  # --- 3. Copy the add-on folder ---------------------------------------------
  say "Writing to ${DEST} ${SUDO_PREFIX:+(privileged)}"
  ssh "${SSH_OPTS[@]}" "$REMOTE" "${SUDO_PREFIX}mkdir -p '$DEST'"
  if command -v rsync >/dev/null 2>&1; then
    say "Copying with rsync ..."
    RSYNC_PATH_ARG=()
    [ -n "$SUDO_PREFIX" ] && RSYNC_PATH_ARG=(--rsync-path="sudo rsync")
    rsync -az --delete \
      --exclude '__pycache__' --exclude '*.pyc' \
      "${RSYNC_PATH_ARG[@]}" \
      -e "ssh ${SSH_OPTS[*]}" \
      "$SRC_DIR/" "$REMOTE:$DEST/"
  else
    say "rsync not found — copying with tar over ssh ..."
    tar czf - -C "$SRC_DIR" --exclude '__pycache__' --exclude '*.pyc' . \
      | ssh "${SSH_OPTS[@]}" "$REMOTE" "${SUDO_PREFIX}mkdir -p '$DEST' && ${SUDO_PREFIX}tar xzf - -C '$DEST'"
  fi
  say "Copied to ${REMOTE}:${DEST}"
fi

# --- 4. Optional: ask Home Assistant to reload the store / rebuild ------------
if [ "$DRY_RUN" -eq 0 ] && [ "$DO_RELOAD" -eq 1 ] && [ -n "$HA_API_URL" ] && [ -n "$HA_TOKEN" ]; then
  HA_API_URL="${HA_API_URL%/}"

  # Verify the URL and token before firing the reload calls.
  auth_code="$(curl -s -o /dev/null -w '%{http_code}' -m 15 \
    -H "Authorization: Bearer $HA_TOKEN" "$HA_API_URL/api/" || echo 000)"
  hassio_code="$(curl -s -o /dev/null -w '%{http_code}' -m 15 \
    -H "Authorization: Bearer $HA_TOKEN" "$HA_API_URL/api/hassio/supervisor/info" || echo 000)"
  if [ "$auth_code" != "200" ]; then
    warn "Home Assistant API auth check returned HTTP ${auth_code} (token length ${#HA_TOKEN})."
    case "$auth_code" in
      401) warn "401 = token invalid, expired, or not from an admin user." ;;
      000) warn "000 = could not reach ${HA_API_URL} (wrong URL / HTTP vs HTTPS / not on the network)." ;;
      403) warn "403 = token belongs to a non-admin account." ;;
    esac
    warn "Skipping auto reload/rebuild. The files are still on the device —"
    warn "install/update it from Settings -> Add-ons -> Add-on Store."
  elif [ "$hassio_code" != "200" ]; then
    warn "Token is valid but your user is NOT an admin (supervisor API -> ${hassio_code})."
    warn "Files copied. Reload the add-on manually: Settings -> Add-ons -> Add-on Store"
    warn "-> three dots (top right) -> Check for updates, then Update/Start Home Plants."
  else
    api() { curl -fsS -m 25 -X POST -H "Authorization: Bearer $HA_TOKEN" \
              -H "Content-Type: application/json" "$HA_API_URL/api/hassio/$1" "${@:2}" >/dev/null; }
    say "Asking Home Assistant to reload the add-on store"
    api "store/reload" || warn "store/reload failed (reload manually in the UI)"
    say "Rebuilding and restarting the add-on ($ADDON_SLUG)"
    api "addons/${ADDON_SLUG}/rebuild" || warn "rebuild failed — the add-on may not be installed yet"
    api "addons/${ADDON_SLUG}/restart" || warn "restart failed"
  fi
fi

# --- 5. Next steps ------------------------------------------------------------
cat <<EOF

$(say "Files are on the device.")

In Home Assistant:
  1. Settings -> Add-ons -> Add-on Store -> (three dots) -> Check for updates
  2. Open "Local add-ons" -> Home Plants
  3. First time: INSTALL.  Later: UPDATE.  Then START.
  4. Fill the add-on Configuration tab (entity IDs, notify service, timezone)
     and Start / Restart.

App URLs:
  http://${HA_HOST}:8099        (from your network)
EOF
