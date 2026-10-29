import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.kirigami as Kirigami

Item {
    id: full
    Layout.preferredWidth: Kirigami.Units.gridUnit * 20
    Layout.preferredHeight: Kirigami.Units.gridUnit * 26
    Layout.minimumWidth: Kirigami.Units.gridUnit * 15
    Layout.minimumHeight: Kirigami.Units.gridUnit * 14

    readonly property var v: root.view

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            spacing: 0
            PC3.TabBar {
                id: tabs
                Layout.fillWidth: true
                // Restored after the buttons exist; a binding here would be overwritten by them.
                property bool restored: false
                Component.onCompleted: Qt.callLater(() => {
                    currentIndex = Plasmoid.configuration.tab === 1 ? 1 : 0;
                    restored = true;
                })
                onCurrentIndexChanged: if (restored) Plasmoid.configuration.tab = currentIndex
                PC3.TabButton { text: full.v ? full.v.text.limits : "Limits" }
                PC3.TabButton { text: full.v ? full.v.text.tokens : "Tokens" }
            }
            PC3.ToolButton {
                icon.name: "view-refresh"
                enabled: !root.loading
                onClicked: root.refresh()
                display: PC3.AbstractButton.IconOnly
                text: full.v ? full.v.labels.refresh : "Refresh"
                PC3.ToolTip.text: text
                PC3.ToolTip.visible: hovered
                RotationAnimation on rotation {
                    running: root.loading
                    from: 0; to: 360; duration: 900; loops: Animation.Infinite
                    onStopped: parent.rotation = 0
                }
            }
        }

        // No data yet: one line saying why and what to do.
        PC3.Label {
            visible: !full.v
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Kirigami.Units.largeSpacing
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
            opacity: 0.7
            text: root.loading ? (root.turkish ? "Yükleniyor…" : "Loading…")
                : (root.lastError || (root.turkish ? "Komut ayarlanmamış: widget ayarlarını aç." : "No command set: open the widget settings."))
        }

        StackLayout {
            visible: !!full.v
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: Kirigami.Units.largeSpacing
            currentIndex: tabs.currentIndex
            LimitsPage { v: full.v }
            TokensPage { v: full.v }
        }

        PC3.Label {
            visible: !!full.v || root.lastError !== ""
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            wrapMode: Text.WordWrap
            font: Kirigami.Theme.smallFont
            color: root.lastError ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
            opacity: root.lastError ? 1 : 0.6
            text: root.lastError ? root.lastError
                : !full.v ? "" : tabs.currentIndex === 0 ? full.v.text.updated : full.v.text.localOnly
        }
    }
}
