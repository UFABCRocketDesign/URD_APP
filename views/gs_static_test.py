from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter, QLabel,
    QPushButton, QPlainTextEdit, QGroupBox, QComboBox,
    QMessageBox, QFileDialog, QInputDialog
)
from PySide6.QtCore import Qt, QTimer
import pyqtgraph as pg
import serial, time
import serial.tools.list_ports

from views.logger import Logger


class GSTestEstaticoPage(QWidget):
    def __init__(self, net, parent=None):
        super().__init__(parent)
        self.net = net

        # estado serial
        self.ser = None
        self.timer_serial = QTimer(self)
        self.timer_serial.timeout.connect(self._read_serial)
        self.connected_ok = False

         # ignição
        self.ignition_state = 0          # 0 = neutro, 1 = armado, 2 = ignição
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self.toggle_blink)
        self.is_blink_on = False

        # dados
        self.data_tempo = []
        self.data_empuxo = []
        self.data_pressao = []
        self.max_thrust_val = 0.0
        self.max_pressure_val = 0.0


        self._build_ui()

        # logger
        self.logger = None
        QTimer.singleShot(100, self.ask_logger)

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QVBoxLayout(self)

        # Splitter geral (vertical): gráfico em cima, resto em baixo
        main_splitter = QSplitter(Qt.Vertical)
        root.addWidget(main_splitter)

        # --- gráfico ---
        self.plot = pg.PlotWidget(title="Teste Estático")
        self.plot.setLabel("bottom", "Tempo", "s")
        self.plot.setLabel("left", "Empuxo (kgf)")
        self.plot.setLabel("right", "Pressão (psi)")
        self.plot.showGrid(x=True, y=True)
        pg.setConfigOptions(antialias=True)

        # eixo secundário para pressão
        self.pressure_axis = pg.ViewBox()
        self.plot.showAxis("right")
        self.plot.scene().addItem(self.pressure_axis)
        self.plot.getAxis("right").linkToView(self.pressure_axis)
        self.pressure_axis.setXLink(self.plot)

        # curvas
        self.curva_empuxo = self.plot.plot(
            pen=pg.mkPen('purple', width=2), name="Empuxo (kgf)"
        )
        self.curva_pressao = pg.PlotCurveItem(
            pen=pg.mkPen('green', width=2), name="Pressão (psi)"
        )
        self.pressure_axis.addItem(self.curva_pressao)

        # legenda manual
        self.legend = pg.LegendItem(offset=(50, 30))
        self.legend.setParentItem(self.plot.graphicsItem())
        self.legend.addItem(self.curva_empuxo, "<span style='color:purple;'>Empuxo (kgf)</span>")
        self.legend.addItem(self.curva_pressao, "<span style='color:green;'>Pressão (psi)</span>")

        # sincroniza os eixos
        self.plot.getViewBox().sigResized.connect(self.update_views)

        main_splitter.addWidget(self.plot)



        # --- parte inferior: splitter horizontal ---
        bottom_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(bottom_splitter)


  

        # terminal (esquerda)
        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setStyleSheet(
            "background: #0f0f0f; color: #dcdcdc; font-family: Consolas, monospace;"
        )
        bottom_splitter.addWidget(self.terminal)

        # direita = splitter vertical
        right_split = QSplitter(Qt.Vertical)
        bottom_splitter.addWidget(right_split)

        # topo direito = botões serial
        top_right = QWidget()
        top_lay = QHBoxLayout(top_right)

        self.combo_ports = QComboBox()
        self.combo_ports.setEditable(True)

        self.btn_connect = QPushButton("Conectar")
        self.btn_disconnect = QPushButton("Desconectar")
        self.btn_clear = QPushButton("Limpar")
        self.btn_cfg = QPushButton("Configurações")

        for b in [self.btn_connect, self.btn_disconnect, self.btn_clear, self.btn_cfg]:
            b.setMinimumHeight(28)

        top_lay.addWidget(QLabel("Porta:"))
        top_lay.addWidget(self.combo_ports)
        top_lay.addWidget(self.btn_connect)
        top_lay.addWidget(self.btn_disconnect)
        top_lay.addWidget(self.btn_clear)
        top_lay.addWidget(self.btn_cfg)

        self.lbl_status = QLabel("Desconectado")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        top_lay.addWidget(self.lbl_status)

        right_split.addWidget(top_right)

        # parte de baixo direito = dados importantes
        data_box = QGroupBox("Dados Importantes")
        grid = QGridLayout(data_box)

        # continuidade
        self.cont_led = QLabel("●")
        self.cont_led.setStyleSheet("color: red; font-size: 32px;")
        grid.addWidget(QLabel("Continuidade:"), 0, 0)
        grid.addWidget(self.cont_led, 0, 1)

        # máximos
        self.max_thrust = QLabel("0.0 kgf")
        self.max_pressure = QLabel("0.0 psi")
        grid.addWidget(QLabel("Máx. Empuxo:"), 1, 0)
        grid.addWidget(self.max_thrust, 1, 1)
        grid.addWidget(QLabel("Máx. Pressão:"), 2, 0)
        grid.addWidget(self.max_pressure, 2, 1)

        # botão ignição
        self.ignition_btn = QPushButton("Desarmado")
        self.ignition_btn.setStyleSheet("background-color: yellow; color: black")
        self.ignition_btn.clicked.connect(self.handle_ignition_click)
        grid.addWidget(self.ignition_btn, 3, 0, 1, 2)

        # botão ping
        self.btn_ping = QPushButton("Ping")
        self.btn_ping.setStyleSheet("background-color: red; color: black")
        self.btn_ping.clicked.connect(self.send_ping)
        grid.addWidget(self.btn_ping, 4, 0, 1, 2)


        right_split.addWidget(data_box)

        main_splitter.setSizes([600, 400])        # gráfico maior
        bottom_splitter.setSizes([700, 300])      # terminal > painel direito

        # comportamento ao redimensionar
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)

        bottom_splitter.setStretchFactor(0, 2)
        bottom_splitter.setStretchFactor(1, 1)
        # conecta sinais serial
        self.btn_connect.clicked.connect(self.connect_serial)
        self.btn_disconnect.clicked.connect(self.disconnect_serial)
        self.btn_clear.clicked.connect(self._clear_terminal)
        self.combo_ports.mousePressEvent = lambda ev: (
            self.refresh_ports(), QComboBox.mousePressEvent(self.combo_ports, ev)
        )

    def update_views(self):
    # Mantém o eixo da pressão alinhado com o eixo principal
        self.pressure_axis.setGeometry(self.plot.getViewBox().sceneBoundingRect())
        self.pressure_axis.linkedViewChanged(self.plot.getViewBox(), self.pressure_axis.XAxis)

    def send_ping(self):
        if self.ser and self.ser.is_open and self.connected_ok:
            self.btn_ping.setStyleSheet("background-color: red; color: black")
            self.cont_led.setStyleSheet("color: red; font-size: 32px;")
            try:
                self.ser.write(b"PING!\n")
                self.terminal.appendPlainText("[PING] enviado.")
            except Exception as e:
                self.terminal.appendPlainText(f"[ERRO] Falha ao enviar PING: {e}")
        else:
            QMessageBox.information(self, "Ping", "Nenhuma conexão ativa com o microcontrolador.")


    # ---------------- Serial ----------------
    def refresh_ports(self):
        self.combo_ports.clear()
        for port in serial.tools.list_ports.comports():
            desc = port.description.lower()
            if "bluetooth" in desc:
                continue
            self.combo_ports.addItem(port.device)
        if self.combo_ports.count() == 0:
            self.combo_ports.addItem("")

    def connect_serial(self):
        port = self.combo_ports.currentText().strip()
        if not port:
            QMessageBox.warning(self, "Erro", "Nenhuma porta selecionada")
            self._set_status("Nenhuma porta selecionada", "#b00")
            return
        try:
            if self.connected_ok:
                QMessageBox.information(self, "Conexão", f"Já está conectado em {self.ser.port}")
                return
            self.ser = serial.Serial(port, 115200, timeout=0.2)
            self.timer_serial.start(50)
            self.ser.write(b"RST\n")
            time.sleep(1)
            self.ser.write(b"READY\n")
            self.connected_ok = False
            self._set_status(f"Aguardando OK em {port}...", "#d4a017")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Falha ao abrir a porta {port}:\n{e}")
            self._set_status("Erro ao abrir a porta", "#b00")

    def disconnect_serial(self):
        if self.ser and self.ser.is_open:
            try:
                self._set_status("Desconectado", "#666")
                self.ser.write(b"RST\n")
                self.timer_serial.stop()
                self.ser.close()
                self.ser = None
                self.connected_ok = False
            except Exception as e:
                QMessageBox.warning(self, "Erro", f"Falha ao desconectar:\n{e}")
                self._set_status("Erro ao desconectar", "#b00")
        else:
            QMessageBox.information(self, "Serial", "Nenhuma porta estava conectada")

    def _read_serial(self):
        if self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if not line:
                    return
                if not self.connected_ok:
                    if line == "OK":
                        self.connected_ok = True
                        self._set_status(f"Conectado em {self.ser.port}", "#060")
                    return
                self.terminal.appendPlainText(line)

                if line.startswith("PONG"):
                    self.btn_ping.setStyleSheet("background-color: green; color: black")
                    if line == "PONG0":
                        self.cont_led.setStyleSheet("color: red; font-size: 32px;")
                    if line == "PONG1":
                        self.cont_led.setStyleSheet("color: green; font-size: 32px;")
                    return
                
                if self.logger:
                    self.logger.save_line(line)  # salva a linha inteira no arquivo

                 # Se recebeu o cabeçalho, só ignora
                if line.startswith("Tempo"):
                    return

                # Divide por tabulação
                parts = line.split("\t")
                if len(parts) >= 5:
                    try:
                        tempo = float(parts[0])
                        avgCell = float(parts[1])
                        avgKgf = float(parts[2])
                        avgTransd = float(parts[3])
                        avgPSI = float(parts[4])

            
                        # Atualiza arrays
                        self.data_tempo.append(tempo)
                        self.data_empuxo.append(avgKgf)
                        self.data_pressao.append(avgPSI)

                        # Atualiza curvas no gráfico
                        self.curva_empuxo.setData(self.data_tempo, self.data_empuxo)
                        self.curva_pressao.setData(self.data_tempo, self.data_pressao)

                        # Atualiza máximos
                        if avgKgf > self.max_thrust_val:
                            self.max_thrust_val = avgKgf
                            self.max_thrust.setText(f"{self.max_thrust_val:.2f} kgf")

                        if avgPSI > self.max_pressure_val:
                            self.max_pressure_val = avgPSI
                            self.max_pressure.setText(f"{self.max_pressure_val:.2f} psi")


                    except ValueError:
                        print(f"[WARN] Linha inválida: {line}")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"A porta {self.ser.port} foi desconectada.\nErro: {e}")
                self._set_status("Desconectado", "#666")
                self.timer_serial.stop()
                if self.ser:
                    self.ser.close()
                self.ser = None
                self.connected_ok = False

    def _clear_terminal(self):
        self.terminal.clear()
        self.btn_ping.setStyleSheet("background-color: red; color: black")
        self.cont_led.setStyleSheet("color: red; font-size: 32px;")

        # reset status
        if not self.ser or not self.ser.is_open or not self.connected_ok:
            self._set_status("Desconectado", "#666")

        # reset dados
        self.data_tempo.clear()
        self.data_empuxo.clear()
        self.data_pressao.clear()

        # limpa curvas do gráfico
        self.curva_empuxo.setData([], [])
        self.curva_pressao.setData([], [])

        # reset máximos
        self.max_thrust_val = 0.0
        self.max_pressure_val = 0.0
        self.max_thrust.setText("0.0 kgf")
        self.max_pressure.setText("0.0 psi")



    def _set_status(self, msg: str, color: str = "#666"):
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"color:{color}; font-weight:500;")

    # ---------------- Ignição ----------------
    def handle_ignition_click(self):
        now = time.time()

        if self.ignition_state == 0:  # neutro → tentar armar
            senha, ok = QInputDialog.getText(self, "Senha", "Digite a senha de ignição:")
            if ok and senha == "urd123":
                self.ignition_state = 1
                self.ignition_btn.setText("Armado")
                self.ignition_btn.setStyleSheet("background-color: orange; color:black;")
                self.terminal.appendPlainText("[IGNIÇÃO] ARMADO enviado.")
                if self.ser and self.ser.is_open and self.connected_ok:
                    self.ser.write(b"ARMED!\n")

                # agora começa a piscar vermelho, aguardando ignição
                self.blink_timer.start(500)

                # se em 4s não clicar, desarma
                QTimer.singleShot(4000, self._check_disarm)

            else:
                self.reset_ignition()

        elif self.ignition_state == 1:  # já armado → ignição
            self.ignition_state = 2
            self.blink_timer.stop()
            self.ignition_btn.setText("Ignição!")
            self.ignition_btn.setStyleSheet("background-color: red; color: white;")
            self.terminal.appendPlainText("[IGNIÇÃO] IGN enviado.")
            if self.ser and self.ser.is_open and self.connected_ok:
                self.ser.write(b"IGN!\n")

            # reseta após 5s
            QTimer.singleShot(5000, self.reset_ignition)

    def _check_disarm(self):
        # Se ainda estiver armado e não foi para ignição → desarma
        if self.ignition_state == 1:
            self.reset_ignition()
            self.terminal.appendPlainText("[IGNIÇÃO] DISARMED enviado.")
            if self.ser and self.ser.is_open and self.connected_ok:
                self.ser.write(b"DISARMED!\n")

    def reset_ignition(self):
        self.ignition_state = 0
        self.blink_timer.stop()
        self.ignition_btn.setText("Desarmado")
        self.ignition_btn.setStyleSheet("background-color: yellow; color:black;")
        self.is_blink_on = False

    def toggle_blink(self):
        if self.ignition_state == 1:  # só pisca quando está armado
            if self.is_blink_on:
                self.ignition_btn.setStyleSheet("background-color: orange; color:black;")
            else:
                self.ignition_btn.setStyleSheet("background-color: red; color:white;")
            self.is_blink_on = not self.is_blink_on


    # ---------------- Logger ----------------
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
                f"TElog_{time.strftime('%Y%m%d_%H%M%S')}.txt",
                "Text Files (*.txt)"
            )
            if filename:
                self.logger = Logger(filename)
            else:
                self.logger = None
        else:
            self.logger = None
