import QtQuick
import QtQuick.Controls.Basic  // own look on every OS; native styles ignore custom backgrounds
import QtQuick.Layouts
import "Theme.js" as T

// Three pages under one fixed header. Limits: a ring card per provider (outer ring 5 hours,
// inner ring weekly, in the provider's colour) and a strip of locally recorded tokens; clicking
// the strip opens Tokens: totals by period, API-price estimate, daily columns and a per-model
// breakdown. The gear opens Settings. Data: viewmodel.widget_view() as `backend.view`.
Item {
    id: popup
    objectName: "popupContent"
    readonly property var v: backend.view
    readonly property var c: backend.palette
    readonly property bool remaining: backend.prefs.showRemaining
    property string page: "limits"  // "limits" | "tokens" | "settings"
    onPageChanged: flick.contentY = 0
    // Token strip: all providers together, or one picked from the chips above it.
    property string tokGroup: "all"
    property string tokPeriod: "7d"  // the Tokens page's period
    // Provider cards in the user's order (saved), then any not placed yet; `dragOrder` while a
    // card is being dragged, so the others make room as it moves.
    property var dragOrder: null
    readonly property var cardOrder: {
        const ids = v ? v.limits.map(l => l.id) : [];
        const saved = (backend.prefs.order || []).filter(id => ids.indexOf(id) >= 0);
        return dragOrder || saved.concat(ids.filter(id => saved.indexOf(id) < 0));
    }
    function moveCard(id, to) {
        const o = cardOrder.filter(x => x !== id);
        o.splice(to, 0, id);
        dragOrder = o;
    }
    readonly property var tok: v ? (v.tokens.data[tokGroup] || v.tokens.data["all"]) : null
    readonly property var tokNow: tok ? tok.periods[tokPeriod] : null
    readonly property color tokColor: {
        for (const g of (v ? v.tokens.groups : [])) if (g.key === tokGroup && g.color) return g.color;
        return c.accent;
    }
    implicitHeight: header.implicitHeight + body.spacing + pages.implicitHeight + 28

    // Slide up, fade in and sweep the rings each time the window is shown.
    function animateIn() {
        page = "limits";
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
                id: header
                Layout.fillWidth: true
                spacing: 2
                IconButton {
                    visible: popup.page !== "limits"
                    Layout.leftMargin: -6
                    c: popup.c
                    kind: "back"
                    tip: popup.v ? popup.v.text.back : "Back"
                    onClicked: popup.page = "limits"
                }
                Logo {
                    visible: popup.page === "limits"
                    Layout.rightMargin: 6
                    color: popup.c.accent
                }
                Text {
                    Layout.fillWidth: true
                    text: !popup.v ? "QuotaRing" : popup.page === "tokens" ? popup.v.text.tokenUsage
                        : popup.page === "settings" ? popup.v.labels.settings : popup.v.labels.title
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
                    onClicked: popup.page === "settings" ? popup.page = "limits" : backend.openSettings()
                }
            }

            // Pages scroll under the fixed header when they are taller than the screen allows.
            Flickable {
                id: flick
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.rightMargin: -10  // the scroll bar sits in the frame's margin
                contentHeight: pages.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                interactive: popup.dragOrder === null  // a dragged card must not scroll the page
                ScrollBar.vertical: ScrollBar {
                    id: vbar
                    policy: flick.contentHeight > flick.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
                    contentItem: Rectangle { implicitWidth: 4; radius: 2; color: popup.c.muted; opacity: vbar.active ? 0.8 : 0.4 }
                }

                ColumnLayout {
                    id: pages
                    width: flick.width - 10
                    spacing: 12

                    Text {
                        visible: popup.page === "limits" && (!popup.v || popup.v.limits.length === 0)
                        Layout.fillWidth: true
                        Layout.topMargin: 20
                        Layout.bottomMargin: 20
                        horizontalAlignment: Text.AlignHCenter
                        color: popup.c.muted
                        text: !popup.v ? (Qt.locale().name.startsWith("tr") ? "Yükleniyor…" : "Loading…") : popup.v.text.noLimits
                    }

                    GridLayout {
                        id: grid
                        visible: popup.page === "limits"
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
                    // Clicking it opens the Tokens page.
                    Rectangle {
                        visible: popup.page === "limits" && !!popup.tok
                        Layout.fillWidth: true
                        implicitHeight: stripBox.implicitHeight + 20
                        radius: 12
                        color: stripHover.hovered ? Qt.tint(popup.c.card, Qt.alpha(popup.c.track, 0.5)) : popup.c.card
                        border.color: popup.c.border
                        TapHandler { onTapped: popup.page = "tokens" }
                        ColumnLayout {
                        id: stripBox
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 8
                        RowLayout {
                            Layout.fillWidth: true
                            // All / per-provider chips; hidden while only one provider has local data.
                            GroupChips { visible: count > 2 }
                            Item { Layout.fillWidth: true; implicitHeight: 1 }
                            Text {
                                text: (popup.v ? popup.v.text.details : "") + " ›"
                                color: stripHover.hovered ? popup.c.text : popup.c.muted
                                font.pointSize: 8.5
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
                                        Tip { visible: hover.containsMouse; delay: 0; text: day.modelData.label + ": " + day.modelData.text }
                                    }
                                }
                            }
                        }
                        }
                        HoverHandler { id: stripHover; cursorShape: Qt.PointingHandCursor }
                        Tip { visible: stripHover.hovered && !!popup.v; delay: 800; text: popup.v ? popup.v.text.localOnly : "" }
                    }

                    TokenDetails {
                        visible: popup.page === "tokens" && !!popup.tokNow
                        Layout.fillWidth: true
                    }

                    // Built when opened, so it always starts from the current settings.
                    Loader {
                        active: popup.page === "settings"
                        visible: active
                        Layout.fillWidth: true
                        sourceComponent: SettingsPage {}
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
        // The ring under the mouse on a model card: its limit takes the middle, like on the others.
        readonly property var hoverPair: multi && ring.hoverRing >= 0 && ring.hoverRing < ringPair.length
            ? ringPair[ring.hoverRing] : null

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

        // Dragged to a new place; the order is saved on release.
        readonly property int slot: Math.max(0, popup.cardOrder.indexOf(modelData.id))
        property bool dragging: false
        property point grab  // where the card was taken, inside it
        property point ptr   // the pointer, in the grid
        function drop() {
            if (!dragging) return;
            dragging = false;
            backend.setCardOrder(popup.dragOrder);
            popup.dragOrder = null;
        }

        Layout.row: Math.floor(slot / 2)
        Layout.column: slot % 2
        Layout.fillWidth: true
        Layout.preferredWidth: 1  // equal columns
        Layout.alignment: Qt.AlignTop
        implicitHeight: col.implicitHeight + 24
        radius: 14
        color: popup.c.card
        border.color: dragging ? Qt.alpha(modelData.color, 0.7) : popup.c.border
        z: dragging ? 10 : 0
        scale: dragging ? 1.03 : 1
        Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        // The others glide to their new place; the dragged one follows the pointer.
        Behavior on x { enabled: popup.dragOrder !== null && !card.dragging; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        Behavior on y { enabled: popup.dragOrder !== null && !card.dragging; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        transform: Translate {
            x: card.dragging ? card.ptr.x - card.grab.x - card.x : 0
            y: card.dragging ? card.ptr.y - card.grab.y - card.y : 0
            Behavior on x { enabled: !card.dragging; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
            Behavior on y { enabled: !card.dragging; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        }

        // Press and drag anywhere on the card, rows included, to move it. The low threshold and
        // the grab it keeps let the card win over the page's scrolling; a click (no movement)
        // still reaches the rows.
        DragHandler {
            id: mover
            target: null
            dragThreshold: 4
            grabPermissions: PointerHandler.CanTakeOverFromAnything
            onActiveChanged: {
                if (active) {
                    card.grab = centroid.pressPosition;
                    card.ptr = card.mapToItem(grid, centroid.pressPosition.x, centroid.pressPosition.y);
                    popup.dragOrder = popup.cardOrder.slice();
                    card.dragging = true;
                } else {
                    card.drop();
                }
            }
            onCentroidChanged: {
                if (!card.dragging) return;
                card.ptr = grid.mapFromItem(null, centroid.scenePosition.x, centroid.scenePosition.y);
                // The card whose place is under the pointer (by layout, not by where the dragged
                // card is drawn: it is always under the pointer itself).
                for (const other of grid.children) {
                    if (other === card || other.objectName !== "providerCard") continue;
                    if (card.ptr.x >= other.x && card.ptr.x < other.x + other.width
                            && card.ptr.y >= other.y && card.ptr.y < other.y + other.height) {
                        popup.moveCard(card.modelData.id, other.slot);
                        break;
                    }
                }
            }
        }

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
                highlight: card.multi ? (card.hoverPair ? ring.hoverRing : -1) : card.lit
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
                readonly property var showing: card.multi ? (card.hoverPair || card.ringWindow) : (card.litWindow || card.tight)
                centerText: !showing ? "—" : showing.limited ? "0" : T.pct(popup.v, card.shown(showing))
                // Which limit the number is ("5 hours", "Weekly"); a model card names the model below.
                label: !showing ? "" : card.hoverPair ? card.hoverPair.short : card.multi ? showing.short : showing.label
                subText: !showing ? "" : showing.limited ? popup.v.text.limitReached
                    : popup.remaining ? popup.v.text.left : popup.v.text.used
                opacity: showing && showing.dim ? 0.5 : 1

                readonly property var tipWindow: !card.multi ? card.litWindow
                    : ring.hoverRing === 1 && card.ringInner ? card.ringInner : card.ringPair[0]
                Tip {
                    visible: !!ring.tipWindow && ring.hoverRing >= 0
                    text: ring.tipWindow ? ring.tipWindow.label + ": " + card.valueText(ring.tipWindow) + " · " + ring.tipWindow.reset : ""
                }
            }

            // The model on the rings, small, under them.
            Text {
                visible: card.multi && !!card.ringWindow && !!card.ringWindow.pair
                Layout.alignment: Qt.AlignHCenter
                Layout.maximumWidth: col.width
                Layout.topMargin: -4
                text: visible ? card.ringWindow.label : ""
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: popup.c.muted
                font.pointSize: 8.5
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
                            Text { text: row.modelData.label; textFormat: Text.PlainText; color: popup.c.text; font.pointSize: 9; Layout.fillWidth: true; elide: Text.ElideRight }
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

    // A pill that can be picked; `dot` adds a provider colour.
    component Chip: Rectangle {
        id: chip
        property string label
        property color dot: "transparent"
        property bool active
        signal picked()
        implicitWidth: chipRow.implicitWidth + 14
        implicitHeight: chipRow.implicitHeight + 6
        radius: height / 2
        color: active ? popup.c.track : (chipHover.hovered ? Qt.alpha(popup.c.track, 0.5) : "transparent")
        Row {
            id: chipRow
            anchors.centerIn: parent
            spacing: 5
            Rectangle {
                visible: chip.dot.a > 0
                width: 7; height: 7; radius: 3.5
                anchors.verticalCenter: parent.verticalCenter
                color: chip.dot
            }
            Text {
                text: chip.label
                color: chip.active ? popup.c.text : popup.c.muted
                font.pointSize: 8.5
                font.weight: chip.active ? Font.DemiBold : Font.Normal
            }
        }
        HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: chip.picked() }
    }

    // All / Claude / Codex / Antigravity.
    component GroupChips: Row {
        readonly property int count: rep.count
        spacing: 4
        Repeater {
            id: rep
            model: popup.v ? popup.v.tokens.groups : []
            delegate: Chip {
                required property var modelData
                label: modelData.label
                dot: modelData.color || "transparent"
                active: (popup.v.tokens.data[popup.tokGroup] ? popup.tokGroup : "all") === modelData.key
                onPicked: popup.tokGroup = modelData.key
            }
        }
    }

    component Card: Rectangle {
        default property alias content: inner.data
        Layout.fillWidth: true
        implicitHeight: inner.implicitHeight + 24
        radius: 12
        color: popup.c.card
        border.color: popup.c.border
        ColumnLayout {
            id: inner
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8
        }
    }

    component SectionTitle: Text {
        color: popup.c.text
        font.pointSize: 10
        font.weight: Font.DemiBold
    }

    // Tokens page: period and provider chips, the total with its API-price estimate and
    // input/output/cache split, daily columns with their values, and every model.
    component TokenDetails: ColumnLayout {
        id: td
        readonly property var p: popup.tokNow
        readonly property bool empty: !p || p.total === 0
        spacing: 10

        Flow {
            Layout.fillWidth: true
            spacing: 4
            Repeater {
                model: popup.v ? popup.v.tokens.periods : []
                delegate: Chip {
                    required property var modelData
                    label: modelData.label
                    active: popup.tokPeriod === modelData.key
                    onPicked: popup.tokPeriod = modelData.key
                }
            }
        }
        GroupChips { visible: count > 2 }

        Card {
            Text {
                text: td.p ? td.p.totalText : ""
                color: popup.c.text
                font.pointSize: 22
                font.weight: Font.DemiBold
                font.features: { "tnum": 1 }
            }
            Text {
                Layout.topMargin: -6
                text: popup.v ? popup.v.text.total.replace("{period}", popup.periodLabel(popup.tokPeriod)) : ""
                color: popup.c.muted
                font.pointSize: 8.5
            }
            Text {
                visible: !td.empty
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: td.p && popup.v ? popup.v.text.apiCost.replace("{cost}", td.p.costText) : ""
                color: popup.c.text
                font.pointSize: 10
            }
            // Each provider's share while all are shown.
            Flow {
                visible: popup.tokGroup === "all" && !!td.p && td.p.providers.length > 1
                Layout.fillWidth: true
                spacing: 12
                Repeater {
                    model: td.p ? td.p.providers : []
                    delegate: Row {
                        required property var modelData
                        spacing: 5
                        Rectangle { width: 8; height: 8; radius: 2; color: parent.modelData.color; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: parent.modelData.name; color: popup.c.text; font.pointSize: 9 }
                        Text { text: parent.modelData.text; color: popup.c.text; font.pointSize: 9; font.weight: Font.DemiBold; font.features: { "tnum": 1 } }
                        Text { text: parent.modelData.cost; color: popup.c.muted; font.pointSize: 9; font.features: { "tnum": 1 } }
                    }
                }
            }
            // Where the tokens went: fresh input, output, and the cache.
            GridLayout {
                visible: !td.empty
                Layout.fillWidth: true
                Layout.topMargin: 2
                columns: 4
                columnSpacing: 6
                Repeater {
                    model: ["input", "output", "cacheRead", "cacheWrite"]
                    delegate: Column {
                        required property string modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        spacing: 1
                        Text {
                            text: td.p ? td.p.parts[parent.modelData] : ""
                            color: popup.c.text
                            font.pointSize: 10
                            font.weight: Font.DemiBold
                            font.features: { "tnum": 1 }
                        }
                        Text { text: popup.v ? popup.v.text[parent.modelData] : ""; color: popup.c.muted; font.pointSize: 7.5 }
                    }
                }
            }
        }

        Card {
            visible: !!popup.tok && popup.tok.daily.length > 0
            SectionTitle { text: popup.v ? popup.v.text.daily : "" }
            // Columns over a light grid; each column carries its value so days compare by number.
            Item {
                id: chart
                Layout.fillWidth: true
                implicitHeight: 150
                readonly property var days: popup.tok ? popup.tok.daily : []
                readonly property real axisW: 34
                readonly property real topPad: 16   // room for the tallest column's label
                readonly property real bottomPad: 18  // date labels
                readonly property real plotH: height - topPad - bottomPad
                Repeater {
                    model: [1, 0.5, 0]
                    delegate: Item {
                        required property real modelData
                        width: chart.width
                        y: chart.topPad + chart.plotH * (1 - modelData)
                        Rectangle { x: chart.axisW; width: parent.width - chart.axisW; height: 1; color: popup.c.track }
                        Text {
                            visible: parent.modelData > 0 && !!popup.tok && popup.tok.daily.some(d => d.value > 0)
                            y: -height / 2
                            width: chart.axisW - 6
                            horizontalAlignment: Text.AlignRight
                            text: !popup.tok ? "" : parent.modelData === 1 ? popup.tok.peakText : popup.tok.halfText
                            color: popup.c.muted
                            font.pointSize: 7
                        }
                    }
                }
                Row {
                    x: chart.axisW + 4
                    width: chart.width - x
                    height: chart.height
                    spacing: 6
                    Repeater {
                        model: chart.days
                        delegate: Item {
                            id: col
                            required property var modelData
                            width: (parent.width - parent.spacing * (chart.days.length - 1)) / Math.max(1, chart.days.length)
                            height: parent.height
                            readonly property real barH: modelData.value > 0 ? Math.max(3, chart.plotH * modelData.ratio) : 0
                            Rectangle {
                                id: bar
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: Math.min(parent.width, 30)
                                y: chart.topPad + chart.plotH - height
                                height: col.barH
                                radius: 3
                                color: colHover.hovered ? Qt.lighter(popup.tokColor, 1.25) : popup.tokColor
                                Behavior on height { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                            }
                            Text {
                                visible: col.modelData.value > 0
                                anchors.horizontalCenter: parent.horizontalCenter
                                y: bar.y - height - 1
                                text: col.modelData.text
                                color: popup.c.text
                                font.pointSize: 7
                                font.features: { "tnum": 1 }
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                y: chart.topPad + chart.plotH + 3
                                text: col.modelData.label
                                color: popup.c.muted
                                font.pointSize: 7
                            }
                            HoverHandler { id: colHover }
                        }
                    }
                }
            }
        }

        Card {
            SectionTitle { text: popup.v ? popup.v.text.byModel : "" }
            Text {
                visible: td.empty
                text: popup.v ? popup.v.text.noData : ""
                color: popup.c.muted
                font.pointSize: 9
            }
            Repeater {
                model: td.p ? td.p.models : []
                delegate: ColumnLayout {
                    id: m
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 3
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Rectangle { width: 8; height: 8; radius: 2; color: m.modelData.color }
                        Text {
                            text: m.modelData.name
                            textFormat: Text.PlainText  // model ids come from local logs
                            color: popup.c.text
                            font.pointSize: 9.5
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            visible: popup.tokGroup === "all"
                            text: m.modelData.provider
                            color: popup.c.muted
                            font.pointSize: 8
                        }
                        Text {
                            text: m.modelData.cost
                            color: popup.c.muted
                            font.pointSize: 9
                            font.features: { "tnum": 1 }
                        }
                        Text {
                            text: m.modelData.text
                            color: popup.c.text
                            font.pointSize: 9.5
                            font.weight: Font.DemiBold
                            font.features: { "tnum": 1 }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 5
                        radius: 2.5
                        color: popup.c.track
                        Rectangle {
                            width: parent.width * m.modelData.ratio
                            height: parent.height
                            radius: 2.5
                            color: m.modelData.color
                            Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.bottomMargin: 4
                        wrapMode: Text.WordWrap
                        text: popup.v ? [popup.v.text.input + " " + m.modelData.parts.input,
                                         popup.v.text.output + " " + m.modelData.parts.output,
                                         popup.v.text.cacheRead + " " + m.modelData.parts.cacheRead,
                                         popup.v.text.cacheWrite + " " + m.modelData.parts.cacheWrite].join(" · ") : ""
                        color: popup.c.muted
                        font.pointSize: 7.5
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: !popup.v || !td.p ? "" : popup.v.text.priceNote + (td.p.unpriced ? " " + popup.v.text.unpriced : "")
            color: popup.c.muted
            font.pointSize: 7.5
        }
    }
}
