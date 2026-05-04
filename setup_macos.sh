#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
VENV_DIR="$SCRIPT_DIR/.venv"
APP_NAME="TalkToVibe"
APP_BUNDLE_NAME="${APP_NAME}.app"
APP_DEST="$HOME/Applications/$APP_BUNDLE_NAME"
HELPER_DEST="$HOME/.talktovibe/bin/talktovibe-configure"
MANIFEST_PATH="$HOME/.talktovibe/install-manifest.yaml"
LAUNCH_AGENT_PATH="$HOME/Library/LaunchAgents/com.talktovibe.app.plist"
SIGNING_DIR="$HOME/.talktovibe/signing"
SIGNING_KEYCHAIN="$SIGNING_DIR/talktovibe-signing.keychain-db"
SIGNING_CERT_P12="$SIGNING_DIR/talktovibe-signing.p12"
SIGNING_CERT_PASSWORD_FILE="$SIGNING_DIR/certificate-password.txt"
SIGNING_KEYCHAIN_PASSWORD_FILE="$SIGNING_DIR/keychain-password.txt"
SIGNING_OPENSSL_CONFIG="$SIGNING_DIR/openssl-signing.cnf"
SIGNING_COMMON_NAME="TalkToVibe Local Dev Signing"
PYTHON_BIN=""
BREW_PACKAGES=(portaudio)
INSTALLED_BREW_PACKAGES=()
AUTO_YES=0
NO_LAUNCH=0
SKIP_LOGIN_ITEM=0
REBUILD=0
REUSE_CONFIG=0
NO_OPEN_SETTINGS=0
ENABLE_LOGIN_ITEM=0
SKIP_SIGNING=0

usage() {
  cat <<EOF
Usage: ./setup_macos.sh [options]

Options:
  --yes               Accept prompts with recommended defaults
  --no-launch         Do not launch TalkToVibe.app after installation
  --skip-login-item   Do not prompt for launch at login
  --reuse-config      Reuse existing valid ~/.talktovibe/config.yaml without re-running setup
  --no-open-settings  Do not open System Settings privacy panes
  --rebuild           Force a fresh PyInstaller rebuild
  --skip-signing      Skip local codesigning of the installed app
EOF
}

confirm() {
  local prompt="$1"
  local default_answer="${2:-y}"
  if [ "$AUTO_YES" -eq 1 ]; then
    [ "$default_answer" = "y" ]
    return
  fi
  local suffix="[y/N]"
  if [ "$default_answer" = "y" ]; then
    suffix="[Y/n]"
  fi
  read -r -p "$prompt $suffix " reply
  reply="${reply:-$default_answer}"
  [[ "$reply" =~ ^[Yy]$ ]]
}

open_privacy_pane() {
  local pane="$1"
  open "x-apple.systempreferences:com.apple.preference.security?$pane" >/dev/null 2>&1 || true
}

ensure_macos() {
  if [ "$(uname -s)" != "Darwin" ]; then
    echo "❌ setup_macos.sh only supports macOS."
    exit 1
  fi
}

ensure_homebrew() {
  if ! command -v brew >/dev/null 2>&1; then
    echo "❌ Homebrew is required. Install it first from https://brew.sh"
    exit 1
  fi
}

ensure_python3() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ python3 is required."
    exit 1
  fi
}

ensure_repo_layout() {
  local required_paths=(
    "$SCRIPT_DIR/requirements.txt"
    "$SCRIPT_DIR/packaging/macos/talktovibe_app.spec"
    "$SCRIPT_DIR/packaging/macos/talktovibe_configure.spec"
    "$SCRIPT_DIR/talk_to_vibe/install/macos_cli.py"
  )
  for path in "${required_paths[@]}"; do
    if [ ! -e "$path" ]; then
      echo "❌ Required project file missing: $path"
      exit 1
    fi
  done
}

install_brew_deps() {
  for package in "${BREW_PACKAGES[@]}"; do
    if brew list "$package" >/dev/null 2>&1; then
      echo "  Homebrew package present: $package"
    else
      echo "  Installing Homebrew package: $package"
      brew install "$package"
      INSTALLED_BREW_PACKAGES+=("$package")
    fi
  done
}

ensure_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
  fi
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  PYTHON_BIN="$VENV_DIR/bin/python"
  echo "  Installing Python dependencies..."
  pip install -q -r "$SCRIPT_DIR/requirements.txt" pyinstaller
}

run_helper_python() {
  PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" -m talk_to_vibe.install.macos_cli "$@"
}

config_is_valid() {
  PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" - <<'PY' >/dev/null
from talk_to_vibe.config.loader import load_config

config = load_config()
raise SystemExit(0 if not config.validate() else 1)
PY
}

run_config_wizard() {
  if [ "$REUSE_CONFIG" -eq 1 ] && config_is_valid; then
    echo ""
    echo "🔧 Reusing existing valid TalkToVibe configuration"
    return
  fi
  echo ""
  echo "🔧 Running TalkToVibe configuration wizard"
  "$PYTHON_BIN" -m talk_to_vibe --setup --terminal
}

build_artifacts() {
  local app_command=("$VENV_DIR/bin/pyinstaller")
  local helper_command=("$VENV_DIR/bin/pyinstaller")
  if [ "$REBUILD" -eq 1 ]; then
    app_command+=(--clean)
    helper_command+=(--clean)
  fi

  echo ""
  echo "📦 Building TalkToVibe.app"
  app_command+=(--noconfirm "$SCRIPT_DIR/packaging/macos/talktovibe_app.spec")
  "${app_command[@]}"

  echo "📦 Building talktovibe-configure helper"
  helper_command+=(--noconfirm "$SCRIPT_DIR/packaging/macos/talktovibe_configure.spec")
  "${helper_command[@]}"

  if [ ! -d "$SCRIPT_DIR/dist/TalkToVibe.app" ]; then
    echo "❌ Expected app bundle not found at $SCRIPT_DIR/dist/TalkToVibe.app"
    exit 1
  fi
  if [ ! -f "$SCRIPT_DIR/dist/talktovibe-configure" ]; then
    echo "❌ Expected helper not found at $SCRIPT_DIR/dist/talktovibe-configure"
    exit 1
  fi
}

install_artifacts() {
  mkdir -p "$HOME/Applications" "$HOME/.talktovibe/bin" "$HOME/.talktovibe/logs" "$HOME/Library/LaunchAgents"
  rm -rf "$APP_DEST"
  cp -R "$SCRIPT_DIR/dist/TalkToVibe.app" "$APP_DEST"
  cp "$SCRIPT_DIR/dist/talktovibe-configure" "$HELPER_DEST"
  chmod +x "$HELPER_DEST"
}

ensure_random_secret_file() {
  local file_path="$1"
  if [ ! -f "$file_path" ]; then
    mkdir -p "$(dirname "$file_path")"
    LC_ALL=C python3 - <<'PY' > "$file_path"
import secrets
import string

alphabet = string.ascii_letters + string.digits
print(''.join(secrets.choice(alphabet) for _ in range(32)), end='')
PY
    chmod 600 "$file_path"
  fi
}

ensure_signing_materials() {
  mkdir -p "$SIGNING_DIR"
  ensure_random_secret_file "$SIGNING_CERT_PASSWORD_FILE"
  ensure_random_secret_file "$SIGNING_KEYCHAIN_PASSWORD_FILE"

  if [ ! -f "$SIGNING_CERT_P12" ]; then
    local cert_password temp_key temp_cert
    cert_password="$(cat "$SIGNING_CERT_PASSWORD_FILE")"
    temp_key="$(mktemp "$SIGNING_DIR/key.XXXXXX.pem")"
    temp_cert="$SIGNING_DIR/cert.pem"

    cat > "$SIGNING_OPENSSL_CONFIG" <<EOF
[ req ]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = ext

[ dn ]
CN = $SIGNING_COMMON_NAME

[ ext ]
basicConstraints = CA:FALSE
keyUsage = digitalSignature
extendedKeyUsage = codeSigning
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
EOF

    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
      -keyout "$temp_key" \
      -out "$temp_cert" \
      -config "$SIGNING_OPENSSL_CONFIG" >/dev/null 2>&1

    openssl pkcs12 -export \
      -inkey "$temp_key" \
      -in "$temp_cert" \
      -out "$SIGNING_CERT_P12" \
      -name "$SIGNING_COMMON_NAME" \
      -passout "pass:$cert_password" >/dev/null 2>&1

    rm -f "$temp_key"
  fi
}

ensure_signing_keychain() {
  ensure_signing_materials
  local keychain_password cert_password
  keychain_password="$(cat "$SIGNING_KEYCHAIN_PASSWORD_FILE")"
  cert_password="$(cat "$SIGNING_CERT_PASSWORD_FILE")"

  if [ ! -f "$SIGNING_KEYCHAIN" ]; then
    security create-keychain -p "$keychain_password" "$SIGNING_KEYCHAIN"
  fi

  security set-keychain-settings "$SIGNING_KEYCHAIN"
  security unlock-keychain -p "$keychain_password" "$SIGNING_KEYCHAIN"

  if ! security find-identity -p codesigning "$SIGNING_KEYCHAIN" | grep -F "$SIGNING_COMMON_NAME" >/dev/null 2>&1; then
    security import "$SIGNING_CERT_P12" \
      -k "$SIGNING_KEYCHAIN" \
      -f pkcs12 \
      -P "$cert_password" \
      -T /usr/bin/codesign >/dev/null
    security add-trusted-cert -d -r trustRoot -k "$SIGNING_KEYCHAIN" "$SIGNING_DIR/cert.pem" >/dev/null
    security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$keychain_password" "$SIGNING_KEYCHAIN" >/dev/null
  fi
}

sign_installed_app() {
  if [ "$SKIP_SIGNING" -eq 1 ]; then
    echo "  Skipping local codesigning"
    return
  fi
  ensure_signing_keychain
  local existing_keychains keychain_password
  existing_keychains="$(security list-keychains -d user | tr -d '"')"
  keychain_password="$(cat "$SIGNING_KEYCHAIN_PASSWORD_FILE")"

  security list-keychains -d user -s "$SIGNING_KEYCHAIN" $existing_keychains >/dev/null
  security unlock-keychain -p "$keychain_password" "$SIGNING_KEYCHAIN"

  codesign --force --deep --sign "$SIGNING_COMMON_NAME" "$APP_DEST"
  codesign --verify --deep --strict "$APP_DEST"

  security list-keychains -d user -s $existing_keychains >/dev/null
}

write_manifest() {
  local command=(
    write-manifest
    --path "$MANIFEST_PATH"
    --app-path "$APP_DEST"
    --helper-path "$HELPER_DEST"
    --launch-agent-path "$LAUNCH_AGENT_PATH"
    --bundle-identifier "com.talktovibe.app"
    --install-version "$("$PYTHON_BIN" - <<'PY'
from talk_to_vibe import __version__
print(__version__)
PY
)"
  )
  local package
  if [ "$ENABLE_LOGIN_ITEM" -eq 1 ]; then
    command+=(--launch-at-login)
  fi
  if [ "${#INSTALLED_BREW_PACKAGES[@]}" -gt 0 ]; then
    for package in "${INSTALLED_BREW_PACKAGES[@]}"; do
      command+=(--brew-package "$package")
    done
  fi
  run_helper_python "${command[@]}"
}

disable_launch_agent() {
  if [ -f "$LAUNCH_AGENT_PATH" ]; then
    launchctl unload "$LAUNCH_AGENT_PATH" >/dev/null 2>&1 || true
    rm -f "$LAUNCH_AGENT_PATH"
  fi
}

install_launch_agent() {
  run_helper_python write-launch-agent --output "$LAUNCH_AGENT_PATH" --app-path "$APP_DEST"
  launchctl unload "$LAUNCH_AGENT_PATH" >/dev/null 2>&1 || true
  launchctl load "$LAUNCH_AGENT_PATH"
}

prompt_launch_agent() {
  if [ "$SKIP_LOGIN_ITEM" -eq 1 ]; then
    return
  fi
  if confirm "Enable launch at login?" "y"; then
    ENABLE_LOGIN_ITEM=1
    install_launch_agent
  else
    disable_launch_agent
  fi
}

show_permissions_help() {
  echo ""
  echo "⚠️  macOS permissions required for $APP_BUNDLE_NAME:"
  echo "  1. Microphone: System Settings -> Privacy & Security -> Microphone"
  echo "  2. Accessibility: System Settings -> Privacy & Security -> Accessibility"
  echo "  3. Some systems may also require Input Monitoring for global key listening"
  echo ""
  if [ "$NO_OPEN_SETTINGS" -eq 0 ]; then
    open_privacy_pane "Privacy_Microphone"
    open_privacy_pane "Privacy_Accessibility"
  fi
}

launch_app() {
  if [ "$NO_LAUNCH" -eq 1 ]; then
    return
  fi
  open "$APP_DEST"
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --yes)
        AUTO_YES=1
        ;;
      --no-launch)
        NO_LAUNCH=1
        ;;
      --skip-login-item)
        SKIP_LOGIN_ITEM=1
        ;;
      --reuse-config)
        REUSE_CONFIG=1
        ;;
      --no-open-settings)
        NO_OPEN_SETTINGS=1
        ;;
      --rebuild)
        REBUILD=1
        ;;
      --skip-signing)
        SKIP_SIGNING=1
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown option: $1"
        usage
        exit 1
        ;;
    esac
    shift
  done
}

main() {
  parse_args "$@"
  ensure_macos
  ensure_python3
  ensure_homebrew
  ensure_repo_layout

  echo "🎤 TalkToVibe macOS Setup"
  echo "========================="
  install_brew_deps
  ensure_venv
  run_config_wizard
  build_artifacts
  install_artifacts
  sign_installed_app
  prompt_launch_agent
  write_manifest
  show_permissions_help
  launch_app

  echo ""
  echo "✅ Installation complete"
  echo "  App:        $APP_DEST"
  echo "  Helper:     $HELPER_DEST"
  echo "  Manifest:   $MANIFEST_PATH"
  echo "  Login item: $([ "$ENABLE_LOGIN_ITEM" -eq 1 ] && echo enabled || echo disabled)"
}

main "$@"
