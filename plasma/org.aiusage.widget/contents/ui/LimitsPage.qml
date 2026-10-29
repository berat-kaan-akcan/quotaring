import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.kirigami as Kirigami
import "Theme.js" as T

PC3.ScrollView {
    id: page
    property var v
    readonly property bool remaining: Plasmoid.configuration.showRemaining
    contentWidth: availableWidth

    ColumnLayout {
        // Room for the overlay scroll bar so right-aligned values are never clipped.
        width: page.availableWidth - Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.largeSpacing

        PC3.Label {
            visible: !!page.v && page.v.limits.length === 0
            Layout.fillWidth: true
            opacity: 0.6
            text: page.v ? page.v.text.noLimits : ""
        }

        Repeater {
            model: page.v ? page.v.limits : []
            delegate: ColumnLayout {
                id: prov
                required property var modelData
                required property int index
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Separator {
                    visible: prov.index > 0
                    Layout.fillWidth: true
                    Layout.bottomMargin: Kirigami.Units.smallSpacing
                    opacity: 0.5
                }

                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { level: 3; text: prov.modelData.name }
                    Rectangle {
                        visible: prov.modelData.plan !== ""
                        radius: height / 2
                        color: Qt.alpha(Kirigami.Theme.highlightColor, 0.18)
                        implicitHeight: planLabel.implicitHeight + 2
                        implicitWidth: planLabel.implicitWidth + Kirigami.Units.largeSpacing
                        PC3.Label {
                            id: planLabel
                            anchors.centerIn: parent
                            text: prov.modelData.plan
                            font: Kirigami.Theme.smallFont
                            color: Kirigami.Theme.highlightColor
                        }
                    }
                    Item { Layout.fillWidth: true }
                    PC3.Label {
                        visible: prov.modelData.note !== ""
                        text: prov.modelData.note
                        font: Kirigami.Theme.smallFont
                        opacity: 0.6
                    }
                }

                // Why there is nothing to show, in one line.
                RowLayout {
                    visible: prov.modelData.message !== ""
                    Layout.fillWidth: true
                    Kirigami.Icon {
                        visible: prov.modelData.level === "bad"
                        source: "dialog-error"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    }
                    PC3.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: prov.modelData.message
                        opacity: 0.7
                    }
                }

                Repeater {
                    model: prov.modelData.windows
                    delegate: ColumnLayout {
                        id: win
                        required property var modelData
                        readonly property int shown: page.remaining ? modelData.remaining : modelData.used
                        readonly property string level: T.levelOf(modelData.remaining, modelData.limited)
                        readonly property color tone: level === "bad" ? Kirigami.Theme.negativeTextColor
                            : level === "warn" ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.highlightColor
                        Layout.fillWidth: true
                        spacing: 3
                        opacity: modelData.dim ? 0.5 : 1

                        RowLayout {
                            Layout.fillWidth: true
                            PC3.Label { text: win.modelData.label; Layout.fillWidth: true; elide: Text.ElideRight }
                            PC3.Label {
                                text: win.modelData.limited ? page.v.text.limitReached : T.pct(page.v, win.shown)
                                font.pointSize: Kirigami.Theme.defaultFont.pointSize * (win.modelData.limited ? 1 : 1.15)
                                font.weight: Font.DemiBold
                                font.features: { "tnum": 1 }
                                color: win.level === "ok" ? Kirigami.Theme.textColor : win.tone
                            }
                            PC3.Label {
                                visible: !win.modelData.limited && page.remaining
                                text: page.v.text.left
                                font: Kirigami.Theme.smallFont
                                opacity: 0.6
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 6
                            radius: 3
                            color: Qt.alpha(Kirigami.Theme.textColor, 0.12)
                            Rectangle {
                                height: parent.height
                                radius: 3
                                width: parent.width * Math.min(100, win.shown) / 100
                                visible: win.shown > 0
                                color: win.tone
                                Behavior on width { NumberAnimation { duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic } }
                            }
                        }
                        PC3.Label {
                            text: win.modelData.reset
                            font: Kirigami.Theme.smallFont
                            opacity: 0.6
                        }
                    }
                }
            }
        }
        Item { Layout.fillHeight: true }
    }
}
