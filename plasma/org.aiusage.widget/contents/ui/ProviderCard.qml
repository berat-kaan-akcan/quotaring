import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PC3
import org.kde.kirigami as Kirigami

// One provider. Account quota (provider-reported) and local activity stay visually separate.
ColumnLayout {
    id: card
    property var p
    property var labels
    property string period: "today"
    spacing: Kirigami.Units.smallSpacing

    function levelColor(level) {
        switch (level) {
        case "ok": return Kirigami.Theme.positiveTextColor;
        case "warn": return Kirigami.Theme.neutralTextColor;
        case "bad": return Kirigami.Theme.negativeTextColor;
        default: return Kirigami.Theme.disabledTextColor;
        }
    }
    function barColor(pct) {
        return pct >= 90 ? Kirigami.Theme.negativeTextColor
             : pct >= 70 ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.highlightColor;
    }

    // header
    RowLayout {
        Layout.fillWidth: true
        Rectangle {
            width: Kirigami.Units.smallSpacing * 2.5; height: width; radius: width / 2
            color: card.p.color
        }
        PC3.Label { text: card.p.name; font.bold: true }
        PC3.Label { text: card.p.plan; opacity: 0.6; visible: text !== "" }
        Item { Layout.fillWidth: true }
        Rectangle {
            radius: height / 2
            color: Qt.alpha(card.levelColor(card.p.pill.level), 0.15)
            implicitWidth: pillText.implicitWidth + Kirigami.Units.largeSpacing
            implicitHeight: pillText.implicitHeight + 2
            PC3.Label {
                id: pillText
                anchors.centerIn: parent
                text: card.p.pill.text
                color: card.levelColor(card.p.pill.level)
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                font.bold: true
            }
        }
    }

    PC3.Label {
        visible: card.p.collapsed
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        opacity: 0.7
        text: card.p.message
    }

    ColumnLayout {
        visible: !card.p.collapsed
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        // ---- account quota ----
        PC3.Label { text: card.labels.quota; opacity: 0.6; font.pointSize: Kirigami.Theme.smallFont.pointSize; font.bold: true }
        Repeater {
            model: card.p.quota
            delegate: ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    PC3.Label { text: modelData.label; Layout.preferredWidth: Kirigami.Units.gridUnit * 7; elide: Text.ElideRight }
                    Rectangle {
                        Layout.fillWidth: true
                        height: Kirigami.Units.smallSpacing * 1.5
                        radius: height / 2
                        color: Qt.alpha(Kirigami.Theme.textColor, 0.12)
                        Rectangle {
                            width: Math.max(height, parent.width * Math.min(100, modelData.percent) / 100)
                            height: parent.height
                            radius: parent.radius
                            visible: modelData.percent > 0
                            color: card.barColor(modelData.percent)
                            opacity: modelData.dim ? 0.45 : 1
                        }
                    }
                    PC3.Label {
                        text: modelData.percentText
                        horizontalAlignment: Text.AlignRight
                        Layout.minimumWidth: Kirigami.Units.gridUnit * 2
                        color: modelData.limited ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                        font.bold: !!modelData.limited
                    }
                }
                PC3.Label { text: modelData.reset; opacity: 0.6; font.pointSize: Kirigami.Theme.smallFont.pointSize }
            }
        }
        PC3.Label {
            visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
            text: card.p.quotaMessage; opacity: 0.75; font.pointSize: Kirigami.Theme.smallFont.pointSize
        }
        PC3.Label {
            visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
            text: card.p.breakdown; opacity: 0.6; font.pointSize: Kirigami.Theme.smallFont.pointSize
        }
        PC3.Label {
            visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
            text: card.p.quotaSource; opacity: 0.5; font.pointSize: Kirigami.Theme.smallFont.pointSize
        }

        // ---- local activity ----
        PC3.Label { text: card.labels.local; opacity: 0.6; font.pointSize: Kirigami.Theme.smallFont.pointSize; font.bold: true }
        RowLayout {
            visible: card.p.local.length > 0
            spacing: Kirigami.Units.gridUnit
            Repeater {
                model: card.p.local
                delegate: ColumnLayout {
                    spacing: 0
                    PC3.Label {
                        text: modelData.value
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.3
                        font.bold: true
                        MouseArea { id: valueHover; anchors.fill: parent; hoverEnabled: true }
                        PC3.ToolTip.text: modelData.tooltip
                        PC3.ToolTip.visible: valueHover.containsMouse
                    }
                    PC3.Label { text: modelData.label; opacity: 0.6; font.pointSize: Kirigami.Theme.smallFont.pointSize }
                }
            }
        }
        PC3.Label {
            visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.WordWrap
            text: card.p.localMessage; opacity: 0.75; font.pointSize: Kirigami.Theme.smallFont.pointSize
        }

        // daily bars (locally recorded tokens)
        Row {
            visible: card.p.daily.length > 0
            Layout.fillWidth: true
            height: Kirigami.Units.gridUnit * 2.5
            spacing: 0
            Repeater {
                model: card.p.daily
                delegate: Item {
                    width: parent.width / card.p.daily.length
                    height: parent.height
                    Rectangle {
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: parent.width * 0.68
                        height: Math.max(2, parent.height * modelData.ratio)
                        radius: 2
                        color: modelData.value > 0 ? card.p.color : Qt.alpha(Kirigami.Theme.textColor, 0.12)
                        opacity: index === card.p.daily.length - 1 ? 1 : 0.7
                    }
                    MouseArea { id: barHover; anchors.fill: parent; hoverEnabled: true }
                    PC3.ToolTip.text: modelData.tooltip
                    PC3.ToolTip.visible: barHover.containsMouse
                }
            }
        }
        PC3.Label {
            visible: card.p.daily.length > 0; Layout.fillWidth: true; wrapMode: Text.WordWrap
            text: card.p.chartLabel; opacity: 0.6; font.pointSize: Kirigami.Theme.smallFont.pointSize
        }

        // per-model table for the selected period
        GridLayout {
            readonly property var rows: (card.p.models && card.p.models[card.period]) || []
            id: table
            visible: card.p.local.length > 0
            Layout.fillWidth: true
            columns: 5
            columnSpacing: Kirigami.Units.smallSpacing
            rowSpacing: 0
            Repeater {
                model: card.labels.columns
                delegate: PC3.Label {
                    text: modelData; opacity: 0.6; font.pointSize: Kirigami.Theme.smallFont.pointSize
                    Layout.fillWidth: index === 0
                    horizontalAlignment: index === 0 ? Text.AlignLeft : Text.AlignRight
                }
            }
            Repeater {
                model: table.rows.length * 5
                delegate: PC3.Label {
                    readonly property int r: Math.floor(index / 5)
                    readonly property int c: index % 5
                    text: table.rows[r][c]
                    elide: c === 0 ? Text.ElideRight : Text.ElideNone
                    Layout.fillWidth: c === 0
                    Layout.maximumWidth: c === 0 ? Kirigami.Units.gridUnit * 8 : -1
                    horizontalAlignment: c === 0 ? Text.AlignLeft : Text.AlignRight
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                }
            }
            PC3.Label {
                visible: table.rows.length === 0
                Layout.columnSpan: 5
                text: card.labels.noUsage.replace("{period}",
                    (card.labels.periods.find(x => x.key === card.period) || {label: card.period}).label)
                opacity: 0.6
                font.pointSize: Kirigami.Theme.smallFont.pointSize
            }
        }
    }

    PC3.Label {
        Layout.fillWidth: true; wrapMode: Text.WordWrap
        text: card.p.footer; opacity: 0.5; font.pointSize: Kirigami.Theme.smallFont.pointSize
    }

    Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: Kirigami.Units.smallSpacing }
}
