import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as P5Support
import org.kde.notification

PlasmoidItem {
    id: root

    // Display-ready, localized JSON from `aiusage --widget-json` (see aiusage/viewmodel.py).
    property var view: null
    property bool loading: false
    property string lastError: ""
    readonly property bool turkish: Qt.locale().name.startsWith("tr")
    readonly property string command: Plasmoid.configuration.command

    function refresh() {
        if (loading || !command || command.indexOf("@COMMAND@") >= 0)
            return;
        loading = true;
        runner.connectSource(command);
    }

    P5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            disconnectSource(source);
            root.loading = false;
            try {
                root.view = JSON.parse(data["stdout"]);
                root.lastError = "";
                // New quota alerts only; the command remembers what was already shown.
                for (const a of (root.view.notify || []))
                    notifier.createObject(root, { title: a.title, text: a.text }).sendEvent();
            } catch (e) {
                const err = (data["stderr"] || "").trim().split("\n").pop();
                root.lastError = (root.turkish ? "Komut geçersiz çıktı verdi: " : "Command returned invalid output: ")
                    + (err || ("exit " + data["exit code"]));
            }
        }
    }

    Component {
        id: notifier
        Notification {
            componentName: "plasma_workspace"
            eventId: "notification"
            iconName: "dialog-warning"
            urgency: Notification.HighUrgency
            autoDelete: true
        }
    }

    Timer {
        interval: Math.max(15, Plasmoid.configuration.intervalSeconds) * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    onExpandedChanged: if (expanded) refresh()

    Plasmoid.icon: Qt.resolvedUrl("../images/icon.png")
    toolTipMainText: view ? view.labels.title : "AI Usage"
    toolTipSubText: view ? view.tooltip : (loading ? (turkish ? "Yükleniyor…" : "Loading…") : lastError)

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: root.view ? root.view.labels.refresh : "Refresh"
            icon.name: "view-refresh"
            onTriggered: root.refresh()
        }
    ]

    switchWidth: Kirigami.Units.gridUnit * 14
    switchHeight: Kirigami.Units.gridUnit * 14

    compactRepresentation: CompactRepresentation {}
    fullRepresentation: FullRepresentation {}
}
