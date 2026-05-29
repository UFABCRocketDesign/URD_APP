# views/gs_flight_rasp.py
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, QRegularExpression
from PySide6.QtGui import QColor, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QPushButton, QPlainTextEdit, QCheckBox, QGroupBox, QComboBox,
    QScrollArea, QSizePolicy, QLineEdit, QMessageBox, QApplication,
    QProgressDialog
)

import pyqtgraph as pg

from views.gs_flight_single import GSFlightSinglePage
from views.map_widget import MapWidget
from views.rocket_3d import Rocket3DView


class GSFlightRaspPage(GSFlightSinglePage):
    """
    Reaproveita a lógica da GSFlightSinglePage e troca apenas o layout
    para a versão do Raspberry / tela menor.
    """
    def _make_info_card(self, title: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("infoCard")
        card.setFrameShape(QFrame.NoFrame)
        card.setStyleSheet("""
            QFrame#infoCard {
                background: transparent;
                border: none;
            }
        """)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("""
            font-size: 11px;
            background: transparent;
            border: none;
        """)

        value_box = QFrame()
        value_box.setObjectName("infoValueBox")
        value_box.setFrameShape(QFrame.NoFrame)
        value_box.setMinimumHeight(26)
        value_box.setMaximumHeight(26)
        value_box.setStyleSheet("""
            QFrame#infoValueBox {
                background-color: #fdfdfd;
                border: 1px solid #c2c8d2;
                border-radius: 6px;
                color: #000000;
            }
        """)

        box_lay = QVBoxLayout(value_box)
        box_lay.setContentsMargins(8, 0, 8, 0)
        box_lay.setSpacing(0)

        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: 800;
                background: transparent;
                color: black;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)

        box_lay.addWidget(value_label)

        lay.addWidget(title_lbl)
        lay.addWidget(value_box)

        return card
    
    def _build_ui(self, os_name):
        self.setObjectName("gs_rasp_page")

        # ============================================================
        # ROOT + SCROLL
        # ============================================================
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        root.addWidget(scroll)

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        scroll.setWidget(content)

        main = QVBoxLayout(content)
        main.setContentsMargins(4, 4, 4, 4)
        main.setSpacing(8)

        # ============================================================
        # LINHA 1
        # [ MAPA ]   [ INFOS / PARAQUEDAS / GPS ]
        # ============================================================
        row1 = QGridLayout()
        row1.setHorizontalSpacing(8)
        row1.setVerticalSpacing(8)

        # ---------- MAPA ----------
        map_group = QGroupBox("Mapa")
        map_lay = QVBoxLayout(map_group)
        map_lay.setContentsMargins(6, 6, 6, 6)
        map_lay.setSpacing(6)

        self.map = MapWidget(
            offline=not self.net.get_status(),
            satellite=self.is_satellite,
            tile_folder=None
        )
        self.apply_map_mode()
        self.map.setMinimumHeight(260)
        self.map.setMinimumWidth(380)
        self.map.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        map_lay.addWidget(self.map)

        map_buttons = QHBoxLayout()
        map_buttons.setSpacing(6)

        map_lay.addLayout(map_buttons)

        # ---------- COLUNA DE INFOS ----------
        infos_col = QWidget()
        infos_col_lay = QVBoxLayout(infos_col)
        infos_col_lay.setContentsMargins(0, 0, 0, 0)
        infos_col_lay.setSpacing(8)

        # ========================
        # PARAQUEDAS
        # ========================
        pq_group = QGroupBox("Paraquedas")
        pq_lay = QGridLayout(pq_group)
        pq_lay.setHorizontalSpacing(6)
        pq_lay.setVerticalSpacing(4)

        label_drogue = QLabel("1st Event")
        label_drogue.setAlignment(Qt.AlignCenter)
        pq_lay.addWidget(label_drogue, 0, 0, 1, 2)

        self.pqd_drogueN = QFrame()
        self.pqd_drogueN.setFrameShape(QFrame.StyledPanel)
        self.pqd_drogueN.setStyleSheet(
            "background: #e0e0e0; border: 1px solid #aaa; border-radius: 8px;"
        )
        self.pqd_drogueN.setMinimumSize(28, 28)
        pq_lay.addWidget(self.pqd_drogueN, 1, 0)

        self.pqd_drogueB = QFrame()
        self.pqd_drogueB.setFrameShape(QFrame.StyledPanel)
        self.pqd_drogueB.setStyleSheet(
            "background: #e0e0e0; border: 1px solid #aaa; border-radius: 8px;"
        )
        self.pqd_drogueB.setMinimumSize(28, 28)
        pq_lay.addWidget(self.pqd_drogueB, 1, 1)

        self.drogueN_text = QLabel("N")
        self.drogueN_text.setAlignment(Qt.AlignCenter)
        pq_lay.addWidget(self.drogueN_text, 2, 0)

        self.drogueB_text = QLabel("B")
        self.drogueB_text.setAlignment(Qt.AlignCenter)
        pq_lay.addWidget(self.drogueB_text, 2, 1)

        label_main = QLabel("2nd Event")
        label_main.setAlignment(Qt.AlignCenter)
        pq_lay.addWidget(label_main, 3, 0, 1, 2)

        self.pqd_mainN = QFrame()
        self.pqd_mainN.setFrameShape(QFrame.StyledPanel)
        self.pqd_mainN.setStyleSheet(
            "background: #e0e0e0; border: 1px solid #aaa; border-radius: 8px;"
        )
        self.pqd_mainN.setMinimumSize(28, 28)
        pq_lay.addWidget(self.pqd_mainN, 4, 0)

        self.pqd_mainB = QFrame()
        self.pqd_mainB.setFrameShape(QFrame.StyledPanel)
        self.pqd_mainB.setStyleSheet(
            "background: #e0e0e0; border: 1px solid #aaa; border-radius: 8px;"
        )
        self.pqd_mainB.setMinimumSize(28, 28)
        pq_lay.addWidget(self.pqd_mainB, 4, 1)

        self.mainN_text = QLabel("N")
        self.mainN_text.setAlignment(Qt.AlignCenter)
        pq_lay.addWidget(self.mainN_text, 5, 0)

        self.mainB_text = QLabel("B")
        self.mainB_text.setAlignment(Qt.AlignCenter)
        pq_lay.addWidget(self.mainB_text, 5, 1)

        # ========================
        # INFOS
        # ========================
        info_group = QGroupBox("Infos")
        info_lay = QGridLayout(info_group)
        info_lay.setHorizontalSpacing(10)
        info_lay.setVerticalSpacing(6)
        info_lay.setContentsMargins(6, 6, 6, 6)

        self.lbl_alt_max = QLabel("—")
        self.lbl_alt_apogeu = QLabel("—")
        self.lbl_vel = QLabel("—")
        self.lbl_temp = QLabel("—")

        info_lay.addWidget(self._make_info_card("Altura Atual (m)", self.lbl_alt_max), 0, 0)
        info_lay.addWidget(self._make_info_card("Velocidade vertical (m/s)", self.lbl_vel), 0, 1)

        info_lay.addWidget(self._make_info_card("Altura Máx (m)", self.lbl_alt_apogeu), 1, 0)
        info_lay.addWidget(self._make_info_card("Temperatura (°C)", self.lbl_temp), 1, 1)

        sd_title = QLabel("SD Card")
        sd_title.setAlignment(Qt.AlignCenter)
        sd_title.setStyleSheet("""
            font-weight: 700;
            background: transparent;
            border: none;
        """)
        info_lay.addWidget(sd_title, 2, 0, 1, 2)

        self.sd_box = QFrame()
        self.sd_box.setFrameShape(QFrame.StyledPanel)
        self.sd_box.setMinimumSize(40, 18)
        self.sd_box.setMaximumHeight(18)
        self.sd_box.setStyleSheet(
            "background: red; border: 1px solid #b0b0b0; border-radius: 6px;"
        )
        info_lay.addWidget(self.sd_box, 3, 0, 1, 2, alignment=Qt.AlignCenter)

        # ========================
        # GPS
        # ========================
        gps_group = QGroupBox("GPS")
        gps_lay = QGridLayout(gps_group)
        gps_lay.setHorizontalSpacing(8)
        gps_lay.setVerticalSpacing(4)
        gps_lay.setContentsMargins(6, 6, 6, 6)

        self.lbl_horario = QLabel("—")
        self.lbl_lat = QLabel("—")
        self.lbl_lon = QLabel("—")
        self.lbl_dist = QLabel("—")

        # Horário (mantém como texto)
        horario_title = QLabel("Horário")
        horario_title.setAlignment(Qt.AlignCenter)
        gps_lay.addWidget(horario_title, 0, 0, 1, 2)
        gps_lay.addWidget(self.lbl_horario, 1, 0, 1, 2, alignment=Qt.AlignCenter)

        # Títulos lat/lon
        lat_title = QLabel("Latitude")
        lat_title.setAlignment(Qt.AlignCenter)
        gps_lay.addWidget(lat_title, 2, 0)

        lon_title = QLabel("Longitude")
        lon_title.setAlignment(Qt.AlignCenter)
        gps_lay.addWidget(lon_title, 2, 1)

        # Caixa latitude
        self.lat_box = QFrame()
        self.lat_box.setFrameShape(QFrame.NoFrame)
        self.lat_box.setMinimumHeight(26)
        self.lat_box.setMaximumHeight(26)
        self.lat_box.setStyleSheet("""
            background-color: #fdfdfd;
            border: 1px solid #c2c8d2;
            border-radius: 6px;
            color: #000000;
        """)
        lat_box_lay = QVBoxLayout(self.lat_box)
        lat_box_lay.setContentsMargins(8, 0, 8, 0)
        lat_box_lay.setSpacing(0)
        self.lbl_lat.setAlignment(Qt.AlignCenter)
        self.lbl_lat.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: 800;
                background: transparent;
                color: black;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        lat_box_lay.addWidget(self.lbl_lat)
        gps_lay.addWidget(self.lat_box, 3, 0)

        # Caixa longitude
        self.lon_box = QFrame()
        self.lon_box.setFrameShape(QFrame.NoFrame)
        self.lon_box.setMinimumHeight(26)
        self.lon_box.setMaximumHeight(26)
        self.lon_box.setStyleSheet("""
            background-color: #fdfdfd;
            border: 1px solid #c2c8d2;
            border-radius: 6px;
            color: #000000;
        """)
        lon_box_lay = QVBoxLayout(self.lon_box)
        lon_box_lay.setContentsMargins(8, 0, 8, 0)
        lon_box_lay.setSpacing(0)
        self.lbl_lon.setAlignment(Qt.AlignCenter)
        self.lbl_lon.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: 800;
                background: transparent;
                color: black;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        lon_box_lay.addWidget(self.lbl_lon)
        gps_lay.addWidget(self.lon_box, 3, 1)

        # Distância base
        dist_title = QLabel("Distância Base")
        dist_title.setAlignment(Qt.AlignCenter)
        gps_lay.addWidget(dist_title, 4, 0, 1, 2)

        self.dist_box = QFrame()
        self.dist_box.setFrameShape(QFrame.NoFrame)
        self.dist_box.setMinimumHeight(26)
        self.dist_box.setMaximumHeight(26)
        self.dist_box.setStyleSheet("""
            background-color: #fdfdfd;
            border: 1px solid #c2c8d2;
            border-radius: 6px;
            color: #000000;
        """)
        dist_box_lay = QVBoxLayout(self.dist_box)
        dist_box_lay.setContentsMargins(8, 0, 8, 0)
        dist_box_lay.setSpacing(0)
        self.lbl_dist.setAlignment(Qt.AlignCenter)
        self.lbl_dist.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: 800;
                background: transparent;
                color: black;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        dist_box_lay.addWidget(self.lbl_dist)
        gps_lay.addWidget(self.dist_box, 5, 0, 1, 2)

        # Precisão
        precisao_title = QLabel("Precisão (HDOP)")
        precisao_title.setAlignment(Qt.AlignCenter)
        gps_lay.addWidget(precisao_title, 6, 0, 1, 2)

        self.lbl_precisao = QFrame()
        self.lbl_precisao.setFrameShape(QFrame.StyledPanel)
        self.lbl_precisao.setMinimumSize(40, 18)
        self.lbl_precisao.setMaximumHeight(18)
        self.lbl_precisao.setStyleSheet(
            "background: red; border: 1px solid #b0b0b0; border-radius: 6px;"
        )
        gps_lay.addWidget(self.lbl_precisao, 7, 0, 1, 2, alignment=Qt.AlignCenter)
        infos_col_lay.addWidget(pq_group)
        infos_col_lay.addWidget(info_group)
        infos_col_lay.addWidget(gps_group)
        infos_col_lay.addStretch(1)
        
        self.sd_box = QFrame()
        self.sd_box.setFrameShape(QFrame.StyledPanel)
        self.sd_box.setMinimumSize(40, 18)
        self.sd_box.setMaximumHeight(18)
        self.sd_box.setStyleSheet(
            "background: red; border: 1px solid #b0b0b0; border-radius: 6px;"
        )

        row1.addWidget(map_group, 0, 0)
        row1.addWidget(infos_col, 0, 1)
        row1.setColumnStretch(0, 3)
        row1.setColumnStretch(1, 2)

        main.addLayout(row1)

        # ============================================================
        # LINHA 2
        # [ BOTOES ]
        # [ STATUS SERIAL ]
        # [ TERMINAL ]
        # [ STATUS DA PAGINA ]
        # ============================================================
        row2_group = QGroupBox("Comunicação")
        row2_lay = QVBoxLayout(row2_group)
        row2_lay.setContentsMargins(6, 6, 6, 6)
        row2_lay.setSpacing(6)

        controls_top = QHBoxLayout()
        controls_top.setSpacing(6)

        self.chk_autoscroll = QCheckBox("Auto-scroll")
        self.chk_autoscroll.setChecked(True)

        porta_label = QLabel("Porta:")
        self.combo_ports = QComboBox()
        self.combo_ports.setEditable(True)
        self.combo_ports.setMinimumWidth(130)

        self.btn_connect = QPushButton("Conectar")
        self.btn_disconnect = QPushButton("Desconectar")
        self.btn_clear = QPushButton("Limpar Terminal")
        self.btn_cfg = QPushButton("Configurações")

        controls_top.addWidget(self.chk_autoscroll)
        controls_top.addSpacing(8)
        controls_top.addWidget(porta_label)
        controls_top.addWidget(self.combo_ports, 1)
        controls_top.addWidget(self.btn_connect)
        controls_top.addWidget(self.btn_disconnect)
        controls_top.addWidget(self.btn_clear)
        controls_top.addWidget(self.btn_cfg)

        # ============================================================
        # LINHA DE CONFIGURAÇÃO LORA
        # ============================================================
        lora_cfg_row = QHBoxLayout()
        lora_cfg_row.setSpacing(6)

        self.combo_lora_freq = QComboBox()
        self.combo_lora_freq.setEditable(True)
        self.combo_lora_freq.setMinimumWidth(170)

        for freq in range(862, 932):
            channel_dec = freq - 862
            self.combo_lora_freq.addItem(
                f"FREQ{freq} / CHAN{channel_dec}",
                str(channel_dec)
            )

        self.combo_lora_freq.setCurrentText("FREQ903 / CHAN29")

        self.input_lora_addr = QLineEdit()
        self.input_lora_addr.setPlaceholderText("0xA1B2")
        self.input_lora_addr.setToolTip("Address hexadecimal de 4 casas. Exemplo: A1B2")
        self.input_lora_addr.setMaximumWidth(120)
        self.input_lora_addr.setMaxLength(6)

        address_validator = QRegularExpressionValidator(
            QRegularExpression(r"^(0x|0X)?[0-9A-Fa-f]{0,4}$")
        )
        self.input_lora_addr.setValidator(address_validator)

        self.btn_lora_change = QPushButton("Enviar LoRa")
        self.btn_lora_change.setMinimumWidth(110)

        self.btn_lora_force_change = QPushButton("Forced")
        self.btn_lora_force_change.setMinimumWidth(90)
        self.btn_lora_force_change.setToolTip("Força a troca apenas na Ground Station.")

        lora_cfg_row.addStretch(1)
        lora_cfg_row.addWidget(QLabel("Freq/CHAN:"))
        lora_cfg_row.addWidget(self.combo_lora_freq)
        lora_cfg_row.addWidget(QLabel("Address HEX:"))
        lora_cfg_row.addWidget(self.input_lora_addr)
        lora_cfg_row.addWidget(self.btn_lora_change)
        lora_cfg_row.addWidget(self.btn_lora_force_change)
        
        # -------- status serial em cima --------
        self.serial_block = QWidget()
        serial_layout = QHBoxLayout(self.serial_block)
        serial_layout.setContentsMargins(0, 2, 0, 0)
        serial_layout.setSpacing(8)

        self.lbl_serial_title = QLabel("Status Serial")
        self.lbl_serial_hz = QLabel("0.0 Hz")

        self.serial_status_box = QFrame()
        self.serial_status_box.setFixedSize(16, 16)
        self.serial_status_box.setStyleSheet(
            "background:#ffcc00; border:1px solid #aaa; border-radius:4px;"
        )

        self.lbl_serial_status = QLabel("IDLE")
        self.lbl_serial_packets = QLabel("0/18")

        serial_layout.addStretch(1)
        serial_layout.addWidget(self.lbl_serial_title)
        serial_layout.addWidget(self.lbl_serial_hz)
        serial_layout.addWidget(self.serial_status_box)
        serial_layout.addWidget(self.lbl_serial_status)
        serial_layout.addWidget(self.lbl_serial_packets)
        serial_layout.addStretch(1)

        self.lbl_header = QLabel("Terminal de Dados")
        self.lbl_header.setStyleSheet("font-weight: bold; color: #bbb; font-size: 11px;")
        self.lbl_header.setAlignment(Qt.AlignCenter)

        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setMinimumHeight(160)
        self.terminal.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.terminal.setStyleSheet(
            "background: #0f0f0f; font-family: Consolas, monospace;"
        )
        self.terminal.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.terminal.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # -------- barra de status embaixo --------
        self.lbl_status = QLabel("Desconectado")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet(
            "color:#666; font-style:italic; padding:4px; border-top:1px solid #ccc;"
        )

        row2_lay.addLayout(controls_top)
        row2_lay.addLayout(lora_cfg_row)
        row2_lay.addWidget(self.lbl_header)
        row2_lay.addWidget(self.serial_block)
        row2_lay.addWidget(self.terminal)
        row2_lay.addWidget(self.lbl_status)

        main.addWidget(row2_group)

        # ============================================================
        # LINHA 3
        # [ ORIENTAÇÃO 3D ]   [ GRÁFICO ]
        # ============================================================
        row3 = QGridLayout()
        row3.setHorizontalSpacing(8)
        row3.setVerticalSpacing(8)

        orient_group = QGroupBox("Orientação 3D")
        orient_lay = QVBoxLayout(orient_group)
        orient_lay.setContentsMargins(6, 6, 6, 6)

        self.rocket3d = Rocket3DView()
        self.rocket3d.setMinimumHeight(240)
        self.rocket3d.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        orient_lay.addWidget(self.rocket3d)

        graph_group = QGroupBox("Altitude")
        graph_lay = QVBoxLayout(graph_group)
        graph_lay.setContentsMargins(6, 6, 6, 6)

        pg.setConfigOptions(antialias=True)
        self.alt_plot = pg.PlotWidget(title="Altitude (m) vs Tempo (s)")
        self.alt_plot.showGrid(x=True, y=True, alpha=0.3)
        self.alt_curve = self.alt_plot.plot(
            [], [], pen=pg.mkPen(QColor(0, 150, 255), width=2)
        )
        self.alt_plot.setMinimumHeight(240)
        self.alt_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        graph_lay.addWidget(self.alt_plot)

        row3.addWidget(orient_group, 0, 0)
        row3.addWidget(graph_group, 0, 1)
        row3.setColumnStretch(0, 1)
        row3.setColumnStretch(1, 1)

        main.addLayout(row3)


        # ============================================================
        # SINAIS
        # ============================================================
        self.btn_clear.clicked.connect(self._clear_terminal)
        self.btn_cfg.clicked.connect(self._open_config_dialog)
        self.btn_connect.clicked.connect(self.connect_serial)
        self.btn_disconnect.clicked.connect(self.disconnect_serial)
        self.combo_ports.mousePressEvent = lambda ev: (
            self.refresh_ports(), QComboBox.mousePressEvent(self.combo_ports, ev)
        )
        self.btn_lora_change.clicked.connect(self._send_lora_change_config)
        self.btn_lora_force_change.clicked.connect(self._send_lora_forced_change_config)
    
    def _send_lora_forced_change_config(self):
        self._send_lora_change_config(forced=True)


    def _send_lora_change_config(self, forced: bool = False):
        """
        Normal:
            APP -> GS : MUDAR_FREQUENCIA
            APP -> GS : VALS:CHANXX_A1B2

            GS -> APP : MUDAR_OK
            GS -> APP : MUDAR_CERTO ou erro

        Forced:
            APP -> GS : MUDAR_AGORA
            APP -> GS : VALS:CHANXX_A1B2

            GS -> APP : MUDAR_AGORA_OK ou erro
        """

        GS_TIMEOUT_S = 30.0
        UI_MARGIN_S = 5.0
        UI_STAGE_TIMEOUT_S = GS_TIMEOUT_S + UI_MARGIN_S
        SEND_DELAY_S = 0.15

        error_messages = {
            "MUDAR_ERRO_SEM_PEDIDO": (
                "A Ground Station recebeu VALS sem antes receber "
                "MUDAR_FREQUENCIA ou MUDAR_AGORA."
            ),
            "MUDAR_ERRO_VALS_FORA_DE_HORA": (
                "A Ground Station recebeu VALS fora do estado esperado."
            ),
            "MUDAR_ERRO_FORMATO": (
                "Formato inválido.\n\n"
                "O esperado é:\n"
                "VALS:CHANXX_A1B2\n\n"
                "Exemplo:\n"
                "VALS:CHAN29_A1B2"
            ),
            "MUDAR_ERRO_CHAN": (
                "CHAN inválido.\n\n"
                "Use hexadecimal com 2 casas.\n"
                "Exemplos: 29, 2A, C3."
            ),
            "MUDAR_ERRO_ADDR": (
                "Address inválido.\n\n"
                "Use hexadecimal com 4 casas.\n"
                "Exemplos: A1B2, 0017, FFFF."
            ),
            "MUDAR_AGORA_ERRO": (
                "A Ground Station falhou ao aplicar a configuração forçada."
            ),
            "MUDAR_ERRO_CONFIRMACAO_FC_FORA_DE_HORA": (
                "O Flight Computer confirmou fora da etapa esperada."
            ),
            "MUDAR_ERRO_CONFIRMACAO_FC_DIFERENTE": (
                "O Flight Computer confirmou uma configuração diferente da solicitada."
            ),
            "MUDAR_ERRO_GS": (
                "A Ground Station falhou ao aplicar a própria configuração LoRa."
            ),
            "MUDAR_ERRO": (
                "Erro geral durante a troca LoRa."
            ),
            "MUDAR_ERRO_REPORTADO_FC": (
                "O Flight Computer reportou erro durante a troca LoRa."
            ),
            "MUDAR_ERRO_TIMEOUT_GERAL": (
                "A Ground Station reportou timeout geral da troca LoRa."
            ),
            "MUDAR_ERRO_TIMEOUT_VALS": (
                "A Ground Station esperou VALS:CHANXX_A1B2 e não recebeu a tempo."
            ),
            "MUDAR_ERRO_TIMEOUT_CONFIRMACAO_FC": (
                "A Ground Station não recebeu a confirmação inicial do Flight Computer a tempo."
            ),
            "MUDAR_ERRO_TIMEOUT_FINAL": (
                "A Ground Station não recebeu JUR0_JUR4D1NH0 do Flight Computer a tempo."
            ),
            "MUDAR_FREQUENCIA_ERROR": (
                "Erro antigo recebido da Ground Station.\n\n"
                "Ela recusou o pedido ou os valores da configuração LoRa."
            ),
        }

        all_error_tokens = set(error_messages.keys())

        def is_hex_text(text: str, expected_len: int) -> bool:
            if len(text) != expected_len:
                return False

            for c in text:
                if c not in "0123456789ABCDEFabcdef":
                    return False

            return True

        def parse_channel_hex_from_ui() -> str:
            text = self.combo_lora_freq.currentText().strip().upper()

            if not text:
                raise ValueError("Selecione ou digite uma frequência/canal.")

            current_index = self.combo_lora_freq.currentIndex()

            if current_index >= 0:
                item_text = self.combo_lora_freq.itemText(current_index).strip().upper()
                item_data = self.combo_lora_freq.itemData(current_index)

                if text == item_text and item_data:
                    return str(item_data).upper().zfill(2)

            # Aceita:
            # FREQ903 / CHAN29
            # CHAN29
            # 29
            # C3
            if "CHAN" in text:
                after_chan = text.split("CHAN", 1)[1]
                after_chan = after_chan.replace("/", " ").strip()

                parts = after_chan.split()

                if not parts:
                    raise ValueError("CHAN inválido. Use algo como CHAN29.")

                chan_text = parts[0].strip().upper()

                if not is_hex_text(chan_text, 2):
                    raise ValueError("O CHAN deve ter exatamente 2 casas hexadecimais. Exemplo: 29 ou C3.")

                chan_value = int(chan_text, 16)

                if chan_value < 0x00 or chan_value > 0xFF:
                    raise ValueError("O CHAN deve estar entre 00 e FF.")

                return chan_text

            # Aceita:
            # FREQ903
            if text.startswith("FREQ"):
                freq_part = text.replace("FREQ", "", 1).strip()

                digits = ""

                for c in freq_part:
                    if c.isdigit():
                        digits += c
                    else:
                        break

                if not digits:
                    raise ValueError("Frequência inválida. Use algo como FREQ903.")

                freq_value = int(digits)

                if freq_value < 862 or freq_value > 931:
                    raise ValueError("A frequência deve estar entre FREQ862 e FREQ931.")

                return f"{freq_value - 862:02X}"

            # Aceita:
            # 903
            if text.isdigit() and len(text) == 3:
                freq_value = int(text)

                if freq_value < 862 or freq_value > 931:
                    raise ValueError("A frequência deve estar entre 862 e 931 MHz.")

                return f"{freq_value - 862:02X}"

            # Aceita:
            # 29
            # C3
            if is_hex_text(text, 2):
                chan_value = int(text, 16)

                if chan_value < 0x00 or chan_value > 0xFF:
                    raise ValueError("O CHAN deve estar entre 00 e FF.")

                return text.upper()

            raise ValueError(
                "Campo de frequência/canal inválido.\n\n"
                "Use um dos formatos:\n"
                "FREQ903\n"
                "903\n"
                "CHAN29\n"
                "29\n"
                "C3"
            )

        def parse_address_hex_from_ui() -> str:
            text = self.input_lora_addr.text().strip().upper()

            if not text:
                raise ValueError("Digite o Address hexadecimal.")

            if text.startswith("0X"):
                text = text[2:]

            if not is_hex_text(text, 4):
                raise ValueError(
                    "O Address deve ter exatamente 4 casas hexadecimais.\n\n"
                    "Exemplos válidos:\n"
                    "A1B2\n"
                    "0017\n"
                    "FFFF\n"
                    "0xA1B2"
                )

            address_value = int(text, 16)

            if address_value < 0x0000 or address_value > 0xFFFF:
                raise ValueError("O Address deve estar entre 0000 e FFFF.")

            return text.upper()

        def send_line(text: str):
            if not self.ser or not self.ser.is_open:
                raise RuntimeError("Serial não conectada.")

            self.ser.write((text.strip() + "\n").encode("utf-8"))

        def append_terminal(text: str):
            self.terminal.appendPlainText(text)

            if self.chk_autoscroll.isChecked():
                self.terminal.verticalScrollBar().setValue(
                    self.terminal.verticalScrollBar().maximum()
                )

        def finish_error(status_text: str, message_text: str):
            self._set_status(status_text, "#b00")
            QMessageBox.warning(self, "LoRa", message_text)

        def finish_success(status_text: str, message_text: str):
            self._set_status(status_text, "#060")
            QMessageBox.information(self, "LoRa", message_text)

        def wait_for_response(expected_tokens: set[str], timeout_s: float, busy, stage_text: str) -> str:
            """
            Espera por um token esperado ou por qualquer erro conhecido.

            Retorna:
                - token recebido
                - "" em timeout local da UI
            """
            start_time = time.time()
            spinner = ["|", "/", "-", "\\"]
            spinner_index = 0

            tokens_to_check = set(expected_tokens) | all_error_tokens

            while (time.time() - start_time) < timeout_s:
                elapsed = time.time() - start_time
                remaining = max(0.0, timeout_s - elapsed)

                if busy is not None:
                    spinner_char = spinner[spinner_index % len(spinner)]
                    spinner_index += 1

                    busy.setLabelText(
                        f"{stage_text}\n\n"
                        f"{spinner_char} Timeout da UI em {remaining:0.1f} s"
                    )

                QApplication.processEvents()

                line = self._readline_decoded()

                if not line:
                    time.sleep(0.01)
                    continue

                line = line.strip()

                if not line:
                    continue

                if self._is_boot_noise_line(line):
                    continue

                append_terminal(f"[LORA CFG RX] {line}")

                token = line.strip()

                if token in tokens_to_check:
                    return token

                QApplication.processEvents()

            return ""

        # ============================================================
        # VALIDAÇÃO DA UI
        # ============================================================
        try:
            channel_hex = parse_channel_hex_from_ui()
            address_hex = parse_address_hex_from_ui()
        except ValueError as e:
            QMessageBox.warning(self, "LoRa", str(e))
            return

        if not self.ser or not self.ser.is_open or not self.connected_ok:
            QMessageBox.warning(self, "LoRa", "A placa não está conectada.")
            return

        request_packet = "MUDAR_AGORA" if forced else "MUDAR_FREQUENCIA"
        vals_packet = f"VALS:CHAN{channel_hex}_{address_hex}"

        # ============================================================
        # PAUSA O LEITOR SERIAL NORMAL PARA EVITAR CONFLITO
        # ============================================================
        timer_was_active = False

        try:
            timer_was_active = self.timer_serial.isActive()
        except Exception:
            timer_was_active = False

        busy = None

        try:
            self.btn_lora_change.setEnabled(False)

            if hasattr(self, "btn_lora_force_change"):
                self.btn_lora_force_change.setEnabled(False)

            if timer_was_active:
                self.timer_serial.stop()

            try:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            except Exception:
                pass

            busy = QProgressDialog(
                "Solicitando configuração LoRa...",
                None,
                0,
                0,
                self
            )
            busy.setWindowTitle("Configurando LoRa")
            busy.setWindowModality(Qt.NonModal)
            busy.setMinimumDuration(0)
            busy.setAutoClose(False)
            busy.setAutoReset(False)
            busy.show()

            self._set_status("Solicitando configuração LoRa...", "#d4a017")

            append_terminal("")
            append_terminal("[LORA CFG] Solicitando configuração LoRa...")
            append_terminal(f"[LORA CFG] CHAN=0x{channel_hex} ADDRESS=0x{address_hex}")
            append_terminal(f"[LORA CFG TX] {request_packet}")

            send_line(request_packet)

            t_delay = time.time()

            while (time.time() - t_delay) < SEND_DELAY_S:
                QApplication.processEvents()
                time.sleep(0.01)

            append_terminal(f"[LORA CFG TX] {vals_packet}")

            send_line(vals_packet)

            # ========================================================
            # MODO FORÇADO
            # ========================================================
            if forced:
                self._set_status("Aguardando confirmação da troca forçada LoRa...", "#d4a017")

                forced_response = wait_for_response(
                    expected_tokens={"MUDAR_AGORA_OK"},
                    timeout_s=UI_STAGE_TIMEOUT_S,
                    busy=busy,
                    stage_text="Aguardando MUDAR_AGORA_OK da Ground Station..."
                )

                if forced_response == "":
                    finish_error(
                        "Timeout aguardando MUDAR_AGORA_OK",
                        "Timeout da UI aguardando confirmação da troca forçada.\n\n"
                        "Como a GS usa timeout de 30 s por etapa, a UI esperou 35 s "
                        "e não recebeu MUDAR_AGORA_OK nem erro da Ground Station."
                    )
                    return

                if forced_response in error_messages:
                    finish_error(
                        "Erro na troca forçada LoRa",
                        error_messages[forced_response]
                    )
                    return

                if forced_response == "MUDAR_AGORA_OK":
                    finish_success(
                        f"LoRa forçado: CHAN{channel_hex}, 0x{address_hex}",
                        "Configuração LoRa forçada com sucesso na Ground Station.\n\n"
                        f"CHAN: 0x{channel_hex}\n"
                        f"Address: 0x{address_hex}"
                    )
                    return

                finish_error(
                    "Resposta inesperada na troca forçada",
                    f"Resposta inesperada da Ground Station:\n{forced_response}"
                )
                return

            # ========================================================
            # MODO NORMAL - ETAPA 1
            # espera MUDAR_OK ou erro
            # ========================================================
            self._set_status("Aguardando MUDAR_OK da Ground Station...", "#d4a017")

            first_response = wait_for_response(
                expected_tokens={"MUDAR_OK"},
                timeout_s=UI_STAGE_TIMEOUT_S,
                busy=busy,
                stage_text="Aguardando MUDAR_OK da Ground Station..."
            )

            if first_response == "":
                finish_error(
                    "Timeout aguardando MUDAR_OK",
                    "Timeout da UI aguardando MUDAR_OK.\n\n"
                    "A UI esperou 35 s para ficar alinhada com o timeout de 30 s da GS, "
                    "mas não recebeu MUDAR_OK nem mensagem de erro."
                )
                return

            if first_response in error_messages:
                finish_error(
                    "Erro antes da confirmação inicial",
                    error_messages[first_response]
                )
                return

            if first_response != "MUDAR_OK":
                finish_error(
                    "Resposta inicial inesperada",
                    f"Resposta inesperada da Ground Station:\n{first_response}"
                )
                return

            # ========================================================
            # MODO NORMAL - ETAPA 2
            # espera MUDAR_CERTO ou erro
            # ========================================================
            self._set_status("GS aceitou. Aguardando resultado final...", "#d4a017")

            final_response = wait_for_response(
                expected_tokens={"MUDAR_CERTO"},
                timeout_s=UI_STAGE_TIMEOUT_S,
                busy=busy,
                stage_text="GS aceitou. Aguardando MUDAR_CERTO ou erro..."
            )

            if final_response == "":
                finish_error(
                    "Timeout aguardando resultado final",
                    "Timeout da UI aguardando o resultado final.\n\n"
                    "A UI esperou 35 s para ficar alinhada com o timeout de 30 s da GS, "
                    "mas não recebeu MUDAR_CERTO nem mensagem de erro."
                )
                return

            if final_response in error_messages:
                finish_error(
                    "Erro durante troca LoRa",
                    error_messages[final_response]
                )
                return

            if final_response == "MUDAR_CERTO":
                finish_success(
                    f"LoRa alterado: CHAN{channel_hex}, 0x{address_hex}",
                    "Configuração LoRa alterada com sucesso.\n\n"
                    f"CHAN: 0x{channel_hex}\n"
                    f"Address: 0x{address_hex}"
                )
                return

            finish_error(
                "Resposta final inesperada",
                f"Resposta inesperada da Ground Station:\n{final_response}"
            )

        except Exception as e:
            self._set_status("Erro inesperado na troca LoRa", "#b00")
            QMessageBox.warning(
                self,
                "LoRa",
                f"Erro inesperado durante a troca LoRa:\n{e}"
            )

        finally:
            if busy is not None:
                busy.close()

            self.btn_lora_change.setEnabled(True)

            if hasattr(self, "btn_lora_force_change"):
                self.btn_lora_force_change.setEnabled(True)

            if timer_was_active and self.ser and self.ser.is_open and self.connected_ok:
                self.timer_serial.start(50)