#!/usr/bin/env bash
# Install (or upgrade) the "AI Usage" Plasma 6 widget for the current user.
#   ./plasma/install_plasmoid.sh            -> ~/.local/share/plasma/plasmoids/org.aiusage.widget
# The widget runs `aiusage --widget-json`. If `ai-usage-widget` is on PATH (deb/Arch package)
# that is used; otherwise this checkout's .venv. Then: right-click desktop or panel →
# "Add or Manage Widgets…" → search "AI Usage".
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/.." && pwd)
if [ -n "${AIUSAGE_COMMAND:-}" ]; then
  CMD=$AIUSAGE_COMMAND
elif command -v ai-usage-widget >/dev/null; then
  CMD="ai-usage-widget --widget-json"
elif [ -x "$ROOT/.venv/bin/python" ]; then
  CMD="env PYTHONPATH='$ROOT' '$ROOT/.venv/bin/python' -m aiusage --widget-json"
else
  echo "No ai-usage-widget on PATH and no $ROOT/.venv — install the app first (see README)." >&2
  exit 1
fi
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp -r "$HERE/org.aiusage.widget" "$STAGE/"
CMD_XML=$(printf '%s' "$CMD" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g')
python3 - "$STAGE/org.aiusage.widget/contents/config/main.xml" "$CMD_XML" <<'PY'
import sys
p, cmd = sys.argv[1], sys.argv[2]
s = open(p, encoding="utf-8").read().replace("@COMMAND@", cmd)
open(p, "w", encoding="utf-8").write(s)
PY
if kpackagetool6 -t Plasma/Applet -s org.aiusage.widget >/dev/null 2>&1; then
  kpackagetool6 -t Plasma/Applet -u "$STAGE/org.aiusage.widget"
  echo "Upgraded. Widgets already on screen pick up QML changes after: systemctl --user restart plasma-plasmashell"
else
  kpackagetool6 -t Plasma/Applet -i "$STAGE/org.aiusage.widget"
fi
echo "Widget command: $CMD"
