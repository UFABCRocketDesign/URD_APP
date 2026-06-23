from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel,
    QGridLayout, QGroupBox, QCheckBox, QMessageBox, QHBoxLayout,
    QDialog, QFormLayout, QDialogButtonBox, QLineEdit, QInputDialog, QComboBox,
    QListWidget, QDoubleSpinBox, QScrollArea
)
from PySide6.QtGui import (QCursor)

from PySide6.QtCore import Qt

import re
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
        self.page_post_process = None

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

        lbl_te = QLabel(
            "Formato esperado: tempo.s, adc.raw.cell, adc.avg.cell, Kgf.raw.cell, Kgf.avg.cell, N.avg.cell, "
            "adc.raw.tdt, adc.avg.tdt, V.raw.tdt, psi.raw.tdt,  psi.avg.tdt, pa.raw.tdt, atm.raw.tdt, bar.raw.tdt, encoder.RPM "
            "\n(se existirem, também serão usadas as colunas calibradas: "
            "Kgf.calibrado, N.calibrado, psi.calibrado, Pa.calibrado, atm.calibrado, bar.calibrado)."
        )
        lbl_te.setStyleSheet("font-size: 9pt; color: gray;")
        lbl_te.setMaximumHeight(40)  # aumentei porque agora o texto é maior
        te_layout.addWidget(lbl_te)


        te_block.setMaximumHeight(90)
        lay.addWidget(te_block)

        # --- Bloco Pós-Processamento ---
        pp_block = QWidget()
        pp_layout = QVBoxLayout(pp_block)
        pp_layout.setContentsMargins(0, 0, 0, 0)
        pp_layout.setSpacing(2)

        btn_pp = QPushButton("Pós-Processamento de Dados")
        btn_pp.setMinimumHeight(60)
        pp_layout.addWidget(btn_pp)

        lbl_pp = QLabel(
            "Recorte o período de voo (com margem de segurança) e concatene múltiplos "
            "arquivos decorrentes de reinicialização do computador de bordo durante o voo."
        )
        lbl_pp.setStyleSheet("font-size: 9pt; color: gray;")
        lbl_pp.setMaximumHeight(30)
        pp_layout.addWidget(lbl_pp)

        pp_block.setMaximumHeight(90)
        lay.addWidget(pp_block)

        # Conectar
        btn_flight.clicked.connect(self.show_flight_page)
        btn_te.clicked.connect(self.show_te_page)
        btn_pp.clicked.connect(self.show_post_process_page)

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

    # ---------------- Post-Processing ----------------
    def show_post_process_page(self):
        self.clear_layout(self.main_layout)
        self.page_post_process = PostProcessingPage()
        btn_back = QPushButton("← Voltar")
        btn_back.clicked.connect(self.show_choice_page)
        self.main_layout.addWidget(btn_back)
        self.main_layout.addWidget(self.page_post_process)

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
            skiprows = None
            header_keywords = ["tempo_s", "tempo.s", "time_s", "time"]
            
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for i in range(5):
                    line = f.readline()
                    if not line:
                        break
                    line_lower = line.lower()
                    if any(k in line_lower for k in header_keywords):
                        skiprows = i
                        break

            if skiprows is not None:
                df = pd.read_csv(path, sep="\t", skiprows=skiprows, index_col=False, on_bad_lines="skip")
            else:
                df = pd.read_csv(path, sep="\t", header=None, index_col=False, on_bad_lines="skip")
                default_names = [
                    "tempo.s", "mps2.x.accel", "mps2.y.accel", "mps2.z.accel",
                    "dps.x.gyros", "dps.y.gyros", "dps.z.gyros",
                    "uT.x.magn", "uT.y.magn", "uT.z.magn",
                    "c.baro", "pa.baro", "m.h.baro",
                    "lat.GPS", "lon.GPS", "m.h.GPS", "mps.GPS", "sat.GPS", "prec.GPS"
                ]
                col_mapping = {i: name for i, name in enumerate(default_names)}
                df = df.rename(columns=col_mapping)

            df.columns = [str(c).strip() for c in df.columns]
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            mapping = {
                "tempo.s": "tempo_s",
                "time_s": "tempo_s",
                "c.baro": "temp_C",
                "baro_temp_c": "temp_C",
                "pa.baro": "pressao_Pa",
                "baro_press_pa": "pressao_Pa",
                "m.h.baro": "alt_m",
                "baro.h.m": "alt_m",
                "alt_m": "alt_m",
                "temperatura": "temp_C",
                "dps.x.gyros": "gyroX_dps",
                "dps.y.gyros": "gyroY_dps",
                "dps.z.gyros": "gyroZ_dps",
                "gx": "gyroX_dps",
                "gy": "gyroY_dps",
                "gz": "gyroZ_dps",
                "uT.x.magn": "magX_uT",
                "uT.y.magn": "magY_uT",
                "uT.z.magn": "magZ_uT",
                "mx": "magX_uT",
                "my": "magY_uT",
                "mz": "magZ_uT",
                "lat.GPS": "lat_deg",
                "lat_deg": "lat_deg",
                "lon.GPS": "lon_deg",
                "lon_deg": "lon_deg",
                "m.h.GPS": "alt_gps_m",
                "gps_alt_m": "alt_gps_m",
                "gps_speed_kmph": "vel_kmph"
            }
            df = df.rename(columns=mapping)

            if "mps2.x.accel" in df.columns:
                df["accX_g"] = df["mps2.x.accel"] / 9.80665
            if "mps2.y.accel" in df.columns:
                df["accY_g"] = df["mps2.y.accel"] / 9.80665
            if "mps2.z.accel" in df.columns:
                df["accZ_g"] = df["mps2.z.accel"] / 9.80665

            if "ax" in df.columns:
                df["accX_g"] = df["ax"] / 9.80665
            if "ay" in df.columns:
                df["accY_g"] = df["ay"] / 9.80665
            if "az" in df.columns:
                df["accZ_g"] = df["az"] / 9.80665

            if "mps.GPS" in df.columns:
                df["vel_kmph"] = df["mps.GPS"] * 3.6

            if "pqd.drogueN.m" in df.columns:
                df["p1_data"] = (df["pqd.drogueN.m"] > 0).astype(int)
            if "pqd.mainN.m" in df.columns:
                df["p3_data"] = (df["pqd.mainN.m"] > 0).astype(int)

            self.df = df
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

COLOR_MAP = {
    "Kgf.avg.cell": "b",        # azul - empuxo
    "psi.avg.tdt": "r",         # vermelho - pressão
    "adc.raw.cell": "g",        # verde - célula bruta
    "adc.avg.cell": "m",        # magenta - célula média
    "adc.raw.tdt": "c",         # ciano - transdutor bruto
    "adc.avg.tdt": "orange",         # preto - transdutor médio
}


class StaticAnalysisPage(QWidget):

    G0 = 9.80665

    SYSTEMS = {
        "Novo": {
            "file": {
                "open_filter": "CSV Files (*.csv);;All Files (*)",
                "save_filter": "CSV Files (*.csv)",
                "default_ext": ".csv",
                "seps_to_try": [",", ";"],       # tenta vírgula e depois ; (comum no BR)
                "decimal_to_try": [".", ","],    # tenta ponto e depois vírgula decimal
            },
            "columns": {
                # nomes internos (use esses no código)
                "internal": {
                    "time": "time_s",
                    "weight": "weight_kg",
                    "force": "force_n",
                    "press_base": "press_mpa",   # pressão base vem em MPa
                    "press_v": "press_v",
                },
                # cabeçalho externo do CSV (para reconhecer o arquivo)
                # chave = "normalizado" -> valor = nome interno
                "external_norm_to_internal": {
                    "time (s)": "time_s",
                    "weight (kg)": "weight_kg",
                    "force (n)": "force_n",
                    "pressure (mpa)": "press_mpa",
                    "pressure (v)": "press_v",
                },
                # export (para salvar CUT com o mesmo cabeçalho “bonito”)
                "internal_to_external": {
                    "time_s": "Time (s)",
                    "weight_kg": "Weight (kg)",
                    "force_n": "Force (N)",
                    "press_mpa": "Pressure (MPa)",
                    "press_v": "Pressure (V)",
                },
                # tipos desejados
                "dtypes": {
                    "time_s": "float64",
                    "weight_kg": "float64",
                    "force_n": "float64",
                    "press_mpa": "float64",
                    "press_v": "float64",
                },
                "required": ["time_s"],  # obrigatórias
            },
            "units": {
                # pressão vem em MPa e converte pra unidade escolhida
                "pressure_base_unit": "MPa",
                "pressure_supported": ["MPa", "psi", "Pa", "bar", "atm"],
                "thrust_supported": ["kgf", "N"],
            },
        },

        "Antigo": {
            "file": {
                "open_filter": "Text Files (*.txt);;All Files (*)",
                "save_filter": "Text Files (*.txt)",
                "default_ext": ".txt",
                "sep": "\t",
                "skiprows_fallback": 1,
            },
            "columns": {
                "internal": {
                    "time": "tempo.s",
                },
                "dtypes": {
                    "tempo.s": "float64",
                    # o resto fica “o que vier” (normalmente float), mas você pode listar aqui também
                },
                "required": ["tempo.s"],
            },
            "units": {
                "pressure_supported": ["psi", "Pa", "bar", "atm"],
                "thrust_supported": ["kgf", "N"],
            },
            # mapeamento de colunas do antigo conforme unidades
            "old_mappings": {
                "thrust_cols": {  # qual coluna plota conforme unidade escolhida
                    "kgf": {"cal": "Kgf.calibrado", "raw": "Kgf.avg.cell"},
                    "N":   {"cal": "N.calibrado",   "raw": "N.avg.cell"},
                },
                "press_cols": {
                    "psi": {"cal": "psi.calibrado", "raw": "psi.avg.tdt"},
                    "Pa":  {"cal": "Pa.calibrado",  "raw": "pascal.raw.tdt"},
                    "bar": {"cal": "bar.calibrado", "raw": "bar.raw.tdt"},
                    "atm": {"cal": "atm.calibrado", "raw": "atm.raw.tdt"},
                },
                "adc_cols": {
                    "cell_raw": "adc.raw.cell",
                    "cell_avg": "adc.avg.cell",
                    "tdt_raw": "adc.raw.tdt",
                    "tdt_avg": "adc.avg.tdt",
                }
            }
        }
    }

    # ============================================================

    def __init__(self, parent=None):
        super().__init__(parent)

        self.df = None
        self.curves = {}

        self._show_selection_dialog()
        self.system_type = self.sel["system_type"]
        self.unit_thrust = self.sel["unit_force"]
        self.unit_press = self.sel["unit_pressure"]
        self.enable_thrust = self.sel["use_force"]
        self.enable_press = self.sel["use_pressure"]

        self.schema = self.SYSTEMS[self.system_type]

        if self.system_type == "Antigo":
            self._build_ui_antigo()
        else:
            self._build_ui_novo()

    # -------------------------
    # Dialog de seleção
    # -------------------------
    def _show_selection_dialog(self):
        dlg = DataSelectionDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.sel = dlg.result_config()
        else:
            self.sel = {
                "system_type": "Novo",
                "use_force": True,
                "use_pressure": True,
                "unit_force": "kgf",
                "unit_pressure": "MPa",
            }

    # =========================
    # UI antigo
    # =========================
    def _build_ui(self):
        # compat, se alguém ainda chamar _build_ui
        self._build_ui_antigo()

    def _build_ui_antigo(self):
        root = QVBoxLayout(self)

        self.btn_open = QPushButton("Abrir arquivo de teste estático (.txt)")
        self.btn_open.clicked.connect(self.load_file)
        root.addWidget(self.btn_open)

        self.analysis_area = QWidget()
        analysis_layout = QVBoxLayout(self.analysis_area)
        root.addWidget(self.analysis_area, stretch=2)

        self.summary_row = QHBoxLayout()
        analysis_layout.addLayout(self.summary_row)

        self.box_time = QGroupBox("Tempo")
        self.box_time_lay = QVBoxLayout(self.box_time)
        self.lbl_t_total = QLabel("Tempo Total: —")
        self.box_time_lay.addWidget(self.lbl_t_total)
        self.summary_row.addWidget(self.box_time)

        self.box_force = QGroupBox("Empuxo")
        self.box_force_lay = QVBoxLayout(self.box_force)
        self.lbl_f_max = QLabel("Máx. Empuxo: —")
        self.lbl_burn = QLabel("Tempo de Queima: —")
        self.lbl_impulse = QLabel("Impulso Total: —")
        self.lbl_empuxo_adcraw = QLabel("Máx. ADC raw: —")
        self.lbl_empuxo_adcavg = QLabel("Máx. ADC filtrado: —")
        self.box_force_lay.addWidget(self.lbl_f_max)
        self.box_force_lay.addWidget(self.lbl_burn)
        self.box_force_lay.addWidget(self.lbl_impulse)
        self.box_force_lay.addWidget(self.lbl_empuxo_adcraw)
        self.box_force_lay.addWidget(self.lbl_empuxo_adcavg)
        self.summary_row.addWidget(self.box_force)

        self.box_press = QGroupBox("Pressão")
        self.box_press_lay = QVBoxLayout(self.box_press)
        self.lbl_p_max = QLabel("Máx. Pressão: —")
        self.lbl_p_duration = QLabel("Tempo de duração: —")
        self.lbl_press_adcraw = QLabel("Máx. ADC raw: —")
        self.lbl_press_adcavg = QLabel("Máx. ADC filtrado: —")
        self.box_press_lay.addWidget(self.lbl_p_max)
        self.box_press_lay.addWidget(self.lbl_p_duration)
        self.box_press_lay.addWidget(self.lbl_press_adcraw)
        self.box_press_lay.addWidget(self.lbl_press_adcavg)
        self.summary_row.addWidget(self.box_press)

        self.plot = pg.PlotWidget(title="Análise dos Dados")
        self.legend = self.plot.addLegend()
        self.plot.showGrid(x=True, y=True)
        analysis_layout.addWidget(self.plot, stretch=2)

        self.label_hover = QLabel("Cursor: -")
        root.addWidget(self.label_hover)

        btn_row = QHBoxLayout()
        self.btn_cut = QPushButton("Recortar Dados")
        self.btn_cut.clicked.connect(self.cut_data)
        btn_row.addWidget(self.btn_cut)

        self.btn_calibrate = QPushButton("Calibrar Dados")
        self.btn_calibrate.clicked.connect(self.calibrate_data)
        btn_row.addWidget(self.btn_calibrate)

        self.btn_screenshot = QPushButton("Exportar Dados")
        self.btn_screenshot.clicked.connect(self.save_screenshot)
        btn_row.addWidget(self.btn_screenshot)

        root.addLayout(btn_row)

        self.plot.scene().sigMouseMoved.connect(self._mouseMoved)

        self.box_force.setVisible(self.enable_thrust)
        self.box_press.setVisible(self.enable_press)

    # =========================
    # UI novo
    # =========================
    def _build_ui_novo(self):
        root = QVBoxLayout(self)

        self.btn_open = QPushButton("Abrir arquivo de teste estático (.csv)")
        self.btn_open.clicked.connect(self.load_file)
        root.addWidget(self.btn_open)

        self.analysis_area = QWidget()
        analysis_layout = QVBoxLayout(self.analysis_area)
        root.addWidget(self.analysis_area, stretch=2)

        self.summary_row = QHBoxLayout()
        analysis_layout.addLayout(self.summary_row)

        self.box_time = QGroupBox("Tempo")
        self.box_time_lay = QVBoxLayout(self.box_time)
        self.lbl_t_total = QLabel("Tempo Total: —")
        self.box_time_lay.addWidget(self.lbl_t_total)
        self.summary_row.addWidget(self.box_time)

        self.box_force = QGroupBox("Força / Empuxo")
        self.box_force_lay = QVBoxLayout(self.box_force)
        self.lbl_f_max = QLabel("Máx. Força: —")
        self.lbl_w_max = QLabel("Máx. Weight: —")
        self.lbl_burn = QLabel("Tempo de Queima: —")
        self.lbl_impulse = QLabel("Impulso Total: —")
        self.box_force_lay.addWidget(self.lbl_f_max)
        self.box_force_lay.addWidget(self.lbl_w_max)
        self.box_force_lay.addWidget(self.lbl_burn)
        self.box_force_lay.addWidget(self.lbl_impulse)
        self.summary_row.addWidget(self.box_force)

        self.box_press = QGroupBox("Pressão")
        self.box_press_lay = QVBoxLayout(self.box_press)
        self.lbl_p_max = QLabel("Máx. Pressão: —")
        self.lbl_p_duration = QLabel("Tempo de duração: —")
        self.lbl_v_max = QLabel("Máx. Tensão: —")
        self.box_press_lay.addWidget(self.lbl_p_max)
        self.box_press_lay.addWidget(self.lbl_p_duration)
        self.box_press_lay.addWidget(self.lbl_v_max)
        self.summary_row.addWidget(self.box_press)

        self.plot = pg.PlotWidget(title="Análise dos Dados (Novo)")
        self.legend = self.plot.addLegend()
        self.plot.showGrid(x=True, y=True)
        analysis_layout.addWidget(self.plot, stretch=2)

        self.label_hover = QLabel("Cursor: -")
        root.addWidget(self.label_hover)

        btn_row = QHBoxLayout()
        self.btn_cut = QPushButton("Recortar Dados")
        self.btn_cut.clicked.connect(self.cut_data)
        btn_row.addWidget(self.btn_cut)

        self.btn_calibrate = QPushButton("Calibrar Dados")
        self.btn_calibrate.setEnabled(False)
        self.btn_calibrate.setToolTip("Novo: CSV já vem em unidades físicas (kg, N, MPa, V).")
        btn_row.addWidget(self.btn_calibrate)

        self.btn_screenshot = QPushButton("Exportar Dados")
        self.btn_screenshot.clicked.connect(self.save_screenshot)
        btn_row.addWidget(self.btn_screenshot)

        root.addLayout(btn_row)

        self.plot.scene().sigMouseMoved.connect(self._mouseMoved)

        self.box_force.setVisible(self.enable_thrust)
        self.box_press.setVisible(self.enable_press)

    # =========================
    # Leitura / conversões
    # =========================
    def _norm_col(self, s: str) -> str:
        s = s.strip().lower()
        s = re.sub(r"\s+", " ", s)
        return s

    def _apply_dtypes(self, df: pd.DataFrame, dtypes: dict) -> pd.DataFrame:
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def _load_csv_novo(self, path: str) -> pd.DataFrame:
        cfg = self.SYSTEMS["Novo"]
        colcfg = cfg["columns"]
        filecfg = cfg["file"]

        last_err = None
        for sep in filecfg["seps_to_try"]:
            for dec in filecfg["decimal_to_try"]:
                try:
                    df = pd.read_csv(path, sep=sep, decimal=dec)
                    if df.shape[1] == 1:
                        # tudo caiu numa coluna -> não serve
                        continue

                    df.columns = [c.strip() for c in df.columns]

                    # rename por cabeçalho normalizado
                    rename = {}
                    for c in df.columns:
                        key = self._norm_col(c)
                        if key in colcfg["external_norm_to_internal"]:
                            rename[c] = colcfg["external_norm_to_internal"][key]
                    df = df.rename(columns=rename)

                    # checa required
                    for req in colcfg["required"]:
                        if req not in df.columns:
                            raise ValueError(f"Coluna obrigatória ausente: {req}")

                    df = self._apply_dtypes(df, colcfg["dtypes"])

                    time_col = colcfg["internal"]["time"]
                    df = df.dropna(subset=[time_col]).sort_values(time_col).reset_index(drop=True)
                    return df
                except Exception as e:
                    last_err = e

        raise ValueError(f"Falha ao ler CSV (testei separadores/decimais). Último erro: {last_err}")

    def _convert_pressure_from_mpa(self, p_mpa: np.ndarray, unit: str) -> np.ndarray:
        unit = unit.strip()
        if unit == "MPa":
            return p_mpa
        p_pa = p_mpa * 1_000_000.0
        if unit == "Pa":
            return p_pa
        if unit == "bar":
            return p_pa / 100_000.0
        if unit == "atm":
            return p_pa / 101_325.0
        if unit == "psi":
            return p_pa / 6_894.757293168
        return p_mpa

    # =========================
    # Ações comuns
    # =========================
    def save_screenshot(self):
        pixmap = self.analysis_area.grab()
        path, _ = QFileDialog.getSaveFileName(self, "Salvar análise", "", "PNG Image (*.png)")
        if not path:
            return
        if not path.endswith(".png"):
            path += ".png"

        pixmap.save(path, "PNG")
        QMessageBox.information(self, "Sucesso", f"Imagem salva em:\n{path}")

    def calibrate_data(self):
        if self.system_type != "Antigo":
            QMessageBox.information(self, "Info", "Novo: calibração por ADC não se aplica.")
            return

        if self.df is None:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Calibração")
        layout = QFormLayout(dialog)

        layout.addRow(QLabel("<b>Empuxo</b>"))
        adc_i_cell_edit = QLineEdit(); layout.addRow("ADC inicial (massa 0):", adc_i_cell_edit)
        adc_f_cell_edit = QLineEdit(); layout.addRow("ADC final (massa com corpo de prova):", adc_f_cell_edit)
        peso_f_cell_edit = QLineEdit(); layout.addRow("Peso corpo de prova (kgf):", peso_f_cell_edit)

        layout.addRow(QLabel("<b>Pressão</b>"))
        adc_i_tdt_edit = QLineEdit(); layout.addRow("ADC inicial transdutor:", adc_i_tdt_edit)
        psi_i_tdt_edit = QLineEdit(); layout.addRow("Pressão inicial transdutor:", psi_i_tdt_edit)
        adc_45v_edit = QLineEdit(); layout.addRow("ADC equivalente a 4.5V:", adc_45v_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            adc_i_cell = float(adc_i_cell_edit.text() or 0)
            adc_f_cell = float(adc_f_cell_edit.text() or 0)
            peso_f_cell = float(peso_f_cell_edit.text() or 0)

            adc_i_tdt = float(adc_i_tdt_edit.text() or 0)
            psi_i_tdt = float(psi_i_tdt_edit.text() or 0)
            adc_45v = float(adc_45v_edit.text() or 0)
        except ValueError:
            QMessageBox.critical(self, "Erro", "Valores inválidos.")
            return

        df_calib = self.df.copy()
        if adc_i_cell != 0 and adc_f_cell != 0 and peso_f_cell != 0:
            m_cell = peso_f_cell / (adc_f_cell - adc_i_cell)
            df_calib["Kgf.calibrado"] = (df_calib["adc.raw.cell"] - adc_i_cell) * m_cell
            df_calib["N.calibrado"] = df_calib["Kgf.calibrado"] * self.G0

        if adc_i_tdt != 0 and adc_45v != 0 and adc_45v > adc_i_tdt:
            m_tdt = 500 / (adc_45v - adc_i_tdt)
            psi_values = (df_calib["adc.avg.tdt"] - adc_i_tdt) * m_tdt + psi_i_tdt
            df_calib["psi.calibrado"] = psi_values
            df_calib["Pa.calibrado"] = df_calib["psi.calibrado"] * 6894.76
            df_calib["atm.calibrado"] = df_calib["psi.calibrado"] / 14.696
            df_calib["bar.calibrado"] = df_calib["psi.calibrado"] / 14.5038

        path, _ = QFileDialog.getSaveFileName(self, "Salvar Arquivo Calibrado", "", self.SYSTEMS["Antigo"]["file"]["save_filter"])
        if not path:
            return
        if not path.endswith(".txt"):
            path += ".txt"
        if "_CALIBRATED" not in path.upper():
            base, ext = path.rsplit(".", 1)
            path = f"{base}_CALIBRATED.{ext}"

        try:
            df_calib.to_csv(path, sep="\t", index=False)
            QMessageBox.information(self, "Sucesso", f"Arquivo calibrado salvo em:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao salvar arquivo:\n{e}")

    def cut_data(self):
        if self.df is None:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return

        t_min, ok1 = QInputDialog.getDouble(self, "Corte de Dados", "Tempo inicial (s):", 0, 0)
        if not ok1:
            return
        t_max, ok2 = QInputDialog.getDouble(self, "Corte de Dados", "Tempo final (s):", 0, 0)
        if not ok2:
            return

        if t_min < 0 or t_max <= 0 or t_min >= t_max:
            QMessageBox.critical(self, "Erro", "Intervalo inválido.")
            return

        if self.system_type == "Novo":
            t_col = self.schema["columns"]["internal"]["time"]
            dialog_filter = self.schema["file"]["save_filter"]
            ext = self.schema["file"]["default_ext"]
            sep = ","
        else:
            t_col = self.schema["columns"]["internal"]["time"]
            dialog_filter = self.schema["file"]["save_filter"]
            ext = self.schema["file"]["default_ext"]
            sep = "\t"

        if t_col not in self.df.columns:
            QMessageBox.critical(self, "Erro", f"Coluna '{t_col}' não encontrada.")
            return

        df_cut = self.df[(self.df[t_col] >= t_min) & (self.df[t_col] <= t_max)]
        if df_cut.empty:
            QMessageBox.critical(self, "Erro", "Nenhum dado dentro do intervalo selecionado.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Salvar Arquivo Cortado", "", dialog_filter)
        if not path:
            return
        if not path.endswith(ext):
            path += ext
        if "_CUT" not in path.upper():
            base, _ = path.rsplit(".", 1)
            path = f"{base}_CUT{ext}"

        try:
            if self.system_type == "Novo":
                df_out = df_cut.rename(columns=self.schema["columns"]["internal_to_external"])
                df_out.to_csv(path, sep=sep, index=False)
            else:
                df_cut.to_csv(path, sep=sep, index=False)

            QMessageBox.information(self, "Sucesso", f"Arquivo cortado salvo em:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao salvar arquivo:\n{e}")

    # =========================
    # Load / Analyze
    # =========================
    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir Arquivo", "", self.schema["file"]["open_filter"])
        if not path:
            return

        try:
            if self.system_type == "Novo":
                df = self._load_csv_novo(path)
            else:
                sep = self.schema["file"]["sep"]
                df = pd.read_csv(path, sep=sep)

                time_col = self.schema["columns"]["internal"]["time"]
                if time_col not in df.columns:
                    df = pd.read_csv(path, sep=sep, skiprows=self.schema["file"]["skiprows_fallback"])

                df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

                for req in self.schema["columns"]["required"]:
                    if req not in df.columns:
                        raise ValueError(f"Coluna obrigatória ausente: {req}")

                df = self._apply_dtypes(df, self.schema["columns"]["dtypes"])
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao ler arquivo:\n{e}")
            return

        self.df = df
        self.analyze_data()

    def analyze_data(self):
        if self.df is None:
            return
        if self.system_type == "Novo":
            self._analyze_data_novo()
        else:
            self._analyze_data_antigo()

    def _prepare_dual_axes(self):
        self.plot.clear()

        if hasattr(self, "right_viewbox") and self.right_viewbox is not None:
            try:
                self.plot.scene().removeItem(self.right_viewbox)
            except Exception:
                pass

        self.legend = self.plot.addLegend()
        self.plot.showGrid(x=True, y=True)

        self.left_viewbox = self.plot.getViewBox()

        self.right_viewbox = pg.ViewBox()
        self.right_viewbox.setMouseEnabled(x=True, y=False)   
        self.right_viewbox.setMenuEnabled(False)               
        self.right_viewbox.setZValue(-100)                     

        self.plot.scene().addItem(self.right_viewbox)
        self.plot.getAxis("right").linkToView(self.right_viewbox)

        self.right_viewbox.setXLink(self.left_viewbox)
        self.right_viewbox.setGeometry(self.left_viewbox.sceneBoundingRect())

        def sync_views():
            self.right_viewbox.setGeometry(self.left_viewbox.sceneBoundingRect())
            self.right_viewbox.linkedViewChanged(self.left_viewbox, self.right_viewbox.XAxis)

        self.left_viewbox.sigResized.connect(sync_views)


    # =========================
    # Analyze Antigo
    # =========================
    def _analyze_data_antigo(self):
        df = self.df
        time_col = self.schema["columns"]["internal"]["time"]
        t = df[time_col].to_numpy()

        self._prepare_dual_axes()

        self.plot.setLabel("bottom", "Tempo", "s")
        self.plot.setLabel("left", "Empuxo", self.unit_thrust)
        self.plot.setLabel("right", "Pressão", self.unit_press)
        self.plot.showAxis("left"); self.plot.showAxis("right")

        if len(t) >= 2:
            self.lbl_t_total.setText(f"Tempo Total: {(t[-1]-t[0]):.3f} s")
        else:
            self.lbl_t_total.setText("Tempo Total: —")

        maps = self.schema["old_mappings"]
        adc = maps["adc_cols"]

        # ---- EMPUXO
        if self.enable_thrust:
            m = maps["thrust_cols"][self.unit_thrust]
            col_thrust = m["cal"] if m["cal"] in df.columns else m["raw"]

            if m["cal"] in df.columns:
                self.box_force.setTitle("Empuxo Calibrado")
            else:
                self.box_force.setTitle("Empuxo")

            if col_thrust in df.columns:
                thrust = df[col_thrust].to_numpy()
                peak = float(np.nanmax(thrust))
                self.lbl_f_max.setText(f"Máx. Empuxo: {peak:.2f} {self.unit_thrust}")

                mask = thrust > 0.05 * peak
                if np.any(mask):
                    s = int(np.argmax(mask))
                    e = int(len(mask) - np.argmax(mask[::-1]) - 1)
                    self.lbl_burn.setText(f"Tempo de Queima: {(t[e]-t[s]):.3f} s")
                    self.plot.addItem(pg.InfiniteLine(pos=float(t[s]), angle=90, pen=pg.mkPen("g", style=Qt.PenStyle.DashLine)))
                    self.plot.addItem(pg.InfiniteLine(pos=float(t[e]), angle=90, pen=pg.mkPen("r", style=Qt.PenStyle.DashLine)))

                    thrust_N = thrust * self.G0 if self.unit_thrust == "kgf" else thrust
                    impulse = float(np.trapezoid(thrust_N[s:e+1], t[s:e+1]))
                else:
                    impulse = 0.0
                    self.lbl_burn.setText("Tempo de Queima: —")

                self.lbl_impulse.setText(f"Impulso Total: {impulse:.2f} Ns")

                c = pg.PlotCurveItem(t, thrust, pen=pg.mkPen("b", width=3, dash=[6,3]),
                                     name=f"Empuxo ({self.unit_thrust})")
                self.left_viewbox.addItem(c)
                self.legend.addItem(c, c.name())

                if adc["cell_raw"] in df.columns:
                    raw = df[adc["cell_raw"]].to_numpy()
                    self.lbl_empuxo_adcraw.setText(f"Máx. ADC raw: {np.nanmax(raw):.0f}/1023")
                if adc["cell_avg"] in df.columns:
                    avg = df[adc["cell_avg"]].to_numpy()
                    self.lbl_empuxo_adcavg.setText(f"Máx. ADC filtrado: {np.nanmax(avg):.1f}/1023")

            self.box_force.setVisible(True)
        else:
            self.box_force.setVisible(False)

        # ---- PRESSÃO
        if self.enable_press:
            m = maps["press_cols"][self.unit_press]
            col_press = m["cal"] if m["cal"] in df.columns else m["raw"]

            if m["cal"] in df.columns:
                self.box_press.setTitle("Pressão Calibrada")
            else:
                self.box_press.setTitle("Pressão")

            if col_press in df.columns:
                press = df[col_press].to_numpy()
                pmax = float(np.nanmax(press))
                self.lbl_p_max.setText(f"Máx. Pressão: {pmax:.2f} {self.unit_press}")

                mask = press > 0.05 * pmax
                if np.any(mask):
                    s = int(np.argmax(mask))
                    e = int(len(mask) - np.argmax(mask[::-1]) - 1)
                    self.lbl_p_duration.setText(f"Tempo de duração: {(t[e]-t[s]):.3f} s")
                else:
                    self.lbl_p_duration.setText("Tempo de duração: —")

                c = pg.PlotCurveItem(t, press, pen=pg.mkPen("r", width=3, style=Qt.PenStyle.DashDotLine),
                                     name=f"Pressão ({self.unit_press})")
                self.right_viewbox.addItem(c)
                self.legend.addItem(c, c.name())

                if adc["tdt_raw"] in df.columns:
                    raw = df[adc["tdt_raw"]].to_numpy()
                    self.lbl_press_adcraw.setText(f"Máx. ADC raw: {np.nanmax(raw):.0f}/1023")
                if adc["tdt_avg"] in df.columns:
                    avg = df[adc["tdt_avg"]].to_numpy()
                    self.lbl_press_adcavg.setText(f"Máx. ADC filtrado: {np.nanmax(avg):.1f}/1023")

            self.box_press.setVisible(True)
        else:
            self.box_press.setVisible(False)

    # =========================
    # Analyze Novo
    # =========================
    def _analyze_data_novo(self):
        df = self.df
        cols = self.schema["columns"]["internal"]

        tcol = cols["time"]
        wcol = cols["weight"]
        fcol = cols["force"]
        pcol = cols["press_base"]
        vcol = cols["press_v"]

        t = df[tcol].to_numpy()
        self._prepare_dual_axes()

        self.plot.setLabel("bottom", "Tempo", "s")
        self.plot.setLabel("left", "Força / Empuxo", self.unit_thrust)
        self.plot.setLabel("right", "Pressão", self.unit_press)
        self.plot.showAxis("left"); self.plot.showAxis("right")

        if len(t) >= 2:
            self.lbl_t_total.setText(f"Tempo Total: {(t[-1]-t[0]):.3f} s")
        else:
            self.lbl_t_total.setText("Tempo Total: —")

        # ---- FORÇA
        if self.enable_thrust:
            force_n = None
            if fcol in df.columns and df[fcol].notna().any():
                force_n = df[fcol].to_numpy()
            elif wcol in df.columns and df[wcol].notna().any():
                force_n = df[wcol].to_numpy() * self.G0

            if force_n is None:
                self.lbl_f_max.setText("Máx. Força: — (sem Force/Weight)")
                self.lbl_w_max.setText("Máx. Weight: —")
                self.lbl_burn.setText("Tempo de Queima: —")
                self.lbl_impulse.setText("Impulso Total: —")
            else:
                y_force = force_n if self.unit_thrust == "N" else (force_n / self.G0)

                self.lbl_f_max.setText(f"Máx. Força: {float(np.nanmax(y_force)):.2f} {self.unit_thrust}")
                if wcol in df.columns and df[wcol].notna().any():
                    self.lbl_w_max.setText(f"Máx. Weight: {float(np.nanmax(df[wcol].to_numpy())):.3f} kg")
                else:
                    self.lbl_w_max.setText("Máx. Weight: —")

                peak = float(np.nanmax(force_n))
                mask = force_n > 0.05 * peak
                if np.any(mask):
                    s = int(np.argmax(mask))
                    e = int(len(mask) - np.argmax(mask[::-1]) - 1)
                    self.lbl_burn.setText(f"Tempo de Queima: {(t[e]-t[s]):.3f} s")
                    self.plot.addItem(pg.InfiniteLine(pos=float(t[s]), angle=90, pen=pg.mkPen("g", style=Qt.PenStyle.DashLine)))
                    self.plot.addItem(pg.InfiniteLine(pos=float(t[e]), angle=90, pen=pg.mkPen("r", style=Qt.PenStyle.DashLine)))
                    impulse = float(np.trapezoid(force_n[s:e+1], t[s:e+1]))
                else:
                    impulse = 0.0
                    self.lbl_burn.setText("Tempo de Queima: —")

                self.lbl_impulse.setText(f"Impulso Total: {impulse:.2f} N·s")

                c = pg.PlotCurveItem(t, y_force, pen=pg.mkPen("b", width=3),
                                     name=f"Força ({self.unit_thrust})")
                self.left_viewbox.addItem(c)
                self.legend.addItem(c, c.name())

            self.box_force.setVisible(True)
        else:
            self.box_force.setVisible(False)

        # ---- PRESSÃO
        if self.enable_press:
            if pcol in df.columns and df[pcol].notna().any():
                p_mpa = df[pcol].to_numpy()
                p = self._convert_pressure_from_mpa(p_mpa, self.unit_press)

                pmax = float(np.nanmax(p))
                self.lbl_p_max.setText(f"Máx. Pressão: {pmax:.3f} {self.unit_press}")

                mask = p > 0.05 * pmax
                if np.any(mask):
                    s = int(np.argmax(mask))
                    e = int(len(mask) - np.argmax(mask[::-1]) - 1)
                    self.lbl_p_duration.setText(f"Tempo de duração: {(t[e]-t[s]):.3f} s")
                else:
                    self.lbl_p_duration.setText("Tempo de duração: —")

                c = pg.PlotCurveItem(t, p, pen=pg.mkPen("r", width=3, style=Qt.PenStyle.DashDotLine),
                                     name=f"Pressão ({self.unit_press})")
                self.right_viewbox.addItem(c)
                self.legend.addItem(c, c.name())

                if vcol in df.columns and df[vcol].notna().any():
                    v = df[vcol].to_numpy()
                    vmax = float(np.nanmax(v))
                    self.lbl_v_max.setText(f"Máx. Tensão: {vmax:.3f} V")

                    # escalona V para o range da pressão (só visual)
                    vmin = float(np.nanmin(v))
                    pmin = float(np.nanmin(p))
                    if (vmax - vmin) > 1e-12 and (pmax - pmin) > 1e-12:
                        v_scaled = (v - vmin) / (vmax - vmin) * (pmax - pmin) + pmin
                        cv = pg.PlotCurveItem(t, v_scaled, pen=pg.mkPen("y", width=2, style=Qt.PenStyle.DotLine),
                                              name="Pressão (V) [escalonada]")
                        self.right_viewbox.addItem(cv)
                        self.legend.addItem(cv, cv.name())
                else:
                    self.lbl_v_max.setText("Máx. Tensão: —")
            else:
                self.lbl_p_max.setText("Máx. Pressão: — (sem Pressure (MPa))")
                self.lbl_p_duration.setText("Tempo de duração: —")
                self.lbl_v_max.setText("Máx. Tensão: —")

            self.box_press.setVisible(True)
        else:
            self.box_press.setVisible(False)

    # =========================
    # Cursor / util
    # =========================
    def _mouseMoved(self, evt):
        pos = evt
        if self.plot.sceneBoundingRect().contains(pos):
            mousePoint = self.plot.plotItem.vb.mapSceneToView(pos)
            self.label_hover.setText(f"Cursor: t={mousePoint.x():.2f}s, y={mousePoint.y():.2f}")


class DataSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Selecionar dados e unidades")

        main = QVBoxLayout(self)
        up = QHBoxLayout(self)

        col_type = QVBoxLayout()
        col_type.addWidget(QLabel("Sistema"))
        self.system_type = QComboBox()
        self.system_type.addItems(["Antigo", "Novo"])
        self.system_type.setCurrentIndex(1)
        col_type.addWidget(self.system_type)
        up.addLayout(col_type)

        right = QVBoxLayout()

        row_checks = QHBoxLayout()
        self.cb_force = QCheckBox("Empuxo")
        self.cb_force.setChecked(True)
        self.cb_pressure = QCheckBox("Pressão")
        self.cb_pressure.setChecked(True)
        row_checks.addWidget(self.cb_force)
        row_checks.addWidget(self.cb_pressure)
        right.addLayout(row_checks)

        row_units = QHBoxLayout()

        col_force = QVBoxLayout()
        col_force.addWidget(QLabel("Unidade (Empuxo)"))
        self.cmb_force = QComboBox()
        self.cmb_force.addItems(["kgf", "N"])
        col_force.addWidget(self.cmb_force)
        row_units.addLayout(col_force)

        col_press = QVBoxLayout()
        col_press.addWidget(QLabel("Unidade (Pressão)"))
        self.cmb_press = QComboBox()
        self.cmb_press.addItems(["MPa", "psi", "Pa", "bar", "atm"])
        self.cmb_press.setCurrentText("MPa")
        col_press.addWidget(self.cmb_press)
        row_units.addLayout(col_press)

        right.addLayout(row_units)

        up.addLayout(right)
        main.addLayout(up)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        main.addWidget(btns, alignment=Qt.AlignmentFlag.AlignCenter)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)

    def _on_accept(self):
        if not (self.cb_force.isChecked() or self.cb_pressure.isChecked()):
            QMessageBox.warning(self, "Aviso", "Selecione pelo menos uma categoria (Empuxo e/ou Pressão).")
            return
        self.accept()

    def result_config(self):
        return {
            "system_type": self.system_type.currentText(),
            "use_force": self.cb_force.isChecked(),
            "use_pressure": self.cb_pressure.isChecked(),
            "unit_force": self.cmb_force.currentText(),
            "unit_pressure": self.cmb_press.currentText(),
        }


class PostProcessingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_paths = []
        self.df_full = None
        self.df = None
        self.curves = {}
        self.gap_regions = []
        self._build_ui()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)

        # Painel esquerdo de controle
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(400)

        ctrl_widget = QWidget()
        ctrl_lay = QVBoxLayout(ctrl_widget)

        # 1. Grupo de Arquivos
        grp_files = QGroupBox("Arquivos de Telemetria (Reinicio de Voo)")
        files_lay = QVBoxLayout(grp_files)
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(150)
        files_lay.addWidget(self.list_widget)

        btn_lay1 = QHBoxLayout()
        self.btn_add = QPushButton("Adicionar")
        self.btn_remove = QPushButton("Remover")
        self.btn_clear = QPushButton("Limpar")
        btn_lay1.addWidget(self.btn_add)
        btn_lay1.addWidget(self.btn_remove)
        btn_lay1.addWidget(self.btn_clear)
        files_lay.addLayout(btn_lay1)

        btn_lay2 = QHBoxLayout()
        self.btn_up = QPushButton("Subir")
        self.btn_down = QPushButton("Descer")
        btn_lay2.addWidget(self.btn_up)
        btn_lay2.addWidget(self.btn_down)
        files_lay.addLayout(btn_lay2)

        ctrl_lay.addWidget(grp_files)

        # 2. Grupo de Conexão
        grp_concat = QGroupBox("Configurações de Conexão")
        concat_lay = QFormLayout(grp_concat)
        self.sp_gap = QDoubleSpinBox()
        self.sp_gap.setRange(0.0, 3600.0)
        self.sp_gap.setValue(5.0)
        self.sp_gap.setSuffix(" s")
        concat_lay.addRow("Intervalo reboot:", self.sp_gap)
        
        self.btn_estimate_gap = QPushButton("Estimar Tempo de Reboot")
        self.btn_concat = QPushButton("Concatenar & Carregar")
        concat_lay.addRow(self.btn_estimate_gap)
        concat_lay.addRow(self.btn_concat)
        ctrl_lay.addWidget(grp_concat)

        # 3. Grupo de Recorte
        grp_crop = QGroupBox("Ajuste de Recorte (Filtro de Voo)")
        crop_lay = QFormLayout(grp_crop)
        self.sp_start = QDoubleSpinBox()
        self.sp_start.setRange(0.0, 1e7)
        self.sp_start.setValue(0.0)
        self.sp_start.setSuffix(" s")
        crop_lay.addRow("Início do Corte:", self.sp_start)

        self.sp_end = QDoubleSpinBox()
        self.sp_end.setRange(0.0, 1e7)
        self.sp_end.setValue(0.0)
        self.sp_end.setSuffix(" s")
        crop_lay.addRow("Fim do Corte:", self.sp_end)

        self.btn_auto_detect = QPushButton("Auto-Detectar Voo")
        self.btn_apply_crop = QPushButton("Aplicar Recorte")
        self.btn_reset_crop = QPushButton("Restaurar Completo")
        crop_lay.addRow(self.btn_auto_detect)
        crop_lay.addRow(self.btn_apply_crop)
        crop_lay.addRow(self.btn_reset_crop)
        ctrl_lay.addWidget(grp_crop)

        # 3.5. Grupo de Diagnóstico
        grp_diag = QGroupBox("Diagnóstico de Telemetria")
        diag_lay = QVBoxLayout(grp_diag)
        self.diag_list = QListWidget()
        self.diag_list.setMinimumHeight(100)
        self.diag_list.setMaximumHeight(150)
        diag_lay.addWidget(self.diag_list)
        self.chk_apply_filters = QCheckBox("Aplicar Filtro de Ruído & Glitches")
        self.chk_apply_filters.setChecked(False)
        self.chk_apply_filters.stateChanged.connect(self.plot_data)
        diag_lay.addWidget(self.chk_apply_filters)
        ctrl_lay.addWidget(grp_diag)

        # 4. Grupo de Exportação
        grp_export = QGroupBox("Exportar")
        export_lay = QVBoxLayout(grp_export)
        self.btn_export = QPushButton("Salvar Dados Tratados (.txt)")
        self.btn_export.setStyleSheet("background-color: #7b2cff; color: white; font-weight: bold;")
        export_lay.addWidget(self.btn_export)
        ctrl_lay.addWidget(grp_export)

        ctrl_lay.addStretch(1)
        scroll.setWidget(ctrl_widget)
        main_layout.addWidget(scroll, stretch=1)

        # Painel direito de plotagem
        plot_widget = QWidget()
        plot_lay = QVBoxLayout(plot_widget)

        # Checkboxes de visualização
        chk_lay = QHBoxLayout()
        self.chk_alt = QCheckBox("Altitude")
        self.chk_vel = QCheckBox("Velocidade")
        self.chk_acc = QCheckBox("Aceleração")
        self.chk_zero_drift = QCheckBox("Zerar deriva de solo (início/fim em 0m)")
        self.chk_preview_cropped = QCheckBox("Ver apenas recortado")
        self.chk_alt.setChecked(True)
        self.chk_vel.setChecked(True)
        self.chk_acc.setChecked(True)
        self.chk_zero_drift.setChecked(True)
        self.chk_preview_cropped.setChecked(False)
        
        self.chk_alt.stateChanged.connect(self.plot_data)
        self.chk_vel.stateChanged.connect(self.plot_data)
        self.chk_acc.stateChanged.connect(self.plot_data)
        self.chk_zero_drift.stateChanged.connect(self.plot_data)
        self.chk_preview_cropped.stateChanged.connect(self.toggle_preview_cropped)

        chk_lay.addWidget(self.chk_alt)
        chk_lay.addWidget(self.chk_vel)
        chk_lay.addWidget(self.chk_acc)
        chk_lay.addWidget(self.chk_zero_drift)
        chk_lay.addWidget(self.chk_preview_cropped)
        chk_lay.addStretch(1)
        plot_lay.addLayout(chk_lay)

        # Plot
        self.plot = pg.PlotWidget(title="Visualização e Recorte do Voo")
        self.plot.addLegend()
        self.plot.showGrid(x=True, y=True)
        plot_lay.addWidget(self.plot, stretch=4)

        # Hover Label
        self.label_hover = QLabel("Cursor: -")
        plot_lay.addWidget(self.label_hover)

        main_layout.addWidget(plot_widget, stretch=3)

        # Conectar botões
        self.btn_add.clicked.connect(self._add_files)
        self.btn_remove.clicked.connect(self._remove_file)
        self.btn_clear.clicked.connect(self._clear_files)
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down.clicked.connect(self._move_down)
        self.btn_concat.clicked.connect(self.load_and_concatenate)
        self.btn_estimate_gap.clicked.connect(self.run_reboot_estimation)
        self.btn_auto_detect.clicked.connect(self.auto_detect_flight)
        self.btn_apply_crop.clicked.connect(self.apply_crop)
        self.btn_reset_crop.clicked.connect(self.reset_crop)
        self.btn_export.clicked.connect(self.export_data)

        # Crosshair e Região
        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.plot.addItem(self.vLine, ignoreBounds=True)
        self.plot.addItem(self.hLine, ignoreBounds=True)
        self.plot.scene().sigMouseMoved.connect(self._mouseMoved)

        self.region = pg.LinearRegionItem()
        self.region.setZValue(10)
        self.region.sigRegionChanged.connect(self._update_spinboxes_from_region)
        self.sp_start.valueChanged.connect(self._update_region_from_spinboxes)
        self.sp_end.valueChanged.connect(self._update_region_from_spinboxes)

    def _mouseMoved(self, evt):
        pos = evt
        if self.plot.sceneBoundingRect().contains(pos):
            mousePoint = self.plot.plotItem.vb.mapSceneToView(pos)
            self.vLine.setPos(mousePoint.x())
            self.hLine.setPos(mousePoint.y())
            self.label_hover.setText(f"Cursor: t={mousePoint.x():.2f}s, y={mousePoint.y():.2f}")

    def _update_spinboxes_from_region(self):
        self.sp_start.blockSignals(True)
        self.sp_end.blockSignals(True)
        r_min, r_max = self.region.getRegion()
        self.sp_start.setValue(r_min)
        self.sp_end.setValue(r_max)
        self.sp_start.blockSignals(False)
        self.sp_end.blockSignals(False)

    def _update_region_from_spinboxes(self):
        self.region.blockSignals(True)
        self.region.setRegion([self.sp_start.value(), self.sp_end.value()])
        self.region.blockSignals(False)

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Adicionar Arquivos de Voo", "", "Text Files (*.txt)")
        if not paths:
            return
        for p in paths:
            if p not in self.file_paths:
                self.file_paths.append(p)
                self.list_widget.addItem(os.path.basename(p))

    def _remove_file(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.list_widget.takeItem(row)
            self.file_paths.pop(row)

    def _clear_files(self):
        self.list_widget.clear()
        self.file_paths.clear()

    def _move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)
            self.file_paths[row], self.file_paths[row-1] = self.file_paths[row-1], self.file_paths[row]

    def _move_down(self):
        row = self.list_widget.currentRow()
        if row < self.list_widget.count() - 1 and row >= 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)
            self.file_paths[row], self.file_paths[row+1] = self.file_paths[row+1], self.file_paths[row]

    def _load_single_file(self, path):
        skiprows = None
        header_keywords = ["tempo_s", "tempo.s", "time_s", "time"]
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for i in range(5):
                line = f.readline()
                if not line:
                    break
                line_lower = line.lower()
                if any(k in line_lower for k in header_keywords):
                    skiprows = i
                    break

        if skiprows is not None:
            df = pd.read_csv(path, sep="\t", skiprows=skiprows, index_col=False, on_bad_lines="skip")
        else:
            df = pd.read_csv(path, sep="\t", header=None, index_col=False, on_bad_lines="skip")
            default_names = [
                "tempo.s", "mps2.x.accel", "mps2.y.accel", "mps2.z.accel",
                "dps.x.gyros", "dps.y.gyros", "dps.z.gyros",
                "uT.x.magn", "uT.y.magn", "uT.z.magn",
                "c.baro", "pa.baro", "m.h.baro",
                "lat.GPS", "lon.GPS", "m.h.GPS", "mps.GPS", "sat.GPS", "prec.GPS"
            ]
            col_mapping = {i: name for i, name in enumerate(default_names)}
            df = df.rename(columns=col_mapping)

        df.columns = [str(c).strip() for c in df.columns]
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        mapping = {
            "tempo.s": "tempo_s",
            "time_s": "tempo_s",
            "c.baro": "temp_C",
            "baro_temp_c": "temp_C",
            "pa.baro": "pressao_Pa",
            "baro_press_pa": "pressao_Pa",
            "m.h.baro": "alt_m",
            "baro.h.m": "alt_m",
            "alt_m": "alt_m",
            "temperatura": "temp_C",
            "dps.x.gyros": "gyroX_dps",
            "dps.y.gyros": "gyroY_dps",
            "dps.z.gyros": "gyroZ_dps",
            "gx": "gyroX_dps",
            "gy": "gyroY_dps",
            "gz": "gyroZ_dps",
            "uT.x.magn": "magX_uT",
            "uT.y.magn": "magY_uT",
            "uT.z.magn": "magZ_uT",
            "mx": "magX_uT",
            "my": "magY_uT",
            "mz": "magZ_uT",
            "lat.GPS": "lat_deg",
            "lat_deg": "lat_deg",
            "lon.GPS": "lon_deg",
            "lon_deg": "lon_deg",
            "m.h.GPS": "alt_gps_m",
            "gps_alt_m": "alt_gps_m",
            "gps_speed_kmph": "vel_kmph"
        }
        df = df.rename(columns=mapping)

        if "mps2.x.accel" in df.columns:
            df["accX_g"] = df["mps2.x.accel"] / 9.80665
        if "mps2.y.accel" in df.columns:
            df["accY_g"] = df["mps2.y.accel"] / 9.80665
        if "mps2.z.accel" in df.columns:
            df["accZ_g"] = df["mps2.z.accel"] / 9.80665

        if "ax" in df.columns:
            df["accX_g"] = df["ax"] / 9.80665
        if "ay" in df.columns:
            df["accY_g"] = df["ay"] / 9.80665
        if "az" in df.columns:
            df["accZ_g"] = df["az"] / 9.80665

        if "mps.GPS" in df.columns:
            df["vel_kmph"] = df["mps.GPS"] * 3.6

        if "pqd.drogueN.m" in df.columns:
            df["p1_data"] = (df["pqd.drogueN.m"] > 0).astype(int)
        if "pqd.mainN.m" in df.columns:
            df["p3_data"] = (df["pqd.mainN.m"] > 0).astype(int)

        # Limpar linhas de calibração/inicialização iniciais com leituras zeradas ou espúrias
        if "pressao_Pa" in df.columns:
            df = df[df["pressao_Pa"] > 1000.0]
        elif "baro_press_pa" in df.columns:
            df = df[df["baro_press_pa"] > 1000.0]

        acc_cols = [c for c in ["accX_g", "accY_g", "accZ_g"] if c in df.columns]
        if len(acc_cols) == 3:
            df = df[~((df[acc_cols[0]] == 0.0) & (df[acc_cols[1]] == 0.0) & (df[acc_cols[2]] == 0.0))]

        return df.reset_index(drop=True)

    def load_and_concatenate(self):
        if not self.file_paths:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo adicionado.")
            return

        try:
            # Ordena os arquivos alfabeticamente para garantir a ordem cronológica correta
            self.file_paths.sort(key=os.path.basename)
            self.list_widget.clear()
            for p in self.file_paths:
                self.list_widget.addItem(os.path.basename(p))

            gap = self.sp_gap.value()
            dfs = []
            last_time_end = None
            self.gap_regions = []

            for p in self.file_paths:
                df = self._load_single_file(p)
                if df.empty or "tempo_s" not in df.columns:
                    continue

                df = df.sort_values("tempo_s").reset_index(drop=True)

                if last_time_end is not None:
                    t0 = df["tempo_s"].iloc[0]
                    offset = (last_time_end + gap) - t0
                    df["tempo_s"] = df["tempo_s"] + offset
                    self.gap_regions.append((last_time_end, last_time_end + gap))

                last_time_end = df["tempo_s"].iloc[-1]
                dfs.append(df)

            if not dfs:
                QMessageBox.warning(self, "Aviso", "Nenhum dado válido carregado.")
                return

            # Encontra a pressão de solo P0 robusta (evitando reboots em voo e glitches)
            P0 = None
            pressures = []
            for df in dfs:
                if "pressao_Pa" in df.columns:
                    valid_p = df["pressao_Pa"][(df["pressao_Pa"] >= 50000.0) & (df["pressao_Pa"] <= 110000.0)].dropna()
                    if not valid_p.empty:
                        pressures.append(valid_p)
            
            if pressures:
                # Usa o percentil 99 do máximo para evitar picos espúrios isolados de ruído
                combined_p = pd.concat(pressures)
                P0 = float(combined_p.quantile(0.99))

            if P0 is not None:
                for df in dfs:
                    if "pressao_Pa" in df.columns:
                        df["alt_m"] = 44330.0 * (1.0 - (df["pressao_Pa"] / P0) ** (1.0 / 5.255))
            else:
                # Fallback: Se não há pressão, aplica deslocamento linear de altitude entre arquivos
                last_alt_end = None
                for df in dfs:
                    if last_alt_end is not None and "alt_m" in df.columns:
                        valid_alt = df["alt_m"].dropna()
                        if not valid_alt.empty:
                            alt_offset = last_alt_end - valid_alt.iloc[0]
                            df["alt_m"] = df["alt_m"] + alt_offset
                    
                    if "alt_m" in df.columns:
                        valid_alt = df["alt_m"].dropna()
                        if not valid_alt.empty:
                            last_alt_end = valid_alt.iloc[-1]

            self.df_full = pd.concat(dfs, ignore_index=True)
            self.df_full = self.df_full.sort_values("tempo_s").reset_index(drop=True)
            self.df = self.df_full.copy()

            t_min = float(self.df["tempo_s"].min())
            t_max = float(self.df["tempo_s"].max())

            self.sp_start.setRange(t_min, t_max)
            self.sp_end.setRange(t_min, t_max)
            self.sp_start.setValue(t_min)
            self.sp_end.setValue(t_max)
            self.region.setRegion([t_min, t_max])

            self.run_diagnostics()
            self.plot_data()

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao concatenar arquivos:\n{e}")

    def run_diagnostics(self):
        self.diag_list.clear()
        if self.df_full is None or self.df_full.empty:
            self.diag_list.addItem("Nenhum dado carregado.")
            return

        warnings = []
        
        # 1. Checa reboots e gaps
        if len(self.file_paths) >= 2:
            warnings.append(f"ℹ️ Total de {len(self.file_paths)} arquivos concatenados.")
            warnings.append(f"ℹ️ Detectadas {len(self.gap_regions)} reinicializações em voo.")
            for i, (g_start, g_end) in enumerate(self.gap_regions):
                gap_dur = g_end - g_start
                warnings.append(f"   • Reboot {i+1}: Gap de ~{gap_dur:.1f} segundos.")
        
        # 2. Checa se inicializou no ar (reboot em voo)
        for i, p in enumerate(self.file_paths):
            df_temp = self._load_single_file(p)
            if not df_temp.empty and "pressao_Pa" in df_temp.columns:
                p_init = df_temp["pressao_Pa"].iloc[0]
                if p_init < 85000.0:
                    alt_init = 44330.0 * (1.0 - (p_init / 101325.0) ** (1.0 / 5.255))
                    warnings.append(f"⚠️ Boot do arquivo {os.path.basename(p)} ocorreu no ar (~{alt_init:.0f}m AGL).")
                    warnings.append(f"   • Altitude recalibrada com referência de solo robusta.")
        
        # 3. Checa deriva de solo
        if "alt_m" in self.df_full.columns and len(self.df_full) >= 2:
            t = self.df_full["tempo_s"]
            alt = self.df_full["alt_m"]
            h0 = alt.iloc[0]
            hf = alt.iloc[-1]
            drift = hf - h0
            if abs(drift) > 5.0:
                warnings.append(f"⚠️ Deriva de solo detectada: {drift:+.2f} metros entre início e fim.")
                warnings.append(f"   • Recomendado: ativar 'Zerar deriva de solo'.")

        # 4. Checa glitches e anomalias físicas
        acc_cols = [c for c in ["accX_g", "accY_g", "accZ_g"] if c in self.df_full.columns]
        if len(acc_cols) == 3:
            acc_mag = np.sqrt(self.df_full[acc_cols[0]]**2 + self.df_full[acc_cols[1]]**2 + self.df_full[acc_cols[2]]**2)
            spikes_acc = int((acc_mag > 35.0).sum())
            if spikes_acc > 0:
                warnings.append(f"⚠️ Detectados {spikes_acc} pontos com aceleração espúria (>35g).")
                warnings.append(f"   • Ative 'Aplicar Filtro de Ruído & Glitches'.")
        
        if "alt_m" in self.df_full.columns:
            alt_diff = np.abs(np.diff(self.df_full["alt_m"], prepend=self.df_full["alt_m"].iloc[0]))
            spikes_alt = int((alt_diff > 30.0).sum())
            if spikes_alt > 0:
                warnings.append(f"⚠️ Detectados {spikes_alt} glitches de altitude (>30m/amostra).")
                warnings.append(f"   • Ative 'Aplicar Filtro de Ruído & Glitches'.")

        if not warnings:
            self.diag_list.addItem("✅ Telemetria saudável! Sem anomalias detectadas.")
        else:
            for w in warnings:
                self.diag_list.addItem(w)

    def apply_telemetry_filters(self, df):
        if df.empty:
            return df
            
        df_filtered = df.copy()
        
        # 1. Filtro de Interpolação para Dropouts (Valores exatamente 0.0)
        # Evitamos interpolar 'tempo_s'
        cols_to_interpolate = [c for c in df_filtered.columns if c != "tempo_s"]
        for c in cols_to_interpolate:
            if c in ["pressao_Pa", "temp_C"]:
                # Pressão e temperatura nunca devem ser exatamente zero em voo
                df_filtered.loc[df_filtered[c] == 0.0, c] = np.nan
            elif c == "alt_m":
                # Altitude caindo para 0.0 em pleno voo (fora da pista) é glitch
                t_start = self.sp_start.value()
                t_end = self.sp_end.value()
                df_filtered.loc[(df_filtered["tempo_s"] > t_start) & (df_filtered["tempo_s"] < t_end) & (df_filtered[c] == 0.0), c] = np.nan
            elif any(k in c.lower() for k in ["acc", "gyro", "mps2", "dps"]):
                # Aceleração e giroscópios caindo para exatamente 0.0 em voo
                df_filtered.loc[df_filtered[c] == 0.0, c] = np.nan
                
            # Interpola linearmente os NaNs e preenche as bordas
            if df_filtered[c].isna().any():
                df_filtered[c] = df_filtered[c].interpolate(method="linear").ffill().bfill()
        
        # 2. Filtro de Glitch e Suavização para Altitude (Rolling Median + Rolling Mean)
        if "alt_m" in df_filtered.columns:
            df_filtered["alt_m"] = df_filtered["alt_m"].rolling(window=5, min_periods=1, center=True).median()
            df_filtered["alt_m"] = df_filtered["alt_m"].rolling(window=5, min_periods=1, center=True).mean()

        # 3. Filtro de Glitch para Velocidade
        if "vel_kmph" in df_filtered.columns:
            df_filtered["vel_kmph"] = df_filtered["vel_kmph"].rolling(window=5, min_periods=1, center=True).median()

        # 4. Filtro de Glitch para Aceleração
        acc_cols = ["accX_g", "accY_g", "accZ_g"]
        if all(c in df_filtered.columns for c in acc_cols):
            for c in acc_cols:
                med = df_filtered[c].rolling(window=5, min_periods=1, center=True).median()
                diff = np.abs(df_filtered[c] - med)
                df_filtered.loc[diff > 10.0, c] = med
                df_filtered[c] = df_filtered[c].rolling(window=5, min_periods=1, center=True).mean()
                
        return df_filtered

    def run_reboot_estimation(self):
        if len(self.file_paths) < 2:
            QMessageBox.warning(self, "Aviso", "São necessários pelo menos 2 arquivos na lista para estimar o tempo de reboot.")
            return

        try:
            df1 = self._load_single_file(self.file_paths[0])
            df2 = self._load_single_file(self.file_paths[1])
            
            if df1.empty or df2.empty or "pressao_Pa" not in df1.columns or "tempo_s" not in df1.columns:
                QMessageBox.warning(self, "Aviso", "Os arquivos não contêm dados de pressão barométrica necessários para a estimativa.")
                return

            P0 = df1["pressao_Pa"].iloc[0]
            
            def calc_alt(P, P0):
                return 44330.0 * (1.0 - (P / P0)**(1.0/5.255))
                
            alt1 = calc_alt(df1["pressao_Pa"], P0)
            alt2 = calc_alt(df2["pressao_Pa"], P0)
            
            alt1_end = alt1.iloc[-1]
            alt2_start = alt2.iloc[0]
            alt_delta = alt1_end - alt2_start
            
            # Velocidade de descida no fim do primeiro arquivo
            if len(df1) >= 50:
                t_seg1 = df1["tempo_s"].iloc[-50:]
                alt_seg1 = alt1.iloc[-50:]
            else:
                t_seg1 = df1["tempo_s"]
                alt_seg1 = alt1
            dt1 = t_seg1.iloc[-1] - t_seg1.iloc[0]
            dalt1 = alt_seg1.iloc[0] - alt_seg1.iloc[-1]
            vy1 = dalt1 / dt1 if dt1 > 0.01 else 0.0

            # Velocidade de descida no início do segundo arquivo
            if len(df2) >= 50:
                t_seg2 = df2["tempo_s"].iloc[:50]
                alt_seg2 = alt2.iloc[:50]
            else:
                t_seg2 = df2["tempo_s"]
                alt_seg2 = alt2
            dt2 = t_seg2.iloc[-1] - t_seg2.iloc[0]
            dalt2 = alt_seg2.iloc[0] - alt_seg2.iloc[-1]
            vy2 = dalt2 / dt2 if dt2 > 0.01 else 0.0

            vy = None
            if vy1 > 0.5 and vy2 > 0.5:
                vy = (vy1 + vy2) / 2.0
            elif vy1 > 0.5:
                vy = vy1
            elif vy2 > 0.5:
                vy = vy2

            if vy is not None and vy > 0.0:
                est_gap = alt_delta / vy
                if 0.1 < est_gap < 120.0:
                    self.sp_gap.setValue(est_gap)
                    QMessageBox.information(
                        self, "Estimativa de Reboot",
                        f"Tempo de reboot estimado com sucesso baseado na física de queda:\n\n"
                        f"• Delta Altitude: {alt_delta:.2f} m\n"
                        f"• Velocidade de descida: {vy:.2f} m/s\n"
                        f"• Tempo estimado: {est_gap:.2f} s\n\n"
                        f"O valor foi atualizado nas configurações de conexão."
                    )
                    self.load_and_concatenate()
                    return
            
            QMessageBox.warning(
                self, "Aviso",
                "Não foi possível estimar o tempo de reboot (o foguete pode não estar em queda estável no momento da falha)."
            )
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao realizar estimativa física:\n{e}")

    def toggle_preview_cropped(self):
        if self.chk_preview_cropped.isChecked():
            self.region.setVisible(False)
        else:
            self.region.setVisible(True)
        self.plot_data()

    def plot_data(self):
        self.plot.clear()
        
        if not self.chk_preview_cropped.isChecked():
            self.plot.addItem(self.region)
            
        self.plot.addItem(self.vLine, ignoreBounds=True)
        self.plot.addItem(self.hLine, ignoreBounds=True)

        t_start = self.sp_start.value()
        t_end = self.sp_end.value()

        # Desenha faixas indicando as áreas onde houve reinicialização (gaps)
        for g_start, g_end in self.gap_regions:
            if self.chk_preview_cropped.isChecked():
                if g_end < t_start or g_start > t_end:
                    continue
                display_start = max(t_start, g_start)
                display_end = min(t_end, g_end)
            else:
                display_start = g_start
                display_end = g_end

            r = pg.LinearRegionItem(values=[display_start, display_end], movable=False,
                                    brush=pg.mkBrush(255, 165, 0, 50), pen=pg.mkPen(255, 165, 0, 100))
            self.plot.addItem(r)

        if self.df is None or self.df.empty:
            return

        # Filtra os dados temporariamente para plotagem se o preview estiver ativado
        if self.chk_preview_cropped.isChecked():
            df_plot = self.df[(self.df["tempo_s"] >= t_start) & (self.df["tempo_s"] <= t_end)].copy()
        else:
            df_plot = self.df.copy()

        if df_plot.empty:
            return

        if self.chk_apply_filters.isChecked():
            df_plot = self.apply_telemetry_filters(df_plot)

        t = df_plot["tempo_s"]
        alt = df_plot["alt_m"].copy() if "alt_m" in df_plot.columns else None

        # Aplica correção de deriva linear de solo se ativado
        if alt is not None and self.chk_zero_drift.isChecked() and len(t) >= 2:
            idx_start = np.abs(df_plot["tempo_s"] - t_start).idxmin()
            idx_end = np.abs(df_plot["tempo_s"] - t_end).idxmin()
            
            h0 = df_plot["alt_m"].loc[idx_start]
            hf = df_plot["alt_m"].loc[idx_end]
            
            corrected_alt = np.zeros_like(alt)
            mask_flight = (t >= t_start) & (t <= t_end)
            mask_before = t < t_start
            mask_after = t > t_end
            
            corrected_alt[mask_flight] = alt[mask_flight] - (h0 + ((t[mask_flight] - t_start) / (t_end - t_start)) * (hf - h0))
            corrected_alt[mask_before] = 0.0
            corrected_alt[mask_after] = 0.0
            alt = pd.Series(corrected_alt, index=alt.index)

        if self.chk_alt.isChecked() and alt is not None:
            self.plot.plot(t.to_numpy(), alt.to_numpy(), pen="b", name="Altitude")

        if self.chk_vel.isChecked() and "vel_kmph" in df_plot.columns:
            vel_ms = df_plot["vel_kmph"] / 3.6
            self.plot.plot(t.to_numpy(), vel_ms.to_numpy(), pen="g", name="Velocidade (m/s)")

        if self.chk_acc.isChecked():
            acc_mag = np.sqrt(df_plot["accX_g"]**2 + df_plot["accY_g"]**2 + df_plot["accZ_g"]**2) if all(c in df_plot.columns for c in ["accX_g","accY_g","accZ_g"]) else np.zeros(len(df_plot))
            self.plot.plot(t.to_numpy(), np.array(acc_mag), pen="r", name="Aceleração (g)")

        # Ajusta o zoom do eixo X se o preview estiver ativado
        if self.chk_preview_cropped.isChecked():
            self.plot.setXRange(t_start, t_end)
        else:
            self.plot.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis)

    def auto_detect_flight(self):
        if self.df_full is None or self.df_full.empty:
            QMessageBox.warning(self, "Aviso", "Nenhum dado carregado.")
            return

        t = self.df_full["tempo_s"]
        alt = self.df_full["alt_m"].copy() if "alt_m" in self.df_full.columns else pd.Series(np.zeros(len(t)))

        # Filtro de mediana robusto para remover glitches de altimetro antes da detecção
        alt_smooth = alt.rolling(window=15, min_periods=1, center=True).median()

        # Mediana das primeiras 100 amostras estáveis como altitude de solo base
        alt_ground = alt_smooth.iloc[:min(100, len(alt_smooth))].median()

        # Decolagem: 15m acima da altitude de solo base
        launch_indices = np.where(alt_smooth > (alt_ground + 15.0))[0]
        if len(launch_indices) > 0:
            idx_start = launch_indices[0]
        else:
            idx_start = 0

        idx_apogee = alt_smooth.idxmax()

        # Pouso: retorna a menos de 10m acima da altitude de solo base após apogeu
        after_apogee = alt_smooth.iloc[idx_apogee:]
        landing_indices = np.where(after_apogee < (alt_ground + 10.0))[0]
        if len(landing_indices) > 0:
            idx_end = idx_apogee + landing_indices[0]
        else:
            idx_end = len(self.df_full) - 1

        t_start = max(float(t.min()), float(t.iloc[idx_start]) - 10.0)
        t_end = min(float(t.max()), float(t.iloc[idx_end]) + 15.0)

        if t_start >= t_end:
            t_start = float(t.min())
            t_end = float(t.max())

        self.sp_start.setValue(t_start)
        self.sp_end.setValue(t_end)
        self.region.setRegion([t_start, t_end])

    def apply_crop(self):
        if self.df_full is None:
            QMessageBox.warning(self, "Aviso", "Nenhum dado carregado.")
            return
        t_start = self.sp_start.value()
        t_end = self.sp_end.value()

        self.df = self.df_full[(self.df_full["tempo_s"] >= t_start) & (self.df_full["tempo_s"] <= t_end)].copy()
        self.plot_data()

    def reset_crop(self):
        if self.df_full is None:
            return
        self.df = self.df_full.copy()

        t_min = float(self.df["tempo_s"].min())
        t_max = float(self.df["tempo_s"].max())

        self.sp_start.setValue(t_min)
        self.sp_end.setValue(t_max)
        self.region.setRegion([t_min, t_max])
        self.plot_data()

    def export_data(self):
        if self.df is None or self.df.empty:
            QMessageBox.warning(self, "Aviso", "Não há dados para exportar.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Salvar Dados Tratados", "", "Text Files (*.txt)")
        if not path:
            return

        try:
            df_export = self.df.copy()
            
            # Se a filtragem de ruído/glitches estiver ativada na tela, exporta com os filtros
            if self.chk_apply_filters.isChecked():
                df_export = self.apply_telemetry_filters(df_export)

            if self.chk_zero_drift.isChecked() and "alt_m" in df_export.columns and len(df_export) >= 2:
                t = df_export["tempo_s"]
                t_start = self.sp_start.value()
                t_end = self.sp_end.value()
                
                t_start = max(float(t.min()), min(t_start, float(t.max())))
                t_end = max(t_start + 1.0, min(t_end, float(t.max())))
                
                idx_start = np.abs(t - t_start).idxmin()
                idx_end = np.abs(t - t_end).idxmin()
                
                alt = df_export["alt_m"]
                h0 = alt.loc[idx_start]
                hf = alt.loc[idx_end]
                
                corrected_alt = np.zeros_like(alt)
                mask_flight = (t >= t_start) & (t <= t_end)
                mask_before = t < t_start
                mask_after = t > t_end
                
                corrected_alt[mask_flight] = alt[mask_flight] - (h0 + ((t[mask_flight] - t_start) / (t_end - t_start)) * (hf - h0))
                corrected_alt[mask_before] = 0.0
                corrected_alt[mask_after] = 0.0
                df_export["alt_m"] = corrected_alt

            df_export.to_csv(path, sep="\t", index=False)
            QMessageBox.information(self, "Sucesso", f"Dados exportados com sucesso para:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao exportar arquivo:\n{e}")

