import QtQuick

// Frameless popup window. Python places it next to the tray (X11, Windows, XWayland);
// LayerPopupWindow.qml anchors it with layer-shell on Wayland. With `docked: false` (no tray)
// it is an ordinary window that stays open.
Window {
    id: win
    property bool docked: true
    width: 400
    // Grows with the page up to a comfortable height (or the screen's); taller pages scroll.
    readonly property int maxHeight: 660
    // The free height of the screen it opens on; Python sets it when placing the popup (the
    // desktop's height is only a fallback: on several screens it is not this screen's).
    property int screenHeight: Screen.desktopAvailableHeight - 24
    height: Math.min(content.implicitHeight, maxHeight, screenHeight)
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
