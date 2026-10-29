import QtQuick
import QtQuick.Controls.Basic  // own look on every OS; native styles ignore custom backgrounds

// A tooltip in the popup's colours. Each use is its own instance: the shared attached
// `ToolTip.text` one could come up as an empty box.
ToolTip {
    id: tip
    property var c: backend.palette
    delay: 400
    padding: 8
    contentItem: Text {
        text: tip.text
        textFormat: Text.PlainText
        color: tip.c.text
        font.pointSize: 9
        wrapMode: Text.Wrap
    }
    background: Rectangle {
        radius: 8
        color: tip.c.card
        border.color: tip.c.border
    }
}
