import QtQuick

// Two concentric arcs: the outer one for the first limit window (5 hours), the inner one for
// the second (weekly). Values are 0–100; a negative value draws only the track. Each ring
// carries a short tag where it starts (12 o'clock), so it says which limit it is.
Item {
    id: gauge
    property real outer: -1
    property real inner: -1
    property string outerTag
    property string innerTag
    property color outerColor
    property color innerColor
    property color track
    property color tagBackground
    property string centerText: "—"
    property string label: ""   // which limit the number is: "5 saat"
    property string subText: "" // "kalan" / "kullanılan"
    property color textColor
    property color subColor
    property int highlight: -1  // 0 outer, 1 inner: the other ring fades
    readonly property int hoverRing: area.ring
    readonly property real lw: width * 0.085
    readonly property real gap: lw * 0.7
    readonly property real outerRadius: width / 2 - lw / 2
    readonly property real innerRadius: width / 2 - lw * 1.5 - gap

    // Animated copies, so the arcs sweep in when the popup opens or a value changes.
    property real shownOuter: Math.max(0, outer)
    property real shownInner: Math.max(0, inner)
    Behavior on shownOuter { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
    Behavior on shownInner { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }

    function sweep() {
        shownOuter = 0;
        shownInner = 0;
        shownOuter = Qt.binding(() => Math.max(0, outer));
        shownInner = Qt.binding(() => Math.max(0, inner));
    }

    Canvas {
        id: art
        anchors.fill: parent
        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            const c = width / 2;
            const rings = [[gauge.outerRadius, gauge.outer, gauge.shownOuter, gauge.outerColor, 0]];
            if (gauge.inner >= 0)
                rings.push([gauge.innerRadius, gauge.inner, gauge.shownInner, gauge.innerColor, 1]);
            ctx.lineWidth = gauge.lw;
            ctx.lineCap = "round";
            for (const [r, raw, value, tone, index] of rings) {
                ctx.globalAlpha = gauge.highlight >= 0 && gauge.highlight !== index ? 0.25 : 1;
                ctx.strokeStyle = gauge.track;
                ctx.beginPath();
                ctx.arc(c, c, r, 0, 2 * Math.PI);
                ctx.stroke();
                if (raw > 0 && value > 0) {
                    ctx.strokeStyle = tone;
                    ctx.beginPath();
                    ctx.arc(c, c, r, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * Math.min(1, value / 100));
                    ctx.stroke();
                }
            }
        }
    }
    onShownOuterChanged: art.requestPaint()
    onShownInnerChanged: art.requestPaint()
    onOuterColorChanged: art.requestPaint()
    onInnerColorChanged: art.requestPaint()
    onTrackChanged: art.requestPaint()
    onInnerChanged: art.requestPaint()
    onHighlightChanged: art.requestPaint()

    // Tags sit on each ring's start; a chip in the card colour cuts the stroke there.
    Repeater {
        model: gauge.inner >= 0 ? [0, 1] : (gauge.outer >= 0 ? [0] : [])
        delegate: Rectangle {
            required property int modelData
            readonly property real r: modelData === 0 ? gauge.outerRadius : gauge.innerRadius
            x: gauge.width / 2 - width / 2
            y: gauge.height / 2 - r - height / 2
            width: tag.implicitWidth + 6
            height: gauge.lw + 3
            radius: height / 2
            color: gauge.tagBackground
            opacity: gauge.highlight >= 0 && gauge.highlight !== modelData ? 0.35 : 1
            Text {
                id: tag
                anchors.centerIn: parent
                text: parent.modelData === 0 ? gauge.outerTag : gauge.innerTag
                color: parent.modelData === 0 ? gauge.outerColor : gauge.innerColor
                font.pixelSize: Math.max(8, gauge.lw * 1.05)
                font.weight: Font.Bold
            }
        }
    }

    Column {
        anchors.centerIn: parent
        anchors.verticalCenterOffset: 2
        spacing: -1
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: gauge.centerText
            color: gauge.textColor
            font.pixelSize: gauge.width * (gauge.centerText.length > 4 ? 0.15 : 0.19)
            font.weight: Font.Bold
            font.features: { "tnum": 1 }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: gauge.label !== ""
            text: gauge.label
            textFormat: Text.PlainText
            color: gauge.textColor
            opacity: 0.85
            font.pixelSize: gauge.width * 0.085
            font.weight: Font.DemiBold
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: gauge.subText !== ""
            text: gauge.subText
            color: gauge.subColor
            font.pixelSize: gauge.width * 0.08
        }
    }

    // Which ring is under the mouse, by distance from the centre.
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        property int ring: -1
        function pick(mx, my) {
            const d = Math.hypot(mx - width / 2, my - height / 2);
            if (Math.abs(d - gauge.outerRadius) <= gauge.lw * 0.9) return 0;
            if (gauge.inner >= 0 && Math.abs(d - gauge.innerRadius) <= gauge.lw * 0.9) return 1;
            return -1;
        }
        onPositionChanged: mouse => ring = pick(mouse.x, mouse.y)
        onExited: ring = -1
    }
}
