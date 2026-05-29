from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QDoubleSpinBox, QCheckBox, QMessageBox, QFileDialog, QFrame,
    QToolButton, QPlainTextEdit
)


class ConfigDialog(QDialog):
    def __init__(self, gs_single, test_password: str = "urd123", parent=None):
        super().__init__(parent)
        self.gs_single = gs_single
        self.test_password = test_password
        self._test_unlocked = False

        # timer só para atualizar UI do status de gravação
        self._rec_ui_timer = QTimer(self)
        self._rec_ui_timer.setInterval(250)
        self._rec_ui_timer.timeout.connect(self._update_recording_status)

        self.setWindowTitle("Configurações")
        self.resize(780, 620)
        self.setMaximumHeight(680)

        self._build_ui()
        self._sync_from_gs()          # runtime-only
        self._sync_recording_ui_state()

    # -----------------------------
    # Helpers base
    # -----------------------------
    def _parse_float_text(self, txt: str, default=None):
        txt = (txt or "").strip().replace(",", ".")
        if not txt:
            return default
        try:
            return float(txt)
        except Exception:
            return default

    def _get_current_base_from_gs(self):
        # FONTE ÚNICA: GSFlightSinglePage.base_latlon
        v = getattr(self.gs_single, "base_latlon", None)
        if not v or not isinstance(v, (tuple, list)) or len(v) != 2:
            return None
        try:
            return (float(v[0]), float(v[1]))
        except Exception:
            return None

    def _refresh_base_in_use_fields(self):
        v = self._get_current_base_from_gs()
        if not v:
            self.base_use_lat.setText("-")
            self.base_use_lon.setText("-")
            return
        lat, lon = v
        self.base_use_lat.setText(f"{lat:.6f}")
        self.base_use_lon.setText(f"{lon:.6f}")

    def _apply_base(self, lat: float, lon: float, silent: bool = False):
        self.gs_single.set_home_location(lat, lon)

        # atualiza o mostrador read-only
        self._refresh_base_in_use_fields()

        # opcional (runtime cfg) - sem persistência
        if hasattr(self.gs_single, "runtime_cfg"):
            try:
                self.gs_single.runtime_cfg.base_lat_text = f"{lat:.6f}"
                self.gs_single.runtime_cfg.base_lon_text = f"{lon:.6f}"
            except Exception:
                pass

        if not silent:
            QMessageBox.information(self, "Base definida", f"Base atualizada: {lat:.6f}, {lon:.6f}")

        self.base_lat.clear()
        self.base_lon.clear()

    # -----------------------------
    # Helpers modo teste
    # -----------------------------
    def _set_test_widgets_enabled(self, enabled: bool):
        self.lat.setEnabled(enabled)
        self.lon.setEnabled(enabled)
        self.alt.setEnabled(enabled)
        for i in range(4):
            self.pq_enabled[i].setEnabled(enabled)
            self.pq_time[i].setEnabled(enabled)
        self.btn_apply.setEnabled(enabled)
        self.btn_reset.setEnabled(enabled)

    # -----------------------------
    # UI
    # -----------------------------
    def _build_ui(self):
        # layout principal: topbar + colunas alinhadas
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)

        # topbar manual (fora da gravação)
        topbar = QHBoxLayout()
        topbar.addStretch(1)
        topbar.addWidget(QLabel("Manual"))
        self.btn_help = QToolButton()
        self.btn_help.setText("?")
        self.btn_help.setToolTip("Abrir manual da UI")
        topbar.addWidget(self.btn_help)
        main.addLayout(topbar)

        # colunas
        root = QHBoxLayout()
        root.setSpacing(10)
        main.addLayout(root)

        left_col = QVBoxLayout()
        right_col = QVBoxLayout()
        left_col.setSpacing(10)
        right_col.setSpacing(10)
        root.addLayout(left_col, 1)
        root.addLayout(right_col, 1)

        # =========================
        # MODO TESTE (esquerda)
        # =========================
        box_test = QGroupBox("Modo Teste")
        lay_test = QGridLayout(box_test)
        lay_test.setHorizontalSpacing(8)
        lay_test.setVerticalSpacing(6)

        self.btn_unlock = QPushButton("Entrar no modo teste…")
        self.lbl_test_status = QLabel("Bloqueado")
        self.lbl_test_status.setStyleSheet("color:#b00; font-weight:600;")

        self.lat = QDoubleSpinBox(); self.lat.setRange(-90, 90); self.lat.setDecimals(6)
        self.lon = QDoubleSpinBox(); self.lon.setRange(-180, 180); self.lon.setDecimals(6)
        self.alt = QDoubleSpinBox(); self.alt.setRange(-1000, 100000); self.alt.setDecimals(2)

        self.pq_enabled = [QCheckBox(f"P{i+1} ativado?") for i in range(4)]
        self.pq_time = [QDoubleSpinBox() for _ in range(4)]
        for sp in self.pq_time:
            sp.setRange(0, 1e6)
            sp.setDecimals(2)

        lay_test.addWidget(self.btn_unlock, 0, 0, 1, 1)
        lay_test.addWidget(self.lbl_test_status, 0, 1, 1, 1)

        lay_test.addWidget(QLabel("Latitude"), 1, 0)
        lay_test.addWidget(self.lat, 1, 1)
        lay_test.addWidget(QLabel("Longitude"), 2, 0)
        lay_test.addWidget(self.lon, 2, 1)
        lay_test.addWidget(QLabel("Altitude (m)"), 3, 0)
        lay_test.addWidget(self.alt, 3, 1)

        for i in range(4):
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(self.pq_enabled[i])
            row.addWidget(QLabel("h (m):"))
            row.addWidget(self.pq_time[i])
            lay_test.addLayout(row, 4 + i, 0, 1, 2)



        self.btn_apply = QPushButton("Aplicar no GS Single")
        self.btn_reset = QPushButton("Reinicializar Página")
        button_style = """
        QPushButton:disabled {
            background-color: #3a3a3a;
            color: #8a8a8a;
            border: 1px solid #555555;
        }
        """
        self.btn_apply.setStyleSheet(button_style)
        self.btn_reset.setStyleSheet(button_style)
        row_btns = QHBoxLayout()
        row_btns.addWidget(self.btn_apply)
        row_btns.addWidget(self.btn_reset)
        lay_test.addLayout(row_btns, 8, 0, 1, 2)

        left_col.addWidget(box_test)
        
        # trava modo teste por padrão
        self._set_test_widgets_enabled(False)

        # =========================
        # GRAVAÇÃO (esquerda, abaixo do teste)
        # =========================
        box_rec = QGroupBox("Gravação da interface (tela inteira)")
        lay_rec = QGridLayout(box_rec)
        lay_rec.setHorizontalSpacing(8)
        lay_rec.setVerticalSpacing(6)

        self.btn_record_ui = QPushButton("Iniciar gravação")
        self.lbl_rec_status = QLabel("Parado")
        self.lbl_rec_status.setAlignment(Qt.AlignCenter)
        self.lbl_rec_status.setStyleSheet(
            "padding:6px; border-radius:8px; background:#eee; color:#444; font-weight:600;"
        )

        lay_rec.addWidget(self.btn_record_ui, 0, 0, 1, 2)
        lay_rec.addWidget(self.lbl_rec_status, 1, 0, 1, 2)

        left_col.addWidget(box_rec)

        # =========================
        # BUZZER SERIAL (esquerda, abaixo da gravação)
        # =========================
        box_buzzer = QGroupBox("Buzzer Serial")
        lay_buzzer = QVBoxLayout(box_buzzer)
        lay_buzzer.setSpacing(6)

        self.chk_serial_beep = QCheckBox("Beep ao receber linha serial")
        self.chk_serial_beep.setChecked(
            bool(getattr(self.gs_single, "serial_beep_enabled", False))
        )

        lay_buzzer.addWidget(self.chk_serial_beep)

        left_col.addWidget(box_buzzer)
        left_col.addStretch(1)


        
        # =========================
        # GRÁFICO (direita)
        # =========================
        box_graph = QGroupBox("Gráfico")
        lay_graph = QGridLayout(box_graph)
        lay_graph.setHorizontalSpacing(8)
        lay_graph.setVerticalSpacing(6)

        lay_graph.addWidget(
            QLabel("<b>Altitude</b><br><span style='color:#666;'>"
                   "Limpa somente os dados do gráfico de altitude</span>"),
            0, 0, 1, 1
        )

        self.btn_reset_alt_graph = QPushButton("Reinicializar gráfico de altitude")
        lay_graph.addWidget(self.btn_reset_alt_graph, 1, 0, 1, 1)

        left_col.addWidget(box_graph)
        left_col.addStretch(1)

        # =========================
        # MAPA (direita)
        # =========================
        box_map = QGroupBox("Mapa")
        lay_map = QGridLayout(box_map)
        lay_map.setHorizontalSpacing(8)
        lay_map.setVerticalSpacing(6)
        r = 0

        # ---- Base em uso (read-only, estética) ----
        lay_map.addWidget(
            QLabel("<b>Base em uso (GS)</b><br><span style='color:#666;'>"
                   "Referência atual usada para distância e centralização</span>"),
            r, 0, 1, 2
        )
        r += 1

        # headers em cima
        lay_map.addWidget(QLabel("Latitude"), r, 0, alignment=Qt.AlignCenter)
        lay_map.addWidget(QLabel("Longitude"), r, 1, alignment=Qt.AlignCenter)
        r += 1

        # Base em uso (read-only)
        self.base_use_lat = QLineEdit("-")
        self.base_use_lon = QLineEdit("-")
        for w in (self.base_use_lat, self.base_use_lon):
            w.setReadOnly(True)
            w.setAlignment(Qt.AlignCenter)
            w.setStyleSheet(
                "QLineEdit{"
                "  font-family: Consolas, monospace;"
                "  font-size: 12px;"
                "  padding: 6px;"
                "  border-radius: 8px;"
                "  border: 1px solid #cfcfcf;"
                "  background: #ffffff;"
                "  color: #111111;"
                "}"
                "QLineEdit:disabled{ background:#f2f2f2; color:#444; }"
            )

        lay_map.addWidget(self.base_use_lat, r, 0)
        lay_map.addWidget(self.base_use_lon, r, 1)
        r += 1

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.HLine)
        sep0.setFrameShadow(QFrame.Sunken)
        lay_map.addWidget(sep0, r, 0, 1, 2)
        r += 1

        # ---- Definir nova base ----
        lay_map.addWidget(
            QLabel("<b>Definir nova Base</b><br><span style='color:#666;'>"
                   "Digite ou pegue Online / centro do mapa</span>"),
            r, 0, 1, 2
        )
        r += 1

        self.base_lat = QLineEdit()
        self.base_lon = QLineEdit()
        self.base_lat.setPlaceholderText("ex.: -23.550520")
        self.base_lon.setPlaceholderText("ex.: -46.633308")

        lat_validator = QDoubleValidator(-90.0, 90.0, 6)
        lat_validator.setNotation(QDoubleValidator.StandardNotation)
        self.base_lat.setValidator(lat_validator)

        lon_validator = QDoubleValidator(-180.0, 180.0, 6)
        lon_validator.setNotation(QDoubleValidator.StandardNotation)
        self.base_lon.setValidator(lon_validator)

        lay_map.addWidget(QLabel("Latitude (entrada)"), r, 0)
        lay_map.addWidget(self.base_lat, r, 1)
        r += 1
        lay_map.addWidget(QLabel("Longitude (entrada)"), r, 0)
        lay_map.addWidget(self.base_lon, r, 1)
        r += 1

        self.btn_set_base = QPushButton("Definir Base (usar campos acima)")
        self.btn_use_my_loc = QPushButton("Usar minha localização (Online)")
        self.btn_get_center = QPushButton("Pegar coordenadas do centro do mapa atual")

        lay_map.addWidget(self.btn_set_base, r, 0, 1, 2); r += 1
        lay_map.addWidget(self.btn_use_my_loc, r, 0, 1, 2); r += 1
        lay_map.addWidget(self.btn_get_center, r, 0, 1, 2); r += 1

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setFrameShadow(QFrame.Sunken)
        lay_map.addWidget(sep1, r, 0, 1, 2)
        r += 1

        # ---- Centralizar mapa na base ----
        lay_map.addWidget(
            QLabel("<b>Centro do mapa</b><br><span style='color:#666;'>"
                   "Centraliza o mapa na Base em uso (GS)</span>"),
            r, 0, 1, 2
        )
        r += 1

        self.btn_center_map = QPushButton("Centralizar mapa na Base em uso")
        lay_map.addWidget(self.btn_center_map, r, 0, 1, 2)
        r += 1

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFrameShadow(QFrame.Sunken)
        lay_map.addWidget(sep2, r, 0, 1, 2)
        r += 1

        # ---- Reinicializar mapa ----
        lay_map.addWidget(QLabel("<b>Reinicilização do mapa</b>"), r, 0, 1, 2)
        r += 1

        self.btn_reinit_map = QPushButton("Reinicializar mapa")
        lay_map.addWidget(self.btn_reinit_map, r, 0, 1, 2)
        r += 1

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setFrameShadow(QFrame.Sunken)
        lay_map.addWidget(sep3, r, 0, 1, 2)
        r += 1

        # ---- Tiles offline agora dentro do Mapa ----
        lay_map.addWidget(
            QLabel("<b>Upload de mapas</b><br><span style='color:#666;'>"
                   "Seleciona a pasta dos tiles locais para o mapa offline</span>"),
            r, 0, 1, 2
        )
        r += 1

        self.lbl_tiles = QLabel("Nenhuma pasta selecionada")
        self.lbl_tiles.setAlignment(Qt.AlignCenter)

        self.btn_pick_tiles = QPushButton("Selecionar pasta de tiles…")
        try:
            self.btn_pick_tiles.setEnabled(not self.gs_single.net.get_status())
        except Exception:
            self.btn_pick_tiles.setEnabled(True)

        lay_map.addWidget(self.lbl_tiles, r, 0, 1, 2)
        r += 1
        lay_map.addWidget(self.btn_pick_tiles, r, 0, 1, 2)
        r += 1

        right_col.addWidget(box_map)


        # =========================
        # sinais
        # =========================
        self.btn_help.clicked.connect(self._show_manual)

        self.btn_unlock.clicked.connect(self._unlock_test)
        self.btn_apply.clicked.connect(self._apply_to_gs)
        self.btn_reset.clicked.connect(self._reset_stats)

        self.btn_set_base.clicked.connect(self._set_base_from_fields)
        self.btn_use_my_loc.clicked.connect(self._use_my_location_online_to_base)
        self.btn_get_center.clicked.connect(self._get_map_center_to_base)

        self.btn_center_map.clicked.connect(self._center_map_on_base)
        self.btn_reinit_map.clicked.connect(self._reinit_map_visual)

        self.btn_pick_tiles.clicked.connect(self._pick_tiles)
        self.btn_reset_alt_graph.clicked.connect(self._reset_altitude_graph)

        self.btn_record_ui.clicked.connect(self._toggle_ui_recording)
        self.chk_serial_beep.toggled.connect(self._toggle_serial_beep)

    def _toggle_serial_beep(self, checked: bool):
        if hasattr(self.gs_single, "set_serial_beep_enabled"):
            self.gs_single.set_serial_beep_enabled(checked)

    # -----------------------------
    # Sync runtime
    # -----------------------------
    def _sync_from_gs(self):
        # base em uso
        self._refresh_base_in_use_fields()

        self.base_lat.clear()
        self.base_lon.clear()

        # tiles
        try:
            folder = (self.gs_single.runtime_cfg.tiles_folder or "").strip()
            self.lbl_tiles.setText(folder if folder else "Nenhuma pasta selecionada")
        except Exception:
            self.lbl_tiles.setText("Nenhuma pasta selecionada")

        # modo teste: tenta puxar posição/altitude atuais
        if getattr(self.gs_single, "last_latlon", None):
            try:
                lat, lon = self.gs_single.last_latlon
                self.lat.setValue(float(lat))
                self.lon.setValue(float(lon))
            except Exception:
                pass

        if getattr(self.gs_single, "alt_max", None) not in (None, float("-inf")):
            try:
                self.alt.setValue(float(self.gs_single.alt_max))
            except Exception:
                pass

        # paraquedas: espelha estado atual (lê stylesheet)
        pq_refs = [
            getattr(self.gs_single, "pqd_drogueN", None),
            getattr(self.gs_single, "pqd_drogueB", None),
            getattr(self.gs_single, "pqd_mainN", None),
            getattr(self.gs_single, "pqd_mainB", None),
        ]
        for i, box in enumerate(pq_refs):
            if box is None:
                continue
            try:
                active = "background: #b6f5b6" in box.styleSheet()
                self.pq_enabled[i].setChecked(active)
            except Exception:
                pass

    # -----------------------------
    # Manual
    # -----------------------------
    def _show_manual(self):
        manual = (
            "MANUAL — URD Ground Station\n"
            "============================================================\n\n"

            "1) VISÃO GERAL\n"
            "------------------------------------------------------------\n"
            "A URD Ground Station recebe telemetria pela porta serial, mostra os dados no terminal,\n"
            "atualiza mapa, gráfico de altitude, orientação 3D, status de GPS, SD Card e eventos\n"
            "de paraquedas.\n\n"
            "Fluxo geral:\n"
            "  APP  <->  Ground Station  <->  Flight Computer\n\n"
            "O APP conversa com a Ground Station pela Serial USB.\n"
            "A Ground Station conversa com o Flight Computer pelo LoRa.\n\n"

            "2) CONEXÃO SERIAL\n"
            "------------------------------------------------------------\n"
            "Passo a passo:\n"
            "  1. Selecione a porta serial correta.\n"
            "  2. Clique em Conectar.\n"
            "  3. O app abre a serial em 115200 baud.\n"
            "  4. O app envia RST.\n"
            "  5. O app envia READY.\n"
            "  6. A Ground Station deve responder OK.\n"
            "  7. O app envia GPS_COORDS.\n"
            "  8. A Ground Station responde latitude/longitude ou ~\\t~.\n\n"
            "Durante a conexão, o app mostra um popup de carregamento para indicar que está\n"
            "aguardando resposta da placa.\n\n"
            "Comandos/respostas da conexão:\n\n"
            "  RST              -> APP pede reset/preparação da GS.\n"
            "  READY            -> APP inicia o handshake.\n"
            "  OK               -> GS confirma o handshake.\n"
            "  GPS_COORDS       -> APP pede coordenadas da base.\n"
            "  GPS_OK           -> GS confirma que recebeu o pedido de GPS.\n"
            "  lat\\tlon         -> GS envia coordenadas válidas.\n"
            "  ~\\t~             -> GS informa que não há coordenadas válidas.\n\n"

            "3) RECEPÇÃO DE TELEMETRIA\n"
            "------------------------------------------------------------\n"
            "Depois da conexão, o app passa a ler continuamente a serial.\n"
            "Cada pacote deve terminar com \\n.\n\n"
            "Formato compacto esperado:\n\n"
            "  L1 T0.25 A-23.123456 O-46.123456 h12 n34 g1.2 H100.5 s1 a300.0 t12.5 D0 d0 N0 B0 c25.4 R0.1 P1.2 Y3.4\n\n"
            "Tabela de campos:\n\n"
            "  Chave   Campo no app              Significado\n"
            "  -----   ------------------------  ----------------------------------\n"
            "  L       linha                     Contador da linha/pacote\n"
            "  T       tempo                     Tempo do pacote ou tempo de voo (s)\n"
            "  A       latitude                  Latitude do GPS\n"
            "  O       longitude                 Longitude do GPS\n"
            "  h       hora                      Hora do GPS\n"
            "  n       minuto                    Minuto do GPS\n"
            "  g       precisao                  Precisão/HDOP do GPS\n"
            "  H       altitude                  Altitude atual (m)\n"
            "  s       sd                        Status do SD Card, 1 = ok, 0 = erro\n"
            "  a       apogeu_h                  Altura de apogeu (m)\n"
            "  t       apogeu_t                  Tempo do apogeu (s)\n"
            "  D       pqd_dn                    Altura do evento Drogue Normal\n"
            "  d       pqd_db                    Altura do evento Drogue Backup\n"
            "  N       pqd_mn                    Altura do evento Main Normal\n"
            "  B       pqd_mb                    Altura do evento Main Backup\n"
            "  c       temp                      Temperatura (°C)\n"
            "  R       roll                      Roll em graus\n"
            "  P       pitch                     Pitch em graus\n"
            "  Y       yaw                       Yaw em graus\n\n"
            "Se algum campo vier inválido, ausente ou fora da faixa, o app marca o pacote como\n"
            "parcialmente inválido. O Status Serial muda para RX ERR e o contador mostra quantos\n"
            "campos válidos chegaram, por exemplo 16/19.\n\n"

            "4) TERMINAL E STATUS SERIAL\n"
            "------------------------------------------------------------\n"
            "Terminal de Dados:\n"
            "  Mostra as linhas recebidas da Ground Station.\n\n"
            "Auto-scroll:\n"
            "  Mantém o terminal sempre no fim da lista.\n\n"
            "Status Serial:\n"
            "  IDLE   -> sem dados recentes.\n"
            "  RX OK  -> pacote recebido e interpretado corretamente.\n"
            "  RX ERR -> pacote incompleto, inválido ou com campos fora da faixa.\n\n"
            "Hz:\n"
            "  Frequência aproximada de recebimento de pacotes.\n\n"

            "5) MAPA\n"
            "------------------------------------------------------------\n"
            "Base em uso:\n"
            "  Mostra a latitude e longitude usadas como referência de distância.\n\n"
            "Definir nova Base:\n"
            "  Permite inserir latitude/longitude manualmente.\n\n"
            "Usar minha localização Online:\n"
            "  Usa localização aproximada por internet.\n\n"
            "Pegar coordenadas do centro do mapa atual:\n"
            "  Usa o centro visual atual do mapa como nova base.\n\n"
            "Centralizar mapa na Base em uso:\n"
            "  Move o mapa para a base atual.\n\n"
            "Reinicializar mapa:\n"
            "  Reinicia apenas a visualização do mapa.\n\n"
            "Upload de mapas:\n"
            "  Seleciona uma pasta de tiles locais para uso offline.\n\n"

            "6) GRÁFICO\n"
            "------------------------------------------------------------\n"
            "Reinicializar gráfico de altitude:\n"
            "  Limpa somente os dados visíveis do gráfico de altitude.\n"
            "  Não desconecta a serial e não apaga a base.\n\n"

            "7) MODO TESTE\n"
            "------------------------------------------------------------\n"
            "O Modo Teste permite alterar manualmente valores da interface sem depender da\n"
            "telemetria real.\n\n"
            "Ele começa bloqueado. Para liberar, clique em Entrar no modo teste e digite a senha.\n\n"
            "Campos disponíveis:\n"
            "  Latitude / Longitude -> posição simulada no mapa.\n"
            "  Altitude             -> altitude manual.\n"
            "  P1/P2/P3/P4          -> simulação de eventos de paraquedas.\n\n"
            "Aplicar no GS Single:\n"
            "  Injeta os valores na interface principal.\n\n"
            "Reinicializar Página:\n"
            "  Limpa/recria o estado visual da página, quando disponível.\n\n"

            "8) GRAVAÇÃO DA INTERFACE\n"
            "------------------------------------------------------------\n"
            "A seção Gravação da interface salva frames PNG da tela inteira.\n"
            "Ela não gera vídeo diretamente.\n\n"
            "Fluxo:\n"
            "  1. Clique em Iniciar gravação.\n"
            "  2. Escolha uma pasta.\n"
            "  3. O app cria uma subpasta com timestamp.\n"
            "  4. Os frames são salvos como PNG.\n"
            "  5. Clique em Parar gravação para finalizar.\n\n"

            "9) BUZZER SERIAL\n"
            "------------------------------------------------------------\n"
            "Quando ativado, gera um beep a cada linha serial válida recebida.\n"
            "No Raspberry, tenta usar GPIO.\n"
            "No Windows, tenta usar winsound.\n\n"

            "10) ENVIO DE FREQUÊNCIA LORA\n"
            "------------------------------------------------------------\n"
            "O botão Enviar LoRa altera a frequência e o Address do módulo LoRa da Ground Station\n"
            "e do Flight Computer.\n\n"
            "Campos usados:\n"
            "  Frequência -> selecionada no ComboBox, de FREQ862 até FREQ931.\n"
            "  Address    -> número inteiro decimal entre 0 e 65535.\n\n"
            "Proteções do app:\n"
            "  - Não envia se não houver frequência.\n"
            "  - Não envia se o Address estiver vazio.\n"
            "  - Não envia se o Address não for inteiro.\n"
            "  - Não envia se o Address estiver fora de 0-65535.\n"
            "  - Não envia se a placa não estiver conectada.\n\n"
            "Sequência esperada:\n\n"
            "  APP -> GS: MUDAR_FREQUENCIA\n"
            "  APP -> GS: VALS:FREQXXX\\tADDRESS\n\n"
            "Resposta inicial:\n"
            "  GS -> APP: MUDAR_OK\n"
            "      A GS aceitou os valores e iniciou o processo.\n\n"
            "  GS -> APP: MUDAR_FREQUENCIA_ERROR\n"
            "      A GS recusou os valores ou nem iniciou o processo.\n\n"
            "Resultado final:\n"
            "  GS -> APP: MUDAR_CERTO\n"
            "      Troca confirmada.\n\n"
            "  GS -> APP: MUDAR_ERRO_GS\n"
            "      Falha ao mudar a configuração da própria Ground Station.\n\n"
            "  GS -> APP: MUDAR_ERRO\n"
            "      Falha no Flight Computer ou timeout. A GS deve tentar voltar para o default.\n\n"
            "Default esperado em caso de erro:\n"
            "  FREQ903\\t43\n\n"
            "Durante a troca, o app para temporariamente a leitura normal da serial, abre o popup\n"
            "de carregamento, envia os comandos, espera as respostas e depois reativa a leitura.\n\n"

            "11) OBSERVAÇÕES\n"
            "------------------------------------------------------------\n"
            " - O TAB entre FREQXXX e ADDRESS deve ser um TAB real quando enviado pelo app.\n"
            " - No Python, use: f'VALS:{frequency}\\t{address}'.\n"
            " - No Serial Monitor, digitar \\t pode mandar barra+t, não TAB real.\n"
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Manual da UI")
        dlg.resize(850, 650)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(manual)
        txt.setLineWrapMode(QPlainTextEdit.NoWrap)
        txt.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        txt.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        lay.addWidget(txt)

        btn = QPushButton("Fechar")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn, alignment=Qt.AlignRight)

        dlg.exec()

    # -----------------------------
    # Modo Teste
    # -----------------------------
    def _unlock_test(self):
        from PySide6.QtWidgets import QInputDialog
        pwd, ok = QInputDialog.getText(
            self, "Senha do modo teste", "Digite a senha:", echo=QLineEdit.Password
        )
        if not ok:
            return

        if pwd == self.test_password:
            self._test_unlocked = True
            self.lbl_test_status.setText("Desbloqueado")
            self.lbl_test_status.setStyleSheet("color:#0a0; font-weight:600;")
            self._set_test_widgets_enabled(True)
        else:
            QMessageBox.warning(self, "Senha incorreta", "Senha inválida.")

    def _apply_to_gs(self):
        if not self._test_unlocked:
            return

        self.gs_single.set_position(self.lat.value(), self.lon.value())
        self.gs_single.inject_altitude(self.alt.value())
        self.gs_single.alt_max = self.alt.value()
        try:
            self.gs_single.lbl_alt_max.setText(f"{self.alt.value():.2f}")
        except Exception:
            pass

        self.gs_single._set_pq(0, self.pq_time[0].value() if self.pq_enabled[0].isChecked() else 0.0)
        self.gs_single._set_pq(1, self.pq_time[1].value() if self.pq_enabled[1].isChecked() else 0.0)
        self.gs_single._set_pq(2, self.pq_time[2].value() if self.pq_enabled[2].isChecked() else 0.0)
        self.gs_single._set_pq(3, self.pq_time[3].value() if self.pq_enabled[3].isChecked() else 0.0)

    def _reset_stats(self):
        if not self._test_unlocked:
            return

        for m in ("recreate_page", "rebuild_page", "_recreate_page", "_rebuild_page", "reset_page", "_reset_page"):
            if hasattr(self.gs_single, m):
                try:
                    getattr(self.gs_single, m)()
                    QMessageBox.information(self, "Reset", "Página reinicializada.")
                    return
                except Exception:
                    pass

        try:
            self.gs_single._reset_state()
        except Exception:
            pass

        try:
            self.gs_single.terminal.clear()
        except Exception:
            pass

        try:
            self.gs_single.alt_curve.setData([], [])
        except Exception:
            pass

        for attr in (
            "lbl_alt_max", "lbl_alt_apogeu", "lbl_vel", "lbl_lat", "lbl_lon",
            "lbl_dist", "lbl_temp", "lbl_horario"
        ):
            try:
                getattr(self.gs_single, attr).setText("—")
            except Exception:
                pass

        try:
            self.gs_single.last_latlon = (0, 0)
        except Exception:
            pass

        try:
            self.gs_single.lbl_precisao.setStyleSheet(
                "background: red; border: 1px solid #ccc; border-radius: 1px;"
            )
        except Exception:
            pass

        try:
            self.gs_single.sd_box.setStyleSheet(
                "background: red; border: 1px solid #ccc; border-radius: 6px;"
            )
        except Exception:
            pass

        self.lat.setValue(0)
        self.lon.setValue(0)
        self.alt.setValue(0)
        for i in range(4):
            self.pq_enabled[i].setChecked(False)
            self.pq_time[i].setValue(0)

        QMessageBox.information(self, "Reset", "Página reinicializada.")

    # -----------------------------
    # Base: botões
    # -----------------------------
    def _set_base_from_fields(self):
        lat = self._parse_float_text(self.base_lat.text(), None)
        lon = self._parse_float_text(self.base_lon.text(), None)
        if lat is None or lon is None:
            QMessageBox.warning(self, "Inválido", "Preencha Latitude/Longitude (entrada) antes de definir.")
            return
        self._apply_base(float(lat), float(lon))

    def _use_my_location_online_to_base(self):
        try:
            import geocoder, requests
            g = geocoder.ip("me")
            if g.ok and g.latlng:
                lat, lon = g.latlng
            else:
                resp = requests.get("https://ipinfo.io/json", timeout=5).json()
                lat, lon = map(float, resp["loc"].split(","))

            self._apply_base(float(lat), float(lon), silent=True)
            QMessageBox.information(self, "Online → Base", f"Base definida via Online: {lat:.6f}, {lon:.6f}")

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível obter localização online: {e}")

    def _get_map_center_to_base(self):
        m = getattr(self.gs_single, "map", None)
        if not m:
            QMessageBox.warning(self, "Indisponível", "Mapa não encontrado no GS.")
            return

        try:
            m.get_view(self._on_map_center_for_base)
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Falha chamando get_view: {e}")

    def _on_map_center_for_base(self, v):
        # v agora é string "lat, lon|zoom" (ou "" se falhar)
        if not v or not isinstance(v, str) or not v.strip():
            QMessageBox.warning(self, "Erro", "Não foi possível obter coordenadas do centro do mapa.")
            return

        try:
            coords, *_ = v.split("|", 1)
            lat_s, lon_s = [p.strip() for p in coords.split(",", 1)]
            lat = float(lat_s.replace(",", "."))
            lon = float(lon_s.replace(",", "."))
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível interpretar o centro do mapa: {e}\nValor recebido: {v!r}")
            return

        self._apply_base(lat, lon, silent=True)

    # -----------------------------
    # Centralizar mapa na base
    # -----------------------------
    def _unlock_map_if_needed(self):
        m = getattr(self.gs_single, "map", None)
        if not m:
            return

        for fn in ("unlock", "set_unlocked", "set_locked", "set_lock", "set_interaction_enabled", "set_pan_enabled"):
            if hasattr(m, fn):
                try:
                    if fn in ("set_locked", "set_lock"):
                        getattr(m, fn)(False)
                    elif fn == "set_unlocked":
                        getattr(m, fn)(True)
                    elif fn in ("set_interaction_enabled", "set_pan_enabled"):
                        getattr(m, fn)(True)
                    else:
                        getattr(m, fn)()
                    break
                except Exception:
                    pass

        for attr in ("btn_lock_map", "btn_map_lock", "btn_lock"):
            if hasattr(self.gs_single, attr):
                try:
                    btn = getattr(self.gs_single, attr)
                    if hasattr(btn, "setChecked"):
                        btn.setChecked(False)
                except Exception:
                    pass

    def _center_map_on_base(self):
        self._unlock_map_if_needed()

        v = self._get_current_base_from_gs()
        if not v:
            QMessageBox.warning(self, "Sem base", "Nenhuma base definida no GS. Defina a base primeiro.")
            return
        lat, lon = v

        if not hasattr(self.gs_single, "map") or not hasattr(self.gs_single.map, "set_view"):
            QMessageBox.warning(self, "Indisponível", "Seu MapWidget ainda não tem set_view(lat, lon, zoom).")
            return

        if hasattr(self.gs_single.map, "get_view"):
            self.gs_single.map.get_view(lambda vv: self._apply_view_with_zoom(vv, lat, lon))
        else:
            self.gs_single.map.set_view(float(lat), float(lon), 12)

    def _apply_view_with_zoom(self, v, lat, lon):
        zoom = 12
        try:
            if isinstance(v, dict):
                zoom = int(v.get("zoom", 12))
            elif isinstance(v, str) and "|" in v:
                _, zoom_part = v.split("|", 1)
                zoom = int(float(zoom_part.strip()))
        except Exception:
            zoom = 12

        self.gs_single.map.set_view(float(lat), float(lon), zoom)

    # -----------------------------
    # Reinicializar mapa (visual)
    # -----------------------------
    def _reinit_map_visual(self):
        ok = QMessageBox.question(
            self,
            "Reinicializar mapa",
            "Isso reinicializa apenas o MAPA VISUAL (HTML/tiles/overlays).\n"
            "Não altera Base nem tiles offline.\n\nContinuar?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        if hasattr(self.gs_single, "map") and hasattr(self.gs_single.map, "_init_map"):
            try:
                self.gs_single.map._init_map()
            except Exception as e:
                QMessageBox.warning(self, "Erro", f"Falha ao reinicializar mapa: {e}")
                return

        v = self._get_current_base_from_gs()
        if v and hasattr(self.gs_single, "map") and hasattr(self.gs_single.map, "set_base"):
            try:
                self.gs_single.map.set_base(float(v[0]), float(v[1]))
            except Exception:
                pass

        QMessageBox.information(self, "OK", "Mapa reinicializado (somente gráfico).")

    # -----------------------------
    # Reinicializar gráfico de altitude
    # -----------------------------
    def _reset_altitude_graph(self):
        ok = QMessageBox.question(
            self,
            "Reinicializar gráfico",
            "Isso limpa apenas o gráfico de altitude.\n\nContinuar?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        # limpa curva visível
        try:
            self.gs_single.alt_curve.setData([], [])
        except Exception:
            pass

        # limpa buffers comuns, caso existam
        for attr in (
            "alt_x", "alt_y", "plot_time", "plot_alt",
            "_plot_x", "_plot_y", "alt_data_x", "alt_data_y"
        ):
            try:
                obj = getattr(self.gs_single, attr)
                if hasattr(obj, "clear"):
                    obj.clear()
                elif isinstance(obj, list):
                    obj[:] = []
            except Exception:
                pass

        QMessageBox.information(self, "OK", "Gráfico de altitude reinicializado.")

    # -----------------------------
    # Tiles offline (runtime-only)
    # -----------------------------
    def _pick_tiles(self):
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta de tiles")
        if folder:
            self.lbl_tiles.setText(folder)
            try:
                self.gs_single.runtime_cfg.tiles_folder = folder
            except Exception:
                pass
            try:
                self.gs_single.apply_map_mode()
            except Exception:
                pass

    # -----------------------------
    # Gravação (controla GSFlightSinglePage)
    # -----------------------------
    def _fmt_elapsed(self, secs: float) -> str:
        s = int(max(0.0, secs))
        h = s // 3600
        m = (s % 3600) // 60
        ss = s % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{ss:02d}"
        return f"{m:02d}:{ss:02d}"

    def _sync_recording_ui_state(self):
        rec = bool(getattr(self.gs_single, "is_ui_recording", lambda: False)())
        if rec:
            self.btn_record_ui.setText("Parar gravação")
            self._rec_ui_timer.start()
            self._update_recording_status()
        else:
            self.btn_record_ui.setText("Iniciar gravação")
            self._rec_ui_timer.stop()
            self.lbl_rec_status.setText("Parado")
            self.lbl_rec_status.setStyleSheet(
                "padding:6px; border-radius:8px; background:#eee; color:#444; font-weight:600;"
            )

    def _update_recording_status(self):
        if not hasattr(self.gs_single, "is_ui_recording") or not self.gs_single.is_ui_recording():
            return
        secs = 0.0
        try:
            secs = float(self.gs_single.ui_recording_elapsed_s())
        except Exception:
            secs = 0.0

        self.lbl_rec_status.setText(f"Gravando • {self._fmt_elapsed(secs)}")
        self.lbl_rec_status.setStyleSheet(
            "padding:6px; border-radius:8px; background:#d9fbe3; color:#0a6; font-weight:700;"
        )

    def _toggle_ui_recording(self):
        if not hasattr(self.gs_single, "is_ui_recording") or not hasattr(self.gs_single, "start_ui_recording"):
            QMessageBox.warning(self, "Indisponível", "GSFlightSinglePage não tem suporte a gravação (start_ui_recording).")
            return

        if not self.gs_single.is_ui_recording():
            base_dir = QFileDialog.getExistingDirectory(self, "Escolher pasta para salvar a gravação (frames PNG)")
            if not base_dir:
                return

            stamp = time.strftime("%Y%m%d_%H%M%S")
            out_dir = os.path.join(base_dir, f"urd_ui_recording_{stamp}")

            ok = self.gs_single.start_ui_recording(out_dir, fps=10, full_desktop=True)
            if not ok:
                QMessageBox.warning(self, "Erro", "Não foi possível iniciar a gravação.")
                return
        else:
            try:
                self.gs_single.stop_ui_recording()
            except Exception:
                pass

        self._sync_recording_ui_state()

    def closeEvent(self, event):
        # NÃO para gravação aqui. Só para o timer de UI do dialog.
        try:
            self._rec_ui_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)