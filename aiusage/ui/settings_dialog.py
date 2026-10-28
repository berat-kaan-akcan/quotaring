"""Settings dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                               QLabel, QLineEdit, QSlider, QSpinBox, QVBoxLayout)
from PySide6.QtCore import Qt

from ..settings import PROVIDER_IDS

NAMES = {"claude": "Claude Code", "codex": "Codex", "antigravity": "Antigravity"}


class SettingsDialog(QDialog):
    def __init__(self, settings, autostart_supported: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Usage — Settings")
        s = settings
        lay = QVBoxLayout(self)

        gen = QGroupBox("General")
        f = QFormLayout(gen)
        self.local_interval = QSpinBox()
        self.local_interval.setRange(15, 3600)
        self.local_interval.setSuffix(" s")
        self.local_interval.setValue(s.local_refresh_seconds)
        f.addRow("Local refresh every", self.local_interval)
        self.quota_interval = QSpinBox()
        self.quota_interval.setRange(60, 86400)
        self.quota_interval.setSuffix(" s")
        self.quota_interval.setValue(s.quota_refresh_seconds)
        f.addRow("Quota refresh every", self.quota_interval)
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 120)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(s.timeout_seconds)
        f.addRow("Query timeout", self.timeout)
        self.theme = QComboBox()
        for v, label in (("system", "Follow system"), ("light", "Light"), ("dark", "Dark")):
            self.theme.addItem(label, v)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.theme)))
        f.addRow("Theme", self.theme)
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity.setValue(int(s.opacity * 100))
        f.addRow("Background opacity", self.opacity)
        self.on_top = QCheckBox("Keep above other windows (compositor permitting)")
        self.on_top.setChecked(s.always_on_top)
        f.addRow(self.on_top)
        self.to_tray = QCheckBox("Closing hides to the tray")
        self.to_tray.setChecked(s.minimize_to_tray)
        f.addRow(self.to_tray)
        self.autostart = QCheckBox("Start at login")
        self.autostart.setChecked(s.start_at_login)
        self.autostart.setEnabled(autostart_supported)
        f.addRow(self.autostart)
        self.notify = QSpinBox()
        self.notify.setRange(0, 100)
        self.notify.setSuffix(" %")
        self.notify.setSpecialValueText("Off")
        self.notify.setValue(s.notify_threshold)
        f.addRow("Notify at quota", self.notify)
        lay.addWidget(gen)

        prov = QGroupBox("Providers")
        pf = QFormLayout(prov)
        self.enabled = {}
        self.quota = {}
        for pid in PROVIDER_IDS:
            e = QCheckBox("Enabled")
            e.setChecked(s.providers_enabled.get(pid, True))
            q = QCheckBox("Query account quota")
            q.setChecked(s.quota_enabled.get(pid, True))
            if pid == "antigravity":
                q.setEnabled(False)
                q.setToolTip("No documented quota source exists for Antigravity")
            self.enabled[pid], self.quota[pid] = e, q
            pf.addRow(QLabel(f"<b>{NAMES[pid]}</b>"))
            pf.addRow(e, q)
        self.claude_cmd = QLineEdit(s.claude_command)
        self.codex_cmd = QLineEdit(s.codex_command)
        pf.addRow("claude command", self.claude_cmd)
        pf.addRow("codex command", self.codex_cmd)
        note = QLabel("Quota checks start the provider's own CLI (no model request). "
                      "The widget never reads or stores credentials.")
        note.setWordWrap(True)
        note.setObjectName("small")
        pf.addRow(note)
        lay.addWidget(prov)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def apply_to(self, s) -> None:
        s.local_refresh_seconds = self.local_interval.value()
        s.quota_refresh_seconds = self.quota_interval.value()
        s.timeout_seconds = self.timeout.value()
        s.theme = self.theme.currentData()
        s.opacity = self.opacity.value() / 100
        s.always_on_top = self.on_top.isChecked()
        s.minimize_to_tray = self.to_tray.isChecked()
        s.start_at_login = self.autostart.isChecked()
        s.notify_threshold = self.notify.value()
        for pid in PROVIDER_IDS:
            s.providers_enabled[pid] = self.enabled[pid].isChecked()
            s.quota_enabled[pid] = self.quota[pid].isChecked()
        s.claude_command = self.claude_cmd.text().strip() or "claude"
        s.codex_command = self.codex_cmd.text().strip() or "codex"
        s.clamp()
