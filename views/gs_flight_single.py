# views/gs_flight_single.py
from __future__ import annotations
import math
from typing import Optional, Tuple, List
import sys
import platform

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter, QFrame, QLabel,
    QPushButton, QPlainTextEdit, QCheckBox, QGroupBox, QSizePolicy, QMessageBox, QComboBox,
    QStackedLayout, QFileDialog, QProgressDialog, QApplication, QDialog
)

from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen

import os
import serial
import serial.tools.list_ports
import pyqtgraph.opengl as gl
import numpy as np
import time
from dataclasses import dataclass, field
import pyqtgraph as pg
import math
import re

from views.net_manager import NetManager
from views.config_dialog import ConfigDialog
from views.map_widget import MapWidget
from views.rocket_3d import Rocket3DView
from views.logger import Logger





def get_os_info():
    os_name = platform.system().lower()
    return os_name

@dataclass
class RuntimeConfig:
    # Base
    base_lat_text: str = ""
    base_lon_text: str = ""

    # Centro do mapa
    map_lat: float = 0.0
    map_lon: float = 0.0
    map_zoom: int = 12

    # Tiles (NÃO persistir depois que fechar app)
    tiles_folder: str = ""

    # (opcional) modo teste
    test_lat: float = 0.0
    test_lon: float = 0.0
    test_alt: float = 0.0
    pq_enabled: list[bool] = field(default_factory=lambda: [False]*4)
    pq_time: list[float] = field(default_factory=lambda: [0.0]*4)

class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(80)
        self.setFixedSize(42, 42)

    def _rotate(self):
        self._angle = (self._angle - 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(6, 6, -6, -6)

        pen_bg = QPen(QColor("#d0d0d0"), 4)
        painter.setPen(pen_bg)
        painter.drawEllipse(rect)

        pen_fg = QPen(QColor("#6a0dad"), 4)  # roxo
        painter.setPen(pen_fg)
        painter.drawArc(rect, self._angle * 16, 100 * 16)


class BusySpinnerDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conectando")
        self.setModal(True)
        self.setFixedSize(320, 150)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        self.spinner = LoadingSpinner(self)
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)

        lay.addWidget(self.spinner, alignment=Qt.AlignCenter)
        lay.addWidget(self.label)

    def setLabelText(self, text: str):
        self.label.setText(text)
        
class GSFlightSinglePage(QWidget):
   
    def __init__(self, net: NetManager, parent=None):
        super().__init__(parent)
        self.net = net
        self.is_satellite = False
        self.net.netChanged.connect(self.onNetChanged)

        self.runtime_cfg = RuntimeConfig()

        self.os_system = get_os_info()
        self.is_linux = self.os_system == "linux"
        print(f"[GS_FLIGHT]: Running on OS: {self.os_system}, Linux mode: {self.is_linux}")

        self._build_ui(self.os_system)
        self._reset_state()

        self.ser = None   # objeto serial
        self.timer_serial = QTimer(self)
        self.timer_serial.timeout.connect(self._read_serial)
        self.connected_ok = False
        
        self.lastvalue_dn = 0.0
        self.lastvalue_db = 0.0
        self.lastvalue_mn = 0.0
        self.lastvalue_mb = 0.0

        self.serial_beep_enabled = False
        self._buzzer = None
        self._last_beep_ts = 0.0
        self._beep_mode = None  # "gpio", "winsound" ou None

        if self.is_linux:
            try:
                from gpiozero import Buzzer
                self._buzzer = Buzzer(6)   # GPIO 6 no Raspberry
                self._beep_mode = "gpio"
            except Exception:
                self._buzzer = None
                self._beep_mode = None
        else:
            try:
                import winsound
                self._beep_mode = "winsound"
            except Exception:
                self._beep_mode = None
    
        self.logger = None 
        QTimer.singleShot(100, self.ask_logger)  # espera 100ms e chama

        self._last_rx_time = time.time()

        self.serial_watchdog = QTimer(self)
        self.serial_watchdog.timeout.connect(self._check_serial_timeout)
        self.serial_watchdog.start(500)

        self._hz_last_time = time.time()
        self._hz_counter = 0
        self._hz_value = 0.0

        # timer para atualizar Hz a cada 1s
        self.serial_hz_timer = QTimer(self)
        self.serial_hz_timer.timeout.connect(self._update_hz_display)
        self.serial_hz_timer.start(1000)

        # =========================
        # GRAVAÇÃO DA TELA (runtime)
        # =========================
        self._ui_recording = False
        self._ui_rec_started_at = 0.0
        self._ui_rec_dir = ""
        self._ui_rec_idx = 0
        self._ui_rec_fps = 10
        self._ui_rec_full_desktop = True

        self._ui_rec_timer = QTimer(self)
        self._ui_rec_timer.timeout.connect(self._ui_rec_capture_frame)

        # Se quiser simular dados, descomente:
        # self._sim = QTimer(self)
        # self._sim.timeout.connect(self._feed_fake)
        # self._sim.start(200)

    # =========================
    # GRAVAÇÃO (full screen)
    # =========================
    def is_ui_recording(self) -> bool:
        return bool(self._ui_recording)

    def ui_recording_elapsed_s(self) -> float:
        if not self._ui_recording:
            return 0.0
        return max(0.0, time.monotonic() - self._ui_rec_started_at)

    def start_ui_recording(self, out_dir: str, fps: int = 10, full_desktop: bool = True) -> bool:
        """
        Salva frames PNG da tela inteira.
        - full_desktop=True  -> captura o DESKTOP inteiro (fullscreen real)
        - full_desktop=False -> captura só a janela do app
        """
        try:
            out_dir = (out_dir or "").strip()
            if not out_dir:
                return False

            os.makedirs(out_dir, exist_ok=True)

            self._ui_rec_dir = out_dir
            self._ui_rec_idx = 0
            self._ui_rec_fps = max(1, int(fps))
            self._ui_rec_full_desktop = bool(full_desktop)

            self._ui_rec_started_at = time.monotonic()
            self._ui_recording = True

            interval_ms = int(1000 / self._ui_rec_fps)
            self._ui_rec_timer.start(max(1, interval_ms))
            return True
        except Exception as e:
            print("start_ui_recording error:", e)
            return False

    def stop_ui_recording(self):
        self._ui_recording = False
        try:
            self._ui_rec_timer.stop()
        except Exception:
            pass

    def _ui_rec_capture_frame(self):
        if not self._ui_recording or not self._ui_rec_dir:
            return

        try:
            screen = QGuiApplication.primaryScreen()
            if not screen:
                return

            if self._ui_rec_full_desktop:
                pix = screen.grabWindow(0)  # desktop inteiro
            else:
                wid = self.window().winId()
                pix = screen.grabWindow(int(wid))  # só a janela do app

            self._ui_rec_idx += 1
            out = os.path.join(self._ui_rec_dir, f"frame_{self._ui_rec_idx:06d}.png")
            pix.save(out, "PNG")
        except Exception:
            pass

    def apply_map_mode(self):
        """
        Fonte única da verdade:
        - online -> mapa online (SEM tiles)
        - offline efetivo (sem net OU forced) -> usa tiles_folder se existir, senão offline sem tiles
        """
        online = bool(self.net.get_status())  # já considera forceOffline
        folder = (self.runtime_cfg.tiles_folder or "").strip()

        if online:
            self.map.set_offline(False)
        else:
            self.map.set_offline(True, folder if folder else None)


    # ------------------ UI ------------------
    def _build_ui(self, os_name):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal, self)
        root.addWidget(splitter)

        # ===== ESQUERDA =====
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(4, 4, 4, 4)
        splitter.addWidget(left)

        # mapa modo online/offline
        self.map = MapWidget(offline=not self.net.get_status(), satellite=self.is_satellite, tile_folder=None)
        self.apply_map_mode()
        self.map.setMinimumSize(300, 200)   # opcional, garante espaço mínimo
        left_lay.addWidget(self.map, stretch=1)


        # --- BOTOES TERMINAL ---
        self.row_container = QWidget()
        row = QHBoxLayout(self.row_container)
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)

        self.left_group = QWidget()
        lg = QHBoxLayout(self.left_group)
        lg.setSpacing(4)
        lg.setContentsMargins(0, 0, 0, 0)

        self.chk_autoscroll = QCheckBox("Auto-scroll")
        self.chk_autoscroll.setMaximumHeight(24)
        self.chk_autoscroll.setChecked(True)

        self.combo_ports = QComboBox()
        self.combo_ports.setEditable(True)
        self.combo_ports.setMaximumHeight(24)

        self.btn_connect = QPushButton("Conectar")
        self.btn_connect.setMaximumHeight(24)

        self.btn_disconnect = QPushButton("Desconectar")
        self.btn_disconnect.setMaximumHeight(24)

        lg.addWidget(self.chk_autoscroll)
        lg.addWidget(QLabel("Porta:"))
        lg.addWidget(self.combo_ports)
        lg.addWidget(self.btn_connect)
        lg.addWidget(self.btn_disconnect)

        self.btn_clear = QPushButton("Limpar Terminal")
        self.btn_clear.setMaximumHeight(24)

        self.btn_cfg = QPushButton("Configurações")
        self.btn_cfg.setMaximumHeight(24)

        # =========================
        # BLOCO STATUS SERIAL
        # =========================
        self.serial_block = QWidget()
        serial_layout = QVBoxLayout(self.serial_block)
        serial_layout.setContentsMargins(0, 0, 0, 0)
        serial_layout.setSpacing(3)

        self.lbl_serial_title = QLabel("Status Serial")
        self.lbl_serial_title.setAlignment(Qt.AlignCenter)
        self.lbl_serial_title.setStyleSheet("font-size:10px; font-weight:600;")

        # linha horizontal principal
        serial_row = QHBoxLayout()
        serial_row.setSpacing(8)

        # Hz (esquerda)
        self.lbl_serial_hz = QLabel("0.0 Hz")
        self.lbl_serial_hz.setStyleSheet("font-size:10px;")
        serial_row.addWidget(self.lbl_serial_hz)

        # centro (box + texto)
        self.serial_status_box = QFrame()
        self.serial_status_box.setFixedSize(16, 16)
        self.serial_status_box.setStyleSheet(
            "background:#ffcc00; border:1px solid #aaa; border-radius:4px;"
        )

        self.lbl_serial_status = QLabel("IDLE")
        self.lbl_serial_status.setStyleSheet("font-size:10px;")

        serial_row.addWidget(self.serial_status_box)
        serial_row.addWidget(self.lbl_serial_status)

        # pacotes válidos
        self.lbl_serial_packets = QLabel("0/19")
        self.lbl_serial_packets.setStyleSheet("font-size:10px;")
        serial_row.addWidget(self.lbl_serial_packets)

        serial_layout.addWidget(self.lbl_serial_title)
        serial_layout.addLayout(serial_row)



        # =========================
        # LAYOUT FINAL DA LINHA
        # =========================
        row.addWidget(self.left_group)
        row.addStretch(1)
        row.addWidget(self.serial_block)
        row.addStretch(1)
        row.addWidget(self.btn_clear)
        row.addWidget(self.btn_cfg)



        left_lay.addWidget(self.row_container)


        # --- terminal ---
        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setMinimumSize(300, 200)  
        self.terminal.setStyleSheet("""
            QPlainTextEdit {
                background: #0f0f0f;
                color: white;
                font-family: Consolas, monospace;
                border: 1px solid #3a3a3a;
            }
        """)
        self.terminal.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.terminal.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # --- header ---
        self.lbl_header = QLabel("Terminal de Dados")
        self.lbl_header.setStyleSheet("font-weight: bold; font-size: 11px;")

        # layout que junta header + terminal
        term_widget = QWidget()
        term_layout = QVBoxLayout(term_widget)
        term_layout.setContentsMargins(0, 0, 0, 0)
        term_layout.addWidget(self.lbl_header)
        term_layout.addWidget(self.terminal)

        # adiciona no lado esquerdo
        left_lay.addWidget(term_widget, stretch=1)


        # --- barra de status ---
        self.lbl_status = QLabel("Desconectado")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color:#666; font-style:italic; padding:4px; border-top:1px solid #ccc;")
        left_lay.addWidget(self.lbl_status)

        # conecta sinais
        self.btn_clear.clicked.connect(self._clear_terminal)
        self.btn_cfg.clicked.connect(self._open_config_dialog)
        self.btn_connect.clicked.connect(self.connect_serial)
        self.btn_disconnect.clicked.connect(self.disconnect_serial)
        self.combo_ports.mousePressEvent = lambda ev: (
            self.refresh_ports(), QComboBox.mousePressEvent(self.combo_ports, ev)
        )

        # ===== DIREITA =====
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(4, 4, 4, 4)
        splitter.addWidget(right)
        splitter.setSizes([900, 500])

        # --- orientação 3D (stack online/offline) ---
        from views.rocket_3d import Rocket3DView
        self.rocket3d = Rocket3DView()
        right_lay.addWidget(self.rocket3d, stretch=3)


        # --- grafico altitude ---
        pg.setConfigOptions(antialias=True)
        self.alt_plot = pg.PlotWidget(title="Altitude (m) vs Tempo (s)")
        self.alt_plot.showGrid(x=True, y=True, alpha=0.3)
        self.alt_curve = self.alt_plot.plot([], [], pen=pg.mkPen(QColor(0, 150, 255), width=2))
        self.alt_plot.setMinimumHeight(250)
        right_lay.addWidget(self.alt_plot, stretch=2)

        # --- linha com paraquedas e infos ---
        # bottom_row = QHBoxLayout()

        # pq_group = QGroupBox("Paraquedas")
        # pq_lay = QGridLayout(pq_group)
        # self.pq_boxes = []
        # self.pq_time_labels = []
        # for i in range(4):
        #     box = QFrame()
        #     box.setFrameShape(QFrame.StyledPanel)
        #     box.setStyleSheet("background: white; border: 1px solid #ccc; border-radius: 8px;")
        #     box.setMinimumSize(28, 28)
        #     time_lbl = QLabel("t=0.00 s")
        #     time_lbl.setStyleSheet("font-weight: 500;")
        #     self.pq_boxes.append(box)
        #     self.pq_time_labels.append(time_lbl)

        #     pq_lay.addWidget(QLabel(f"P{i+1}"), i, 0)
        #     pq_lay.addWidget(box, i, 1)
        #     pq_lay.addWidget(time_lbl, i, 2)

        # info_group = QGroupBox("Infos")
        # info_lay = QGridLayout(info_group)
        # self.lbl_alt_max = QLabel("—")
        # self.lbl_alt_apogeu = QLabel("—")
        # self.lbl_vel = QLabel("—")
        # self.lbl_lat = QLabel("—")
        # self.lbl_lon = QLabel("—")
        # self.lbl_dist = QLabel("—")
        # info_lay.addWidget(QLabel("Altura Atual (m):"), 0, 0)
        # info_lay.addWidget(self.lbl_alt_max, 0, 1)
        # info_lay.addWidget(QLabel("Altura Máx (m):"), 1, 0)
        # info_lay.addWidget(self.lbl_alt_apogeu, 1, 1)
        # info_lay.addWidget(QLabel("Velocidade (m/s):"), 2, 0)
        # info_lay.addWidget(self.lbl_vel, 2, 1)
        # info_lay.addWidget(QLabel("Latitude:"), 3, 0)
        # info_lay.addWidget(self.lbl_lat, 3, 1)
        # info_lay.addWidget(QLabel("Longitude:"), 4, 0)
        # info_lay.addWidget(self.lbl_lon, 4, 1)
        # info_lay.addWidget(QLabel("Distância à Base (m):"), 5, 0)
        # info_lay.addWidget(self.lbl_dist, 5, 1)

        # pq_group.setMaximumHeight(150)
        # info_group.setMaximumHeight(150)

        # bottom_row.addWidget(pq_group, stretch=1)
        # bottom_row.addWidget(info_group, stretch=1)

        # --- linha com paraquedas e infos ---
        bottom_row = QHBoxLayout()

        # ========================
        #  BLOCO DE PARAQUEDAS
        # ========================
        pq_group = QGroupBox("Paraquedas")
        pq_lay = QGridLayout(pq_group)

        # Drogues
        label_drogue = QLabel("1st Event")
        label_drogue.setAlignment(Qt.AlignCenter)
        pq_lay.addWidget(label_drogue, 0, 0, 1, 2)

        # Drogue N
        self.pqd_drogueN = QFrame()
        self.pqd_drogueN.setFrameShape(QFrame.StyledPanel)
        self.pqd_drogueN.setStyleSheet("background: white; border: 1px solid #ccc; border-radius: 8px;")
        self.pqd_drogueN.setMinimumSize(32, 32)
        pq_lay.addWidget(self.pqd_drogueN, 1, 0)

        # Caixa de texto embaixo do Drogue N
        self.drogueN_text = QLabel()
        pq_lay.addWidget(self.drogueN_text, 2, 0)

        # Drogue B
        self.pqd_drogueB = QFrame()
        self.pqd_drogueB.setFrameShape(QFrame.StyledPanel)
        self.pqd_drogueB.setStyleSheet("background: white; border: 1px solid #ccc; border-radius: 8px;")
        self.pqd_drogueB.setMinimumSize(32, 32)
        pq_lay.addWidget(self.pqd_drogueB, 1, 1)

        # Caixa de texto embaixo do Drogue B
        self.drogueB_text = QLabel()
        pq_lay.addWidget(self.drogueB_text, 2, 1)

        # Main
        label_main = QLabel("2nd Event")
        label_main.setAlignment(Qt.AlignCenter)
        pq_lay.addWidget(label_main, 3, 0, 1, 2)

        # Main N
        self.pqd_mainN = QFrame()
        self.pqd_mainN.setFrameShape(QFrame.StyledPanel)
        self.pqd_mainN.setStyleSheet("background: white; border: 1px solid #ccc; border-radius: 8px;")
        self.pqd_mainN.setMinimumSize(32, 32)
        pq_lay.addWidget(self.pqd_mainN, 4, 0)

        # Caixa de texto embaixo do Main N
        self.mainN_text = QLabel()
        pq_lay.addWidget(self.mainN_text, 5, 0)

        # Main B
        self.pqd_mainB = QFrame()
        self.pqd_mainB.setFrameShape(QFrame.StyledPanel)
        self.pqd_mainB.setStyleSheet("background: white; border: 1px solid #ccc; border-radius: 8px;")
        self.pqd_mainB.setMinimumSize(32, 32)
        pq_lay.addWidget(self.pqd_mainB, 4, 1)

        # Caixa de texto embaixo do Main B
        self.mainB_text = QLabel()
        pq_lay.addWidget(self.mainB_text, 5, 1)



        # Definindo altura máxima do grupo
        pq_group.setMaximumHeight(200)
        pq_group.setMinimumWidth(200)

        # Definindo o texto inicial
        self.drogueN_text.setText("Normal")
        self.drogueB_text.setText("Backup")
        self.mainN_text.setText("Normal")
        self.mainB_text.setText("Backup")


        # ========================
        #  BLOCO DE INFORMAÇÕES
        # ========================
        info_group = QGroupBox("Infos")
        info_lay = QGridLayout(info_group)

        # Altitude, velocidade, etc.
        self.lbl_alt_max = QLabel("—")
        self.lbl_alt_apogeu = QLabel("—")
        self.lbl_vel = QLabel("—")
        self.lbl_temp = QLabel("—")

        # SD Card status
        label_sd = QLabel("SD Card")
        label_sd.setAlignment(Qt.AlignCenter)
        info_lay.addWidget(label_sd, 4, 0, 1, 2)

        info_lay.addWidget(QLabel("Altura Atual (m):"), 0, 0)
        info_lay.addWidget(self.lbl_alt_max, 0, 1)
        info_lay.addWidget(QLabel("Altura Máx (m):"), 1, 0)
        info_lay.addWidget(self.lbl_alt_apogeu, 1, 1)
        info_lay.addWidget(QLabel("Velocidade vertical (m/s):"), 2, 0)
        info_lay.addWidget(self.lbl_vel, 2, 1)
        info_lay.addWidget(QLabel("Temperatura (C°):"), 3, 0)
        info_lay.addWidget(self.lbl_temp, 3, 1)
        self.sd_box = QFrame()
        self.sd_box.setFrameShape(QFrame.StyledPanel)
        self.sd_box.setStyleSheet("background: red; border: 1px solid #ccc; border-radius: 6px;")
        self.sd_box.setMinimumSize(40, 20)
        info_lay.addWidget(self.sd_box, 5, 0, 1, 2, alignment=Qt.AlignCenter)

        info_group.setMaximumWidth(200)
        info_group.setMinimumHeight(200)

        # ========================
        #  BLOCO DE GPS
        # ========================
        gps_group = QGroupBox("GPS")
        gps_lay = QGridLayout(gps_group)

        # Labels para exibição de valores
        self.lbl_horario = QLabel("—")
        self.lbl_lat = QLabel("—")
        self.lbl_lon = QLabel("—")
        self.lbl_dist = QLabel("—")

        # Títulos para as labels
        lbl_precisao_title = QLabel("Precisão (HDOP)")
        lbl_precisao_title.setAlignment(Qt.AlignCenter)

        lbl_horario_title = QLabel("Horário (UTC-LOCAL)")
        lbl_horario_title.setAlignment(Qt.AlignCenter)

        # Adicionando widgets ao layout
        gps_lay.addWidget(lbl_horario_title, 0, 0, 1, 2)
        gps_lay.addWidget(self.lbl_horario, 1, 0, 1, 2, alignment=Qt.AlignCenter)

        # Alinhamento central para Latitude e Longitude
        gps_lay.addWidget(QLabel("Latitude:"), 2, 0, alignment=Qt.AlignCenter)  # Alinha o título
        gps_lay.addWidget(self.lbl_lat, 3, 0, alignment=Qt.AlignCenter)         # Alinha o valor

        gps_lay.addWidget(QLabel("Longitude:"), 2, 1, alignment=Qt.AlignCenter)  # Alinha o título
        gps_lay.addWidget(self.lbl_lon, 3, 1, alignment=Qt.AlignCenter)         # Alinha o valor

        gps_lay.addWidget(QLabel("Distância a Base:"), 4, 0, alignment=Qt.AlignCenter)
        gps_lay.addWidget(self.lbl_dist, 4, 1, alignment=Qt.AlignCenter)

        # Título da precisão e o campo de precisão (caixa vermelha)
        lbl_precisao_title = QLabel("Precisão (HDOP)")
        lbl_precisao_title.setAlignment(Qt.AlignCenter)

        # Criando a caixa da precisão
        self.lbl_precisao = QFrame()
        self.lbl_precisao.setFrameShape(QFrame.StyledPanel)
        self.lbl_precisao.setStyleSheet("background: red; border: 1px solid #ccc; border-radius: 6px;")
        self.lbl_precisao.setMinimumSize(40, 20)  # Tamanho mínimo similar ao SD Card

        # Adicionando a caixa de precisão ao layout
        gps_lay.addWidget(lbl_precisao_title, 5, 0, 1, 2)
        gps_lay.addWidget(self.lbl_precisao, 6, 0, 1, 2, alignment=Qt.AlignCenter)

        # Ajuste de altura mínima para o grupo de GPS
        gps_group.setMinimumHeight(200)
        gps_group.setMaximumWidth(200)



        # --- Distribuição final ---
        bottom_row.addWidget(pq_group, stretch=1)
        bottom_row.addWidget(info_group, stretch=1)
        bottom_row.addWidget(gps_group, stretch=1)


        right_lay.addLayout(bottom_row)

        # if os_name == "linux":
        #     # self.left_group.hide()              
        #     self._set_status("Raspberry Pi Mode", "#17d4ce")  # ciano

    # --- Status Serial ---
    def _set_serial_status(self, state: str):

        # pequeno efeito de pulso por cor
        if state == "ok":
            color = "#4caf50"
            text = "RX OK"

            self.serial_status_box.setStyleSheet(
                """
                background:#4caf50;
                border:2px solid #81c784;
                border-radius:4px;
                """
            )

            QTimer.singleShot(120, lambda: self.serial_status_box.setStyleSheet(
                "background:#4caf50; border:1px solid #4caf50; border-radius:4px;"
            ))
   

        elif state == "bad":
            color = "#f44336"
            text = "RX ERR"
            self.serial_status_box.setStyleSheet(
                f"background:{color}; border:1px solid #aaa; border-radius:4px;"
            )

        else:
            color = "#ffcc00"
            text = "IDLE"
            self.serial_status_box.setStyleSheet(
                f"background:{color}; border:1px solid #aaa; border-radius:4px;"
            )

        self.lbl_serial_status.setText(text)

    @Slot()
    def _check_serial_timeout(self):
        if time.time() - self._last_rx_time > 2.0:
            self._set_serial_status("idle")


    def toggle_map(self):
        self.map.toggle_map()

        txt = self.btn_toggle_map.text().strip()

        if txt == "Dark Map":
            self.btn_toggle_map.setText("Satellite Map")
        elif txt == "Satellite Map":
            self.btn_toggle_map.setText("Light Map")
        else:
            self.btn_toggle_map.setText("Dark Map")

    
    def set_orientation(self, roll: float, pitch: float, yaw: float, degrees: bool = False):
        """Atualiza a orientação do foguete no 3D (online/offline)."""
        self.rocket3d.set_orientation(roll, pitch, yaw, degrees)


    # ------------------ Estado ------------------
    def _reset_state(self):
        self.t_last: Optional[float] = None
        self.alt_last: Optional[float] = None
        self.alt_max: float = float("-inf")
        self.series_t: List[float] = []
        self.series_alt: List[float] = []
        self.last_latlon: Optional[Tuple[float, float]] = None
        self.base_latlon: Optional[Tuple[float, float]] = None  # para distância
        self.alt_max: float = float("-inf")
        self.apogee_h: float = 0.0
        self.apogee_t: float = 0.0
        self.sd_bool: float = 0.0
        self.precisao: float = 0.0
        self.hora: float = 0.0
        self.minuto: float = 0.0

        self.temperatura: Optional[float] = None
        
        # reset paraquedas
        for i in range(4):
            self._set_pq(i, 0.0)


    # ------------------ API pública ------------------
    NAN = float("nan")

    def _is_ok(self, x) -> bool:
        return x is not None and isinstance(x, (int, float)) and math.isfinite(x)

    def _to_float(self, s: str):
        if s is None:
            return None
        s = s.strip().replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None

    def _in_range(self, name: str, v: float) -> bool:
        # ranges “seguros” (ajuste como quiser)
        R = {
            "linha": (0, 1e9),
            "tempo": (0, 1e9),
            "latitude": (-90.0, 90.0),
            "longitude": (-180.0, 180.0),
            "hora": (0, 23),
            "minuto": (0, 59),
            "precisao": (0.0, 101.0),         # HDOP
            "altitude": (-15000.0, 15000.0),
            "sd": (0.0, 1.0),
            "apogeu_h": (-15000.0, 15000.0),
            "apogeu_t": (0.0, 1e9),
            "pqd_mn": (-15000.0, 15000.0),
            "pqd_dn": (-15000.0, 15000.0),
            "pqd_mb": (-15000.0, 15000.0),
            "pqd_db": (-15000.0, 15000.0),
            "temp": (-80.0, 150.0),
            "roll": (-720.0, 720.0),
            "pitch": (-720.0, 720.0),
            "yaw": (-720.0, 720.0),
        }
        lo, hi = R.get(name, (-float("inf"), float("inf")))
        return lo <= v <= hi

    def _fmt(self, v, fmt="{:.2f}"):
        return fmt.format(v) if self._is_ok(v) else "—"

    def _extract_value(self, field: str):
        """
        Extrai o valor numérico de um campo no formato "texto:valor" ou apenas "valor".
        Retorna None se o campo for "~" ou se não houver número.
        """
        if not field or field.strip() == "~":
            return None

        field = field.strip()

        # Se houver dois pontos, pega apenas a parte depois
        if ":" in field:
            _, value = field.split(":", 1)
        else:
            value = field

        value = value.strip()

        # Remove caracteres não numéricos simples no início ou fim
        # (Ex: "alt=123", "H 123", etc.)
        clean = ""
        for c in value:
            if c in "0123456789.-":
                clean += c
            elif clean:  # já começou o número e veio um char estranho -> parar
                break

        # Tenta converter
        try:
            return float(clean)
        except ValueError:
            return None


    # def _parse_packet(self, line: str):
    #     if not line:
    #         return None

    #     # ORDEM OFICIAL E FIXA
    #     ORDER = [
    #         "linha","tempo","latitude","longitude","hora","minuto","precisao",
    #         "altitude","sd","apogeu_h","apogeu_t",
    #         "pqd_dn","pqd_db","pqd_mn","pqd_mb",
    #         "temp","roll","pitch","yaw"
    #     ]

    #     # PREFIXOS PERMITIDOS
    #     TAG = {
    #         "L": "linha",
    #         "T": "tempo",
    #         "LAT": "latitude",
    #         "LON": "longitude",
    #         "HR": "hora",
    #         "M": "minuto",
    #         "PR": "precisao",
    #         "H": "altitude",
    #         "SD": "sd",
    #         "AH": "apogeu_h",
    #         "AT": "apogeu_t",
    #         "DN": "pqd_dn",
    #         "DB": "pqd_db",
    #         "MN": "pqd_mn",
    #         "MB": "pqd_mb",
    #         "TP": "temp",
    #         "R": "roll",
    #         "P": "pitch",
    #         "Y": "yaw",
    #     }

    #     # -------- 1) separação robusta --------
    #     # pega qualquer coisa no formato chave:valor
    #     tokens = re.findall(r'([A-Za-z_]+)\s*:\s*([-+]?\d*\.?\d+)', line)

    #     if not tokens:
    #         return None

    #     raw = {k: None for k in ORDER}
    #     app = {k: self.NAN for k in ORDER}

    #     used_keys = set()

    #     for key_txt, value_txt in tokens:

    #         key_txt = key_txt.upper().strip()
    #         key = TAG.get(key_txt)

    #         # ignora chave desconhecida
    #         if key is None:
    #             continue

    #         # ignora chave duplicada
    #         if key in used_keys:
    #             continue

    #         used_keys.add(key)

    #         num = self._to_float(value_txt)

    #         # salva RAW sempre
    #         raw[key] = num

    #         # valida número
    #         if num is not None and self._in_range(key, num):
    #             app[key] = num
    #         else:
    #             app[key] = self.NAN

    #     return raw, app

    def _parse_packet(self, line: str):
        if not line:
            return None

        line = line.strip()

        LIST = [
            "linha", "tempo", "latitude", "longitude", "hora", "minuto", "precisao",
            "altitude", "sd", "apogeu_h", "apogeu_t",
            "pqd_dn", "pqd_db", "pqd_mn", "pqd_mb",
            "temp", "roll", "pitch", "yaw"
        ]

        # Tabela chave valor
        TAG = {
            "L": "linha",
            "T": "tempo",
            "A": "latitude",
            "O": "longitude",

            "h": "hora",
            "n": "minuto",
            "g": "precisao",

            "H": "altitude",
            "s": "sd",

            "a": "apogeu_h",
            "t": "apogeu_t",

            "D": "pqd_dn",   
            "d": "pqd_db",   
            "N": "pqd_mn",   
            "B": "pqd_mb",

            "c": "temp",

            "R": "roll",
            "P": "pitch",
            "Y": "yaw",
        }

        # Número com sinal, decimal e notação científica
        NUM = r"[-+]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[eE][-+]?\d+)?"

        # Formatos aceitos:
        # H3000
        # T342.17
        # R-1.55
        # A0.000000
        tokens = re.findall(rf"([A-Za-z])\s*({NUM})", line)

        if not tokens:
            return None

        raw = {k: None for k in LIST}
        app = {k: self.NAN for k in LIST}

        used_keys = set()

        for key_txt, value_txt in tokens:

            key_txt = key_txt.strip()

            key = TAG.get(key_txt)

            # ignora chave desconhecida
            if key is None:
                continue

            # ignora chave duplicada no mesmo pacote
            if key in used_keys:
                continue

            used_keys.add(key)

            num = self._to_float(value_txt)

            # salva RAW sempre
            raw[key] = num

            # valida número para uso no app
            if num is not None and self._in_range(key, num):
                app[key] = num
            else:
                app[key] = self.NAN

        return raw, app


    def feed_line(self, line: str):
        self._hz_counter += 1

        # marcou que recebeu algo (para watchdog)
        self._last_rx_time = time.time()

        parsed = self._parse_packet(line)

        # Mostra linha bruta formatada (substitui TAB por espaço)
        # ui_line = line.replace("\t", " ")
        # self.terminal.appendPlainText(ui_line)

        # Mostra linha bruta original (com TAB, para debug)
        self.terminal.appendPlainText(line)


        # ---------------- STATUS SERIAL ----------------
        if not parsed:
            # string veio quebrada
            self._set_serial_status("bad")
            return

        raw, app = parsed

        #  buzzer beep a cada linha valida recebida 
        self._serial_rx_beep()

        # ================= DEBUG TERMINAL =================
        print("------- Linha {} -------".format(app["linha"] if self._is_ok(app["linha"]) else "?"))

        for key, value in app.items():
            if self._is_ok(value):
                print(f"[{key.upper()}] = {value}")
            else:
                print(f"[{key.upper()}] = INVALID")

        # ============================================

        # -------- STATUS POR LINHA --------
        total_fields = len(app)
        valid_fields = sum(1 for v in app.values() if self._is_ok(v))

        self.lbl_serial_packets.setText(f"{valid_fields}/{total_fields}")

        if valid_fields == total_fields:
            self._set_serial_status("ok")
        else:
            self._set_serial_status("bad")
        # ----------------------------------

        # ------------------------------------------------


        # ---- 1) LOGGER: salva RAW (sem NaN do filtro do app) ----
        if self.logger:
            self.logger.save_line(
                raw["linha"], raw["tempo"], raw["latitude"], raw["longitude"],
                raw["hora"], raw["minuto"], raw["precisao"], raw["altitude"], raw["sd"],
                raw["apogeu_h"], raw["apogeu_t"],
                raw["pqd_mn"], raw["pqd_dn"], raw["pqd_mb"], raw["pqd_db"],
                raw["temp"], raw["roll"], raw["pitch"], raw["yaw"]
            )

        # ---- 2) APP: usa APP (com NaN onde falhou) ----
        linha      = app["linha"]
        tempo      = app["tempo"]
        latitude   = app["latitude"]
        longitude  = app["longitude"]
        hora       = app["hora"]
        minuto     = app["minuto"]
        precisao   = app["precisao"]
        altitude   = app["altitude"]
        sd         = app["sd"]
        apogeu_h   = app["apogeu_h"]
        pqd_mn     = app["pqd_mn"]
        pqd_dn     = app["pqd_dn"]
        pqd_mb     = app["pqd_mb"]
        pqd_db     = app["pqd_db"]
        temperatura= app["temp"]
        roll       = app["roll"]
        pitch      = app["pitch"]
        yaw        = app["yaw"]

        # Auto-scroll
        if self.chk_autoscroll.isChecked():
            self.terminal.verticalScrollBar().setValue(
                self.terminal.verticalScrollBar().maximum()
            )

        # GPS/mapa: só processa se não for NaN
        if self._is_ok(latitude) and self._is_ok(longitude):
            if latitude != 0.0 and longitude != 0.0:
                self.last_latlon = (latitude, longitude)
                self.map.add_point(latitude, longitude)
                self._update_distance()
            self.lbl_lat.setText(self._fmt(latitude, "{:.6f}"))
            self.lbl_lon.setText(self._fmt(longitude, "{:.6f}"))

        # horário: só se válido
        if self._is_ok(hora) and self._is_ok(minuto):
            self.lbl_horario.setText(f"{int(hora):02d}:{int(minuto):02d}")

        # precisão
        if self._is_ok(precisao):
            if precisao <= 1.0:
                color = "green"
            elif precisao <= 2.5:
                color = "yellow"
            elif precisao <= 5.0:
                color = "orange"
            else:
                color = "red"
            self.lbl_precisao.setStyleSheet(f"background: {color}; border: 1px solid #ccc; border-radius: 6px;")

        # altitude + gráfico
        if self._is_ok(altitude) and self._is_ok(tempo):
            self.series_t.append(tempo)
            self.series_alt.append(altitude)
            self.alt_curve.setData(self.series_t, self.series_alt)

            if len(self.series_t) >= 2:
                dt = self.series_t[-1] - self.series_t[-2]
                if dt > 1e-6:
                    vel = (self.series_alt[-1] - self.series_alt[-2]) / dt
                    self.lbl_vel.setText(self._fmt(vel, "{:.2f}"))
            self.lbl_alt_max.setText(self._fmt(altitude, "{:.2f}"))

        if self._is_ok(apogeu_h):
            self.lbl_alt_apogeu.setText(self._fmt(apogeu_h, "{:.2f}"))

        # SD
        if self._is_ok(sd):
            self.sd_box.setStyleSheet("background: green; border: 1px solid #ccc; border-radius: 6px;" if sd == 1 else
                                    "background: red; border: 1px solid #ccc; border-radius: 6px;")

        # Paraquedas 
        if self._is_ok(pqd_dn):
            self.lastvalue_dn = self._is_ok(pqd_dn)
        if self._is_ok(pqd_db):
            self.lastvalue_db = self._is_ok(pqd_db)
        if self._is_ok(pqd_mn):
            self.lastvalue_mn = self._is_ok(pqd_mn)
        if self._is_ok(pqd_mb):
            self.lastvalue_mb = self._is_ok(pqd_mb)
        
        self._set_pq(0, pqd_dn if self._is_ok(pqd_dn) else self.lastvalue_dn)
        self._set_pq(1, pqd_db if self._is_ok(pqd_db) else self.lastvalue_db)
        self._set_pq(2, pqd_mn if self._is_ok(pqd_mn) else self.lastvalue_mn)
        self._set_pq(3, pqd_mb if self._is_ok(pqd_mb) else self.lastvalue_mb )

        if self._is_ok(temperatura):
            self.lbl_temp.setText(self._fmt(temperatura, "{:.2f}"))

        # Euler só se vierem válidos (senão não atualiza 3D)
        if self._is_ok(roll) and self._is_ok(pitch) and self._is_ok(yaw):
            self.set_orientation(roll=roll, pitch=pitch, yaw=yaw, degrees=True)
    
    @Slot()
    def _update_hz_display(self):
        now = time.time()
        dt = now - self._hz_last_time

        if dt > 4:
            self._hz_value = self._hz_counter / dt

            self._hz_counter = 0
            self._hz_last_time = now

            self.lbl_serial_hz.setText(f"{self._hz_value:.1f} Hz")


    def _safe_convert(self, value, tipo,  value_type="float"):
        """Tenta converter o valor para o tipo adequado (float ou int). Retorna '~' se não for possível converter."""
        
        if value in (None, "", "-"):
            return tipo  # Para valores None, vazios ou '-'

        try:
            if value_type == "float":
                return float(value)  # Tenta converter para float
            elif value_type == "int":
                return int(value)  # Tenta converter para int
        except (ValueError, TypeError):
            return tipo  # Retorna '~' se a conversão falhar

        


    # ---------- Métodos para a Config ----------
    def set_position(self, lat: float, lon: float):
        """Força a posição no mapa/infos (modo teste)."""
        self.lbl_lat.setText(f"{lat:.6f}")
        self.lbl_lon.setText(f"{lon:.6f}")
        self.last_latlon = (lat, lon)
        self.map.set_position(lat, lon)


    def inject_altitude(self, alt: float, t: Optional[float] = None):
        """Injeta altitude manual (modo teste)."""
        if t is None:
            t = self.series_t[-1] + 0.1 if self.series_t else 0.0
        self.series_t.append(t)
        self.series_alt.append(alt)
        self.alt_curve.setData(self.series_t, self.series_alt)
        if alt > self.alt_max:
            self.alt_max = alt
            self.lbl_alt_max.setText(f"{self.alt_max:.2f}")
        if len(self.series_t) >= 2:
            dt = self.series_t[-1] - self.series_t[-2]
            if dt > 1e-6:
                vel = (self.series_alt[-1] - self.series_alt[-2]) / dt
                self.lbl_vel.setText(f"{vel:.2f}")

    # def set_parachute_state(self, idx: int, activated: bool, t_s: float):
    #     """Define estado e tempo de disparo de um paraquedas."""
    #     self._set_pq(idx, activated=activated, t=t_s)

    def set_home_location(self, lat: float, lon: float):
        self.base_latlon = (lat, lon)
        self._update_distance()
        if hasattr(self, "map"):
            self.map.set_base(lat, lon)



    def _set_pq(self, idx: int, height: float):
        """
        Atualiza a cor de cada paraquedas com base na altura de abertura (height).
        Verde = abriu (height != 0 e != None)
        Cinza = não abriu (height == 0 ou None)
        """
        # Define cor e borda
        if height not in (None, 0.0):
            color = "#b6f5b6"   # verde claro
            border = "#4caf50"
        else:
            color = "#e0e0e0"   # cinza
            border = "#aaa"

        style = f"background: {color}; border: 1px solid {border}; border-radius: 8px;"


        if sys.platform.startswith("linux"):
            if idx == 0:
                self.drogueN_text.setText(f"Normal: {height:.2f} m")
                self.pqd_drogueN.setStyleSheet(style)
            elif idx == 1:
                self.drogueB_text.setText(f"Backup: {height:.2f} m")
                self.pqd_drogueB.setStyleSheet(style)
            elif idx == 2:
                self.mainN_text.setText(f"Normal: {height:.2f} m")
                self.pqd_mainN.setStyleSheet(style)
            elif idx == 3:
                self.mainB_text.setText(f"Backup: {height:.2f} m")
                self.pqd_mainB.setStyleSheet(style)
        else:
            if idx == 0:
                self.drogueN_text.setText(f"Normal: {height:.2f} m")
                self.pqd_drogueN.setStyleSheet(style)
            elif idx == 1:
                self.drogueB_text.setText(f"Backup: {height:.2f} m")
                self.pqd_drogueB.setStyleSheet(style)
            elif idx == 2:
                self.mainN_text.setText(f"Normal: {height:.2f} m")
                self.pqd_mainN.setStyleSheet(style)
            elif idx == 3:
                self.mainB_text.setText(f"Backup: {height:.2f} m")
                self.pqd_mainB.setStyleSheet(style)

    def _open_config_dialog(self):
        dlg = ConfigDialog(self, parent=self)
        dlg.exec()

    def _update_distance(self):
        if self.base_latlon and self.last_latlon:
            dist_m = _haversine_m(self.base_latlon, self.last_latlon)
            self.lbl_dist.setText(f"{dist_m:.1f} m")
        else:
            self.lbl_dist.setText("—")

    # ----------- Simulação opcional -----------
    def _feed_fake(self):
        if not hasattr(self, "_sim_t"):
            self._sim_t = 0.0
            self._sim_lat = -23.55
            self._sim_lon = -46.63

        self._sim_t += 0.2
        self._sim_lat += 0.0002
        self._sim_lon += 0.0002
        apogee = max(0.0, 300.0 * math.sin(self._sim_t * 0.08))
        alt = max(0.0, 250.0 * math.sin(self._sim_t * 0.1) + 50.0)

        # ativa P1 aos 8s, P2 aos 10s…
        p1t = 8.0 if self._sim_t > 8.0 else 0.0
        p2t = 10.0 if self._sim_t > 10.0 else 0.0
        p3t = 0.0
        p4t = 0.0

        line = f"{self._sim_t:.2f}\t{self._sim_lat:.6f}\t{self._sim_lon:.6f}\t{apogee:.2f}\t{alt:.2f}\t" \
               f"{alt:.2f}\t{p1t:.2f}\t{alt-10:.2f}\t{p2t:.2f}\t0\t0"
        self.feed_line(line)

    # ---------- serial --------------
    def _read_serial(self):
        if not (self.ser and self.ser.is_open):
            return

        if not hasattr(self, "_rx_buf"):
            self._rx_buf = b""

        try:
            n = self.ser.in_waiting
            if n <= 0:
                return

            chunk = self.ser.read(n)
            if not chunk:
                return

            self._rx_buf += chunk

            # -------- Proteções anti-lag / anti-buffer infinito --------
            MAX_LINES_PER_TICK = 50          # processa no máximo 50 linhas por tick do timer
            MAX_BUF_BYTES = 256_000          # corta buffer se crescer demais (256 KB)
            MAX_LINE_BYTES = 4096            # descarta linha absurda (>4 KB)

            # se buffer explodiu (ex.: sem \n por muito tempo), corta o mais antigo
            if len(self._rx_buf) > MAX_BUF_BYTES:
                self._rx_buf = self._rx_buf[-MAX_BUF_BYTES:]
                self._set_serial_status("bad")  # indica que algo estranho aconteceu

            processed = 0
            while b"\n" in self._rx_buf and processed < MAX_LINES_PER_TICK:
                raw_line, self._rx_buf = self._rx_buf.split(b"\n", 1)
                raw_line = raw_line.strip(b"\r")
                if not raw_line:
                    continue

                if len(raw_line) > MAX_LINE_BYTES:
                    processed += 1
                    continue

                line = raw_line.decode(errors="ignore").strip()
                if line:
                    self.feed_line(line)

                processed += 1

        except Exception as e:
            print("Erro serial (read_serial):", e)


    def _clear_terminal(self):
        """Limpa o terminal e, se não houver conexão ativa, reseta o status."""
        self.terminal.clear()

        # Se não tem porta aberta ou ainda não recebeu OK → status = desconectado
        # if not self.ser or not self.ser.is_open or not self.connected_ok and self.os_system != "linux":
        #     self._set_status("Desconectado", "#666")
        if not self.ser or not self.ser.is_open or not self.connected_ok:
            self._set_status("Desconectado", "#666")

    def refresh_ports(self):
        """Atualiza a lista de portas COM disponíveis (ignora Bluetooth/virtuais)."""
        import serial.tools.list_ports
        self.combo_ports.clear()

        for port in serial.tools.list_ports.comports():
            desc = port.description.lower()
            device = port.device

            if "bluetooth" in desc: # ignora portas BT
                continue

            if device in ["COM3", "COM4"]: # ignora portas padrão
                continue

            # if self.is_linux:
            #     if not any(x in device for x in ["ttyS", "ttyAMA", "ttyUSB", "ttyACM"]):
            #         continue

            self.combo_ports.addItem(device)

        
        # se não achar nenhuma porta
        if self.combo_ports.count() == 0:
            self.combo_ports.addItem("")  # placeholder vazio

    def connect_serial(self):
        """Conecta na porta escolhida e faz handshake robusto com READY / GPS_COORDS."""
        port = self.combo_ports.currentText().strip()
        if not port:
            QMessageBox.warning(self, "Erro", "Nenhuma porta selecionada")
            self._reset_button_styles()
            self._set_status("Nenhuma porta selecionada", "#b00")
            return

        try:
            if self.connected_ok and self.ser and self.ser.is_open:
                QMessageBox.information(self, "Conexão", f"Já está conectado em {self.ser.port}")
                return

            if self.logger:
                self.logger.write_header([
                    "linha", "tempo.s", "lat.GPS", "lon.GPS", "hora.GPS", "min.GPS",
                    "precisao.GPS", "baro.h.m", "sd.ok.bool", "apogeu.h.m", "apogeu.t.s",
                    "pqd.mainN.m", "pqd.drogueN.m", "pqd.mainB.m", "pqd.drogueB.m",
                    "temperatura", "roll", "pitch", "yaw"
                ])

            # abre serial
            self.ser = serial.Serial(port, 115200, timeout=0.2)
            self.connected_ok = False

            # durante o handshake, não deixa o timer paralelo lendo ao mesmo tempo
            try:
                self.timer_serial.stop()
            except Exception:
                pass

            # limpa buffers
            try:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            except Exception:
                pass

            self._set_status(f"Inicializando em {port}...", "#d4a017")
            busy = self._show_busy_dialog("Resetando telemetria...")

            try:
                # 1) reset
                self.ser.write(b"RST\n")
                QApplication.processEvents()
                time.sleep(1.0)

                # 2) drena prints de boot/reset do ESP
                self._drain_serial_input(seconds=1.20)

                # 3) envia READY e espera OK
                self.ser.write(b"READY\n")
                self._set_status(f"Aguardando OK em {port}...", "#d4a017")

                ok = self._wait_for_token(
                    expected="OK",
                    timeout_s=12.0,
                    busy=busy,
                    busy_text="Aguardando OK da telemetria..."
                )

                if not ok:
                    raise TimeoutError("Timeout aguardando OK")

                # 4) envia GPS_COORDS e espera fluxo do GPS
                self._set_status(f"Solicitando coordenadas em {port}...", "#17d4ce")
                self.ser.write(b"GPS_COORDS\n")

                gps_line = self._wait_for_gps_result(
                    timeout_s=15.0,
                    busy=busy
                )

                lat = None
                lon = None

                if gps_line != "~\t~":
                    try:
                        lat_str, lon_str = gps_line.split("\t")
                        lat = _safe_float(lat_str)
                        lon = _safe_float(lon_str)
                    except Exception:
                        lat = None
                        lon = None

                if lat is not None and lon is not None:
                    self.set_home_location(lat, lon)
                    self.map.set_base(lat, lon)
                    QMessageBox.information(
                        self,
                        "Localização obtida do GPS",
                        f"Lat: {lat:.6f}, Lon: {lon:.6f}"
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "GPS",
                        "Não foi possível obter coordenadas válidas no tempo limite.\nSerial conectada com sucesso!"
                    )

                # 5) drena rapidamente o que restou do handshake/header
                self._drain_serial_input(seconds=0.40)

                # 6) conexão concluída
                self.connected_ok = True
                self.btn_connect.setStyleSheet("background:#c8f7c5; font-weight:600;")
                self._set_status(f"Conectado em {port}", "#060")

            finally:
                busy.close()

            
            self.terminal.appendPlainText("                                                                                                 UFABC Rocket Design")
            self.terminal.appendPlainText("                                                                                                 Ground Station Online")
            self.terminal.appendPlainText("-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------")

            
            self.timer_serial.start(50)

        except serial.SerialException as e:
            self._cleanup_serial_on_error()
            self._set_status("Erro: Falha ao abrir a porta", "#b00")
            QMessageBox.warning(self, "Erro", f"Falha ao abrir a porta {port}:\n{e}")
            self._reset_button_styles()

        except PermissionError:
            self._cleanup_serial_on_error()
            self._set_status("Erro: Acesso negado", "#b00")
            QMessageBox.warning(
                self,
                "Erro",
                f"Acesso negado à porta {port}. Feche outros programas que estejam usando essa COM."
            )
            self._reset_button_styles()

        except Exception as e:
            self._cleanup_serial_on_error()
            self._set_status("Erro: Erro inesperado", "#b00")
            QMessageBox.warning(self, "Erro", f"Erro inesperado:\n{e}")
            self._reset_button_styles()

    def _force_disconnect_serial(self, reason: str = "Desconectado", send_rst: bool = False):
        ser = self.ser

        try:
            if self.timer_serial.isActive():
                self.timer_serial.stop()
        except Exception:
            pass

        self.ser = None
        self.connected_ok = False

        try:
            self._rx_buf = b""
        except Exception:
            pass

        if ser is not None and send_rst:
            try:
                if getattr(ser, "is_open", False):
                    ser.write(b"RST\n")
                    ser.flush()
            except Exception as e:
                print("[SERIAL] Não foi possível enviar RST antes de desconectar:", e)

        if ser is not None:
            try:
                if getattr(ser, "is_open", False):
                    ser.reset_input_buffer()
            except Exception:
                pass

            try:
                if getattr(ser, "is_open", False):
                    ser.reset_output_buffer()
            except Exception:
                pass

            try:
                if getattr(ser, "is_open", False):
                    ser.close()
            except Exception as e:
                print("[SERIAL] Erro ignorado ao fechar porta:", e)

        try:
            self._set_status(reason, "#666")
            self._set_serial_status("idle")
            self.lbl_serial_packets.setText("0/19")
            self.lbl_serial_hz.setText("0.0 Hz")
        except Exception:
            pass

        try:
            self.btn_connect.setStyleSheet("")
            self.btn_disconnect.setStyleSheet("background:#f8d7da; font-weight:600;")
            QTimer.singleShot(500, self._reset_button_styles)
        except Exception:
            pass


    def disconnect_serial(self):

        if self.ser is None:
            QMessageBox.information(self, "Serial", "Nenhuma porta estava conectada")
            self._reset_button_styles()
            return

        self._force_disconnect_serial(
            reason="Desconectado",
            send_rst=True
        )
        
    # def disconnect_serial(self):
    #     """Desconecta, envia RST e pisca vermelho."""
    #     if self.ser and self.ser.is_open:
    #         try:
    #             self._set_status("Desconectado", "#666")        # cinza neutro
    #             self.ser.write(b"RST\n")  # pede reset no ESP
    #             self.timer_serial.stop()
    #             self.ser.close()
    #             self.ser = None
    #             self.connected_ok = False
    #             self.lbl_serial_packets.setText("0/19")

    #             # pisca vermelho
    #             self.btn_disconnect.setStyleSheet("background:#f8d7da; font-weight:600;")
    #             QTimer.singleShot(500, self._reset_button_styles)

    #         except Exception as e:
    #             self._set_status("Erro: Falha ao desconectar", "#b00") # vermelho
    #             QMessageBox.warning(self, "Erro", f"Falha ao desconectar:\n{e}")
    #             self._reset_button_styles()
    #     else:
    #         QMessageBox.information(self, "Serial", "Nenhuma porta estava conectada")
    #         self._reset_button_styles()

    def _readline_decoded(self) -> str:
        if not (self.ser and self.ser.is_open):
            return ""

        try:
            raw = self.ser.readline()
            if not raw:
                return ""
            return raw.decode(errors="ignore").strip()
        except Exception:
            return ""


    def _is_boot_noise_line(self, line: str) -> bool:
        if not line:
            return True

        s = line.strip()

        noise_prefixes = (
            "ets ",
            "rst:",
            "boot:",
            "load:",
            "entry ",
            "configsip:",
            "clk_drv:",
            "mode:",
            "waiting for download",
        )

        if s.lower().startswith(tuple(p.lower() for p in noise_prefixes)):
            return True

        if "ESP-ROM" in s or "invalid header" in s:
            return True

        return False


    def _is_header_line(self, line: str) -> bool:
        s = (line or "").strip()
        if not s:
            return False

        return (
            "URD Ground Station" in s
            or "UFABC Rocket Design" in s
            or s.startswith("---")
        )


    def _is_sat_status_line(self, line: str) -> bool:
        s = (line or "").strip().upper()
        return (
            "SAT" in s
            or "SATS" in s
            or "SATELITE" in s
            or "SATÉLITE" in s
        )


    def _is_valid_coord_line(self, line: str) -> bool:
        s = (line or "").strip()

        if s == "~\t~":
            return True

        if s.count("\t") != 1:
            return False

        try:
            a, b = s.split("\t")
            float(a)
            float(b)
            return True
        except Exception:
            return False


    def _append_handshake_line(self, line: str):
        """
        Mostra no terminal apenas linhas úteis do handshake.
        Evita poluir com lixo de boot.
        """
        if not line:
            return

        if self._is_boot_noise_line(line):
            return

        self.terminal.appendPlainText(line)

        if self.chk_autoscroll.isChecked():
            self.terminal.verticalScrollBar().setValue(
                self.terminal.verticalScrollBar().maximum()
            )


    def _drain_serial_input(self, seconds: float = 1.0):
        """
        Drena a serial por um curto período para limpar ruído de boot/reset.
        """
        t0 = time.time()
        while time.time() - t0 < seconds:
            QApplication.processEvents()
            line = self._readline_decoded()
            if line and not self._is_boot_noise_line(line):
                self._append_handshake_line(line)
            time.sleep(0.01)


    def _wait_for_token(self, expected: str, timeout_s: float, busy=None, busy_text: str = "") -> bool:
        """
        Aguarda uma linha exatamente igual a 'expected'.
        Ignora ruído de boot e outros prints soltos.
        """
        t0 = time.time()

        while time.time() - t0 < timeout_s:
            QApplication.processEvents()

            if busy is not None and busy_text:
                busy.setLabelText(busy_text)
                QApplication.processEvents()

            line = self._readline_decoded()

            if not line:
                time.sleep(0.01)
                continue

            if self._is_boot_noise_line(line):
                continue

            # mostra linhas úteis do handshake
            self._append_handshake_line(line)

            if line.strip() == expected:
                return True

        return False


    def _wait_for_gps_result(self, timeout_s: float, busy=None) -> str:
        """
        Espera o fluxo do GPS:
        - pode vir GPS_OK
        - pode vir status de satélites
        - pode vir header
        - pode vir coordenada válida
        - pode vir ~\\t~
        Retorna:
        - 'lat\\tlon' se vier coordenada
        - '~\\t~' se timeout / falha
        """
        t0 = time.time()
        gps_ok_received = False
        last_sat_line = ""

        while time.time() - t0 < timeout_s:
            QApplication.processEvents()

            if busy is not None:
                if gps_ok_received:
                    busy.setLabelText("GPS_OK recebido. Aguardando coordenadas...")
                elif last_sat_line:
                    busy.setLabelText(f"Aguardando GPS... {last_sat_line}")
                else:
                    busy.setLabelText("Aguardando GPS_OK / coordenadas...")
                QApplication.processEvents()

            line = self._readline_decoded()

            if not line:
                time.sleep(0.01)
                continue

            if self._is_boot_noise_line(line):
                continue

            # header do firmware após inicialização
            if self._is_header_line(line):
                self._append_handshake_line(line)
                continue

            # status de satélites
            if self._is_sat_status_line(line):
                last_sat_line = line.strip()
                self._append_handshake_line(line)
                continue

            # confirmação do comando GPS_COORDS
            if line.strip() == "GPS_OK":
                gps_ok_received = True
                self._append_handshake_line(line)
                continue

            # coordenadas válidas ou timeout do firmware
            if self._is_valid_coord_line(line):
                self._append_handshake_line(line)
                return line.strip()

            # qualquer outro print útil também pode aparecer no terminal
            self._append_handshake_line(line)

        return "~\t~"


    def _cleanup_serial_on_error(self):
        try:
            if self.timer_serial.isActive():
                self.timer_serial.stop()
        except Exception:
            pass

        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass

        self.ser = None
        self.connected_ok = False
    def _reset_button_styles(self):
        """Reseta as cores de Connect/Disconnect para neutro."""
        self.btn_connect.setStyleSheet("")
        self.btn_disconnect.setStyleSheet("")
    
    def _set_status(self, msg: str, color: str = "#666"):
        """Atualiza a barra de status com texto e cor."""
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"color:{color}; font-weight:500; padding:4px; border-top:1px solid #ccc;")

    def _show_busy_dialog(self, text: str):
        dlg = BusySpinnerDialog(text, self)
        dlg.show()
        QApplication.processEvents()
        return dlg
    
    def _serial_rx_beep(self):
        if not self.serial_beep_enabled:
            return

        now = time.monotonic()
        if now - self._last_beep_ts < 0.08:
            return

        self._last_beep_ts = now

        try:
            if self._beep_mode == "gpio" and self._buzzer:
                self._buzzer.on()
                QTimer.singleShot(30, self._buzzer.off)

            elif self._beep_mode == "winsound":
                import winsound
                # winsound.MessageBeep()
                # alternativa:
                winsound.Beep(600, 60)

        except Exception:
            pass
    
    def set_serial_beep_enabled(self, enabled: bool):
        self.serial_beep_enabled = bool(enabled)

    def reset_altitude_graph(self):
        try:
            self.alt_curve.setData([], [])
        except Exception:
            pass

        if hasattr(self, "alt_x"):
            self.alt_x.clear()
        if hasattr(self, "alt_y"):
            self.alt_y.clear()
        if hasattr(self, "alt_data"):
            self.alt_data.clear()
        if hasattr(self, "plot_time"):
            self.plot_time.clear()
        if hasattr(self, "plot_alt"):
            self.plot_alt.clear()
    # Net
    def onNetChanged(self, status: bool):
        self.apply_map_mode()

    
    # -------- Controle de execução --------
    def pause(self):
        # mapa
        if hasattr(self, "map"):
            self.map.page().runJavaScript("if(window.pauseRender) pauseRender();")

        # 3D
        if hasattr(self, "rocket3d"):
            self.rocket3d.pause()

    def resume(self):
        # mapa
        if hasattr(self, "map"):
            self.map.page().runJavaScript("if(window.resumeRender) resumeRender();")

        # 3D
        if hasattr(self, "rocket3d"):
            self.rocket3d.resume()

    def ask_logger(self):
            reply = QMessageBox.question(
                self,
                "Salvar Dados?",
                "Deseja salvar os dados desta sessão em arquivo?",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                filename, _ = QFileDialog.getSaveFileName(
                    self,
                    "Escolher local para salvar log",
                    f"log_{time.strftime('%Y%m%d_%H%M%S')}.txt",
                    "Text Files (*.txt)"
                )
                if filename:
                    self.logger = Logger(filename)
                else:
                    self.logger = None






# ---------- utils ----------
def closeEvent(self, event):
    if hasattr(self, "map"):
        self.map.deleteLater()
    super().closeEvent(event)


def _safe_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except Exception:
        return None


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Distância em metros entre (lat,lon) a e b."""
    R = 6371000.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(h))


