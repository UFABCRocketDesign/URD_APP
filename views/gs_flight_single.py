# views/gs_flight_single.py
from __future__ import annotations
import math
from typing import Optional, Tuple, List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter, QFrame, QLabel,
    QPushButton, QPlainTextEdit, QCheckBox, QGroupBox, QSizePolicy, QMessageBox, QComboBox,
    QStackedLayout, QFileDialog
)

import serial
import serial.tools.list_ports
import pyqtgraph.opengl as gl
import numpy as np
import time

from views.net_manager import NetManager
from views.config_dialog import ConfigDialog
from views.map_widget import MapWidget
from views.rocket_3d import Rocket3DView
from views.logger import Logger




# --- Gráfico ---
import pyqtgraph as pg


class GSFlightSinglePage(QWidget):
   
    def __init__(self, net: NetManager, parent=None):
        super().__init__(parent)
        self.net = net
        self.has_web = self.net.get_status()
        self.is_satellite = False

        
        self._build_ui()
        self._reset_state()

        self.ser = None   # objeto serial
        self.timer_serial = QTimer(self)
        self.timer_serial.timeout.connect(self._read_serial)
        self.connected_ok = False


        self.logger = None 
        QTimer.singleShot(100, self.ask_logger)  # espera 100ms e chama

        # Se quiser simular dados, descomente:
        # self._sim = QTimer(self)
        # self._sim.timeout.connect(self._feed_fake)
        # self._sim.start(200)

    # ------------------ UI ------------------
    def _build_ui(self):
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
        self.map = MapWidget(offline=not self.has_web, satellite= self.is_satellite)
        self.map.setMinimumSize(300, 200)   # opcional, garante espaço mínimo
        left_lay.addWidget(self.map, stretch=1)


        # --- botoes compactos ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)  # espaço pequeno entre botões

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

        self.btn_clear = QPushButton("Limpar")
        self.btn_clear.setMaximumHeight(24)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # cria botão
        self.btn_toggle_map = QPushButton("Trocar Mapa")
        self.btn_toggle_map.setMaximumHeight(24)

        self.btn_cfg = QPushButton("Configurações")
        self.btn_cfg.setMaximumHeight(24)

        # adicionar todos os botões na linha
        btn_row.addWidget(self.chk_autoscroll)
        btn_row.addWidget(QLabel("Porta:"))
        btn_row.addWidget(self.combo_ports)
        btn_row.addWidget(self.btn_connect)
        btn_row.addWidget(self.btn_disconnect)
        btn_row.addWidget(self.btn_clear)
        btn_row.addWidget(spacer)  # espaço invisível
        btn_row.addWidget(self.btn_toggle_map)
        btn_row.addWidget(self.btn_cfg)

        left_lay.addLayout(btn_row)

        

        # --- terminal ---
        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setMinimumSize(300, 200)  # mesmo mínimo do mapa
        self.terminal.setStyleSheet(
            "background: #0f0f0f; color: #dcdcdc; font-family: Consolas, monospace;"
        )

        # --- header ---
        self.lbl_header = QLabel("Tempo (s)\tLatitude  \tLongitude \tAltura (m)\tP1/TP1 \tP2/TP2 \tP3/TP3 \tP4/TP4")
        self.lbl_header.setStyleSheet("font-weight: bold; color: #bbb; font-size: 11px;")

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
        self.btn_toggle_map.clicked.connect(self.toggle_map)

        # ===== DIREITA =====
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(4, 4, 4, 4)
        splitter.addWidget(right)
        splitter.setSizes([800, 600])

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
        bottom_row = QHBoxLayout()

        pq_group = QGroupBox("Paraquedas")
        pq_lay = QGridLayout(pq_group)
        self.pq_boxes = []
        self.pq_time_labels = []
        for i in range(4):
            box = QFrame()
            box.setFrameShape(QFrame.StyledPanel)
            box.setStyleSheet("background: white; border: 1px solid #ccc; border-radius: 8px;")
            box.setMinimumSize(28, 28)
            time_lbl = QLabel("t=0.00 s")
            time_lbl.setStyleSheet("font-weight: 500;")
            self.pq_boxes.append(box)
            self.pq_time_labels.append(time_lbl)

            pq_lay.addWidget(QLabel(f"P{i+1}"), i, 0)
            pq_lay.addWidget(box, i, 1)
            pq_lay.addWidget(time_lbl, i, 2)

        info_group = QGroupBox("Infos")
        info_lay = QGridLayout(info_group)
        self.lbl_alt_max = QLabel("—")
        self.lbl_vel = QLabel("—")
        self.lbl_lat = QLabel("—")
        self.lbl_lon = QLabel("—")
        self.lbl_dist = QLabel("—")
        info_lay.addWidget(QLabel("Altura Máx (m):"), 0, 0)
        info_lay.addWidget(self.lbl_alt_max, 0, 1)
        info_lay.addWidget(QLabel("Velocidade (m/s):"), 1, 0)
        info_lay.addWidget(self.lbl_vel, 1, 1)
        info_lay.addWidget(QLabel("Latitude:"), 2, 0)
        info_lay.addWidget(self.lbl_lat, 2, 1)
        info_lay.addWidget(QLabel("Longitude:"), 3, 0)
        info_lay.addWidget(self.lbl_lon, 3, 1)
        info_lay.addWidget(QLabel("Distância à Base (m):"), 4, 0)
        info_lay.addWidget(self.lbl_dist, 4, 1)

        pq_group.setMaximumHeight(150)
        info_group.setMaximumHeight(150)

        bottom_row.addWidget(pq_group, stretch=1)
        bottom_row.addWidget(info_group, stretch=1)

        right_lay.addLayout(bottom_row)


    def toggle_map(self):
        if self.is_satellite:
            self.is_satellite = False
            self.btn_toggle_map.setText("Mapa Normal")
            self.map.toggle_map(False)
        else:
            self.is_satellite = True
            self.btn_toggle_map.setText("Mapa Satélite")
            self.map.toggle_map(True)


    
    def set_orientation(self, qw: float, qx: float, qy: float, qz: float):
        """Atualiza a orientação do foguete no 3D (online/offline)."""
        self.rocket3d.set_orientation(qw, qx, qy, qz)


    # ------------------ Estado ------------------
    def _reset_state(self):
        self.t_last: Optional[float] = None
        self.alt_last: Optional[float] = None
        self.alt_max: float = float("-inf")
        self.series_t: List[float] = []
        self.series_alt: List[float] = []
        self.last_latlon: Optional[Tuple[float, float]] = None
        self.base_latlon: Optional[Tuple[float, float]] = None  # para distância
        # reset paraquedas
        for i in range(4):
            self._set_pq(i, activated=False, t=0.0)

    # ------------------ API pública ------------------
    def feed_line(self, line: str):
        parsed = self._parse_packet(line)
        if not parsed:
            self.terminal.appendPlainText("-")
            return

        t, lat, lon, alt, pqs, qw, qx, qy, qz = parsed

       # salva quaternions internamente normalizados
        norm = (qw**2 + qx**2 + qy**2 + qz**2) ** 0.5
        if norm == 0:  # proteção contra divisão por zero
            norm = 1.0

        self.qw = qw / norm
        self.qx = qx / norm
        self.qy = qy / norm
        self.qz = qz / norm

        if self.logger:
            self.logger.save_line(t, lat, lon, alt, pqs)

        # monta linha de dados
        row = f"{t:.2f}\t{lat:.6f}\t{lon:.6f}\t{alt:.2f}\t"
        for (h, tp) in pqs:
            row += f"{int(h)} {tp:.2f}\t"   # apenas um espaço entre PQD e TPQD

        self.terminal.appendPlainText(row)

        if self.chk_autoscroll.isChecked():
            self.terminal.verticalScrollBar().setValue(
                self.terminal.verticalScrollBar().maximum()
            )

        # atualiza paraquedas na UI (blocos verdes/brancos + tempo)
        for idx, (h, tp) in enumerate(pqs):
            self._set_pq(idx, activated=(tp > 0.0), t=tp)

        # Atualiza mapa (online ou offline)
        if lat is not None and lon is not None:
            self.last_latlon = (lat, lon)
            self.map.add_point(lat, lon)
            self.lbl_lat.setText(f"{lat:.6f}")
            self.lbl_lon.setText(f"{lon:.6f}")
            self._update_distance()


        # Atualiza 3D
        norm = math.sqrt(qw*qw + qx*qx + qy*qy + qz*qz)
        if norm > 1e-8:
            qw, qx, qy, qz = qw/norm, qx/norm, qy/norm, qz/norm
        self.rocket3d.set_orientation(qw, qx, qy, qz)

        # Altitude + gráfico
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

    def set_parachute_state(self, idx: int, activated: bool, t_s: float):
        """Define estado e tempo de disparo de um paraquedas."""
        self._set_pq(idx, activated=activated, t=t_s)

    def set_home_location(self, lat: float, lon: float):
        self.base_latlon = (lat, lon)
        self._update_distance()
        if self.has_web:
            self.map.set_base(lat, lon)




    # ------------------ Helpers ------------------
    def _set_pq(self, idx: int, activated: bool, t: float):
        if not (0 <= idx < 4):
            return
        box = self.pq_boxes[idx]
        time_lbl = self.pq_time_labels[idx]
        if activated:
            box.setStyleSheet("background: #c8f7c5; border: 1px solid #4caf50; border-radius: 8px;")
        else:
            box.setStyleSheet("background: white; border: 1px solid #ccc; border-radius: 8px;")
        time_lbl.setText(f"t={t:.2f} s")

    def _parse_packet(self, line: str):
        """
        Espera formato TSV:
        t, lat, lon, alt,
        p1, tp1, p2, tp2, p3, tp3, p4, tp4,
        qw, qx, qy, qz
        """
        parts = line.strip().split("\t")
        if len(parts) < 15:   # mínimo esperado
            return None

        try:
            t   = float(parts[0])
            lat = float(parts[1])
            lon = float(parts[2])
            alt = float(parts[3])

            # paraquedas: lista [(p1,tp1), (p2,tp2), ...]
            pqs = []
            for i in range(4):
                h  = float(parts[4 + i*2])
                tp = float(parts[5 + i*2])
                pqs.append((h, tp))

            # quaternions
            qw, qx, qy, qz = map(float, parts[12:16])

        except Exception:
            return None

        return (t, lat, lon, alt, pqs, qw, qx, qy, qz)


    def _open_config_dialog(self):
        dlg = ConfigDialog(self, parent=self)
        dlg.exec()

    def _update_distance(self):
        if self.base_latlon and self.last_latlon:
            dist_m = _haversine_m(self.base_latlon, self.last_latlon)
            self.lbl_dist.setText(f"{dist_m:.1f}")
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
        if self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if not line:
                    return

                # Se ainda não recebeu OK, só verifica isso
                if not self.connected_ok:
                    if line == "OK":
                        self.connected_ok = True
                        self.btn_connect.setStyleSheet("background:#c8f7c5; font-weight:600;")
                        self._set_status(f"Conectado em {self.ser.port}", "#060")
                    return  # ignora todo resto enquanto não chegou OK

                # Já conectado -> processa telemetria
                self.feed_line(line)
            except Exception as e:
                # Aqui tratamos o caso de desconectar o USB
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Erro", f"A porta {self.ser.port} foi desconectada.\nErro: {e}")
                
                # Reset total
                self._reset_button_styles()
                self._set_status("Desconectado", "#666")
                if self.timer_serial.isActive():
                    self.timer_serial.stop()
                try:
                    if self.ser:
                        self.ser.close()
                except:
                    pass
                self.ser = None
                self._reset_state()
                self.connected_ok = False

    def _clear_terminal(self):
        """Limpa o terminal e, se não houver conexão ativa, reseta o status."""
        self.terminal.clear()

        # Se não tem porta aberta ou ainda não recebeu OK → status = desconectado
        if not self.ser or not self.ser.is_open or not self.connected_ok:
            self._set_status("Desconectado", "#666")

    def refresh_ports(self):
        """Atualiza a lista de portas COM disponíveis (ignora Bluetooth/virtuais)."""
        import serial.tools.list_ports
        self.combo_ports.clear()

        for port in serial.tools.list_ports.comports():
            desc = port.description.lower()
            if "bluetooth" in desc:
                continue   # ignora portas BT
            if port.device in ["COM3", "COM4"]:
                continue   # ignora as padrão que travam
            self.combo_ports.addItem(port.device)

        # se não achar nenhuma porta
        if self.combo_ports.count() == 0:
            self.combo_ports.addItem("")  # placeholder vazio

    def connect_serial(self):
        """Conecta na porta COM escolhida, envia READY e aguarda resposta."""
        port = self.combo_ports.currentText().strip()
        if not port:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Erro", "Nenhuma porta selecionada")
            self._reset_button_styles()
            self._set_status("Nenhuma porta selecionada", "#b00")
            return

        try:
            # tenta abrir porta

            if self.connected_ok:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Conexão", f"Já está conectado em {self.ser.port}")
                return

            self.ser = serial.Serial(port, 115200, timeout=0.2)
            self.timer_serial.start(50)  # leitura periódica (20 Hz)

            # envia READY e espera resposta
            self.ser.write(b"RST\n")
            time.sleep(1)  
            self.ser.write(b"READY\n")

            self.connected_ok = False     # aguardando resposta
            self._set_status(f"Aguardando OK em {port}...", "#d4a017")  # amarelo
            if self.logger:
                self.logger.write_header(["t", "lat", "lon", "alt","p1", "tp1","p2", "tp2","p3", "tp3","p4", "tp4"])


        except serial.SerialException as e:
            from PySide6.QtWidgets import QMessageBox
            self._set_status("Erro: Falha ao abrir a porta", "#b00") # vermelho
            QMessageBox.warning(self, "Erro", f"Falha ao abrir a porta {port}:\n{e}")
            self._reset_button_styles()
        except PermissionError:
            from PySide6.QtWidgets import QMessageBox
            self._set_status("Erro: Acesso negado", "#b00") # vermelho
            QMessageBox.warning(self, "Erro", f"Acesso negado à porta {port}. "
                                            "Feche outros programas que estejam usando essa COM.")
            self._reset_button_styles()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            self._set_status("Erro: Erro inesperado", "#b00") # vermelho
            QMessageBox.warning(self, "Erro", f"Erro inesperado:\n{e}")
            self._reset_button_styles()

    def disconnect_serial(self):
        """Desconecta, envia RST e pisca vermelho."""
        if self.ser and self.ser.is_open:
            try:
                self._set_status("Desconectado", "#666")        # cinza neutro
                self.ser.write(b"RST\n")  # pede reset no ESP
                self.timer_serial.stop()
                self.ser.close()
                self.ser = None
                self.connected_ok = False

                # pisca vermelho
                self.btn_disconnect.setStyleSheet("background:#f8d7da; font-weight:600;")
                QTimer.singleShot(500, self._reset_button_styles)

            except Exception as e:
                self._set_status("Erro: Falha ao desconectar", "#b00") # vermelho
                QMessageBox.warning(self, "Erro", f"Falha ao desconectar:\n{e}")
                self._reset_button_styles()
        else:
            QMessageBox.information(self, "Serial", "Nenhuma porta estava conectada")
            self._reset_button_styles()

    def _reset_button_styles(self):
        """Reseta as cores de Connect/Disconnect para neutro."""
        self.btn_connect.setStyleSheet("")
        self.btn_disconnect.setStyleSheet("")
    
    def _set_status(self, msg: str, color: str = "#666"):
        """Atualiza a barra de status com texto e cor."""
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"color:{color}; font-weight:500; padding:4px; border-top:1px solid #ccc;")

    # Net

    def onNetChanged(self, status: bool):
        """
        Chamado pelo MainWindow (via NetManager) quando a conexão mudar ou for forçada.
        Alterna entre online (WebEngine) e offline (QLabel/Rocket3DWin) usando QStackedLayout.
        """
        self.has_web = status

        # ---- MAPA ----
        self.map.set_offline(not status)



    
    # -------- Controle de execução --------
    def pause(self):
        # mapa
        if self.has_web and hasattr(self, "map"):
            self.map.page().runJavaScript("if(window.pauseRender) pauseRender();")

        # 3D
        if hasattr(self, "rocket3d"):
            self.rocket3d.pause()

    def resume(self):
        # mapa
        if self.has_web and hasattr(self, "map"):
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


