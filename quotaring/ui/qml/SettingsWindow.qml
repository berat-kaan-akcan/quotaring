import QtQuick
import QtQuick.Controls.Basic  // own look on every OS; native styles ignore custom backgrounds
import QtQuick.Layouts

// Settings, in the popup's look. Edits a draft of `backend.settingsForm.values` (see
// ui/settings_form.py); Save hands it to Python, which clamps and applies it.
Window {
    id: win
    readonly property var f: backend.settingsForm
    readonly property var t: f.text || ({})
    readonly property var c: backend.palette
    property var draft: ({})

    width: 480
    height: 720
    minimumWidth: 420
    minimumHeight: 480
    title: t.title || "Settings"
    color: c.bg

    function set(key, value) {
        const d = Object.assign({}, draft);
        d[key] = value;
        draft = d;
    }
    onVisibleChanged: if (visible) draft = Object.assign({}, f.values || {})

    Shortcut { sequence: "Esc"; onActivated: win.close() }
    Shortcut { sequences: ["Ctrl+S", "Ctrl+Return"]; onActivated: save.clicked() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth

            ColumnLayout {
                x: 18
                width: scroll.availableWidth - 36
                spacing: 14

                Item { implicitHeight: 4 }
                Text {
                    text: win.t.title ? win.t.title.split(" — ").pop() : ""
                    color: win.c.text
                    font.pointSize: 17
                    font.weight: Font.Bold
                }

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
                    Row2 {
                        label: win.t.autostart
                        hint: win.t.autostartHint
                        enabled: !!win.f.autostartSupported
                        Toggle { checked: !!win.draft.start_at_login; onToggled: v => win.set("start_at_login", v) }
                    }
                }

                Section {
                    title: win.t.notifications
                    Row2 {
                        label: win.t.notifyHint
                        Text {
                            readonly property int n: win.draft.notify_threshold || 0
                            text: n === 0 ? win.t.off : win.t.pct.replace("{n}", n)
                            color: n === 0 ? win.c.muted : win.c.accent
                            font.pointSize: 12
                            font.weight: Font.DemiBold
                            font.features: { "tnum": 1 }
                        }
                    }
                    Slider {
                        id: notify
                        Layout.fillWidth: true
                        from: 0; to: 100; stepSize: 5
                        value: win.draft.notify_threshold || 0
                        onMoved: win.set("notify_threshold", Math.round(value))
                        background: Rectangle {
                            x: notify.leftPadding
                            y: notify.topPadding + notify.availableHeight / 2 - height / 2
                            width: notify.availableWidth
                            height: 6
                            radius: 3
                            color: win.c.track
                            Rectangle {
                                width: notify.visualPosition * parent.width
                                height: parent.height
                                radius: 3
                                color: win.c.accent
                            }
                        }
                        handle: Rectangle {
                            x: notify.leftPadding + notify.visualPosition * (notify.availableWidth - width)
                            y: notify.topPadding + notify.availableHeight / 2 - height / 2
                            width: 20
                            height: 20
                            radius: 10
                            color: "white"
                            border.color: win.c.accent
                            border.width: 2
                        }
                    }
                }

                Section {
                    title: win.t.providers
                    Repeater {
                        model: win.f.providers || []
                        delegate: ColumnLayout {
                            id: prov
                            required property var modelData
                            required property int index
                            readonly property bool tracked: !!win.draft["enabled_" + modelData.id]
                            Layout.fillWidth: true
                            spacing: 8
                            Rectangle {
                                visible: prov.index > 0
                                Layout.fillWidth: true
                                implicitHeight: 1
                                color: win.c.border
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                Rectangle { implicitWidth: 4; implicitHeight: 22; radius: 2; color: prov.modelData.color }
                                ColumnLayout {
                                    spacing: 0
                                    Text { text: prov.modelData.name; color: win.c.text; font.pointSize: 11; font.weight: Font.DemiBold }
                                    Text { text: win.t.track; color: win.c.muted; font.pointSize: 8.5 }
                                }
                                Item { Layout.fillWidth: true }
                                Toggle {
                                    tone: prov.modelData.color
                                    checked: prov.tracked
                                    onToggled: v => win.set("enabled_" + prov.modelData.id, v)
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.leftMargin: 14
                                spacing: 10
                                enabled: prov.tracked && prov.modelData.quotaNote === ""
                                opacity: enabled ? 1 : 0.45
                                Text {
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                    text: prov.modelData.quotaNote || win.t.checkQuota
                                    color: win.c.text
                                    font.pointSize: 9.5
                                }
                                Toggle {
                                    tone: prov.modelData.color
                                    checked: !!win.draft["quota_" + prov.modelData.id]
                                    onToggled: v => win.set("quota_" + prov.modelData.id, v)
                                }
                            }
                        }
                    }
                }

                Section {
                    title: win.t.commands
                    Field { label: win.t.claudeCommand; text: win.draft.claude_command || ""; onEdited: v => win.set("claude_command", v) }
                    Field { label: win.t.codexCommand; text: win.draft.codex_command || ""; onEdited: v => win.set("codex_command", v) }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: win.t.privacy || ""
                        color: win.c.muted
                        font.pointSize: 8.5
                    }
                }
                Item { implicitHeight: 4 }
            }
        }

        // Footer: always visible under the scrolling sections.
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 62
            color: win.c.bg
            Rectangle { width: parent.width; height: 1; color: win.c.border }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                spacing: 10
                Item { Layout.fillWidth: true }
                Button2 { text: win.t.cancel || "Cancel"; onClicked: win.close() }
                Button2 {
                    id: save
                    primary: true
                    text: win.t.save || "Save"
                    onClicked: {
                        backend.saveSettings(win.draft);
                        win.close();
                    }
                }
            }
        }
    }

    // -- building blocks ------------------------------------------------------

    component Section: Rectangle {
        id: sec
        property string title
        default property alias content: inner.data
        Layout.fillWidth: true
        implicitHeight: inner.implicitHeight + 32
        radius: 14
        color: win.c.card
        border.color: win.c.border
        ColumnLayout {
            id: inner
            x: 16
            y: 14
            width: parent.width - 32
            spacing: 12
            Text {
                text: sec.title ? sec.title.toLocaleUpperCase(win.t.locale || "en") : ""
                color: win.c.muted
                font.pointSize: 8
                font.weight: Font.DemiBold
                font.letterSpacing: 0.8
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
                font.pointSize: 8.5
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
        Accessible.checked: checked
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
                }
            }
        }
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

    component Button2: Rectangle {
        id: b
        property string text
        property bool primary: false
        signal clicked()
        implicitWidth: label.implicitWidth + 32
        implicitHeight: 36
        radius: 10
        color: primary ? (bMouse.containsMouse ? Qt.lighter(win.c.accent, 1.1) : win.c.accent)
            : (bMouse.containsMouse ? win.c.track : "transparent")
        border.color: primary ? "transparent" : win.c.border
        Text {
            id: label
            anchors.centerIn: parent
            text: b.text
            color: b.primary ? win.c.bg : win.c.text
            font.pointSize: 10
            font.weight: Font.DemiBold
        }
        MouseArea {
            id: bMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: b.clicked()
        }
    }
}
