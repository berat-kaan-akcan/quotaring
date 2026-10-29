import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_command: commandField.text
    property alias cfg_intervalSeconds: intervalBox.value
    property alias cfg_showRemaining: remainingBox.checked
    property string cfg_period
    property string cfg_group
    property int cfg_tab
    property bool cfg_showRemainingDefault
    property string cfg_groupDefault
    property int cfg_tabDefault
    property string cfg_commandDefault
    property int cfg_intervalSecondsDefault
    property string cfg_periodDefault

    readonly property bool turkish: Qt.locale().name.startsWith("tr")

    Kirigami.FormLayout {
        QQC2.TextField {
            id: commandField
            Kirigami.FormData.label: turkish ? "Komut:" : "Command:"
            Layout.minimumWidth: Kirigami.Units.gridUnit * 24
        }
        QQC2.CheckBox {
            id: remainingBox
            Kirigami.FormData.label: turkish ? "Gösterim:" : "Show:"
            text: turkish ? "Kalan yüzdeyi göster (kapalıysa kullanılan)" : "Remaining percent (off: used)"
        }
        QQC2.SpinBox {
            id: intervalBox
            Kirigami.FormData.label: turkish ? "Yenileme aralığı (sn):" : "Refresh every (s):"
            from: 15
            to: 3600
        }
        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 24
            wrapMode: Text.WordWrap
            opacity: 0.7
            text: turkish
                ? "Kota, uygulama ayarlarındaki kota aralığına göre sorgulanır (varsayılan 5 dk); bu aralık yalnızca yerel tokenları etkiler."
                : "Quota is queried on the app's own quota interval (default 5 min); this interval only affects local tokens."
        }
    }
}
