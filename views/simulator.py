"""
URD - Página de Simulação Serial

Fluxo principal:
1) UI conecta na COM.
2) URDSerialHandler envia READY e espera OK.
3) Usuário seleciona CSV de simulação.
4) Ao clicar em Iniciar Simulação, UI pede START ao handler.
5) Handler envia SIMULATION e espera STARTED.
6) UI passa a enviar pressão a cada X segundos.
7) Handler lê continuamente a telemetria padrão do micro e parseia pacotes tipo H3000 T342.17 etc.
8) O gráfico plota altitude calculada pela pressão enviada e altitude recebida do micro.
9) Timeout serial apenas sinaliza falha; não há reconexão automática.
"""

from __future__ import annotations

import csv
import math
import platform
import queue
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pyqtgraph as pg
import serial
import serial.tools.list_ports
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

# ============================================================
# Utilidades de simulação
# ============================================================


def pressure_to_altitude_m(pressure_pa: float, sea_level_pa: float = 101325.0) -> float:
    """
    Converte pressão absoluta em altitude aproximada pela atmosfera padrão.

    h = 44330 * (1 - (P/P0)^(1/5.255))

    Use isso apenas como referência de simulação. Se o firmware usa outro P0
    ou faz calibração de zero, mantenha o mesmo P0 nos dois lados.
    """
    if pressure_pa <= 0.0 or sea_level_pa <= 0.0:
        return float("nan")
    return 44330.0 * (1.0 - (pressure_pa / sea_level_pa) ** (1.0 / 5.255))


def safe_float(text: str) -> Optional[float]:
    try:
        value = float(str(text).strip())
        if math.isfinite(value):
            return value
        return None
    except Exception:
        return None


@dataclass
class SimulationSample:
    time_s: float
    pressure_pa: float
    altitude_m: float


class FlightSimulation:
    """
    Carrega um CSV com coluna de tempo e pressão.

    A pressão é convertida para Pa conforme a unidade escolhida.
    Depois, em runtime, a UI consulta a amostra correspondente ao tempo atual.
    """

    UNIT_SCALE_TO_PA = {
        "Pa": 1.0,
        "hPa": 100.0,
        "kPa": 1000.0,
        "bar": 100000.0,
        "mbar": 100.0,
    }

    def __init__(self, samples: list[SimulationSample], sea_level_pa: float = 101325.0):
        self.samples = sorted(samples, key=lambda s: s.time_s)
        self.sea_level_pa = sea_level_pa

    @classmethod
    def from_csv(
        cls,
        path: str,
        separator: str,
        time_column: str,
        pressure_column: str,
        pressure_unit: str,
        sea_level_pa: float,
    ) -> "FlightSimulation":
        csv_path = Path(path)
        if not csv_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")

        scale = cls.UNIT_SCALE_TO_PA.get(pressure_unit, 1.0)
        samples: list[SimulationSample] = []
        raw_rows: list[
            tuple[float, float, float]
        ] = []  # tempo, pressão real em Pa, altitude bruta

        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=separator)

            if not reader.fieldnames:
                raise ValueError("CSV sem cabeçalho.")

            if time_column not in reader.fieldnames:
                raise ValueError(
                    f"Coluna de tempo '{time_column}' não encontrada. Colunas: {reader.fieldnames}"
                )

            if pressure_column not in reader.fieldnames:
                raise ValueError(
                    f"Coluna de pressão '{pressure_column}' não encontrada. Colunas: {reader.fieldnames}"
                )

            for row in reader:
                t = safe_float(row.get(time_column, ""))
                p_raw = safe_float(row.get(pressure_column, ""))
                if t is None or p_raw is None:
                    continue

                pressure_pa = p_raw * scale
                altitude_m_raw = pressure_to_altitude_m(pressure_pa, sea_level_pa)
                raw_rows.append((t, pressure_pa, altitude_m_raw))

        if len(raw_rows) < 2:
            raise ValueError(
                "CSV precisa ter pelo menos 2 amostras válidas de tempo/pressão."
            )

        # Zera somente a curva de altitude do arquivo pela média das 10 primeiras altitudes.
        # A pressão enviada ao micro continua sendo a pressão real do CSV.
        first_n = raw_rows[:10]
        altitude_zero = sum(row[2] for row in first_n) / len(first_n)
        samples = [
            SimulationSample(t, pressure_pa, altitude_m_raw - altitude_zero)
            for t, pressure_pa, altitude_m_raw in raw_rows
        ]

        return cls(samples, sea_level_pa=sea_level_pa)

    @property
    def duration_s(self) -> float:
        return self.samples[-1].time_s

    def sample_at(self, elapsed_s: float) -> SimulationSample:
        """
        Retorna a amostra mais próxima por busca sequencial simples.
        Para arquivos muito grandes, dá para trocar por bisect.
        """
        if elapsed_s <= self.samples[0].time_s:
            return self.samples[0]

        if elapsed_s >= self.samples[-1].time_s:
            return self.samples[-1]

        # Interpolação linear entre duas amostras.
        # Para simulação de pressão, isso evita degraus quando o timer da UI
        # não bate exatamente com o timestamp do CSV.
        lo = 0
        hi = len(self.samples) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.samples[mid].time_s < elapsed_s:
                lo = mid + 1
            else:
                hi = mid - 1

        right = self.samples[lo]
        left = self.samples[lo - 1]

        dt = right.time_s - left.time_s
        if dt <= 0.0:
            return left

        alpha = (elapsed_s - left.time_s) / dt
        pressure_pa = left.pressure_pa + alpha * (right.pressure_pa - left.pressure_pa)
        altitude_m = left.altitude_m + alpha * (right.altitude_m - left.altitude_m)
        return SimulationSample(elapsed_s, pressure_pa, altitude_m)


# ============================================================
# Parser da telemetria URD
# ============================================================


class URDPacketParser:
    """
    Parser para pacote sem ordem fixa e com chave de 1 caractere.

    Exemplo aceito:
        L0 T342.17 A0.000000 O0.000000 H3000 R-1.55 P3.93 Y0.77

    Observação:
    - p é phase/flight state na telemetria recebida.
    - P é pitch na telemetria recebida.
    - Para enviar pressão para o micro, use outro comando, por exemplo PRS101325.00.
    """

    NAN = float("nan")

    LIST = [
        "linha",
        "tempo",
        "phase",
        "latitude",
        "longitude",
        "hora",
        "minuto",
        "precisao",
        "altitude",
        "sd",
        "apogeu_h",
        "apogeu_t",
        "pqd_dn",
        "pqd_db",
        "pqd_mn",
        "pqd_mb",
        "temp",
        "roll",
        "pitch",
        "yaw",
    ]

    TAG = {
        "L": "linha",
        "T": "tempo",
        "p": "phase",  # flight state
        "A": "latitude",
        "O": "longitude",
        "h": "hora",
        "n": "minuto",
        "g": "precisao",
        "H": "altitude",
        "s": "sd",
        "a": "apogeu_h",  # apogeu continua usando chave a
        "t": "apogeu_t",
        "D": "pqd_dn",
        "d": "pqd_db",
        "M": "pqd_mn",  # Main nominal
        "m": "pqd_mb",  # Main backup
        "c": "temp",
        "R": "roll",
        "P": "pitch",  # P permanece pitch
        "Y": "yaw",
    }

    NUM = r"[-+]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[eE][-+]?\d+)?"

    def parse_packet(self, line: str):
        if not line:
            return None

        line = line.strip()
        tokens = re.findall(rf"([A-Za-z])\s*({self.NUM})", line)

        if not tokens:
            return None

        raw = {k: None for k in self.LIST}
        app = {k: self.NAN for k in self.LIST}
        used_keys = set()

        for key_txt, value_txt in tokens:
            key = self.TAG.get(key_txt.strip())
            if key is None:
                continue

            if key in used_keys:
                continue

            used_keys.add(key)
            num = safe_float(value_txt)
            raw[key] = num

            if num is not None and self._in_range(key, num):
                app[key] = num
            else:
                app[key] = self.NAN

        return raw, app

    def _in_range(self, key: str, value: float) -> bool:
        """
        Ajuste fino dos limites do app.
        A ideia é filtrar pacote corrompido sem depender da ordem.
        """
        ranges = {
            "linha": (0, 10_000_000),
            "tempo": (-1, 1_000_000),
            "phase": (0, 6),
            "latitude": (-90, 90),
            "longitude": (-180, 180),
            "hora": (0, 23),
            "minuto": (0, 59),
            "precisao": (0, 100),
            "altitude": (-1000, 100_000),
            "sd": (0, 1),
            "apogeu_h": (-1000, 100_000),
            "apogeu_t": (-1, 1_000_000),
            "pqd_dn": (-1000, 100_000),
            "pqd_db": (-1000, 100_000),
            "pqd_mn": (-1000, 100_000),
            "pqd_mb": (-1000, 100_000),
            "temp": (-80, 120),
            "roll": (-360, 360),
            "pitch": (-360, 360),
            "yaw": (-360, 360),
        }
        lo, hi = ranges.get(key, (-float("inf"), float("inf")))
        return lo <= value <= hi


# ============================================================
# Handler serial reutilizável
# ============================================================


class URDSerialHandler(QThread):
    """
    Thread dona da comunicação serial.

    Comandos previstos no firmware:
    - UI -> micro: READY\n
    - micro -> UI: OK\n
    - UI -> micro: SIMULATION\n
    - micro -> UI: STARTED\n
    - UI -> micro durante simulação: <pressao_em_Pa>\n
    Altere PRESSURE_CMD_PREFIX se quiser.
    """

    log = Signal(str)
    status = Signal(str, str)  # texto, cor
    connected = Signal()
    disconnected = Signal()
    handshake_ok = Signal()
    simulation_started = Signal()
    simulation_recovered = Signal()
    timeout_detected = Signal(float)
    packet_received = Signal(dict, dict, str)  # raw, app, linha original
    error = Signal(str)

    PRESSURE_CMD_PREFIX = ""

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        timeout_s: float = 1.0,
        parent=None,
    ):
        super().__init__(parent)
        self.port = port
        self.baud = baud
        self.timeout_s = timeout_s

        self._ser: Optional[serial.Serial] = None
        self._running = False
        self._connected_ok = False
        self._simulation_requested = False
        self._simulation_active = False
        self._last_rx_mono = 0.0

        self._parser = URDPacketParser()
        self._cmd_queue: queue.Queue[tuple[str, object | None]] = queue.Queue()

    def run(self):
        self._running = True

        try:
            self.status.emit(f"Abrindo {self.port}...", "#d4a017")
            self._ser = serial.Serial(
                self.port, self.baud, timeout=0.02, write_timeout=0.5
            )
            self._safe_reset_buffers()
            self.connected.emit()

            ok = self._perform_ready_handshake(timeout_s=6.0)
            if not ok:
                raise TimeoutError("Timeout aguardando OK no handshake READY/OK.")

            self._connected_ok = True
            self.handshake_ok.emit()
            self.status.emit(f"Conectado em {self.port}", "#060")

            while self._running:
                self._consume_commands()
                self._read_available_line()
                self._check_timeout_and_recover()
                self.msleep(5)

        except Exception as e:
            self.error.emit(str(e))
            self.status.emit("Erro na serial", "#b00")

        finally:
            self._close_serial()
            self.disconnected.emit()

    # ---------- API pública usada pela UI ----------

    def request_start_simulation(self):
        self._cmd_queue.put(("START_SIMULATION", None))

    def send_pressure(self, pressure_pa: float):
        self._cmd_queue.put(("PRESSURE", float(pressure_pa)))

    def stop_simulation_mode(self):
        self._cmd_queue.put(("STOP_SIMULATION", None))

    def stop_handler(self):
        self._running = False
        self._cmd_queue.put(("STOP", None))

    # ---------- Núcleo serial ----------

    def _consume_commands(self):
        for _ in range(10):
            try:
                cmd, value = self._cmd_queue.get_nowait()
            except queue.Empty:
                return

            if cmd == "START_SIMULATION":
                self._simulation_requested = True
                self._perform_simulation_start(timeout_s=4.0)

            elif cmd == "PRESSURE":
                if self._simulation_active and value is not None:
                    self._write_line(f"{self.PRESSURE_CMD_PREFIX}{float(value):.2f}")

            elif cmd == "STOP_SIMULATION":
                self._simulation_active = False
                self._simulation_requested = False
                self._write_line("STOP_SIMULATION")
                self.status.emit("Simulação encerrada", "#666")

            elif cmd == "STOP":
                self._running = False
                return

    def _perform_ready_handshake(self, timeout_s: float) -> bool:
        if not self._ser or not self._ser.is_open:
            return False

        self._safe_reset_buffers()
        self._drain_input(seconds=0.20)

        self.status.emit("Enviando READY...", "#d4a017")
        self._write_line("READY")

        ok = self._wait_for_token("OK", timeout_s=timeout_s)
        if ok:
            self._last_rx_mono = time.monotonic()
            self.log.emit("[HANDSHAKE] READY -> OK")
        return ok

    def _perform_simulation_start(self, timeout_s: float) -> bool:
        if not self._connected_ok:
            self.error.emit("Serial ainda não concluiu READY/OK.")
            return False

        self.status.emit("Enviando SIMULATION...", "#d4a017")
        self._write_line("SIMULATION")

        ok = self._wait_for_token("STARTED", timeout_s=timeout_s)
        if ok:
            self._simulation_active = True
            self._last_rx_mono = time.monotonic()
            self.log.emit("[SIM] SIMULATION -> STARTED")
            self.status.emit("Simulação ativa", "#060")
            self.simulation_started.emit()
        else:
            self.error.emit("Timeout aguardando STARTED.")
        return ok

    def _check_timeout_and_recover(self):
        if not self._connected_ok or not self._ser or not self._ser.is_open:
            return

        now = time.monotonic()
        if self._last_rx_mono <= 0.0:
            self._last_rx_mono = now
            return

        elapsed = now - self._last_rx_mono
        if elapsed < self.timeout_s:
            return

        # Sem reconexão automática: depois do READY/OK o micro fica esperando SIMULATION.
        # Se a UI refizesse READY sozinha, ela poderia quebrar esse fluxo.
        self._last_rx_mono = now
        self.timeout_detected.emit(elapsed)
        self.status.emit(
            f"Timeout serial ({elapsed:.2f}s). Sem reconexão automática.", "#d4a017"
        )
        self.log.emit(
            f"[TIMEOUT] Sem dados por {elapsed:.2f}s. Reconexão automática desativada."
        )

    def _read_available_line(self):
        if not self._ser or not self._ser.is_open:
            return

        try:
            raw = self._ser.readline()
            if not raw:
                return

            line = raw.decode(errors="ignore").strip()
            if not line:
                return

            self._last_rx_mono = time.monotonic()
            self.log.emit(f"RX: {line}")

            if line == "OK" or line == "STARTED":
                return

            parsed = self._parser.parse_packet(line)
            if parsed is not None:
                raw_packet, app_packet = parsed
                self.packet_received.emit(raw_packet, app_packet, line)

        except Exception as e:
            self.error.emit(f"Erro de leitura serial: {e}")

    def _wait_for_token(self, expected: str, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s

        while self._running and time.monotonic() < deadline:
            if not self._ser or not self._ser.is_open:
                return False

            try:
                raw = self._ser.readline()
                if not raw:
                    self.msleep(5)
                    continue

                line = raw.decode(errors="ignore").strip()
                if not line:
                    continue

                self._last_rx_mono = time.monotonic()
                self.log.emit(f"RX: {line}")

                if line == expected:
                    return True

                # Se chegar telemetria durante uma espera, não joga fora.
                parsed = self._parser.parse_packet(line)
                if parsed is not None:
                    raw_packet, app_packet = parsed
                    self.packet_received.emit(raw_packet, app_packet, line)

            except Exception as e:
                self.error.emit(f"Erro aguardando {expected}: {e}")
                return False

        return False

    def _write_line(self, text: str):
        if not self._ser or not self._ser.is_open:
            return

        payload = (text.strip() + "\n").encode("utf-8")
        self._ser.write(payload)
        self.log.emit(f"TX: {text.strip()}")

    def _safe_reset_buffers(self):
        try:
            if self._ser and self._ser.is_open:
                self._ser.reset_input_buffer()
                self._ser.reset_output_buffer()
        except Exception:
            pass

    def _drain_input(self, seconds: float):
        if not self._ser or not self._ser.is_open:
            return

        end = time.monotonic() + seconds
        while time.monotonic() < end:
            raw = self._ser.readline()
            if raw:
                line = raw.decode(errors="ignore").strip()
                if line:
                    self.log.emit(f"RX[drain]: {line}")
            else:
                self.msleep(5)

    def _close_serial(self):
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:
            pass
        self._ser = None
        self._connected_ok = False
        self._simulation_active = False


# ============================================================
# Dialog de configuração da simulação
# ============================================================


class SimulationConfigDialog(QDialog):
    def __init__(self, parent=None, cfg: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Configuração da Simulação")
        self.setModal(True)
        self.setMinimumWidth(560)

        cfg = cfg or {}

        self.ed_input = QLineEdit(cfg.get("input_path", ""), self)
        self.btn_browse = QPushButton("Selecionar...", self)
        self.btn_browse.clicked.connect(self._pick_input)

        self.combo_sep = QComboBox(self)
        self.combo_sep.addItems([",", ";", "\\t", " "])
        sep = cfg.get("separator", ",")
        sep_display = "\\t" if sep == "\t" else sep
        idx = self.combo_sep.findText(sep_display)
        self.combo_sep.setCurrentIndex(idx if idx >= 0 else 0)

        self.ed_time_col = QLineEdit(cfg.get("time_column", "time"), self)
        self.ed_pressure_col = QLineEdit(cfg.get("pressure_column", "pressure"), self)

        self.combo_pressure_unit = QComboBox(self)
        self.combo_pressure_unit.addItems(["Pa", "hPa", "kPa", "mbar", "bar"])
        unit_idx = self.combo_pressure_unit.findText(cfg.get("pressure_unit", "Pa"))
        self.combo_pressure_unit.setCurrentIndex(unit_idx if unit_idx >= 0 else 0)

        self.ed_send_interval = QLineEdit(str(cfg.get("send_interval_s", 0.10)), self)
        self.ed_timeout = QLineEdit(str(cfg.get("timeout_s", 10.00)), self)
        self.ed_sea_level = QLineEdit(str(cfg.get("sea_level_pa", 101325.0)), self)
        self.ed_log_output = QLineEdit(cfg.get("output_path", ""), self)
        self.btn_log_browse = QPushButton("Selecionar...", self)
        self.btn_log_browse.clicked.connect(self._pick_output)

        form = QFormLayout()

        file_row = QHBoxLayout()
        file_row.addWidget(self.ed_input)
        file_row.addWidget(self.btn_browse)
        form.addRow("CSV de simulação:", self._wrap(file_row))

        form.addRow("Separador:", self.combo_sep)
        form.addRow("Coluna de tempo [s]:", self.ed_time_col)
        form.addRow("Coluna de pressão:", self.ed_pressure_col)
        form.addRow("Unidade da pressão:", self.combo_pressure_unit)
        form.addRow("Intervalo de envio [s]:", self.ed_send_interval)
        form.addRow("Timeout serial [s]:", self.ed_timeout)
        form.addRow("Pressão nível do mar P0 [Pa]:", self.ed_sea_level)

        log_row = QHBoxLayout()
        log_row.addWidget(self.ed_log_output)
        log_row.addWidget(self.btn_log_browse)
        form.addRow("Log local opcional:", self._wrap(log_row))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def _wrap(self, layout: QHBoxLayout) -> QWidget:
        w = QWidget(self)
        w.setLayout(layout)
        return w

    def _pick_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar CSV", "", "CSV (*.csv);;Todos (*)"
        )
        if path:
            self.ed_input.setText(path)

    def _pick_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Selecionar log", "", "CSV (*.csv);;Texto (*.txt);;Todos (*)"
        )
        if path:
            self.ed_log_output.setText(path)

    def _on_accept(self):
        try:
            cfg = self.get_config()
            if not cfg["input_path"]:
                raise ValueError("Selecione um CSV de simulação.")
            if cfg["send_interval_s"] <= 0.0:
                raise ValueError("Intervalo de envio precisa ser maior que zero.")
            if cfg["timeout_s"] <= 0.0:
                raise ValueError("Timeout precisa ser maior que zero.")
            if cfg["sea_level_pa"] <= 0.0:
                raise ValueError("P0 precisa ser maior que zero.")
        except Exception as e:
            QMessageBox.warning(self, "Configuração inválida", str(e))
            return

        self.accept()

    def get_config(self) -> dict:
        sep = self.combo_sep.currentText()
        if sep == "\\t":
            sep = "\t"

        return {
            "input_path": self.ed_input.text().strip(),
            "separator": sep,
            "time_column": self.ed_time_col.text().strip(),
            "pressure_column": self.ed_pressure_col.text().strip(),
            "pressure_unit": self.combo_pressure_unit.currentText(),
            "send_interval_s": float(self.ed_send_interval.text().replace(",", ".")),
            "timeout_s": float(self.ed_timeout.text().replace(",", ".")),
            "sea_level_pa": float(self.ed_sea_level.text().replace(",", ".")),
            "output_path": self.ed_log_output.text().strip(),
        }


# ============================================================
# Página principal
# ============================================================


class MetricBox(QFrame):
    """
    Pequena caixa reutilizável para valores de monitoramento.

    Ela aceita setText(...) para ser compatível com QLabel no resto do código,
    mas visualmente separa título e valor.
    """

    def __init__(self, title: str, value: str = "--", parent=None):
        super().__init__(parent)
        self._ok = False
        self.setObjectName("MetricBox")
        self.setMinimumHeight(56)
        self.setFrameShape(QFrame.StyledPanel)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(2)

        self.title = QLabel(title, self)
        self.title.setObjectName("MetricTitle")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.value = QLabel(value, self)
        self.value.setObjectName("MetricValue")
        self.value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)

        lay.addWidget(self.title)
        lay.addWidget(self.value)
        self.set_state("idle")

    def setText(self, text: str):
        self.value.setText(str(text))

    def text(self) -> str:
        return self.value.text()

    def set_state(self, state: str = "idle"):
        if state == "ok":
            border = "#4caf50"
            bg = "rgba(76, 175, 80, 0.12)"
        elif state == "bad":
            border = "#f44336"
            bg = "rgba(244, 67, 54, 0.12)"
        elif state == "warn":
            border = "#d4a017"
            bg = "rgba(212, 160, 23, 0.12)"
        else:
            border = "#4a4a4a"
            bg = "rgba(255, 255, 255, 0.03)"

        self.setStyleSheet(f"""
            QFrame#MetricBox {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            QLabel#MetricTitle {{
                color: #a9a9a9;
                font-size: 10px;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#MetricValue {{
                color: #f0f0f0;
                font-size: 13px;
                font-weight: 700;
                background: transparent;
            }}
        """)


class URDSimulatorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("URD - Simulador de Voo")
        self.resize(1200, 760)

        self.serial_handler: Optional[URDSerialHandler] = None
        self.simulation: Optional[FlightSimulation] = None

        self.cfg = {
            "input_path": "",
            "separator": "\t",
            "time_column": "time",
            "pressure_column": "pressure",
            "pressure_unit": "Pa",
            "send_interval_s": 0.01,
            "timeout_s": 10.00,
            "sea_level_pa": 101325.0,
            "output_path": "",
        }

        self.connected_ok = False
        self.simulation_started = False
        self.paused_by_timeout = False
        self.pause_started_mono = 0.0
        self.sim_start_mono = 0.0
        self.last_send_mono = 0.0
        self.last_micro_altitude = float("nan")
        self.last_sim_altitude = float("nan")
        self.last_pressure_pa = float("nan")
        self.last_micro_time_raw = float("nan")
        self.t0_micro: Optional[float] = None

        self.x_sim: list[float] = []
        self.y_sim: list[float] = []
        self.x_micro: list[float] = []
        self.y_micro: list[float] = []
        self.event_points: list[dict] = []
        self.detected_events: set[str] = set()

        self.log_file = None

        self._hz_counter = 0
        self._hz_last_mono = time.monotonic()
        self._hz_value = 0.0

        self._build_ui()
        self._refresh_ports()

        self.sim_timer = QTimer(self)
        self.sim_timer.timeout.connect(self._simulation_tick)
        self.sim_timer.start(20)

        self.serial_hz_timer = QTimer(self)
        self.serial_hz_timer.timeout.connect(self._update_serial_hz)
        self.serial_hz_timer.start(1000)

    # ---------- UI ----------

    def _build_ui(self):
        pg.setConfigOptions(antialias=True)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ========================
        #  GRÁFICO PRINCIPAL
        # ========================
        plot_group = QGroupBox("Comparação de Altitude", self)
        plot_layout = QVBoxLayout(plot_group)
        plot_layout.setContentsMargins(8, 10, 8, 8)

        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.30)
        self.plot.setLabel("bottom", "Tempo de simulação", units="s")
        self.plot.setLabel("left", "Altitude", units="m")
        self.plot.addLegend(offset=(10, 10))

        self.curve_sim = self.plot.plot(
            [], [], pen=pg.mkPen("#17a2ff", width=2), name="Altura simulador"
        )
        self.curve_micro = self.plot.plot(
            [], [], pen=pg.mkPen("#ffb347", width=2), name="Altura micro"
        )
        self.scatter_events = pg.ScatterPlotItem(
            size=11, brush=pg.mkBrush("#ff3355"), pen=pg.mkPen("#ffffff", width=1)
        )
        self.plot.addItem(self.scatter_events)

        self.plot.setMinimumHeight(330)
        plot_group.setMinimumHeight(380)
        plot_layout.addWidget(self.plot)
        root.addWidget(plot_group, stretch=8)

        # ========================
        #  CONTROLES DE SIMULAÇÃO
        #  Ficam entre gráfico e blocos inferiores.
        # ========================
        run_bar = self._build_run_controls()
        root.addWidget(run_bar)

        # ========================
        #  TERMINAL + MONITORAMENTO
        # ========================
        lower = QSplitter(Qt.Horizontal, self)
        root.addWidget(lower, stretch=2)

        lower.addWidget(self._build_terminal_group())
        lower.addWidget(self._build_monitoring_group())
        # lower.setSizes([760, 520])

        self._set_serial_status("idle")
        self._set_button_visual(self.btn_start, "start_idle")
        self._set_button_visual(self.btn_stop, "stop_idle")

    def _build_run_controls(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("RunControlBar")
        bar.setStyleSheet("""
            QFrame#RunControlBar {
                background: rgba(255, 255, 255, 0.035);
                border: 1px solid #4a4a4a;
                border-radius: 10px;
            }
        """)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        title = QLabel("Controle da Simulação", self)
        title.setStyleSheet("font-weight:700; font-size:12px;")
        lay.addWidget(title)
        lay.addStretch(1)

        self.btn_start = QPushButton("Iniciar Simulação", self)
        self.btn_start.setMinimumHeight(34)
        self.btn_start.setMinimumWidth(170)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._start_simulation)
        lay.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Encerrar Simulação", self)
        self.btn_stop.setMinimumHeight(34)
        self.btn_stop.setMinimumWidth(170)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_simulation)
        lay.addWidget(self.btn_stop)

        lay.addSpacing(16)

        self.btn_reset_page = QPushButton("Resetar Página", self)
        self.btn_reset_page.setMinimumHeight(34)
        self.btn_reset_page.setMinimumWidth(150)
        self.btn_reset_page.clicked.connect(self._reset_page)
        lay.addWidget(self.btn_reset_page)

        return bar

    def _build_terminal_group(self) -> QGroupBox:
        term_group = QGroupBox("Terminal Serial", self)
        term_layout = QVBoxLayout(term_group)
        term_layout.setContentsMargins(8, 10, 8, 8)
        term_layout.setSpacing(6)

        # Linha de botões dentro do bloco do terminal.
        top = QWidget(self)
        row = QHBoxLayout(top)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.chk_autoscroll = QCheckBox("Auto-scroll", self)
        self.chk_autoscroll.setChecked(True)
        self.chk_autoscroll.setMaximumHeight(26)
        row.addWidget(self.chk_autoscroll)

        row.addWidget(QLabel("Porta:", self))
        self.combo_ports = QComboBox(self)
        self.combo_ports.setEditable(True)
        self.combo_ports.setMinimumWidth(130)
        self.combo_ports.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_ports.mousePressEvent = lambda ev: (
            self._refresh_ports(),
            QComboBox.mousePressEvent(self.combo_ports, ev),
        )
        row.addWidget(self.combo_ports, stretch=1)

        self.btn_connect = QPushButton("Conectar", self)
        self.btn_connect.setMaximumHeight(26)
        self.btn_connect.clicked.connect(self._connect_serial)
        row.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("Desconectar", self)
        self.btn_disconnect.setMaximumHeight(26)
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self._disconnect_serial)
        row.addWidget(self.btn_disconnect)

        self.btn_clear = QPushButton("Limpar", self)
        self.btn_clear.setMaximumHeight(26)
        self.btn_clear.clicked.connect(self._clear_terminal)
        row.addWidget(self.btn_clear)

        self.btn_config = QPushButton("Configurar CSV", self)
        self.btn_config.setMaximumHeight(26)
        self.btn_config.clicked.connect(self._open_config)
        row.addWidget(self.btn_config)

        term_layout.addWidget(top)

        self.terminal = QPlainTextEdit(self)
        self.terminal.setReadOnly(True)
        self.terminal.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.terminal.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.terminal.setStyleSheet("""
            QPlainTextEdit {
                background:#0f0f0f;
                color:#e5e5e5;
                font-family:Consolas, Menlo, monospace;
                font-size:12px;
                border:1px solid #3a3a3a;
                border-radius:8px;
                padding:6px;
            }
        """)
        term_layout.addWidget(self.terminal, stretch=1)

        # Status dentro do mesmo bloco, embaixo, no estilo da GS.
        status_box = QWidget(self)
        status_lay = QVBoxLayout(status_box)
        status_lay.setContentsMargins(0, 0, 0, 0)
        status_lay.setSpacing(3)

        serial_title = QLabel("Status Serial", self)
        serial_title.setAlignment(Qt.AlignCenter)
        serial_title.setStyleSheet("font-size:10px; font-weight:700;")
        status_lay.addWidget(serial_title)

        serial_row = QHBoxLayout()
        serial_row.setSpacing(8)

        self.lbl_serial_hz = QLabel("0.0 Hz", self)
        self.lbl_serial_hz.setStyleSheet("font-size:10px; font-weight:600;")
        serial_row.addWidget(self.lbl_serial_hz)

        self.serial_status_box = QFrame(self)
        self.serial_status_box.setFixedSize(16, 16)
        serial_row.addWidget(self.serial_status_box)

        self.lbl_serial_status = QLabel("IDLE", self)
        self.lbl_serial_status.setStyleSheet("font-size:10px; font-weight:700;")
        serial_row.addWidget(self.lbl_serial_status)

        serial_row.addStretch(1)

        self.lbl_serial_packets = QLabel("0/19", self)
        self.lbl_serial_packets.setStyleSheet("font-size:10px; font-weight:600;")
        serial_row.addWidget(self.lbl_serial_packets)

        status_lay.addLayout(serial_row)

        self.lbl_status = QLabel("Desconectado", self)
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet(
            "color:#666; font-weight:600; padding:4px; border-top:1px solid #4a4a4a;"
        )
        status_lay.addWidget(self.lbl_status)

        term_layout.addWidget(status_box)
        return term_group

    def _build_monitoring_group(self) -> QGroupBox:
        values_group = QGroupBox("Monitoramento", self)
        root = QVBoxLayout(values_group)
        root.setContentsMargins(8, 10, 8, 8)
        root.setSpacing(8)

        # -------- Simulação --------
        sim_group = QGroupBox("Simulação enviada ao micro", self)
        sim_grid = QGridLayout(sim_group)
        sim_grid.setContentsMargins(8, 10, 8, 8)
        sim_grid.setHorizontalSpacing(8)
        sim_grid.setVerticalSpacing(8)

        self.lbl_file = MetricBox("Arquivo CSV", "Nenhum", self)
        self.lbl_pressure = MetricBox("Pressão enviada", "-- Pa", self)
        self.lbl_alt_sim = MetricBox("Altura do simulador", "-- m", self)
        self.lbl_timeout = MetricBox(
            "Timeout serial", f"{self.cfg['timeout_s']:.2f} s", self
        )

        sim_grid.addWidget(self.lbl_file, 0, 0, 1, 2)
        sim_grid.addWidget(self.lbl_pressure, 1, 0)
        sim_grid.addWidget(self.lbl_alt_sim, 1, 1)
        sim_grid.addWidget(self.lbl_timeout, 2, 0, 1, 2)
        root.addWidget(sim_group)

        # -------- Retorno do micro --------
        micro_group = QGroupBox("Retorno do microcontrolador", self)
        micro_grid = QGridLayout(micro_group)
        micro_grid.setContentsMargins(8, 10, 8, 8)
        micro_grid.setHorizontalSpacing(8)
        micro_grid.setVerticalSpacing(8)

        self.lbl_alt_micro = MetricBox("Altura do micro", "-- m", self)
        self.lbl_delta = MetricBox("Erro (micro - simulador)", "-- m", self)
        self.lbl_packet_time = MetricBox("Tempo no pacote", "-- s", self)

        micro_grid.addWidget(self.lbl_alt_micro, 0, 0)
        micro_grid.addWidget(self.lbl_delta, 0, 1)
        micro_grid.addWidget(self.lbl_packet_time, 1, 0, 1, 2)
        root.addWidget(micro_group)

        # -------- Eventos --------
        events_group = QGroupBox("Eventos e paraquedas", self)
        events_grid = QGridLayout(events_group)
        events_grid.setContentsMargins(8, 10, 8, 8)
        events_grid.setHorizontalSpacing(8)
        events_grid.setVerticalSpacing(8)

        self.lbl_phase = MetricBox("Fase de voo", "Desconectado", self)
        self.lbl_apogee = MetricBox("Apogeu", "--", self)
        self.lbl_drogue_n = MetricBox("Drogue nominal", "--", self)
        self.lbl_drogue_b = MetricBox("Drogue backup", "--", self)
        self.lbl_main_n = MetricBox("Main nominal", "--", self)
        self.lbl_main_b = MetricBox("Main backup", "--", self)

        events_grid.addWidget(self.lbl_phase, 0, 0, 1, 2)
        events_grid.addWidget(self.lbl_apogee, 1, 0, 1, 2)
        events_grid.addWidget(self.lbl_drogue_n, 2, 0)
        events_grid.addWidget(self.lbl_drogue_b, 2, 1)
        events_grid.addWidget(self.lbl_main_n, 3, 0)
        events_grid.addWidget(self.lbl_main_b, 3, 1)
        root.addWidget(events_group)

        root.addStretch(1)
        return values_group

    def _refresh_ports(self):
        current = (
            self.combo_ports.currentText().strip()
            if hasattr(self, "combo_ports")
            else ""
        )
        self.combo_ports.clear()
        ports = []
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            device = p.device
            if "bluetooth" in desc:
                continue

            ports.append(device)

        self.combo_ports.addItems(ports)
        if current and current not in ports:
            self.combo_ports.addItem(current)
            self.combo_ports.setCurrentText(current)
        elif ports:
            self.combo_ports.setCurrentText(ports[0])
        else:
            self.combo_ports.addItem("")

    def _append_terminal(self, text: str):
        self.terminal.appendPlainText(text)
        if not hasattr(self, "chk_autoscroll") or self.chk_autoscroll.isChecked():
            sb = self.terminal.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _clear_terminal(self):
        self.terminal.clear()
        if not self.connected_ok:
            self._set_status("Desconectado", "#666")
            self._set_serial_status("idle")

    def _set_status(self, text: str, color: str = "#666"):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(
            f"color:{color}; font-weight:600; padding:4px; border-top:1px solid #4a4a4a;"
        )

    def _set_serial_status(self, state: str):
        if state == "ok":
            color = "#4caf50"
            text = "RX OK"
            border = "#81c784"
        elif state == "bad":
            color = "#f44336"
            text = "RX ERR"
            border = "#f44336"
        elif state == "connected":
            color = "#17d4ce"
            text = "READY"
            border = "#17d4ce"
        elif state == "sim":
            color = "#4caf50"
            text = "SIM"
            border = "#81c784"
        elif state == "timeout":
            color = "#d4a017"
            text = "RECOVERY"
            border = "#d4a017"
        else:
            color = "#ffcc00"
            text = "IDLE"
            border = "#aaa"

        self.serial_status_box.setStyleSheet(
            f"background:{color}; border:1px solid {border}; border-radius:4px;"
        )
        self.lbl_serial_status.setText(text)

    def _set_button_visual(self, button: QPushButton, state: str):
        styles = {
            "start_idle": """
                QPushButton { background:#3a3a3a; color:#f2f2f2; border:1px solid #4a4a4a; border-radius:8px; font-weight:700; }
                QPushButton:hover { background:#2f6f46; border:1px solid #4caf50; }
                QPushButton:disabled { background:#2a2a2a; color:#777; border:1px solid #3a3a3a; }
            """,
            "start_active": """
                QPushButton { background:#1f7a3a; color:white; border:2px solid #81c784; border-radius:8px; font-weight:800; }
                QPushButton:hover { background:#238844; }
                QPushButton:disabled { background:#1f7a3a; color:white; border:2px solid #81c784; }
            """,
            "start_flash": """
                QPushButton { background:#b6f5b6; color:#102410; border:2px solid #ffffff; border-radius:8px; font-weight:900; }
            """,
            "stop_idle": """
                QPushButton { background:#3a3a3a; color:#f2f2f2; border:1px solid #4a4a4a; border-radius:8px; font-weight:700; }
                QPushButton:hover { background:#7a3030; border:1px solid #f44336; }
                QPushButton:disabled { background:#2a2a2a; color:#777; border:1px solid #3a3a3a; }
            """,
            "stop_ready": """
                QPushButton { background:#7a3030; color:white; border:1px solid #f44336; border-radius:8px; font-weight:800; }
                QPushButton:hover { background:#a33a3a; }
                QPushButton:disabled { background:#7a3030; color:white; border:1px solid #f44336; }
            """,
            "stop_flash": """
                QPushButton { background:#f8d7da; color:#4a1111; border:2px solid #ffffff; border-radius:8px; font-weight:900; }
            """,
        }
        button.setStyleSheet(styles.get(state, ""))

    def _blink_button(
        self,
        button: QPushButton,
        flash_state: str,
        final_state: str,
        pulses: int = 4,
        interval_ms: int = 120,
    ):
        """Pisca um botão alternando entre flash_state e final_state."""
        counter = {"i": 0}

        def step():
            if counter["i"] >= pulses:
                self._set_button_visual(button, final_state)
                return
            self._set_button_visual(
                button, flash_state if counter["i"] % 2 == 0 else final_state
            )
            counter["i"] += 1
            QTimer.singleShot(interval_ms, step)

        step()

    def _update_buttons(self):
        has_sim = self.simulation is not None
        self.btn_connect.setEnabled(not self.connected_ok)
        self.btn_disconnect.setEnabled(self.connected_ok)
        self.btn_start.setEnabled(
            self.connected_ok and has_sim and not self.simulation_started
        )
        self.btn_stop.setEnabled(self.simulation_started)

        if self.simulation_started:
            self._set_button_visual(self.btn_start, "start_active")
            self._set_button_visual(self.btn_stop, "stop_ready")
        else:
            self._set_button_visual(self.btn_start, "start_idle")
            self._set_button_visual(self.btn_stop, "stop_idle")

    def _update_serial_hz(self):
        now = time.monotonic()
        dt = now - self._hz_last_mono
        if dt <= 0.0:
            return
        self._hz_value = self._hz_counter / dt
        self._hz_counter = 0
        self._hz_last_mono = now
        if hasattr(self, "lbl_serial_hz"):
            self.lbl_serial_hz.setText(f"{self._hz_value:.1f} Hz")

    # ---------- Configuração ----------

    def _open_config(self):
        dlg = SimulationConfigDialog(self, self.cfg)
        if not dlg.exec():
            return

        self.cfg = dlg.get_config()
        self.lbl_timeout.setText(f"{self.cfg['timeout_s']:.2f} s")

        try:
            self.simulation = FlightSimulation.from_csv(
                path=self.cfg["input_path"],
                separator=self.cfg["separator"],
                time_column=self.cfg["time_column"],
                pressure_column=self.cfg["pressure_column"],
                pressure_unit=self.cfg["pressure_unit"],
                sea_level_pa=self.cfg["sea_level_pa"],
            )
        except Exception as e:
            self.simulation = None
            QMessageBox.warning(self, "Erro ao carregar CSV", str(e))
            self._update_buttons()
            return

        self.lbl_file.setText(
            f"{Path(self.cfg['input_path']).name} | {len(self.simulation.samples)} amostras"
        )
        self._append_terminal(f"[CSV] Carregado: {self.cfg['input_path']}")
        self._append_terminal(
            f"[CSV] Duração: {self.simulation.duration_s:.2f}s | Amostras: {len(self.simulation.samples)}"
        )
        self._update_buttons()

    # ---------- Serial ----------

    def _connect_serial(self):
        port = self.combo_ports.currentText().strip()
        if not port:
            QMessageBox.warning(self, "Serial", "Selecione uma porta COM.")
            return

        self._disconnect_serial(silent=True)

        timeout_s = float(self.cfg.get("timeout_s", 1.0))
        self.serial_handler = URDSerialHandler(
            port=port, baud=115200, timeout_s=timeout_s, parent=self
        )
        self.serial_handler.log.connect(self._append_terminal)
        self.serial_handler.status.connect(self._set_status)
        self.serial_handler.handshake_ok.connect(self._on_handshake_ok)
        self.serial_handler.disconnected.connect(self._on_serial_disconnected)
        self.serial_handler.timeout_detected.connect(self._on_serial_timeout)
        self.serial_handler.simulation_started.connect(
            self._on_micro_simulation_started
        )
        self.serial_handler.simulation_recovered.connect(self._on_micro_recovered)
        self.serial_handler.packet_received.connect(self._on_packet_received)
        self.serial_handler.error.connect(self._on_serial_error)
        self.serial_handler.start()

        self._set_status(f"Abrindo {port}...", "#d4a017")

    def _disconnect_serial(self, silent: bool = False):
        if self.serial_handler:
            try:
                self.serial_handler.stop_handler()
                self.serial_handler.wait(800)
            except Exception:
                pass
            self.serial_handler = None

        self.connected_ok = False
        if not silent:
            self._set_status("Desconectado", "#666")
        self._update_buttons()

    def _on_handshake_ok(self):
        self.connected_ok = True
        self._set_serial_status("connected")
        self._append_terminal(
            "[UI] Handshake concluído. UI pronta para iniciar simulação."
        )
        self._update_buttons()

    def _on_serial_disconnected(self):
        self.connected_ok = False
        self._set_serial_status("idle")
        self._update_buttons()

    def _on_serial_error(self, text: str):
        self._set_serial_status("bad")
        self._append_terminal(f"[ERRO] {text}")

    def _on_serial_timeout(self, elapsed: float):
        self._set_serial_status("timeout")
        self._append_terminal(
            "[UI] Timeout detectado. Reconexão automática desativada."
        )

    def _on_micro_recovered(self):
        # Mantido apenas por compatibilidade com versões antigas do handler.
        self._set_serial_status("sim" if self.simulation_started else "connected")

    # ---------- Simulação ----------

    def _start_simulation(self):
        if not self.serial_handler or not self.connected_ok:
            QMessageBox.warning(
                self, "Simulação", "Conecte na serial antes de iniciar."
            )
            return

        if not self.simulation:
            QMessageBox.warning(
                self, "Simulação", "Carregue um CSV de simulação antes de iniciar."
            )
            return

        self._reset_plot_data()
        self.simulation_started = False
        self.paused_by_timeout = False
        # T0_micro é capturado ao clicar em iniciar se já existir um T válido.
        # Caso contrário, o primeiro T válido recebido após STARTED vira o T0_micro.
        self.t0_micro = (
            self.last_micro_time_raw
            if self._is_valid_number(self.last_micro_time_raw)
            else None
        )
        self.serial_handler.request_start_simulation()
        self._blink_button(self.btn_start, "start_flash", "start_idle", pulses=4)
        self._set_status("Solicitando STARTED...", "#d4a017")
        self._update_buttons()

    def _on_micro_simulation_started(self):
        # Essa função também é chamada em recuperação. Só reinicia o tempo no primeiro STARTED.
        if not self.simulation_started:
            self.simulation_started = True
            self.sim_start_mono = time.monotonic()
            self.last_send_mono = 0.0
            self._open_log_if_needed()
            self._append_terminal("[UI] STARTED recebido. Envio de pressão liberado.")
            self._blink_button(self.btn_start, "start_flash", "start_active", pulses=6)
        self.paused_by_timeout = False
        self._set_serial_status("sim")
        self._update_buttons()

    def _stop_simulation(self):
        self.simulation_started = False
        self.paused_by_timeout = False

        if self.serial_handler:
            self.serial_handler.stop_simulation_mode()

        self._close_log_file()
        self._set_status("Simulação encerrada", "#666")
        self._blink_button(self.btn_stop, "stop_flash", "stop_idle", pulses=5)
        self._set_serial_status("connected" if self.connected_ok else "idle")
        self._update_buttons()

    def _simulation_tick(self):
        if not self.simulation_started or not self.simulation:
            return

        if self.paused_by_timeout:
            return

        now = time.monotonic()
        elapsed_s = now - self.sim_start_mono

        if elapsed_s > self.simulation.duration_s:
            self._append_terminal("[SIM] Fim do arquivo de simulação.")
            self._stop_simulation()
            return

        send_interval = float(self.cfg.get("send_interval_s", 0.1))
        if self.last_send_mono > 0.0 and (now - self.last_send_mono) < send_interval:
            return

        self.last_send_mono = now
        sample = self.simulation.sample_at(elapsed_s)

        self.last_pressure_pa = sample.pressure_pa
        self.last_sim_altitude = sample.altitude_m

        if self.serial_handler:
            self.serial_handler.send_pressure(sample.pressure_pa)

        self.x_sim.append(elapsed_s)
        self.y_sim.append(sample.altitude_m)
        self.curve_sim.setData(self.x_sim, self.y_sim)

        self.lbl_pressure.setText(f"{sample.pressure_pa:.2f} Pa")
        self.lbl_alt_sim.setText(f"{sample.altitude_m:.2f} m")
        self._update_delta_label()
        self._write_log_row(elapsed_s)

    def _reset_plot_data(self):
        self.x_sim.clear()
        self.y_sim.clear()
        self.x_micro.clear()
        self.y_micro.clear()
        self.event_points.clear()
        self.detected_events.clear()
        self.curve_sim.setData([], [])
        self.curve_micro.setData([], [])
        self.scatter_events.setData([])

        for event_box in [
            self.lbl_apogee,
            self.lbl_drogue_n,
            self.lbl_drogue_b,
            self.lbl_main_n,
            self.lbl_main_b,
        ]:
            event_box.setText("--")
            if hasattr(event_box, "set_state"):
                event_box.set_state("idle")

    # ---------- Recepção de pacotes ----------

    def _on_packet_received(self, raw: dict, app: dict, line: str):
        self._hz_counter += 1
        total_fields = len(app)
        valid_fields = sum(1 for v in app.values() if self._is_valid_number(v))
        self.lbl_serial_packets.setText(f"{valid_fields}/{total_fields}")
        self._set_serial_status("ok" if valid_fields == total_fields else "bad")

        micro_alt = app.get("altitude", float("nan"))
        micro_time = app.get("tempo", float("nan"))

        micro_time_rel = float("nan")
        if self._is_valid_number(micro_time):
            self.last_micro_time_raw = micro_time
            if self.simulation_started and self.t0_micro is None:
                self.t0_micro = micro_time
                self._append_terminal(
                    f"[UI] T0_micro definido pelo primeiro T válido após STARTED: {self.t0_micro:.2f}s"
                )
            if self.t0_micro is not None:
                micro_time_rel = micro_time - self.t0_micro

        if self._is_valid_number(micro_alt):
            self.last_micro_altitude = micro_alt
            x = (
                micro_time_rel
                if self._is_valid_number(micro_time_rel)
                else self._current_elapsed_s()
            )
            self.x_micro.append(x)
            self.y_micro.append(micro_alt)
            self.curve_micro.setData(self.x_micro, self.y_micro)
            self.lbl_alt_micro.setText(f"{micro_alt:.2f} m")

        if self._is_valid_number(micro_time):
            if self._is_valid_number(micro_time_rel):
                self.lbl_packet_time.setText(f"{micro_time_rel:.2f} s")
            else:
                self.lbl_packet_time.setText(f"{micro_time:.2f} s")

        self._update_delta_label()
        self._check_parachute_events(app)

    def _check_parachute_events(self, app: dict):
        phase_names = {
            0: "Boot",
            1: "Pre initialization",
            2: "Boost",
            3: "Coast",
            4: "1st event",
            5: "2nd event",
            6: "Landed",
        }

        phase = app.get("phase", float("nan"))
        if self._is_valid_number(phase):
            phase_i = int(phase)
            self.lbl_phase.setText(f"{phase_i} - {phase_names.get(phase_i, 'Unknown')}")
            self.lbl_phase.set_state("ok" if phase_i in phase_names else "warn")

        event_map = {
            "apogeu_h": ("Apogeu", self.lbl_apogee),
            "pqd_dn": ("Drogue nominal", self.lbl_drogue_n),
            "pqd_db": ("Drogue backup", self.lbl_drogue_b),
            "pqd_mn": ("Main nominal", self.lbl_main_n),
            "pqd_mb": ("Main backup", self.lbl_main_b),
        }

        for key, (name, label) in event_map.items():
            value = app.get(key, float("nan"))
            if not self._is_valid_number(value):
                continue

            # Considera evento detectado quando sai de 0 e fica positivo.
            # Se seu firmware mandar -1 antes do evento, essa lógica também funciona.
            if value <= 0.0 or key in self.detected_events:
                continue

            self.detected_events.add(key)
            x = self.x_micro[-1] if self.x_micro else self._current_elapsed_s()
            y = (
                self.last_micro_altitude
                if self._is_valid_number(self.last_micro_altitude)
                else self.last_sim_altitude
            )

            self.event_points.append({"pos": (x, y), "data": name})
            self.scatter_events.setData(self.event_points)
            label.setText(f"{value:.2f} m @ {x:.2f}s")
            if hasattr(label, "set_state"):
                label.set_state("ok")
            self._append_terminal(f"[EVENTO] {name}: {value:.2f} m em t={x:.2f}s")

    def _update_delta_label(self):
        if self._is_valid_number(self.last_micro_altitude) and self._is_valid_number(
            self.last_sim_altitude
        ):
            delta = self.last_micro_altitude - self.last_sim_altitude
            self.lbl_delta.setText(f"{delta:.2f} m")
            if hasattr(self.lbl_delta, "set_state"):
                self.lbl_delta.set_state("ok" if abs(delta) < 20.0 else "warn")
        else:
            self.lbl_delta.setText("-- m")
            if hasattr(self.lbl_delta, "set_state"):
                self.lbl_delta.set_state("idle")

    def _current_elapsed_s(self) -> float:
        if self.sim_start_mono <= 0.0:
            return 0.0
        return time.monotonic() - self.sim_start_mono

    @staticmethod
    def _is_valid_number(value) -> bool:
        try:
            return math.isfinite(float(value))
        except Exception:
            return False

    def _reset_page(self):
        self.simulation_started = False
        self.paused_by_timeout = False
        self.sim_start_mono = 0.0
        self.last_send_mono = 0.0
        self.last_micro_altitude = float("nan")
        self.last_sim_altitude = float("nan")
        self.last_pressure_pa = float("nan")
        self.last_micro_time_raw = float("nan")
        self.t0_micro = None

        if self.serial_handler:
            self.serial_handler.stop_simulation_mode()

        self._close_log_file()
        self._reset_plot_data()

        self.lbl_pressure.setText("-- Pa")
        self.lbl_alt_sim.setText("-- m")
        self.lbl_alt_micro.setText("-- m")
        self.lbl_delta.setText("-- m")
        self.lbl_delta.set_state("idle")
        self.lbl_packet_time.setText("-- s")
        self.lbl_phase.setText("Boot" if self.connected_ok else "Desconectado")
        self.lbl_phase.set_state("idle")
        self.lbl_serial_packets.setText("0/19")
        self._set_serial_status("connected" if self.connected_ok else "idle")
        self._set_status(
            "Página resetada" if self.connected_ok else "Desconectado", "#666"
        )
        self._update_buttons()

    # ---------- Log opcional ----------

    def _open_log_if_needed(self):
        self._close_log_file()
        output_path = self.cfg.get("output_path", "")
        if not output_path:
            return

        try:
            self.log_file = open(output_path, "w", encoding="utf-8", newline="")
            self.log_file.write("t_sim_s,pressure_pa,alt_sim_m,alt_micro_m,delta_m\n")
        except Exception as e:
            self.log_file = None
            self._append_terminal(f"[LOG] Não foi possível abrir log: {e}")

    def _write_log_row(self, elapsed_s: float):
        if not self.log_file:
            return

        alt_micro = self.last_micro_altitude
        delta = (
            alt_micro - self.last_sim_altitude
            if self._is_valid_number(alt_micro)
            else float("nan")
        )
        self.log_file.write(
            f"{elapsed_s:.4f},{self.last_pressure_pa:.4f},{self.last_sim_altitude:.4f},{alt_micro:.4f},{delta:.4f}\n"
        )
        self.log_file.flush()

    def _close_log_file(self):
        try:
            if self.log_file:
                self.log_file.close()
        except Exception:
            pass
        self.log_file = None

    def closeEvent(self, event):
        self._stop_simulation()
        self._disconnect_serial(silent=True)
        super().closeEvent(event)
