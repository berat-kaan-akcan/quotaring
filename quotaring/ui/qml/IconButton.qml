import QtQuick
import QtQuick.Controls.Basic  // own look on every OS; native styles ignore custom backgrounds

// Drawn rather than glyphs: symbol fonts differ between systems.
AbstractButton {
    id: btn
    property var c  // palette
    property string kind  // "refresh" | "settings" | "back"
    property string tip
    property bool spinning: false
    implicitWidth: 32
    implicitHeight: 32
    hoverEnabled: true
    Accessible.name: tip
    Tip { visible: btn.hovered; delay: 600; text: btn.tip; c: btn.c }
    background: Rectangle {
        radius: 8
        color: btn.hovered ? btn.c.track : "transparent"
    }
    contentItem: Item {
        Canvas {
            id: art
            anchors.centerIn: parent
            width: 18
            height: 18
            opacity: btn.enabled || btn.spinning ? 1 : 0.4
            property color tone: btn.hovered ? btn.c.text : btn.c.muted
            onToneChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d");
                ctx.reset();
                const c = width / 2;
                ctx.strokeStyle = tone;
                ctx.fillStyle = tone;
                if (btn.kind === "refresh") {
                    const r = width * 0.34, e = 1.5 * Math.PI - 0.35;
                    ctx.lineWidth = 1.8;
                    ctx.lineCap = "round";
                    ctx.beginPath();
                    ctx.arc(c, c, r, -Math.PI / 2 + 0.6, e);
                    ctx.stroke();
                    // Arrowhead along the clockwise tangent at the arc's end.
                    const ex = c + r * Math.cos(e), ey = c + r * Math.sin(e);
                    const tx = -Math.sin(e), ty = Math.cos(e), nx = Math.cos(e), ny = Math.sin(e);
                    ctx.beginPath();
                    ctx.moveTo(ex + tx * 3.5, ey + ty * 3.5);
                    ctx.lineTo(ex - tx * 1.5 + nx * 3.2, ey - ty * 1.5 + ny * 3.2);
                    ctx.lineTo(ex - tx * 1.5 - nx * 3.2, ey - ty * 1.5 - ny * 3.2);
                    ctx.closePath();
                    ctx.fill();
                } else if (btn.kind === "back") {
                    ctx.lineWidth = 1.8;
                    ctx.lineCap = "round";
                    ctx.lineJoin = "round";
                    ctx.beginPath();
                    ctx.moveTo(c + 2.5, c - 5.5);
                    ctx.lineTo(c - 3, c);
                    ctx.lineTo(c + 2.5, c + 5.5);
                    ctx.stroke();
                } else {
                    ctx.lineWidth = width * 0.16;
                    for (let i = 0; i < 8; i++) {
                        const a = i * Math.PI / 4;
                        ctx.beginPath();
                        ctx.moveTo(c + Math.cos(a) * width * 0.2, c + Math.sin(a) * width * 0.2);
                        ctx.lineTo(c + Math.cos(a) * width * 0.46, c + Math.sin(a) * width * 0.46);
                        ctx.stroke();
                    }
                    ctx.beginPath();
                    ctx.arc(c, c, width * 0.32, 0, 2 * Math.PI);
                    ctx.fill();
                    ctx.globalCompositeOperation = "destination-out";
                    ctx.beginPath();
                    ctx.arc(c, c, width * 0.13, 0, 2 * Math.PI);
                    ctx.fill();
                }
            }
            RotationAnimation on rotation {
                running: btn.spinning
                from: 0; to: 360; duration: 900; loops: Animation.Infinite
                onStopped: art.rotation = 0
            }
        }
    }
}
