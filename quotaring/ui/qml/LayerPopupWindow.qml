import QtQuick
import org.kde.layershell 1.0 as LayerShell

// Wayland: a layer-shell surface anchored to the screen corner by the panel, the only way a
// regular client can place itself there. Loaded only when org.kde.layershell is available.
PopupWindow {
    property bool atTop: false
    LayerShell.Window.scope: "quotaring-popup"
    LayerShell.Window.layer: LayerShell.Window.LayerTop
    LayerShell.Window.anchors: (atTop ? LayerShell.Window.AnchorTop : LayerShell.Window.AnchorBottom)
        | LayerShell.Window.AnchorRight
    LayerShell.Window.margins.top: 8
    LayerShell.Window.margins.bottom: 8
    property int rightMargin: 8  // set by Python to sit above the clicked tray icon
    LayerShell.Window.margins.right: rightMargin
    LayerShell.Window.exclusionZone: 0
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityOnDemand
}
