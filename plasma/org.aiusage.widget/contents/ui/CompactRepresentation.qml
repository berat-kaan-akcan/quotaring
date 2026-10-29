import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PC3
import org.kde.kirigami as Kirigami

// Panel icon: a ring around the tightest limit. The arc and number show what is left
// (or what is used, per the widget setting); the plain icon when no provider reports limits.
MouseArea {
    id: compact
    readonly property var r: root.view ? root.view.ring : null
    readonly property bool available: !!r && r.available
    readonly property bool remaining: Plasmoid.configuration.showRemaining
    readonly property int value: available ? (remaining ? r.remaining : r.used) : 0
    readonly property color tone: !available ? Kirigami.Theme.disabledTextColor
        : r.level === "bad" ? Kirigami.Theme.negativeTextColor
        : r.level === "warn" ? Kirigami.Theme.neutralTextColor
        : Kirigami.Theme.highlightColor

    Layout.minimumWidth: Kirigami.Units.iconSizes.small
    Layout.preferredWidth: Plasmoid.formFactor === PlasmaCore.Types.Horizontal ? height : width
    Layout.preferredHeight: Plasmoid.formFactor === PlasmaCore.Types.Vertical ? width : height
    hoverEnabled: true
    onClicked: root.expanded = !root.expanded

    Kirigami.Icon {
        anchors.fill: parent
        visible: !compact.available
        source: Plasmoid.icon
        active: compact.containsMouse
    }

    Canvas {
        id: ring
        visible: compact.available
        readonly property real size: Math.min(compact.width, compact.height) - 2
        width: size
        height: size
        anchors.centerIn: parent
        property real fraction: compact.value / 100
        property color tone: compact.tone
        property color track: Qt.alpha(Kirigami.Theme.textColor, 0.18)
        onFractionChanged: requestPaint()
        onToneChanged: requestPaint()
        onTrackChanged: requestPaint()
        onWidthChanged: requestPaint()
        Behavior on fraction { NumberAnimation { duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic } }

        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            const lw = Math.max(2, width * 0.12);
            const rad = (width - lw) / 2;
            const c = width / 2;
            ctx.lineWidth = lw;
            ctx.lineCap = "round";
            ctx.strokeStyle = track;
            ctx.beginPath();
            ctx.arc(c, c, rad, 0, 2 * Math.PI);
            ctx.stroke();
            if (fraction > 0) {
                ctx.strokeStyle = tone;
                ctx.beginPath();
                ctx.arc(c, c, rad, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * Math.min(1, fraction));
                ctx.stroke();
            }
        }

        PC3.Label {
            anchors.centerIn: parent
            text: compact.value
            color: compact.r && compact.r.limited ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
            font.pixelSize: Math.max(7, ring.width * (compact.value >= 100 ? 0.3 : 0.38))
            font.weight: Font.DemiBold
            font.features: { "tnum": 1 }
        }
    }
}
