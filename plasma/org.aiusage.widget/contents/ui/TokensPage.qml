import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.kirigami as Kirigami

PC3.ScrollView {
    id: page
    property var v
    readonly property var t: v ? v.tokens : null
    property string period: Plasmoid.configuration.period || "7d"
    property string group: Plasmoid.configuration.group || "all"
    readonly property var g: t ? (t.data[group] || t.data["all"]) : null
    readonly property var p: g ? g.periods[period] : null
    contentWidth: availableWidth

    function labelOf(list, key) {
        for (const x of (list || [])) if (x.key === key) return x.label;
        return key;
    }

    ColumnLayout {
        // Room for the overlay scroll bar so right-aligned values are never clipped.
        width: page.availableWidth - Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            PC3.ComboBox {
                Layout.fillWidth: true
                model: page.t ? page.t.periods : []
                textRole: "label"
                valueRole: "key"
                Component.onCompleted: currentIndex = Math.max(0, indexOfValue(page.period))
                onModelChanged: currentIndex = Math.max(0, indexOfValue(page.period))
                onActivated: Plasmoid.configuration.period = page.period = currentValue
            }
            PC3.ComboBox {
                Layout.fillWidth: true
                visible: !!page.t && page.t.groups.length > 2
                model: page.t ? page.t.groups : []
                textRole: "label"
                valueRole: "key"
                Component.onCompleted: currentIndex = Math.max(0, indexOfValue(page.group))
                onModelChanged: currentIndex = Math.max(0, indexOfValue(page.group))
                onActivated: Plasmoid.configuration.group = page.group = currentValue
            }
        }

        ColumnLayout {
            spacing: 0
            PC3.Label {
                text: page.p ? page.p.totalText : "0"
                font.pointSize: Kirigami.Theme.defaultFont.pointSize * 2.2
                font.weight: Font.DemiBold
                font.features: { "tnum": 1 }
            }
            PC3.Label {
                text: page.v ? page.v.text.total.replace("{period}", page.labelOf(page.t.periods, page.period).toLocaleLowerCase()) : ""
                font: Kirigami.Theme.smallFont
                opacity: 0.6
            }
        }

        // Last 7 days, one bar per day; the busiest day carries its value.
        ColumnLayout {
            visible: !!page.g && page.g.daily.length > 0
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
            PC3.Label { text: page.v ? page.v.text.daily : ""; font.weight: Font.Medium }
            Item {
                Layout.fillWidth: true
                implicitHeight: Kirigami.Units.gridUnit * 5
                Row {
                    id: bars
                    anchors.fill: parent
                    spacing: Kirigami.Units.smallSpacing
                    readonly property int n: page.g ? page.g.daily.length : 1
                    Repeater {
                        model: page.g ? page.g.daily : []
                        delegate: Item {
                            id: day
                            required property var modelData
                            width: (bars.width - bars.spacing * (bars.n - 1)) / bars.n
                            height: bars.height
                            Rectangle {
                                anchors.bottom: parent.bottom
                                width: parent.width
                                radius: 3
                                height: Math.max(2, (parent.height - Kirigami.Units.gridUnit) * day.modelData.ratio)
                                color: day.modelData.value > 0 ? Kirigami.Theme.highlightColor : Qt.alpha(Kirigami.Theme.textColor, 0.12)
                                PC3.Label {
                                    visible: day.modelData.ratio === 1 && day.modelData.value > 0
                                    anchors.bottom: parent.top
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: day.modelData.text
                                    font: Kirigami.Theme.smallFont
                                }
                            }
                            MouseArea {
                                id: hover
                                anchors.fill: parent
                                hoverEnabled: true
                            }
                            PC3.ToolTip.visible: hover.containsMouse
                            PC3.ToolTip.text: day.modelData.label + ": " + day.modelData.text
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                PC3.Label { text: page.g && page.g.daily.length ? page.g.daily[0].label : ""; font: Kirigami.Theme.smallFont; opacity: 0.6 }
                Item { Layout.fillWidth: true }
                PC3.Label { text: page.g && page.g.daily.length ? page.g.daily[page.g.daily.length - 1].label : ""; font: Kirigami.Theme.smallFont; opacity: 0.6 }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
            PC3.Label { text: page.v ? page.v.text.byModel : ""; font.weight: Font.Medium }
            PC3.Label {
                visible: !page.p || page.p.models.length === 0
                text: page.v ? page.v.text.noData : ""
                opacity: 0.6
            }
            Repeater {
                model: page.p ? page.p.models.slice(0, 6) : []
                delegate: ColumnLayout {
                    id: m
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 2
                    RowLayout {
                        Layout.fillWidth: true
                        Rectangle { width: 8; height: 8; radius: 2; color: m.modelData.color }
                        PC3.Label { text: m.modelData.name; Layout.fillWidth: true; elide: Text.ElideRight }
                        PC3.Label { text: m.modelData.text; font.weight: Font.DemiBold; font.features: { "tnum": 1 } }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 4
                        radius: 2
                        color: Qt.alpha(Kirigami.Theme.textColor, 0.10)
                        Rectangle {
                            height: parent.height
                            radius: 2
                            width: Math.max(height, parent.width * m.modelData.ratio)
                            color: m.modelData.color
                        }
                    }
                }
            }
        }
        Item { Layout.fillHeight: true }
    }
}
