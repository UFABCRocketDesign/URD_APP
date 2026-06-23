from __future__ import annotations

import platform
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QCheckBox, QLabel,
    QPushButton, QMessageBox, QFrame, QApplication
)


class GeneralSettingsDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window

        self.setWindowTitle("Configurações Gerais")
        self.resize(420, 290)

        self._build_ui()
        self._sync_from_state()

        try:
            self.main_window.netManager.netChanged.connect(self._sync_from_state)
        except Exception:
            pass

    def _build_ui(self):
        root = QVBoxLayout(self)


        # --- Rede ---
        box_net = QGroupBox("Rede")
        lay_net = QVBoxLayout(box_net)

        self.chk_force_offline = QCheckBox("Forçar modo offline")
        lay_net.addWidget(self.chk_force_offline)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignLeft)
        lay_net.addWidget(self.lbl_status)

        root.addWidget(box_net)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        root.addWidget(line)

        # --- Ações ---
        box_actions = QGroupBox("Ações")
        lay_actions = QVBoxLayout(box_actions)

        self.chk_light_theme = QCheckBox("Light Theme")
        lay_actions.addWidget(self.chk_light_theme)

        self.btn_toggle_fullscreen = QPushButton("")
        lay_actions.addWidget(self.btn_toggle_fullscreen)

        self.btn_quit = QPushButton("Encerrar aplicativo")
        lay_actions.addWidget(self.btn_quit)

        self.btn_shutdown = QPushButton("Desligar computador (shutdown)")
        lay_actions.addWidget(self.btn_shutdown)

        root.addWidget(box_actions)
        root.addStretch(1)

        # sinais
        self.chk_force_offline.toggled.connect(self._on_force_offline_toggled)
        self.chk_light_theme.toggled.connect(self._on_light_theme_toggled)
        self.btn_toggle_fullscreen.clicked.connect(self._on_toggle_fullscreen_clicked)
        self.btn_quit.clicked.connect(self._on_quit_clicked)
        self.btn_shutdown.clicked.connect(self._on_shutdown_clicked)

        self._update_fullscreen_button_text()

    def _sync_from_state(self, *_):
        nm = self.main_window.netManager

        self.chk_force_offline.blockSignals(True)
        self.chk_force_offline.setChecked(bool(nm.forceOffline))
        self.chk_force_offline.blockSignals(False)

        self.chk_light_theme.blockSignals(True)
        self.chk_light_theme.setChecked(bool(getattr(self.main_window, "_light_theme_enabled", False)))
        self.chk_light_theme.blockSignals(False)

        if nm.forceOffline:
            self.lbl_status.setText("Status: OFFLINE (forçado)")
        else:
            self.lbl_status.setText("Status: ONLINE" if nm.hasNet else "Status: OFFLINE")

        self._update_fullscreen_button_text()

    def _update_fullscreen_button_text(self):
        if self.main_window.isFullScreen():
            self.btn_toggle_fullscreen.setText("Sair da tela cheia")
        else:
            self.btn_toggle_fullscreen.setText("Entrar em tela cheia")

    def _on_force_offline_toggled(self, checked: bool):
        self.main_window.netManager.set_force_offline(bool(checked))

    def _on_light_theme_toggled(self, checked: bool):
        if hasattr(self.main_window, "set_light_theme_enabled"):
            self.main_window.set_light_theme_enabled(bool(checked))

    def _on_toggle_fullscreen_clicked(self):
        if self.main_window.isFullScreen():
            self.main_window.showNormal()
        else:
            self.main_window.showFullScreen()

        self._update_fullscreen_button_text()

    def _on_quit_clicked(self):
        ok = QMessageBox.question(
            self,
            "Encerrar",
            "Deseja encerrar o aplicativo?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok == QMessageBox.Yes:
            QApplication.instance().quit()

    def _on_shutdown_clicked(self):
        ok = QMessageBox.question(
            self,
            "Shutdown",
            "Deseja desligar o computador agora?\n\nIsso vai encerrar o sistema.",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        os_system = platform.system().lower()
        if os_system == "windows":
            cmds = [
                ["shutdown", "/s", "/t", "0"],
            ]
        else:
            cmds = [
                ["systemctl", "poweroff"],
                ["shutdown", "-h", "now"],
            ]

        last_err = None
        for cmd in cmds:
            try:
                subprocess.run(cmd, check=True)
                return
            except Exception as e:
                last_err = e

        QMessageBox.critical(
            self,
            "Falha no shutdown",
            f"Não foi possível desligar automaticamente.\n\nErro: {last_err}"
        )