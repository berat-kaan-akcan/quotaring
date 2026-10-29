import QtQuick

// Frameless popup window. Python places it next to the tray (X11, Windows, XWayland);
// LayerPopupWindow.qml anchors it with layer-shell on Wayland. With `docked: false` (no tray)
// it is an ordinary window that stays open.
Window {
    id: win
    property bool docked: true
    width: 400
    // Fits the cards; scrolling a popup this small would only hide things.
    height: Math.min(content.implicitHeight, Screen.desktopAvailableHeight - 24)
    title: backend.view ? backend.view.labels.title : "QuotaRing"
    color: "transparent"
    flags: docked ? (Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint) : Qt.Window

    // Clicking anywhere else closes the popup, like a panel popup.
    onActiveChanged: if (docked && !active && visible) backend.focusLost()
    onVisibleChanged: if (visible) content.animateIn()

    PopupContent {
        id: content
        anchors.fill: parent
        focus: true
        Keys.onEscapePressed: backend.hide()
    }

    Shortcut { sequences: ["F5", "Ctrl+R"]; onActivated: backend.refresh() }
    Shortcut { sequence: "Ctrl+,"; onActivated: backend.openSettings() }
    Shortcut { sequence: "Ctrl+Q"; onActivated: backend.quit() }
}
