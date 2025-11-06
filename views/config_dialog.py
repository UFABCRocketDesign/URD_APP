from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
    QDoubleSpinBox, QCheckBox, QHBoxLayout, QMessageBox, QFileDialog
)
from PySide6.QtGui import QDoubleValidator

import time

class ConfigDialog(QDialog):
    def __init__(self, gs_single, test_password: str = "urd123", parent=None):
        super().__init__(parent)
        self.gs_single = gs_single
        self.test_password = test_password
        self._test_unlocked = False

        self.setWindowTitle("Configurações")
        self.resize(420, 600)
        self._build_ui()
        self._load_from_gs()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # --- Modo Teste ---
        box_test = QGroupBox("Modo Teste")
        lay_test = QGridLayout(box_test)

        self.btn_unlock = QPushButton("Entrar no modo teste…")
        self.lbl_status = QLabel("Bloqueado")
        self.lbl_status.setStyleSheet("color:#b00; font-weight:600;")

        # coordenadas e altitude
        self.lat = QDoubleSpinBox(); self.lat.setRange(-90, 90); self.lat.setDecimals(6)
        self.lon = QDoubleSpinBox(); self.lon.setRange(-180, 180); self.lon.setDecimals(6)
        self.alt = QDoubleSpinBox(); self.alt.setRange(-1000, 100000); self.alt.setDecimals(2)

        # paraquedas
        self.pq_enabled = [QCheckBox(f"P{i+1} ativado?") for i in range(4)]
        self.pq_time = [QDoubleSpinBox() for _ in range(4)]
        for sp in self.pq_time:
            sp.setRange(0, 1e6); sp.setDecimals(2)

        lay_test.addWidget(self.btn_unlock, 0, 0, 1, 1)
        lay_test.addWidget(self.lbl_status, 0, 1, 1, 1)
        lay_test.addWidget(QLabel("Latitude"), 1, 0); lay_test.addWidget(self.lat, 1, 1)
        lay_test.addWidget(QLabel("Longitude"), 2, 0); lay_test.addWidget(self.lon, 2, 1)
        lay_test.addWidget(QLabel("Altitude (m)"), 3, 0); lay_test.addWidget(self.alt, 3, 1)

        for i in range(4):
            row = QHBoxLayout()
            row.addWidget(self.pq_enabled[i])
            row.addWidget(QLabel("h (m):"))
            row.addWidget(self.pq_time[i])
            lay_test.addLayout(row, 4+i, 0, 1, 2)

        self.btn_apply = QPushButton("Aplicar no GS Single")
        self.btn_reset = QPushButton("Reinicializar Página")
        self.btn_apply.setEnabled(False)
        self.btn_reset.setEnabled(False)

        row_btns = QHBoxLayout()
        row_btns.addWidget(self.btn_apply)
        row_btns.addWidget(self.btn_reset)
        lay_test.addLayout(row_btns, 8, 0, 1, 2)

        root.addWidget(box_test)

        # --- Base ---
        box_base = QGroupBox("Base (para cálculo de distância, use ',' como separador)")
        lay_base = QGridLayout(box_base)

        # Latitude: -90 a 90, 6 casas decimais
        self.base_lat = QLineEdit()
        lat_validator = QDoubleValidator(-90.0, 90.0, 6)
        lat_validator.setNotation(QDoubleValidator.StandardNotation)
        self.base_lat.setValidator(lat_validator)

        # Longitude: -180 a 180, 6 casas decimais
        self.base_lon = QLineEdit()
        lon_validator = QDoubleValidator(-180.0, 180.0, 6)
        lon_validator.setNotation(QDoubleValidator.StandardNotation)
        self.base_lon.setValidator(lon_validator)

        self.btn_set_base = QPushButton("Definir Base")
        self.btn_use_my_loc = QPushButton("Usar minha localização")

        # Layout
        lay_base.addWidget(QLabel("Lat base"), 0, 0)
        lay_base.addWidget(self.base_lat, 0, 1)
        lay_base.addWidget(QLabel("Lon base"), 1, 0)
        lay_base.addWidget(self.base_lon, 1, 1)
        lay_base.addWidget(self.btn_set_base, 2, 0, 1, 2)
        lay_base.addWidget(self.btn_use_my_loc, 3, 0, 1, 2)

        root.addWidget(box_base)


        # --- Mapas Offline ---
        box_tiles = QGroupBox("Mapas Offline")
        lay_tiles = QGridLayout(box_tiles)

        self.lbl_tiles = QLabel("Nenhuma pasta selecionada")
        self.btn_pick_tiles = QPushButton("Selecionar pasta de tiles…")
        self.btn_pick_tiles.setEnabled(not self.gs_single.net.get_status())
 

        lay_tiles.addWidget(self.lbl_tiles, 0, 0, 1, 1, alignment=Qt.AlignCenter)
        lay_tiles.addWidget(self.btn_pick_tiles, 1, 0, 1, 1, alignment=Qt.AlignCenter)

        root.addWidget(box_tiles)
        root.addStretch(1)

        # sinais
        self.btn_unlock.clicked.connect(self._unlock_test)
        self.btn_apply.clicked.connect(self._apply_to_gs)
        self.btn_set_base.clicked.connect(self._set_base)
        self.btn_reset.clicked.connect(self._reset_stats)
        self.btn_use_my_loc.clicked.connect(self._use_my_location)
        self.btn_pick_tiles.clicked.connect(self._pick_tiles)


    # ---- ações ----
    def _unlock_test(self):
        from PySide6.QtWidgets import QInputDialog
        pwd, ok = QInputDialog.getText(self, "Senha do modo teste", "Digite a senha:", echo=QLineEdit.Password)
        if not ok:
            return
        if pwd == self.test_password:
            self._test_unlocked = True
            self.btn_apply.setEnabled(True)
            self.btn_reset.setEnabled(True)
            self.lbl_status.setText("Desbloqueado")
            self.lbl_status.setStyleSheet("color:#0a0; font-weight:600;")
        else:
            QMessageBox.warning(self, "Senha incorreta", "Senha inválida.")

    def _apply_to_gs(self):
        if not self._test_unlocked:
            return

        self.gs_single.set_position(self.lat.value(), self.lon.value())
        self.gs_single.inject_altitude(self.alt.value())
        self.gs_single.alt_max = self.alt.value()
        self.gs_single.lbl_alt_max.setText(f"{self.alt.value():.2f}")

        # Atualiza manualmente os 4 paraquedas
        self.gs_single._set_pq(0, self.pq_time[0].value() if self.pq_enabled[0].isChecked() else 0.0)
        self.gs_single._set_pq(1, self.pq_time[1].value() if self.pq_enabled[1].isChecked() else 0.0)
        self.gs_single._set_pq(2, self.pq_time[2].value() if self.pq_enabled[2].isChecked() else 0.0)
        self.gs_single._set_pq(3, self.pq_time[3].value() if self.pq_enabled[3].isChecked() else 0.0)

    def _set_base(self):
        lat = float(self.base_lat.text()) if self.base_lat.text() else 0.0
        lon = float(self.base_lon.text()) if self.base_lon.text() else 0.0
        self.gs_single.set_home_location(lat, lon)
        self.gs_single.map.set_base(lat, lon)
        QMessageBox.information(self, "Base definida", f"Base atualizada: {lat:.6f}, {lon:.6f}")

    def _reset_stats(self):
        if not self._test_unlocked:
            return
        self.gs_single._reset_state()
        self.gs_single.terminal.clear()
        self.gs_single.alt_curve.setData([], [])
        self.gs_single.lbl_alt_max.setText("—")
        self.gs_single.lbl_vel.setText("—")
        self.gs_single.lbl_lat.setText("—")
        self.gs_single.lbl_lon.setText("—")
        self.gs_single.last_latlon = (0, 0)
        self.gs_single.lbl_dist.setText("—")

        self.lat.setValue(0)
        self.lon.setValue(0)
        self.alt.setValue(0)
        for i in range(4):
            self.pq_enabled[i].setChecked(False)
            self.pq_time[i].setValue(0)


        # reinicializa mapa e 3D
        self.gs_single.map._init_map()
        if hasattr(self.gs_single, "rocket3d"):
            self.gs_single.rocket3d.reset()


        QMessageBox.information(self, "Reset", "Página reinicializada.")


    def _use_my_location(self):
        # if self.gs_single.connected_ok:
        #     self.gs_single.ser.write(b"GPS_COORDS\n")
        #     self.gs_single.time.sleep(5)
        #     line = self.gs_single.ser.readline().decode(errors="ignore").strip()
        #     if line.startswith("GPS_OK\n"):
        #         try:
        #             line = self.gs_single.ser.readline().decode(errors="ignore").strip()
        #             print(line)
        #             _, lat_str, lon_str = line.split("\t")
        #             lat = float(lat_str)
        #             lon = float(lon_str)
        #             if lat and lon:
        #                 self.base_lat.setText(f"{lat: .6f}")
        #                 self.base_lon.setText(f"{lon: .6f}")
        #                 self.gs_single.set_home_location(lat, lon)
        #                 self.gs_single.map.set_base(lat, lon)
        #                 QMessageBox.information(self, "Localização obtida do GPS", f"Lat: {lat:.6f}, Lon: {lon:.6f}")
        #                 return
        #             else:
        #                 QMessageBox.warning(self, "Erro", f"Coordenadas inválidas ou nulas recebidas do GPS.")
        #                 return

        #         except Exception as e:
        #             QMessageBox.warning(self, "Erro", f"Não foi possível interpretar os dados do GPS: {e}")
        #             return
        #     else:
        try:
            import geocoder, requests
            g = geocoder.ip('me')
            if g.ok and g.latlng:
                lat, lon = g.latlng
            else:
                resp = requests.get("https://ipinfo.io/json").json()
                lat, lon = map(float, resp["loc"].split(","))
            self.base_lat.setText(f"{lat: .6f}")
            self.base_lon.setText(f"{lon: .6f}")
            self.gs_single.set_home_location(lat, lon)
            self.gs_single.map.set_base(lat, lon)
            QMessageBox.information(self, "Localização detectada", f"Lat: {lat:.6f}, Lon: {lon:.6f}")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível obter localização: {e}")

    def _pick_tiles(self):
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta de tiles")
        if folder:
            self.lbl_tiles.setText(folder)
            self.gs_single.map.set_offline(True, folder)

    def _use_online_tiles(self):
        self.gs_single.map.set_offline(False)

    # ---- persistência ----
    def _load_from_gs(self):
        if hasattr(self.gs_single, "last_latlon") and self.gs_single.last_latlon:
            lat, lon = self.gs_single.last_latlon
            self.lat.setValue(lat)
            self.lon.setValue(lon)

        if getattr(self.gs_single, "alt_max", None) not in (None, float("-inf")):
            self.alt.setValue(self.gs_single.alt_max)

        # Novo mapeamento entre índice e caixa de paraquedas
        pq_refs = [
            self.gs_single.pqd_drogueN,
            self.gs_single.pqd_drogueB,
            self.gs_single.pqd_mainN,
            self.gs_single.pqd_mainB,
        ]

        for i, box in enumerate(pq_refs):
            # Detecta se a caixa está verde (ativa)
            active = "background: #b6f5b6" in box.styleSheet()
            self.pq_enabled[i].setChecked(active)

            # Como não há mais label de tempo, define o spin como 0
            self.pq_time[i].setValue(0.0)

