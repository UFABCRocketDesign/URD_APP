from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel,
    QGridLayout, QGroupBox, QCheckBox, QMessageBox, QHBoxLayout, QScrollArea, QToolTip, 
    QDialog, QFormLayout, QDialogButtonBox, QLineEdit, QInputDialog
)
from PySide6.QtGui import (QCursor)

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

COLOR_MAP = {
    "Kgf.avg.cell": "b",        # azul - empuxo
    "psi.avg.tdt": "r",         # vermelho - pressão
    "adc.raw.cell": "g",        # verde - célula bruta
    "adc.avg.cell": "m",        # magenta - célula média
    "adc.raw.tdt": "c",         # ciano - transdutor bruto
    "adc.avg.tdt": "orange",         # preto - transdutor médio
}

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

        # Gráfico
        self.plot = pg.PlotWidget(title="Análise do Teste Estático")
        self.plot.addLegend()
        self.plot.showGrid(x=True, y=True)
        root.addWidget(self.plot, stretch=1)

        # Label do cursor
        self.label_hover = QLabel("Cursor: -")
        root.addWidget(self.label_hover)

        # Botões de ações
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

        # Conexão do cursor 
        self.plot.scene().sigMouseMoved.connect(self._mouseMoved)

        self.curves = {}
        self.df = None

    def cut_data(self):
        if self.df is None:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return

        # pega intervalo
        t_min, ok1 = QInputDialog.getDouble(self, "Corte de Dados", "Tempo inicial (s):", 0, 0)
        if not ok1:
            return
        t_max, ok2 = QInputDialog.getDouble(self, "Corte de Dados", "Tempo final (s):", 0, 0)
        if not ok2:
            return

        # validação
        if t_min <= 0 or t_max <= 0 or t_min >= t_max:
            QMessageBox.critical(self, "Erro", "Intervalo inválido.")
            return

        t_col = "tempo.s"
        if t_col not in self.df.columns:
            QMessageBox.critical(self, "Erro", f"Coluna '{t_col}' não encontrada.")
            return

        df_cut = self.df[(self.df[t_col] >= t_min) & (self.df[t_col] <= t_max)]
        if df_cut.empty:
            QMessageBox.critical(self, "Erro", "Nenhum dado dentro do intervalo selecionado.")
            return

        # salvar com novo nome
        path, _ = QFileDialog.getSaveFileName(self, "Salvar Arquivo Cortado", "", "Text Files (*.txt)")
        if not path:
            return

        if not path.endswith(".txt"):
            path += ".txt"
        if "_CUT" not in path:
            base, ext = path.rsplit(".", 1)
            path = f"{base}_CUT.{ext}"

        try:
            df_cut.to_csv(path, sep="\t", index=False)
            QMessageBox.information(self, "Sucesso", f"Arquivo cortado salvo em:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao salvar arquivo:\n{e}")



    def calibrate_data(self):
        if self.df is None:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Calibração")
        layout = QFormLayout(dialog)

        # ---- Empuxo ----
        layout.addRow(QLabel("<b>Empuxo</b>"))
        adc_i_cell_edit = QLineEdit(); layout.addRow("ADC inicial (massa 0):", adc_i_cell_edit)
        adc_f_cell_edit = QLineEdit(); layout.addRow("ADC final (massa com corpo de prova):", adc_f_cell_edit)
        peso_f_cell_edit = QLineEdit(); layout.addRow("Peso corpo de prova (kgf):", peso_f_cell_edit)

        # ---- Pressão ----
        layout.addRow(QLabel("<b>Pressão</b>"))
        adc_i_tdt_edit = QLineEdit(); layout.addRow("ADC inicial transdutor (0 psi):", adc_i_tdt_edit)
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
            adc_45v = float(adc_45v_edit.text() or 0)
        except ValueError:
            QMessageBox.critical(self, "Erro", "Valores inválidos.")
            return

        df_calib = self.df.copy()

        # ---- Calibração Empuxo ----
        if adc_i_cell != 0 and adc_f_cell != 0 and peso_f_cell != 0:
            m_cell = peso_f_cell / (adc_f_cell - adc_i_cell)
            df_calib["Kgf.calibrado"] = (df_calib["adc.raw.cell"] - adc_i_cell) * m_cell
            df_calib["N.calibrado"] = df_calib["Kgf.calibrado"] * 9.80665

        # ---- Calibração Pressão ----
        if adc_i_tdt != 0 and adc_45v != 0 and adc_45v > adc_i_tdt:
            m_tdt = 500 / (adc_45v - adc_i_tdt)
            psi_values = (df_calib["adc.avg.tdt"] - adc_i_tdt) * m_tdt
            psi_values = psi_values.clip(lower=0, upper=500)  # força limite
            df_calib["psi.calibrado"] = psi_values
            df_calib["Pa.calibrado"] = df_calib["psi.calibrado"] * 6894.76
            df_calib["atm.calibrado"] = df_calib["psi.calibrado"] / 14.696
            df_calib["bar.calibrado"] = df_calib["psi.calibrado"] / 14.5038

        # salvar com novo nome
        path, _ = QFileDialog.getSaveFileName(self, "Salvar Arquivo Calibrado", "", "Text Files (*.txt)")
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


    def save_screenshot(self):
        # Captura toda a página (StaticAnalysisPage)
        pixmap = self.grab()

        # Caixa de diálogo para salvar
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar análise como imagem", "", "PNG Image (*.png)"
        )
        if not path:
            return
        if not path.endswith(".png"):
            path += ".png"

        # Salva em PNG
        pixmap.save(path, "PNG")
        QMessageBox.information(self, "Sucesso", f"Imagem salva em:\n{path}")


    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir Arquivo", "", "Text Files (*.txt)")
        if not path:
            return

        try:
            df = pd.read_csv(path, sep="\t")
            if not df.columns.str.contains("tempo.s").any():
                # tenta de novo pulando a primeira linha
                df = pd.read_csv(path, sep="\t", skiprows=1)
        except Exception as e:
            QMessageBox.critical(self, "Erro", "Arquivo inválido: coluna 'tempo.s' não encontrada.\n {e}")
            return

        if "tempo.s" not in df.columns:
            QMessageBox.critical(self, "Erro", "Arquivo inválido: coluna 'tempo.s' não encontrada.")
            return

        self.df = df
        self.analyze_data()

    def analyze_data(self):
        df = self.df

        # garante que tempo seja numérico
        t = pd.to_numeric(df["tempo.s"], errors="coerce")

        # Se existir calibrado, usa ele, senão usa o normal
        if "Kgf.calibrado" in df:
            thrust = df["Kgf.calibrado"]
        elif "Kgf.avg.cell" in df:
            thrust = df["Kgf.avg.cell"]
        else:
            thrust = None

        if "psi.calibrado" in df:
            press = df["psi.calibrado"]
        elif "psi.avg.tdt" in df:
            press = df["psi.avg.tdt"]
        else:
            press = None

        max_thrust = thrust.max() if thrust is not None else 0
        max_press = press.max() if press is not None else 0

        # tempo total: diferença entre último e primeiro tempo válidos
        t_valid = t.dropna()
        t_total = t_valid.iloc[-1] - t_valid.iloc[0] if not t_valid.empty else 0

        burn_time = 0
        if thrust is not None and not thrust.dropna().empty:
            peak = thrust.max(skipna=True)
            threshold = 0.05 * peak

            # índices onde o empuxo > 10% do pico
            valid_idx = np.where(thrust.to_numpy() > threshold)[0]

            if len(valid_idx) > 0:
                start = valid_idx[0]   # início da queima
                end = valid_idx[-1]    # fim da queima
                burn_time = t.iloc[end] - t.iloc[start]

                # desenha linhas verticais no gráfico
                line_start = pg.InfiniteLine(
                    pos=t.iloc[start], angle=90,
                    pen=pg.mkPen('g', width=2, style=Qt.DashLine)
                )
                line_end = pg.InfiniteLine(
                    pos=t.iloc[end], angle=90,
                    pen=pg.mkPen('r', width=2, style=Qt.DashLine)
                )

            else:
                burn_time = 0



        # preencher resumo
        self.clear_layout(self.grid)
        stats = {
            "Máx. Empuxo (kgf)": max_thrust,
            "Máx. Pressão (psi)": max_press,
            "Tempo Total (s)": t_total,
            "Tempo Queima (s)": burn_time,
        }
        row = 0
        for k, v in stats.items():
            box = QGroupBox(k)
            lay = QVBoxLayout(box)
            lay.addWidget(QLabel(f"{v:.2f}"))
            self.grid.addWidget(box, row // 2, row % 2)
            row += 1

        # plota curvas permitidas
        self.plot.clear()
        self.plot.addLegend()
        self.curves.clear()
        self.plot.addItem(line_start)
        self.plot.addItem(line_end)

        allowed_cols = [
            "adc.raw.cell", "adc.avg.cell",
            "adc.raw.tdt", "adc.avg.tdt",
            "Kgf.avg.cell", "psi.avg.tdt",
            "Kgf.calibrado", "psi.calibrado"
        ]

        COLOR_MAP = {
            # --- Célula de carga ---
            "adc.raw.cell": "g",
            "adc.avg.cell": "m",
            "Kgf.avg.cell": "b",
            "Kgf.calibrado": "navy",

            # --- Transdutor ---
            "adc.raw.tdt": "y",
            "adc.avg.tdt": "orange",
            "psi.avg.tdt": "r",
            "psi.calibrado": "purple",
        }


        for col, color in COLOR_MAP.items():
            if col not in df.columns:
                continue

            # # Linha
            # line = self.plot.plot(
            #     t, df[col],
            #     pen=pg.mkPen(color=color, width=2),
            #     name=col  # <- entra na legenda apenas uma vez
            # )

            # Bolinhas (sem adicionar na legenda)
            # scatter = pg.ScatterPlotItem(
            #     x=t, y=df[col],
            #     brush=pg.mkBrush(color),
            #     size=5,
            #     pen=pg.mkPen(color),
            #     name=None  # não aparece na legenda
            # )
            # self.plot.addItem(scatter)

            curve = self.plot.plot(
                t, df[col],
                pen=pg.mkPen(color=color, width=2),  # linha
                symbol='o',                          # bolinhas
                symbolSize=5,
                symbolBrush=color,
                name=col  # aparece na legenda apenas 1 vez
            )

            self.curves[col] = curve

            # # guarda referência
            # self.curves[col] = (line, scatter)




    def _mouseMoved(self, evt):
        pos = evt
        if self.plot.sceneBoundingRect().contains(pos):
            mousePoint = self.plot.plotItem.vb.mapSceneToView(pos)
            self.label_hover.setText(f"Cursor: t={mousePoint.x():.2f}s, y={mousePoint.y():.2f}")

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()


