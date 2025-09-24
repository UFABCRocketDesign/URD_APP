from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox, QPushButton,
    QLabel, QPlainTextEdit, QLineEdit, QFileDialog, QComboBox, QSizePolicy,
    QDialog, QDialogButtonBox, QFormLayout, QFrame
)
import serial
import serial.tools.list_ports
import pyqtgraph as pg


# -------------------- Janela de Configuração --------------------
class ConfigDialog(QDialog):
    """
    Janela pequena com:
      - Arquivo de entrada (CSV)
      - Arquivo de saída (log)
      - Separador
      - Colunas a plotar (ex.: time,pressure)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self.setModal(True)
        self.setFixedSize(420, 260)

        self.ed_input = QLineEdit(self)
        self.btn_in_browse = QPushButton("Selecionar…", self)
        self.btn_in_browse.clicked.connect(self._pick_input)

        self.ed_output = QLineEdit(self)
        self.btn_out_browse = QPushButton("Selecionar…", self)
        self.btn_out_browse.clicked.connect(self._pick_output)

        self.combo_sep = QComboBox(self)
        # ordem comum de separadores
        self.combo_sep.addItems([",", "\t", ";", " "])

        self.ed_columns = QLineEdit(self)
        self.ed_columns.setPlaceholderText("Ex.: time,pressure")

        # form layout
        form = QFormLayout()
        # linha input
        box_in = QHBoxLayout()
        box_in.addWidget(self.ed_input)
        box_in.addWidget(self.btn_in_browse)
        form.addRow("Arquivo de entrada (CSV):", self._wrap(box_in))

        # linha output
        box_out = QHBoxLayout()
        box_out.addWidget(self.ed_output)
        box_out.addWidget(self.btn_out_browse)
        form.addRow("Arquivo de log (saída):", self._wrap(box_out))

        form.addRow("Separador:", self.combo_sep)
        form.addRow("Colunas a plotar:", self.ed_columns)

        # botões OK/Cancelar
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)

        # layout principal
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addStretch(1)
        root.addWidget(btns)

    def _wrap(self, layout):
        w = QWidget(self)
        w.setLayout(layout)
        return w

    def _pick_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar arquivo de entrada", "", "CSV (*.csv);;Todos (*)")
        if path:
            self.ed_input.setText(path)

    def _pick_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Selecionar arquivo de log", "", "Texto (*.txt);;Todos (*)")
        if path:
            self.ed_output.setText(path)

    def _on_accept(self):
        # Validação simples (exija input, output e colunas)
        if not self.ed_input.text().strip() or not self.ed_output.text().strip() or not self.ed_columns.text().strip():
            # mantém aberto se faltar algo
            return
        self.accept()

    # getters práticos
    def get_config(self):
        return {
            "input_path": self.ed_input.text().strip(),
            "output_path": self.ed_output.text().strip(),
            "separator": self.combo_sep.currentText(),
            "columns": [c.strip() for c in self.ed_columns.text().split(",") if c.strip()],
        }


# -------------------- Thread de leitura serial (opcional) --------------------
class SerialReader(QThread):
    new_line = Signal(str)

    def __init__(self, port: str, baud: int = 115200, parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = baud
        self._ser = None
        self._running = True

    def run(self):
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.2)
        except Exception as e:
            self.new_line.emit(f"[ERRO] Falha ao abrir {self.port}: {e}")
            return

        while self._running:
            try:
                raw = self._ser.readline()
                if not raw:
                    continue
                line = raw.decode(errors="ignore").rstrip("\r\n")
                self.new_line.emit(line)
            except Exception as e:
                self.new_line.emit(f"[ERRO] Leitura: {e}")
                break

        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except:
            pass

    def stop(self):
        self._running = False


# -------------------- Widget principal (layout solicitado) --------------------
class SimuladorApp(QWidget):
    """
    ORDEM:
      - Gráfico
      - Splitter
      - (Terminal | Status + Porta COM + Espaçador Invisível + Config + Iniciar Simulação)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Simulador de Voo")
        self.resize(1000, 640)

        # estado/config
        self.cfg = {
            "input_path": "",
            "output_path": "",
            "separator": ",",
            "columns": []  # ex.: ["time", "pressure"]
        }
        self._serial_thread: SerialReader | None = None

        # --------- layout raiz ---------
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # --------- Gráfico (pyqtgraph de verdade) ---------
        pg.setConfigOptions(antialias=True)
        self.plot = pg.PlotWidget(title="Altura x Tempo")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel("bottom", "Tempo")
        self.plot.setLabel("left", "Altura (m)")
        self.curve = self.plot.plot([], [], pen=pg.mkPen(width=2))
        self._xs: list[float] = []
        self._ys: list[float] = []
        root.addWidget(self.plot, stretch=4)

        # --------- Splitter (horizontal) ---------
        splitter = QSplitter(Qt.Vertical, self)
        root.addWidget(splitter, stretch=6)

        # ---- Lado esquerdo do splitter: Terminal ----
        term_group = QGroupBox("Terminal", self)
        term_lay = QVBoxLayout(term_group)
        term_lay.setContentsMargins(6, 6, 6, 6)

        self.terminal = QPlainTextEdit(self)
        self.terminal.setReadOnly(True)
        self.terminal.setStyleSheet(
            "background:#0f0f0f; color:#e5e5e5; font-family: Consolas, Menlo, monospace; font-size:12px;"
        )
        term_lay.addWidget(self.terminal)
        splitter.addWidget(term_group)

        # ---- Status, Porta COM, Spacer, Config, Iniciar ----
        bottom = QWidget(self)
        bottom_lay = QHBoxLayout(bottom)
        bottom_lay.setContentsMargins(4, 4, 4, 4)
        bottom_lay.setSpacing(6)

        # Status
        self.lbl_status = QLabel("Status: Desconectado", self)
        self.lbl_status.setStyleSheet("color:#666;")
        bottom_lay.addWidget(self.lbl_status)

        # Porta COM (label + combo)
        com_row = QHBoxLayout()
        com_row.setSpacing(6)
        com_row.addWidget(QLabel("Porta COM:", self))
        self.combo_ports = QComboBox(self)
        self.combo_ports.setEditable(True)
        self.combo_ports.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_ports.mousePressEvent = lambda ev: (self._refresh_ports(),
                                                       QComboBox.mousePressEvent(self.combo_ports, ev))
        com_row.addWidget(self.combo_ports)
        bottom_lay.addLayout(com_row)

        # Botão Iniciar Simulação (desabilitado até configurar)
        self.btn_start = QPushButton("Iniciar Simulação", self)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._start)
        bottom_lay.addWidget(self.btn_start)

        # Botão Iniciar Simulação (desabilitado até configurar)
        self.btn_close = QPushButton("Encerrar Simulação", self)
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self._close)
        bottom_lay.addWidget(self.btn_close)

        # Espaçador invisível (empurra os botões para baixo)
        bottom_lay.addStretch(1)

        # Botão Config
        self.btn_cfg = QPushButton("Config", self)
        self.btn_cfg.clicked.connect(self._open_config)
        bottom_lay.addWidget(self.btn_cfg)

        
        splitter.addWidget(bottom)
        splitter.setSizes([700, 300])  # proporção inicial

        # Timer opcional para demo do gráfico (comente se não quiser demo)
        # self._demo = QTimer(self)
        # self._demo.timeout.connect(self._feed_demo)
        # self._demo.start(200)

    # -------------------- UI helpers --------------------
    def _append_terminal(self, text: str):
        self.terminal.appendPlainText(text)
        sb = self.terminal.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _refresh_ports(self):
        self.combo_ports.clear()
        for p in serial.tools.list_ports.comports():
            # filtra Bluetooth se quiser
            if "bluetooth" in (p.description or "").lower():
                continue
            self.combo_ports.addItem(p.device)
        if self.combo_ports.count() == 0:
            self.combo_ports.addItem("")  # placeholder

    def _open_config(self):
        dlg = ConfigDialog(self)
        # Pré-carrega (se já tiver)
        dlg.ed_input.setText(self.cfg.get("input_path", ""))
        dlg.ed_output.setText(self.cfg.get("output_path", ""))
        # define separador atual se existir
        sep = self.cfg.get("separator", ",")
        idx = max(0, dlg.combo_sep.findText(sep))
        dlg.combo_sep.setCurrentIndex(idx)
        dlg.ed_columns.setText(",".join(self.cfg.get("columns", [])))

        if dlg.exec():  # OK
            self.cfg = dlg.get_config()
            # habilita o botão iniciar se estiver tudo preenchido
            ready = bool(self.cfg["input_path"] and self.cfg["output_path"] and self.cfg["columns"])
            self.btn_start.setEnabled(ready)

    # -------------------- Execução --------------------
    def _close(self):
        print("oi")

    def _start(self):
        """
        Aqui você pode:
          - abrir a serial escolhendo a porta em self.combo_ports.currentText()
          - iniciar um thread de leitura (para preencher o terminal e, se quiser, o gráfico)
          - ou iniciar a lógica de simulação baseada no arquivo CSV (self.cfg)
        """
        port = self.combo_ports.currentText().strip()
        if not port:
            self._set_status("Selecione uma porta COM primeiro.", error=True)
            return

        # inicia thread de leitura
        if self._serial_thread:
            try:
                self._serial_thread.stop()
            except:
                pass
            self._serial_thread = None

        self._serial_thread = SerialRead
