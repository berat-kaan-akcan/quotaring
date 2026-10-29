import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PC3
import org.kde.kirigami as Kirigami

MouseArea {
    id: compact
    readonly property bool horizontal: Plasmoid.formFactor === PlasmaCore.Types.Horizontal
    readonly property string headline: root.view ? root.view.headline : ""

    Layout.minimumWidth: horizontal ? row.implicitWidth : Kirigami.Units.iconSizes.small
    Layout.preferredWidth: Layout.minimumWidth
    hoverEnabled: true
    onClicked: root.expanded = !root.expanded

    RowLayout {
        id: row
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing
        Kirigami.Icon {
            source: Plasmoid.icon
            Layout.fillHeight: true
            Layout.preferredWidth: height
        }
        // Highest provider-reported quota use; empty when no provider reports quota.
        PC3.Label {
            visible: compact.horizontal && compact.headline !== ""
            text: compact.headline
            font.bold: true
        }
    }
}
