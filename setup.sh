#!/usr/bin/env bash
#
# Work Radar - one-time setup for a new machine / teammate.
# Safe to re-run; every step is idempotent.
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$REPO_DIR/dashboard.5m.py"
SWIFTBAR_DIR="$HOME/.swiftbar"
KEYCHAIN_SERVICE="work-radar-jira"

info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$1"; }

# 1. Prerequisites -----------------------------------------------------------
info "Checking prerequisites (gh, jira, brew)"
command -v brew >/dev/null || { warn "Homebrew required: https://brew.sh"; exit 1; }
command -v gh   >/dev/null || { info "Installing GitHub CLI"; brew install gh; }
command -v jira >/dev/null || { info "Installing jira-cli"; brew install ankitpokhrel/jira-cli/jira-cli; }

# 2. GitHub auth -------------------------------------------------------------
if gh auth status >/dev/null 2>&1; then
  info "GitHub CLI already authenticated"
else
  info "Authenticate the GitHub CLI"
  gh auth login
fi

# 3. Jira auth ---------------------------------------------------------------
if jira me >/dev/null 2>&1; then
  info "jira-cli already configured ($(jira me))"
else
  warn "jira-cli is not configured yet."
  echo "  You'll need a Jira API token: https://id.atlassian.com/manage-profile/security/api-tokens"
  echo "  Run 'jira init' (it will ask for your server, email, and token), then re-run this script."
  exit 1
fi

# 4. Store the Jira token in the Keychain ------------------------------------
# SwiftBar does not load your shell rc, so the plugin reads the token from here.
if security find-generic-password -s "$KEYCHAIN_SERVICE" >/dev/null 2>&1; then
  info "Jira token already in Keychain (service: $KEYCHAIN_SERVICE)"
elif [ -n "${JIRA_API_TOKEN:-}" ]; then
  info "Storing Jira token in Keychain from \$JIRA_API_TOKEN"
  security add-generic-password -U -a "$USER" -s "$KEYCHAIN_SERVICE" -T /usr/bin/security -w "$JIRA_API_TOKEN"
else
  info "Paste your Jira API token to store it in the Keychain"
  read -rs -p "  Jira API token: " token; echo
  security add-generic-password -U -a "$USER" -s "$KEYCHAIN_SERVICE" -T /usr/bin/security -w "$token"
fi

# 5. SwiftBar ----------------------------------------------------------------
[ -d /Applications/SwiftBar.app ] || { info "Installing SwiftBar"; brew install --cask swiftbar; }

info "Linking the plugin into $SWIFTBAR_DIR"
mkdir -p "$SWIFTBAR_DIR"
ln -sf "$PLUGIN" "$SWIFTBAR_DIR/dashboard.5m.py"
chmod +x "$PLUGIN"

info "Pointing SwiftBar at $SWIFTBAR_DIR"
defaults write com.ameba.SwiftBar PluginDirectory "$SWIFTBAR_DIR"
defaults write com.ameba.SwiftBar MakePluginExecutable -bool true

# 6. Launch at login + start now ---------------------------------------------
info "Enabling launch at login"
osascript -e 'tell application "System Events" to if not (exists login item "SwiftBar") then make login item at end with properties {path:"/Applications/SwiftBar.app", hidden:false}' >/dev/null 2>&1 || warn "Could not add login item automatically; enable it in SwiftBar if desired."

info "Starting SwiftBar"
osascript -e 'tell application "SwiftBar" to quit' >/dev/null 2>&1 || true
sleep 1
open -a SwiftBar

echo
info "Done. Look for the sunglasses icon in your menu bar."
