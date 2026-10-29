import QtQuick
import QtQuick.Controls.Basic  // own look on every OS; native styles ignore custom backgrounds
import QtQuick.Layouts
import "Theme.js" as T

// One screen: a ring card per provider (outer ring 5 hours, inner ring weekly, in the provider's
// colour) and a strip of locally recorded tokens. Data: viewmodel.widget_view() as `backend.view`.
Item {
    id: popup
    objectName: "popupContent"
    readonly property var v: backend.view
    readonly property var c: backend.palette
    readonly property bool remaining: backend.prefs.showRemaining
    // Token strip: all providers together, or one picked from the chips above it.
    property string tokGroup: "all"
    readonly property var tok: v ? (v.tokens.data[tokGroup] || v.tokens.data["all"]) : null
    readonly property color tokColor: {
        for (const g of (v ? v.tokens.groups : [])) if (g.key === tokGroup && g.color) return g.color;
        return c.accent;
    }
    implicitHeight: body.implicitHeight + 28

    // Slide up, fade in and sweep the rings each time the window is shown.
    function animateIn() {
        intro.restart();
        for (let i = 0; i < cards.count; i++)
            cards.itemAt(i).sweep();
    }

    function periodLabel(key) {
        for (const p of (v ? v.tokens.periods : [])) if (p.key === key) return p.label;
        return key;
    }

    Rectangle {
        id: frame
        anchors.fill: parent
        radius: 16
        color: popup.c.bg
        border.color: popup.c.border
        transform: Translate { id: slide }

        ParallelAnimation {
            id: intro
            NumberAnimation { target: frame; property: "opacity"; from: 0; to: 1; duration: 160; easing.type: Easing.OutCubic }
            NumberAnimation { target: slide; property: "y"; from: 14; to: 0; duration: 220; easing.type: Easing.OutCubic }
        }

        ColumnLayout {
            id: body
            anchors.fill: parent
            anchors.margins: 14
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    text: popup.v ? popup.v.labels.title : "QuotaRing"
                    color: popup.c.text
                    font.pointSize: 12
                    font.weight: Font.DemiBold
                }
                IconButton {
                    c: popup.c
                    kind: "refresh"
                    tip: popup.v ? popup.v.labels.refresh : "Refresh"
                    enabled: !backend.busy
                    spinning: backend.busy
                    onClicked: backend.refresh()
                }
                IconButton {
                    c: popup.c
                    kind: "settings"
                    tip: popup.v ? popup.v.labels.settings : "Settings"
                    onClicked: backend.openSettings()
                }
            }

            Text {
                visible: !popup.v || popup.v.limits.length === 0
                Layout.fillWidth: true
                Layout.topMargin: 20
                Layout.bottomMargin: 20
                horizontalAlignment: Text.AlignHCenter
                color: popup.c.muted
                text: !popup.v ? (Qt.locale().name.startsWith("tr") ? "Yükleniyor…" : "Loading…") : popup.v.text.noLimits
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 10
                rowSpacing: 10
                Repeater {
                    id: cards
                    model: popup.v ? popup.v.limits : []
                    delegate: ProviderCard {}
                }
            }

            // Locally recorded tokens: today and 7 days, with the last 7 days as bars.
            Rectangle {
                visible: !!popup.tok
                Layout.fillWidth: true
                implicitHeight: stripBox.implicitHeight + 20
                radius: 12
                color: popup.c.card
                border.color: popup.c.border
                ColumnLayout {
                id: stripBox
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8
                // All / per-provider chips; hidden while only one provider has local data.
                Row {
                    visible: chips.count > 2
                    spacing: 4
                    Repeater {
                        id: chips
                        model: popup.v ? popup.v.tokens.groups : []
                        delegate: Rectangle {
                            id: chip
                            required property var modelData
                            readonly property bool active: (popup.v.tokens.data[popup.tokGroup] ? popup.tokGroup : "all") === modelData.key
                            width: chipRow.implicitWidth + 14
                            height: chipRow.implicitHeight + 6
                            radius: height / 2
                            color: active ? popup.c.track : (chipHover.hovered ? Qt.alpha(popup.c.track, 0.5) : "transparent")
                            Row {
                                id: chipRow
                                anchors.centerIn: parent
                                spacing: 5
                                Rectangle {
                                    visible: !!chip.modelData.color
                                    width: 7; height: 7; radius: 3.5
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: chip.modelData.color || "transparent"
                                }
                                Text {
                                    text: chip.modelData.label
                                    color: chip.active ? popup.c.text : popup.c.muted
                                    font.pointSize: 8.5
                                    font.weight: chip.active ? Font.DemiBold : Font.Normal
                                }
                            }
                            HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: popup.tokGroup = chip.modelData.key }
                        }
                    }
                }
                RowLayout {
                    id: strip
                    Layout.fillWidth: true
                    spacing: 14
                    Repeater {
                        model: ["today", "7d"]
                        delegate: Column {
                            required property string modelData
                            Text {
                                text: popup.tok ? popup.tok.periods[parent.modelData].totalText : ""
                                color: popup.c.text
                                font.pointSize: 13
                                font.weight: Font.DemiBold
                                font.features: { "tnum": 1 }
                            }
                            Text {
                                text: popup.periodLabel(parent.modelData)
                                color: popup.c.muted
                                font.pointSize: 8.5
                            }
                        }
                    }
                    Row {
                        id: bars
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 3
                        readonly property var days: popup.tok ? popup.tok.daily : []
                        Repeater {
                            model: bars.days
                            delegate: Item {
                                id: day
                                required property var modelData
                                width: (bars.width - bars.spacing * (bars.days.length - 1)) / Math.max(1, bars.days.length)
                                height: bars.height
                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    radius: 2
                                    height: Math.max(2, parent.height * day.modelData.ratio)
                                    color: day.modelData.value > 0 ? (hover.containsMouse ? popup.c.text : popup.tokColor) : popup.c.track
                                    Behavior on height { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                                }
                                MouseArea { id: hover; anchors.fill: parent; hoverEnabled: true }
                                ToolTip.visible: hover.containsMouse
                                ToolTip.text: day.modelData.label + ": " + day.modelData.text
                            }
                        }
                    }
                }
                }
                HoverHandler { id: stripHover }
                ToolTip.visible: stripHover.hovered && !!popup.v
                ToolTip.delay: 800
                ToolTip.text: popup.v ? popup.v.text.localOnly : ""
            }

            Text {
                visible: !!popup.v
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignRight
                font.pointSize: 8
                color: popup.c.muted
                text: popup.v ? popup.v.text.updated : ""
            }
        }
    }

    component ProviderCard: Rectangle {
        id: card
        objectName: "providerCard"
        required property var modelData
        readonly property var w: modelData.windows
        readonly property var first: w.length > 0 ? w[0] : null
        readonly property var second: w.length > 1 ? w[1] : null
        // The tightest window decides the number in the middle and the warning colour.
        readonly property var tight: {
            let t = null;
            for (const x of w) if (!x.dim && (!t || x.remaining < t.remaining)) t = x;
            return t || first;
        }
        readonly property string level: tight ? T.levelOf(tight.remaining, tight.limited) : "muted"
        readonly property color tone: level === "bad" ? popup.c.bad : level === "warn" ? popup.c.warn : modelData.color

        // More limits than two rings (Antigravity: one per model): one ring for the chosen limit.
        readonly property bool multi: w.length > 2
        readonly property int tightIndex: w.indexOf(tight)
        // A clicked row stays on the ring (saved in settings); click it again to release it.
        readonly property int pinnedIndex: {
            const label = (backend.prefs.pinned || {})[modelData.id];
            for (let i = 0; i < w.length; i++) if (w[i].label === label) return i;
            return -1;
        }
        // Hovering a row previews it; leaving goes back to the pinned limit.
        property int rowHover: -1
        readonly property int lit: rowHover >= 0 ? rowHover
            : (!multi && ring.hoverRing >= 0) ? ring.hoverRing : pinnedIndex
        readonly property var litWindow: lit >= 0 && lit < w.length ? w[lit] : null
        readonly property int hoverLit: rowHover >= 0 ? rowHover : (!multi && ring.hoverRing >= 0) ? ring.hoverRing : -1
        // What a single-ring card draws: the lit limit, else the tightest one.
        readonly property var ringWindow: multi ? (litWindow || tight) : null
        // A model row (Antigravity) carries its 5-hour and weekly limits: both go on the rings.
        readonly property var ringPair: ringWindow ? (ringWindow.pair || [ringWindow]) : []
        readonly property var ringInner: ringPair.length > 1 ? ringPair[1] : null

        function shown(x) { return popup.remaining ? x.remaining : x.used; }
        function toneOf(x) {
            const lv = T.levelOf(x.remaining, x.limited);
            return lv === "bad" ? popup.c.bad : lv === "warn" ? popup.c.warn : modelData.color;
        }
        function valueText(x) {
            return x.limited ? popup.v.text.limitReached
                : T.pct(popup.v, shown(x)) + " " + (popup.remaining ? popup.v.text.left : popup.v.text.used);
        }
        function sweep() { ring.sweep(); }

        Layout.fillWidth: true
        Layout.preferredWidth: 1  // equal columns
        Layout.alignment: Qt.AlignTop
        implicitHeight: col.implicitHeight + 24
        radius: 14
        color: popup.c.card
        border.color: popup.c.border

        ColumnLayout {
            id: col
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8

            RingGauge {
                id: ring
                Layout.alignment: Qt.AlignHCenter
                implicitWidth: 120
                implicitHeight: 120
                outer: card.multi ? card.shown(card.ringPair[0]) : card.first ? card.shown(card.first) : -1
                inner: card.multi ? (card.ringInner ? card.shown(card.ringInner) : -1)
                    : card.second ? card.shown(card.second) : -1
                outerTag: card.multi ? card.ringPair[0].tag : card.first ? card.first.tag : ""
                innerTag: card.multi ? (card.ringInner ? card.ringInner.tag : "") : card.second ? card.second.tag : ""
                tagBackground: popup.c.card
                highlight: card.multi ? -1 : card.lit
                outerColor: card.multi ? card.toneOf(card.ringPair[0])
                    : card.first && card.first === card.tight ? card.tone : card.modelData.color
                innerColor: card.multi && card.ringInner && T.levelOf(card.ringInner.remaining, card.ringInner.limited) !== "ok"
                    ? card.toneOf(card.ringInner)
                    : !card.multi && card.second && card.second === card.tight ? card.tone
                    : Qt.tint(popup.c.card, Qt.alpha(card.modelData.color, 0.6))
                track: popup.c.track
                // Coloured only when the limit shown in the middle is low.
                textColor: !showing || T.levelOf(showing.remaining, showing.limited) === "ok" ? popup.c.text : card.toneOf(showing)
                subColor: popup.c.muted
                // The middle follows the highlighted ring, else shows the tightest limit.
                readonly property var showing: card.multi ? card.ringWindow : (card.litWindow || card.tight)
                centerText: !showing ? "—" : showing.limited ? "0" : T.pct(popup.v, card.shown(showing))
                label: showing ? showing.label : ""
                subText: !showing ? "" : showing.limited ? popup.v.text.limitReached
                    : popup.remaining ? popup.v.text.left : popup.v.text.used
                opacity: showing && showing.dim ? 0.5 : 1

                readonly property var tipWindow: !card.multi ? card.litWindow
                    : ring.hoverRing === 1 && card.ringInner ? card.ringInner : card.ringPair[0]
                ToolTip.visible: !!tipWindow && ring.hoverRing >= 0
                ToolTip.text: tipWindow ? tipWindow.label + ": " + card.valueText(tipWindow) + " · " + tipWindow.reset : ""
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: 6
                Text {
                    text: card.modelData.name
                    color: popup.c.text
                    font.pointSize: 10.5
                    font.weight: Font.DemiBold
                }
                Rectangle {
                    visible: card.modelData.plan !== ""
                    radius: height / 2
                    color: Qt.alpha(card.modelData.color, 0.2)
                    implicitHeight: plan.implicitHeight + 4
                    implicitWidth: plan.implicitWidth + 10
                    Text {
                        id: plan
                        anchors.centerIn: parent
                        text: card.modelData.plan
                        font.pointSize: 8
                        color: card.modelData.color
                    }
                }
            }

            Text {
                visible: card.modelData.message !== ""
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                font.pointSize: 8.5
                color: card.modelData.level === "bad" ? popup.c.bad : popup.c.muted
                text: card.modelData.message
            }

            // One line per limit: its ring tag, value and reset. Click to keep it on the ring.
            Repeater {
                model: card.w
                delegate: Rectangle {
                    id: row
                    required property var modelData
                    required property int index
                    readonly property bool pinned: card.pinnedIndex === index
                    readonly property bool onRing: card.multi ? card.ringWindow === modelData : index < 2
                    Layout.fillWidth: true
                    Layout.leftMargin: -6
                    Layout.rightMargin: -6
                    implicitHeight: rowCol.implicitHeight + 6
                    radius: 7
                    color: pinned ? Qt.alpha(card.modelData.color, 0.14) : rowHoverHandler.hovered ? popup.c.track : "transparent"
                    border.color: pinned ? Qt.alpha(card.modelData.color, 0.45) : "transparent"
                    opacity: modelData.dim || (card.hoverLit >= 0 && card.hoverLit !== index) ? 0.45 : 1
                    Behavior on opacity { NumberAnimation { duration: 120 } }
                    Behavior on color { ColorAnimation { duration: 120 } }
                    HoverHandler {
                        id: rowHoverHandler
                        cursorShape: Qt.PointingHandCursor
                        onHoveredChanged: card.rowHover = hovered ? row.index : (card.rowHover === row.index ? -1 : card.rowHover)
                    }
                    TapHandler { onTapped: backend.pin(card.modelData.id, row.modelData.label) }
                    ColumnLayout {
                        id: rowCol
                        anchors.fill: parent
                        anchors.leftMargin: 6
                        anchors.rightMargin: 6
                        anchors.topMargin: 3
                        spacing: 1
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            // The same tag as on the ring, in the ring's colour while it is on the ring.
                            Text {
                                visible: !card.multi  // per-model rows are named in full
                                Layout.preferredWidth: 18
                                text: row.modelData.tag
                                color: !row.onRing ? popup.c.muted
                                    : card.multi || row.index === 0 ? ring.outerColor : ring.innerColor
                                font.pointSize: 8
                                font.weight: Font.Bold
                            }
                            Text { text: row.modelData.label; color: popup.c.text; font.pointSize: 9; Layout.fillWidth: true; elide: Text.ElideRight }
                            Text {
                                text: row.modelData.limited ? "!" : T.pct(popup.v, card.shown(row.modelData))
                                color: row.modelData.limited ? popup.c.bad : popup.c.text
                                font.pointSize: 9
                                font.weight: Font.DemiBold
                                font.features: { "tnum": 1 }
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.leftMargin: card.multi ? 0 : 23
                            text: row.modelData.reset
                            wrapMode: Text.WordWrap
                            font.pointSize: 7.5
                            color: popup.c.muted
                        }
                    }
                }
            }

            Text {
                visible: card.modelData.note !== ""
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: card.modelData.note
                font.pointSize: 7.5
                color: popup.c.warn
            }
        }
    }
}
