import QtQuick
import QtQuick.Controls.Basic  // own look on every OS; native styles ignore custom backgrounds
import QtQuick.Layouts

// The popup's Settings page. Edits a copy of `backend.settingsForm.values` (see
// ui/settings_form.py) and hands every change to Python right away, which clamps and applies it.
ColumnLayout {
    id: win
    objectName: "settingsPage"
    readonly property var f: backend.settingsForm
    readonly property var t: f.text || ({})
    readonly property var c: backend.palette
    property var draft: ({})
    spacing: 12

    // The page is built each time it opens: start from the current settings, follow tray-menu
    // changes while open, and save a pending change when it closes.
    Component.onCompleted: draft = Object.assign({}, f.values || {})
    onFChanged: {
        if (!f.values) return;
        draft = applyTimer.running ? Object.assign({}, draft, { notify_enabled: f.values.notify_enabled })
                                   : Object.assign({}, f.values);
    }
    Component.onDestruction: flush()
    // Changes apply as they are made. Typed paths wait for a pause so a half-typed one is never used.
    function set(key, value, typed) {
        const d = Object.assign({}, draft);
        d[key] = value;
        draft = d;
        applyTimer.interval = typed ? 800 : 150;
        applyTimer.restart();
    }
    function flush() {
        if (applyTimer.running) {
            applyTimer.stop();
            backend.saveSettings(draft);
        }
    }
    Timer { id: applyTimer; onTriggered: backend.saveSettings(win.draft) }

    Section {
        title: win.t.appearance
        Row2 {
            label: win.t.theme
            Segmented {
                options: [["system", win.t.system], ["light", win.t.light], ["dark", win.t.dark]]
                value: win.draft.theme || "system"
                onPicked: v => win.set("theme", v)
            }
        }
        Row2 {
            label: win.t.accent
            Segmented {
                options: [["slate", win.t.slate], ["ink", win.t.ink], ["amber", win.t.amber]]
                value: win.draft.accent || "slate"
                onPicked: v => win.set("accent", v)
            }
        }
        Row2 {
            label: win.t.language
            Segmented {
                options: [["system", win.t.system], ["en", "English"], ["tr", "Türkçe"]]
                value: win.draft.language || "system"
                onPicked: v => win.set("language", v)
            }
        }
        Row2 {
            label: win.t.remaining
            Toggle { checked: !!win.draft.show_remaining; onToggled: v => win.set("show_remaining", v) }
        }
    }

    Section {
        title: win.t.general
        Row2 {
            label: win.t.autostart
            enabled: !!win.f.autostartSupported
            Toggle { checked: !!win.draft.start_at_login; onToggled: v => win.set("start_at_login", v) }
        }
        Row2 {
            label: win.t.prices
            hint: win.t.pricesHint
            Toggle { checked: !!win.draft.update_prices; onToggled: v => win.set("update_prices", v) }
        }
        Row2 {
            label: win.t.updates
            hint: win.t.updatesHint
            Toggle { checked: !!win.draft.check_updates; onToggled: v => win.set("check_updates", v) }
        }
    }

    // What to be told about, and for which providers. Every alert appears once per limit window.
    Section {
        id: notifySec
        title: win.t.notifications
        readonly property bool on: !!win.draft.notify_enabled && win.f.notifySupported !== false
        function hasLevel(n) { return (win.draft.notify_levels || []).indexOf(n) >= 0; }
        function toggleLevel(n) {
            const cur = (win.draft.notify_levels || []).filter(x => x !== n);
            if (!hasLevel(n))
                cur.push(n);
            win.set("notify_levels", cur.sort((a, b) => a - b));
        }
        Row2 {
            label: win.t.notifyEnabled
            hint: win.f.notifySupported === false ? (win.t.notifyNoTray || "") : (win.t.notifyEnabledHint || "")
            enabled: win.f.notifySupported !== false
            Toggle { checked: !!win.draft.notify_enabled; onToggled: v => win.set("notify_enabled", v) }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            enabled: notifySec.on
            opacity: enabled ? 1 : 0.45
            Text { Layout.fillWidth: true; text: win.t.notifyLevels || ""; color: win.c.text; font.pointSize: 10; wrapMode: Text.WordWrap }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: win.f.notifyLevels || []
                    delegate: Chip {
                        required property var modelData
                        text: (win.t.pct || "{n}%").replace("{n}", modelData)
                        checked: notifySec.hasLevel(modelData)
                        onToggled: notifySec.toggleLevel(modelData)
                    }
                }
            }
            Text { Layout.fillWidth: true; text: win.t.notifyLevelsHint || ""; color: win.c.muted; font.pointSize: 8; wrapMode: Text.WordWrap }
        }
        Row2 {
            label: win.t.notifyLimit
            enabled: notifySec.on
            Toggle { checked: !!win.draft.notify_limit_reached; onToggled: v => win.set("notify_limit_reached", v) }
        }
        Row2 {
            label: win.t.notifyReset
            enabled: notifySec.on
            Toggle { checked: !!win.draft.notify_reset; onToggled: v => win.set("notify_reset", v) }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            enabled: notifySec.on
            opacity: enabled ? 1 : 0.45
            Text { Layout.fillWidth: true; text: win.t.notifyProviders || ""; color: win.c.text; font.pointSize: 10 }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: win.f.providers || []
                    delegate: Chip {
                        required property var modelData
                        text: modelData.name
                        tone: modelData.color
                        checked: !!win.draft["notify_" + modelData.id]
                        onToggled: win.set("notify_" + modelData.id, !checked)
                    }
                }
            }
        }
        Rectangle {
            id: testBtn
            enabled: notifySec.on
            opacity: enabled ? 1 : 0.45
            implicitWidth: testText.implicitWidth + 24
            implicitHeight: 30
            radius: 8
            color: testMouse.containsMouse ? win.c.track : "transparent"
            border.color: win.c.border
            Text { id: testText; anchors.centerIn: parent; text: win.t.notifyTest || ""; color: win.c.text; font.pointSize: 9 }
            MouseArea {
                id: testMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: backend.testNotification()
            }
            Accessible.role: Accessible.Button
            Accessible.name: testText.text
            Accessible.onPressAction: if (enabled) backend.testNotification()
        }
    }

    // One line per provider: track it, and check its account limits.
    Section {
        title: win.t.providers
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Item { Layout.fillWidth: true; implicitHeight: 1 }
            Text { Layout.preferredWidth: 42; horizontalAlignment: Text.AlignHCenter; text: win.t.track || ""; color: win.c.muted; font.pointSize: 8 }
            Text { Layout.preferredWidth: 42; horizontalAlignment: Text.AlignHCenter; text: win.t.limits || ""; color: win.c.muted; font.pointSize: 8 }
        }
        Repeater {
            model: win.f.providers || []
            delegate: RowLayout {
                id: prov
                required property var modelData
                readonly property bool tracked: !!win.draft["enabled_" + modelData.id]
                Layout.fillWidth: true
                spacing: 10
                Rectangle { implicitWidth: 4; implicitHeight: 20; radius: 2; color: prov.modelData.color }
                Text { Layout.fillWidth: true; text: prov.modelData.name; color: win.c.text; font.pointSize: 10 }
                Toggle {
                    name: prov.modelData.name + ": " + (win.t.track || "")
                    tone: prov.modelData.color
                    checked: prov.tracked
                    onToggled: v => win.set("enabled_" + prov.modelData.id, v)
                }
                Toggle {
                    name: prov.modelData.name + ": " + (win.t.limits || "")
                    tone: prov.modelData.color
                    enabled: prov.tracked && prov.modelData.quotaNote === ""
                    opacity: enabled ? 1 : 0.45
                    checked: !!win.draft["quota_" + prov.modelData.id]
                    onToggled: v => win.set("quota_" + prov.modelData.id, v)
                }
            }
        }
    }

    // Rarely changed: closed until asked for.
    Section {
        title: win.t.advanced
        collapsible: true
        Row2 {
            label: win.t.local
            Stepper { from: 15; to: 3600; step: 15; value: win.draft.local_refresh_seconds || 60; onEdited: v => win.set("local_refresh_seconds", v) }
        }
        Row2 {
            label: win.t.quota
            Stepper { from: 60; to: 86400; step: 60; value: win.draft.quota_refresh_seconds || 300; onEdited: v => win.set("quota_refresh_seconds", v) }
        }
        Row2 {
            label: win.t.timeout
            Stepper { from: 5; to: 120; step: 5; value: win.draft.timeout_seconds || 20; onEdited: v => win.set("timeout_seconds", v) }
        }
        Field { label: win.t.claudeCommand; text: win.draft.claude_command || ""; onEdited: v => win.set("claude_command", v, true) }
        Field { label: win.t.codexCommand; text: win.draft.codex_command || ""; onEdited: v => win.set("codex_command", v, true) }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: win.t.privacy || ""
            color: win.c.muted
            font.pointSize: 8
        }
    }

    // -- building blocks ------------------------------------------------------

    // A card with an upper-case title; a collapsible one opens and closes from its title.
    component Section: Rectangle {
        id: sec
        property string title
        property bool collapsible: false
        property bool open: !collapsible
        default property alias content: body.data
        Layout.fillWidth: true
        implicitHeight: inner.implicitHeight + 28
        radius: 14
        color: win.c.card
        border.color: win.c.border
        ColumnLayout {
            id: inner
            x: 14
            y: 12
            width: parent.width - 28
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: sec.title ? sec.title.toLocaleUpperCase(win.t.locale || "en") : ""
                    color: win.c.muted
                    font.pointSize: 8
                    font.weight: Font.DemiBold
                    font.letterSpacing: 0.8
                }
                Text {
                    visible: sec.collapsible
                    text: "›"
                    color: win.c.muted
                    font.pointSize: 12
                    rotation: sec.open ? 90 : 0
                    Behavior on rotation { NumberAnimation { duration: 120 } }
                }
                HoverHandler { enabled: sec.collapsible; cursorShape: Qt.PointingHandCursor }
                TapHandler { enabled: sec.collapsible; onTapped: sec.open = !sec.open }
            }
            ColumnLayout {
                id: body
                visible: sec.open
                Layout.fillWidth: true
                spacing: 10
            }
        }
    }

    // A label (and optional hint) on the left, one control on the right.
    component Row2: RowLayout {
        id: row
        property string label
        property string hint
        default property alias control: slot.data
        Layout.fillWidth: true
        spacing: 12
        opacity: enabled ? 1 : 0.45
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text { Layout.fillWidth: true; text: row.label; color: win.c.text; font.pointSize: 10; wrapMode: Text.WordWrap }
            Text {
                visible: row.hint !== ""
                Layout.fillWidth: true
                text: row.hint
                color: win.c.muted
                font.pointSize: 8
                wrapMode: Text.WordWrap
            }
        }
        Item {
            id: slot
            implicitWidth: childrenRect.width
            implicitHeight: childrenRect.height
        }
    }

    component Toggle: Rectangle {
        id: sw
        // For screen readers; inside a Row2 (slot -> row) its label.
        property string name: parent && parent.parent && parent.parent.label !== undefined ? parent.parent.label : ""
        property bool checked
        property color tone: win.c.accent
        signal toggled(bool value)
        implicitWidth: 42
        implicitHeight: 24
        radius: 12
        color: checked ? tone : win.c.track
        Behavior on color { ColorAnimation { duration: 140 } }
        Rectangle {
            width: 18
            height: 18
            radius: 9
            y: 3
            x: sw.checked ? sw.width - width - 3 : 3
            color: "white"
            Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: sw.toggled(!sw.checked)
        }
        Accessible.role: Accessible.CheckBox
        Accessible.name: name
        Accessible.checked: checked
        Accessible.onToggleAction: if (enabled) toggled(!checked)
        Accessible.onPressAction: if (enabled) toggled(!checked)
    }

    component Segmented: Rectangle {
        id: seg
        property var options: []  // [[value, label], ...]
        property string value
        signal picked(string value)
        implicitWidth: segRow.implicitWidth + 6
        implicitHeight: 32
        radius: 9
        color: win.c.track
        Row {
            id: segRow
            anchors.centerIn: parent
            spacing: 2
            Repeater {
                model: seg.options
                delegate: Rectangle {
                    id: opt
                    required property var modelData
                    readonly property bool current: seg.value === modelData[0]
                    width: optText.implicitWidth + 20
                    height: 26
                    radius: 7
                    color: current ? win.c.card : (optMouse.containsMouse ? Qt.alpha(win.c.card, 0.5) : "transparent")
                    border.color: current ? win.c.border : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }
                    Text {
                        id: optText
                        anchors.centerIn: parent
                        text: opt.modelData[1]
                        color: opt.current ? win.c.text : win.c.muted
                        font.pointSize: 9
                        font.weight: opt.current ? Font.DemiBold : Font.Normal
                    }
                    MouseArea {
                        id: optMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: seg.picked(opt.modelData[0])
                    }
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: opt.modelData[1]
                    Accessible.checked: opt.current
                    Accessible.onPressAction: seg.picked(opt.modelData[0])
                }
            }
        }
    }

    // A pill that is on or off; several can be on at once.
    component Chip: Rectangle {
        id: chip
        property string text
        property bool checked
        property color tone: win.c.accent
        signal toggled()
        implicitWidth: chipText.implicitWidth + 24
        implicitHeight: 28
        radius: 14
        color: checked ? Qt.alpha(tone, 0.18) : (chipMouse.containsMouse ? win.c.track : "transparent")
        border.color: checked ? tone : win.c.border
        Behavior on color { ColorAnimation { duration: 120 } }
        Text {
            id: chipText
            anchors.centerIn: parent
            text: (chip.checked ? "✓ " : "") + chip.text
            color: chip.checked ? win.c.text : win.c.muted
            font.pointSize: 9
            font.weight: chip.checked ? Font.DemiBold : Font.Normal
        }
        MouseArea {
            id: chipMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chip.toggled()
        }
        Accessible.role: Accessible.CheckBox
        Accessible.name: chip.text
        Accessible.checked: checked
        Accessible.onToggleAction: if (enabled) toggled()
        Accessible.onPressAction: if (enabled) toggled()
    }

    component Stepper: Rectangle {
        id: st
        property int value
        property int from
        property int to
        property int step: 1
        signal edited(int value)
        function commit(v) { st.edited(Math.max(from, Math.min(to, v))); }
        implicitWidth: 150
        implicitHeight: 32
        radius: 8
        color: win.c.bg
        border.color: win.c.border
        RowLayout {
            anchors.fill: parent
            spacing: 0
            StepButton { glyph: "−"; onClicked: st.commit(st.value - st.step) }
            TextInput {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: st.value
                color: win.c.text
                font.pointSize: 10
                font.features: { "tnum": 1 }
                validator: IntValidator { bottom: 0; top: 999999 }
                selectByMouse: true
                onEditingFinished: st.commit(parseInt(text) || st.from)
            }
            Text { text: win.t.seconds || "s"; color: win.c.muted; font.pointSize: 8.5; rightPadding: 4 }
            StepButton { glyph: "+"; onClicked: st.commit(st.value + st.step) }
        }
    }

    component StepButton: Rectangle {
        id: sb
        property string glyph
        signal clicked()
        implicitWidth: 30
        implicitHeight: 30
        radius: 7
        color: sbMouse.containsMouse ? win.c.track : "transparent"
        Text { anchors.centerIn: parent; text: sb.glyph; color: win.c.text; font.pointSize: 12 }
        MouseArea {
            id: sbMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: sb.clicked()
        }
    }

    component Field: ColumnLayout {
        id: fld
        property string label
        property string text
        signal edited(string value)
        Layout.fillWidth: true
        spacing: 4
        Text { text: fld.label; color: win.c.text; font.pointSize: 9.5 }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 32
            radius: 8
            color: win.c.bg
            border.color: input.activeFocus ? win.c.accent : win.c.border
            TextInput {
                id: input
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                verticalAlignment: Text.AlignVCenter
                text: fld.text
                color: win.c.text
                font.family: "monospace"
                font.pointSize: 9.5
                selectByMouse: true
                clip: true
                onTextEdited: fld.edited(text)
            }
        }
    }

}
