from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel,
    QGridLayout, QGroupBox, QCheckBox, QMessageBox, QHBoxLayout
)
from PySide6.QtCore import Qt

import pyqtgraph as pg
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os


class DataAnalysisPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.main_layout = QVBoxLayout(self)

        self.page_choice = None
        self.page_flight = None
        self.page_te = None

        self.show_choice_page()

    # ---------------- Menu inicial ----------------
    def show_choice_page(self):
        self.clear_layout(self.main_layout)
        self.page_choice = QWidget()
        lay = QVBoxLayout(self.page_choice)

        # --- Bloco Voo ---
        flight_block = QWidget()
        flight_layout = QVBoxLayout(flight_block)
        flight_layout.setContentsMargins(0, 0, 0, 0)
        flight_layout.setSpacing(2)

        btn_flight = QPushButton("Análise de Voo")
        btn_flight.setMinimumHeight(60)
        flight_layout.addWidget(btn_flight)

        lbl_flight = QLabel(
            "Formato esperado: tempo_s, temp_C, pressao_Pa, alt_m, "
            "wuf, descendo, altApogee_m, tApogee_s, altMax_m, "
            "tdht_C, umidade_%, "
            "accX_g, accY_g, accZ_g, "
            "gyroX_dps, gyroY_dps, gyroZ_dps, "
            "magX_uT, magY_uT, magZ_uT, \n"
            "p1_data, p1_info, p2_data, p2_info, "
            "p3_data, p3_info, p4_data, p4_info, "
            "lat_deg, lon_deg, alt_gps_m, vel_kmph"
        )

        lbl_flight.setStyleSheet("font-size: 9pt; color: gray;")
        lbl_flight.setMaximumHeight(30)
        flight_layout.addWidget(lbl_flight)

        flight_block.setMaximumHeight(100)  
        lay.addWidget(flight_block)

        # --- Bloco TE ---
        te_block = QWidget()
        te_layout = QVBoxLayout(te_block)
        te_layout.setContentsMargins(0, 0, 0, 0)
        te_layout.setSpacing(2)

        btn_te = QPushButton("Análise de Teste Estático")
        btn_te.setMinimumHeight(60)
        te_layout.addWidget(btn_te)

        lbl_te = QLabel("Formato esperado: tempo, raw.cell, raw.Kgf, avg.cell, avg.Kgf, avg.N, raw.tdt, V.tdt, psi.tdt, pascal.tdt, atm.tdt, bar.tdt, encoder.RPM")
        lbl_te.setStyleSheet("font-size: 9pt; color: gray;")
        lbl_te.setMaximumHeight(20)
        te_layout.addWidget(lbl_te)

        te_block.setMaximumHeight(90)
        lay.addWidget(te_block)

        # Conectar
        btn_flight.clicked.connect(self.show_flight_page)
        btn_te.clicked.connect(self.show_te_page)

        self.main_layout.addWidget(self.page_choice)



    # ---------------- Flight Analysis ----------------
    def show_flight_page(self):
        self.clear_layout(self.main_layout)
        self.page_flight = FlightAnalysisPage()
        btn_back = QPushButton("← Voltar")
        btn_back.clicked.connect(self.show_choice_page)
        self.main_layout.addWidget(btn_back)
        self.main_layout.addWidget(self.page_flight)

    # ---------------- TE Analysis ----------------
    def show_te_page(self):
        self.clear_layout(self.main_layout)
        self.page_te = StaticAnalysisPage()
        btn_back = QPushButton("← Voltar")
        btn_back.clicked.connect(self.show_choice_page)
        self.main_layout.addWidget(btn_back)
        self.main_layout.addWidget(self.page_te)

    # ---------------- Utils ----------------
    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()


# ---------------- Flight Analysis Sub-Page ----------------
class FlightAnalysisPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Botão abrir arquivo
        self.btn_open = QPushButton("Abrir arquivo de voo (.txt)")
        self.btn_open.clicked.connect(self.load_file)
        root.addWidget(self.btn_open)

        # Resumo em grid de caixas
        self.data_box = QGroupBox("Resumo do Voo")
        self.grid = QGridLayout(self.data_box)
        root.addWidget(self.data_box)

        # Área principal com gráfico + checkboxes
        area = QHBoxLayout()
        root.addLayout(area)

        # Gráfico
        self.plot = pg.PlotWidget(title="Análise de Dados de Voo")
        self.plot.addLegend()
        self.plot.showGrid(x=True, y=True)
        area.addWidget(self.plot, stretch=4)

        # Checkboxes pequenas na lateral
        side = QVBoxLayout()
        area.addLayout(side, stretch=1)
        self.chk_alt = QCheckBox("Alt")
        self.chk_vel = QCheckBox("Vel")
        self.chk_acc = QCheckBox("Acc")
        self.chk_gyro = QCheckBox("Gyro")
        for chk in [self.chk_alt, self.chk_vel, self.chk_acc, self.chk_gyro]:
            chk.setChecked(True)
            chk.setMaximumWidth(60)
            chk.stateChanged.connect(self.update_plot)
            side.addWidget(chk)
        side.addStretch(1)

        # Botão exportar gráficos
        self.btn_export = QPushButton("Exportar Gráficos")
        self.btn_export.clicked.connect(self.export_plots)
        root.addWidget(self.btn_export)

        # Crosshair interativo
        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.plot.addItem(self.vLine, ignoreBounds=True)
        self.plot.addItem(self.hLine, ignoreBounds=True)
        self.plot.scene().sigMouseMoved.connect(self._mouseMoved)

        self.label_hover = QLabel("Cursor: -")
        root.addWidget(self.label_hover)

        self.curves = {}

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir Arquivo", "", "Text Files (*.txt)")
        if not path:
            return
        try:
            self.df = pd.read_csv(path, sep="\t")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao ler arquivo:\n{e}")
            return
        self.analyze_data(path)

    def analyze_data(self, path):
        df = self.df
        t = df["tempo_s"]

        # velocidade em m/s
        vel_ms = df["vel_kmph"] / 3.6 if "vel_kmph" in df else np.zeros(len(df))
        acc_mag = np.sqrt(df["accX_g"]**2 + df["accY_g"]**2 + df["accZ_g"]**2) if all(c in df for c in ["accX_g","accY_g","accZ_g"]) else np.zeros(len(df))

        # Mach corrigido pela temperatura
        if "temp_C" in df:
            T = df["temp_C"] + 273.15
            a = np.sqrt(1.4 * 287 * T)
            mach = vel_ms / a
        else:
            mach = vel_ms / 343.0

        # apogeu e tempos
        alt = df["alt_m"] if "alt_m" in df else np.zeros(len(df))
        alt_max = alt.max()
        t_apogee = t[alt.idxmax()]

        # detectar início (15 m acima do mínimo)
        t_start_idx = np.argmax(alt > (alt.min() + 15))
        t_start = t.iloc[t_start_idx]
        t0 = max(0, t_start - 10)

        # detectar pouso
        t_end_idx = np.argmax((t > t_start) & (vel_ms < 1) & (alt < 5))
        if t_end_idx == 0: t_end_idx = len(df)-1
        t_end = t.iloc[t_end_idx]
        tf = t_end + 10
        t_flight = t_end - t_start

        # tempo de queima = até aceleração cair próximo de 1g
        burn_end_idx = np.argmax((t > t_start) & (acc_mag < 0.2))
        if burn_end_idx == 0: burn_end_idx = alt.idxmax()
        burn_time = t.iloc[burn_end_idx] - t_start
        coast_time = t_apogee - t.iloc[burn_end_idx]

        # velocidades drogue e main
        vel_drogue = vel_main = 0
        desc_drogue = desc_main = 0
        if "p1_data" in df and "p3_data" in df:
            try:
                idx_p1 = df.index[df["p1_data"] == 1][0]
                idx_p3 = df.index[df["p3_data"] == 1][0]
                vel_drogue = vel_ms.iloc[idx_p1:idx_p3].mean()
                vel_main = vel_ms.iloc[idx_p3:t_end_idx].mean()
                desc_drogue = t.iloc[idx_p3] - t.iloc[idx_p1]
                desc_main = t_end - t.iloc[idx_p3]
            except: pass

        # preencher resumo em caixas
        self.clear_layout(self.grid)
        stats = {
            "Apogeu (m)": alt_max,
            "Mach Máx": mach.max(),
            "Vel Máx (m/s)": vel_ms.max(),
            "Acel Máx (g)": acc_mag.max(),
            "Tempo Voo (s)": t_flight,
            "Tempo Queima (s)": burn_time,
            "Coast (s)": coast_time,
            "Descida Drogue (s)": desc_drogue,
            "Descida Main (s)": desc_main,
        }
        row=0
        for k,v in stats.items():
            box = QGroupBox(k)
            lay = QVBoxLayout(box)
            lay.addWidget(QLabel(f"{v:.2f}"))
            self.grid.addWidget(box,row//3,row%3)
            row+=1

        # plota gráfico
        self.plot.clear()
        self.curves={}
        self.curves["alt"] = self.plot.plot(t,alt,pen="b",name="Altitude") if "alt_m" in df else None
        self.curves["vel"] = self.plot.plot(t,vel_ms,pen="g",name="Velocidade") if "vel_kmph" in df else None
        self.curves["acc"] = self.plot.plot(t,acc_mag,pen="r",name="Aceleração") if "accX_g" in df else None

    def export_plots(self):
        out_dir = QFileDialog.getExistingDirectory(self,"Escolher pasta")
        if not out_dir: return
        exporter = pg.exporters.ImageExporter(self.plot.plotItem)
        exporter.export(os.path.join(out_dir,"flight_plot.png"))

    def update_plot(self):
        if "alt" in self.curves and self.curves["alt"]: self.curves["alt"].setVisible(self.chk_alt.isChecked())
        if "vel" in self.curves and self.curves["vel"]: self.curves["vel"].setVisible(self.chk_vel.isChecked())
        if "acc" in self.curves and self.curves["acc"]: self.curves["acc"].setVisible(self.chk_acc.isChecked())

    def _mouseMoved(self, evt):
        pos = evt
        if self.plot.sceneBoundingRect().contains(pos):
            mousePoint = self.plot.plotItem.vb.mapSceneToView(pos)
            self.vLine.setPos(mousePoint.x())
            self.hLine.setPos(mousePoint.y())
            self.label_hover.setText(f"Cursor: t={mousePoint.x():.2f}s, y={mousePoint.y():.2f}")

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

class StaticAnalysisPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Botão abrir arquivo
        self.btn_open = QPushButton("Abrir arquivo de teste estático (.txt)")
        self.btn_open.clicked.connect(self.load_file)
        root.addWidget(self.btn_open)

        # Resumo
        self.data_box = QGroupBox("Resumo do Teste Estático")
        self.grid = QGridLayout(self.data_box)
        root.addWidget(self.data_box)

        # Área principal com gráfico + checkboxes
        area = QHBoxLayout()
        root.addLayout(area)

        # Gráfico com dois eixos Y
        self.plot = pg.PlotWidget(title="Empuxo e Pressão")
        self.plot.showGrid(x=True, y=True)
        area.addWidget(self.plot, stretch=4)

        # Checkboxes
        side = QVBoxLayout()
        area.addLayout(side, stretch=1)
        self.chk_thrust = QCheckBox("Empuxo")
        self.chk_press = QCheckBox("Pressão")
        for chk in [self.chk_thrust, self.chk_press]:
            chk.setChecked(True)
            chk.setMaximumWidth(80)
            chk.stateChanged.connect(self.update_plot)
            side.addWidget(chk)
        side.addStretch(1)

        # Crosshair
        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.plot.addItem(self.vLine, ignoreBounds=True)
        self.plot.addItem(self.hLine, ignoreBounds=True)
        self.plot.scene().sigMouseMoved.connect(self._mouseMoved)

        self.label_hover = QLabel("Cursor: -")
        root.addWidget(self.label_hover)

        self.curves = {}
        self.unit_thrust = "kgf"
        self.unit_press = "psi"

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir Arquivo", "", "Text Files (*.txt)")
        if not path:
            return
        try:
            self.df = pd.read_csv(path, sep="\t")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao ler arquivo:\n{e}")
            return
        self.analyze_data()

    def analyze_data(self):
        df = self.df
        t = df["tempo"] if "tempo" in df else np.arange(len(df))

        # escolhe empuxo
        thrust = None
        if "avg.Kgf" in df:
            thrust = df["avg.Kgf"]
            self.unit_thrust = "kgf"
        elif "avg.N" in df:
            thrust = df["avg.N"]
            self.unit_thrust = "N"

        # escolhe pressão
        press = None
        for col, unit in [("psi.tdt","psi"),("pascal.tdt","Pa"),("atm.tdt","atm"),("bar.tdt","bar")]:
            if col in df:
                press = df[col]
                self.unit_press = unit
                break

        # métricas
        max_thrust = thrust.max() if thrust is not None else 0
        max_press = press.max() if press is not None else 0
        t_total = t.iloc[-1] - t.iloc[0]

        # tempo de queima = até o empuxo cair < 10% do máximo
        burn_time = 0
        if thrust is not None:
            peak = thrust.max()
            idx_end = np.argmax(thrust < 0.1*peak)
            burn_time = t.iloc[idx_end] - t.iloc[0] if idx_end > 0 else t_total

        # preencher resumo
        self.clear_layout(self.grid)
        stats = {
            f"Máx. Empuxo ({self.unit_thrust})": max_thrust,
            f"Máx. Pressão ({self.unit_press})": max_press,
            "Tempo Total (s)": t_total,
            "Tempo Queima (s)": burn_time,
        }
        row=0
        for k,v in stats.items():
            box = QGroupBox(k)
            lay = QVBoxLayout(box)
            lay.addWidget(QLabel(f"{v:.2f}"))
            self.grid.addWidget(box,row//2,row%2)
            row+=1

        # plota curvas
        self.plot.clear()
        self.curves = {}
        if thrust is not None:
            self.curves["thrust"] = self.plot.plot(t, thrust, pen="b", name=f"Empuxo ({self.unit_thrust})")
        if press is not None:
            self.curves["press"] = self.plot.plot(t, press, pen="r", name=f"Pressão ({self.unit_press})")

    def update_plot(self):
        if "thrust" in self.curves: self.curves["thrust"].setVisible(self.chk_thrust.isChecked())
        if "press" in self.curves: self.curves["press"].setVisible(self.chk_press.isChecked())

    def _mouseMoved(self, evt):
        pos = evt
        if self.plot.sceneBoundingRect().contains(pos):
            mousePoint = self.plot.plotItem.vb.mapSceneToView(pos)
            self.vLine.setPos(mousePoint.x())
            self.hLine.setPos(mousePoint.y())
            self.label_hover.setText(f"Cursor: t={mousePoint.x():.2f}s, y={mousePoint.y():.2f}")

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
