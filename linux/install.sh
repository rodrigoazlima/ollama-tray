#!/usr/bin/env bash
# install.sh — install ollama-tray on Linux (KDE/GNOME)
#
# Usage:
#   ./linux/install.sh              # install deps + register autostart
#   ./linux/install.sh --no-deps    # skip system/pip packages
#   ./linux/install.sh --uninstall  # remove autostart entry
#   ./linux/install.sh --python python3.12   # specify Python executable

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
NO_DEPS=false
UNINSTALL=false

for arg in "$@"; do
  case "$arg" in
    --no-deps)    NO_DEPS=true ;;
    --uninstall)  UNINSTALL=true ;;
    --python=*)   PYTHON="${arg#*=}" ;;
    --python)     shift; PYTHON="$1" ;;
  esac
done

if [[ "$UNINSTALL" == true ]]; then
  "$PYTHON" "$SCRIPT_DIR/ollama_tray_linux.py" --uninstall
  exit $?
fi

if [[ "$NO_DEPS" == false ]]; then
  echo "==> Installing system dependencies..."

  if command -v apt-get &>/dev/null; then
    sudo apt-get install -y \
      python3-tk \
      gir1.2-ayatanaappindicator3-0.1 \
      libayatana-appindicator3-1 \
      python3-gi \
      python3-gi-cairo
  elif command -v dnf &>/dev/null; then
    sudo dnf install -y \
      python3-tkinter \
      libayatana-appindicator-gtk3 \
      python3-gobject \
      python3-cairo
  elif command -v pacman &>/dev/null; then
    sudo pacman -S --needed --noconfirm \
      tk \
      libayatana-appindicator \
      python-gobject \
      python-cairo
  elif command -v zypper &>/dev/null; then
    sudo zypper install -y \
      python3-tk \
      typelib-1_0-AyatanaAppIndicator3-0_1 \
      python3-gobject \
      python3-cairo
  else
    echo "  [warn] Unknown distro — install python3-tk and libayatana-appindicator manually."
  fi

  echo "==> Installing Python dependencies..."
  "$PYTHON" -m pip install --user pystray Pillow psutil
fi

echo "==> Registering autostart..."
"$PYTHON" "$SCRIPT_DIR/ollama_tray_linux.py" --install

echo ""
echo "Done. Launch now with:"
echo "  $PYTHON $SCRIPT_DIR/ollama_tray_linux.py"
