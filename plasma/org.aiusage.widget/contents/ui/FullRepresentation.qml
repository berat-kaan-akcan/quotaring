import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.kirigami as Kirigami

Item {
    id: full
    Layout.preferredWidth: Kirigami.Units.gridUnit * 22
    Layout.preferredHeight: Kirigami.Units.gridUnit * 30
    Layout.minimumWidth: Kirigami.Units.gridUnit * 16
    Layout.minimumHeight: Kirigami.Units.gridUnit * 12

    readonly property var v: root.view
    property string period: Plasmoid.configuration.period || "today"

    ColumnLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            Kirigami.Heading {
                level: 4
                text: full.v ? full.v.labels.title : "AI Usage"
                Layout.fillWidth: true
            }
            PC3.ComboBox {
                id: periodBox
                visible: !!full.v
                model: full.v ? full.v.labels.periods : []
                textRole: "label"
                valueRole: "key"
                Component.onCompleted: currentIndex = Math.max(0, indexOfValue(full.period))
                onModelChanged: currentIndex = Math.max(0, indexOfValue(full.period))
                onActivated: {
                    full.period = currentValue;
                    Plasmoid.configuration.period = currentValue;
                }
            }
            PC3.ToolButton {
                icon.name: "view-refresh"
                enabled: !root.loading
                onClicked: root.refresh()
                PC3.ToolTip.text: full.v ? full.v.labels.refresh : "Refresh"
                PC3.ToolTip.visible: hovered
            }
        }

        PC3.Label {
            visible: !full.v
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: root.loading ? (root.turkish ? "Yükleniyor…" : "Loading…")
                : (root.lastError || (root.turkish ? "Komut ayarlanmamış (widget ayarları)." : "No command set (widget settings)."))
        }
        PC3.Label {
            visible: !!full.v && root.lastError !== ""
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Kirigami.Theme.negativeTextColor
            text: root.lastError
        }

        PC3.ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !!full.v
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.width
                spacing: Kirigami.Units.largeSpacing
                Repeater {
                    model: full.v ? full.v.providers : []
                    delegate: ProviderCard {
                        Layout.fillWidth: true
                        p: modelData
                        labels: full.v.labels
                        period: full.period
                    }
                }
            }
        }
    }
}
