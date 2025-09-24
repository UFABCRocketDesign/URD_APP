# main.py
import sys, os
os.system("cls")

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QToolButton,
    QVBoxLayout, QGridLayout, QStackedWidget, QToolBar, QStatusBar,
    QSizePolicy, QPushButton, QSplitter, QCheckBox
)



# >>> IMPORTA AS PÁGINAS <<<
from views.net_manager import NetManager
from views.gs_flight_single import GSFlightSinglePage
from views.maps_manager import MapsManagerPage
from views.gs_static_test import GSTestEstaticoPage
from views.data_analysis import DataAnalysisPage
from views.simulator import SimuladorApp




APP_TITLE = "URD — App"

def resource_path(relative_path):
    """Acha o caminho mesmo dentro do .exe"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
# --------- páginas placeholder ---------
def make_placeholder(title: str) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    h = QLabel(title)
    h.setAlignment(Qt.AlignCenter)
    h.setStyleSheet("font-size: 22px; font-weight: 600; color: black;")
    lay.addStretch(1)
    lay.addWidget(h)
    lay.addStretch(1)
    return w


def make_gs_dual_placeholder() -> QWidget:
    w = QWidget()
    root = QVBoxLayout(w)
    splitter = QSplitter(Qt.Horizontal, w)
    left = make_placeholder("GS Flight — Left (placeholder)")
    right = make_placeholder("GS Flight — Right (placeholder)")
    splitter.addWidget(left)
    splitter.addWidget(right)
    splitter.setSizes([1, 1])
    root.addWidget(splitter)
    return w


def make_general_settings(main_window) -> QWidget:
    """Página de configurações gerais."""
    w = QWidget()
    lay = QVBoxLayout(w)

    lbl = QLabel("Configurações Gerais")
    lbl.setStyleSheet("font-size:18px; font-weight:600; margin-bottom:12px;")
    lay.addWidget(lbl)

    # Toggle para forçar offline
    chk_offline = QCheckBox("Forçar modo offline")
    lay.addWidget(chk_offline)
    chk_offline.setChecked(main_window.netManager.forceOffline)

    def toggle_offline():
        if chk_offline.isChecked():
            # ativa offline forçado
            main_window.netManager.set_force_offline(True)
        else:
            # desativa offline forçado
            main_window.netManager.set_force_offline(False)

        # atualiza label de status imediatamente
        main_window._update_net_label()

        # notifica páginas dependentes
        if hasattr(main_window.page_gs_single, "onNetChanged"):
            main_window.page_gs_single.onNetChanged(main_window.netManager.get_status())
        if hasattr(main_window.page_maps, "onNetChanged"):
            main_window.page_maps.onNetChanged(main_window.netManager.get_status())

    chk_offline.toggled.connect(toggle_offline)

    lay.addStretch(1)
    return w




class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 750)

        self.setWindowIcon(QIcon("logo.ico"))

        # NetManager único e compartilhado
        self.netManager = NetManager()

        # Timer net
        self.timer_net = QTimer(self)
        self.timer_net.timeout.connect(self._check_net)
        self.timer_net.start(2000)

        # Toolbar
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setMinimumHeight(50)
        self.addToolBar(tb)

        self.btn_back = QToolButton()
        self.btn_back.setText("←")
        self.btn_back.setMinimumSize(50, 50)
        self.btn_back.setStyleSheet("""
            QToolButton {
                font-size: 28px;
                padding: 12px;
                border-radius: 8px;
            }
            QToolButton:hover {
                background: rgba(230,230,230,200);
            }
        """)
        tb.addWidget(self.btn_back)

        spacer1 = QWidget()
        spacer1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer1)

        self.lbl_net = QLabel()
        self.lbl_net.setAlignment(Qt.AlignCenter)
        tb.addWidget(self.lbl_net)
        self._update_net_label()

        spacer2 = QWidget()
        spacer2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer2)

        self.btn_settings = QToolButton()
        self.btn_settings.setText("⋮")
        self.btn_settings.setMinimumSize(50, 50)
        self.btn_settings.setStyleSheet("""
            QToolButton {
                font-size: 28px;
                padding: 12px;
                border-radius: 8px;
            }
            QToolButton:hover {
                background: rgba(230,230,230,200);
            }
        """)
        tb.addWidget(self.btn_settings)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Stack
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # Páginas fixas
        self.page_home = self._build_home()
        self.page_general_cfg = make_general_settings(self)

        self.idx_home = self.stack.addWidget(self.page_home)
        self.idx_general_cfg = self.stack.addWidget(self.page_general_cfg)

        # Lazy pages (criadas quando abrir)
        self.page_gs_single = None
        self.page_gs_dual = None
        self.page_static = None
        self.page_analysis = None
        self.page_sim = None
        self.page_maps = None

        # Botões toolbar
        self.btn_back.clicked.connect(lambda: self._go_page("home", "Home"))
        self.btn_settings.clicked.connect(lambda: self._go_page("config", "Configurações"))

        self._go_page("home", "Home")

    # ---------- Home ----------
    def _build_home(self) -> QWidget:
        home = QWidget()
        root = QVBoxLayout(home)

        logo = QLabel()
        pix = QPixmap(resource_path("logo.png"))
        self.setWindowIcon(QIcon(resource_path("logo.ico")))

        if not pix.isNull():
            pix = pix.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo.setPixmap(pix)
        logo.setAlignment(Qt.AlignCenter)

        grid = QGridLayout()
        btn_gs_single = QPushButton("GS Flight (Single)")
        btn_gs_dual   = QPushButton("GS Flight (Dual)")
        btn_static    = QPushButton("GS Teste Estático")
        btn_analysis = QPushButton("Data Analysis")
        btn_sim       = QPushButton("Simulador")
        btn_maps      = QPushButton("Gerenciar Mapas")

        for b in [btn_gs_single, btn_gs_dual, btn_static, btn_analysis, btn_sim, btn_maps]:
            grid.addWidget(b)
            b.setMinimumHeight(50)

        content = QVBoxLayout()
        content.addStretch(1)
        content.addWidget(logo, alignment=Qt.AlignCenter)
        content.addLayout(grid)
        content.addStretch(1)
        root.addLayout(content)

        btn_gs_single.clicked.connect(lambda: self._go_page("gs_single", "GS Flight (Single)"))
        btn_gs_dual.clicked.connect(lambda: self._go_page("gs_dual", "GS Flight (Dual)"))
        btn_static.clicked.connect(lambda: self._go_page("static", "GS Teste Estático"))
        btn_analysis.clicked.connect(lambda: self._go_page("analysis", "Data Analysis"))
        btn_sim.clicked.connect(lambda: self._go_page("sim", "Simulador"))
        btn_maps.clicked.connect(lambda: self._go_page("maps", "Gerenciar Mapas"))

        return home




    # ---------- Navegação ----------
    def _go_page(self, name: str, msg: str):
        """Cria, pausa e alterna páginas conforme necessário"""

        # Pausa todas páginas antes de trocar
        self._pause_all()

        # Decide qual abrir
        if name == "home":
            self.stack.setCurrentIndex(self.idx_home)

        elif name == "config":
            self.stack.setCurrentIndex(self.idx_general_cfg)

        elif name == "gs_single":
            if self.page_gs_single is None:
                self.page_gs_single = GSFlightSinglePage(self.netManager, parent=self)
                self.idx_gs_single = self.stack.addWidget(self.page_gs_single)
                self.netManager.netChanged.connect(self.page_gs_single.onNetChanged)
            self.stack.setCurrentWidget(self.page_gs_single)
            self.page_gs_single.resume()

        elif name == "gs_dual":
            if self.page_gs_dual is None:
                self.page_gs_dual = make_gs_dual_placeholder()
                self.idx_gs_dual = self.stack.addWidget(self.page_gs_dual)
            self.stack.setCurrentWidget(self.page_gs_dual)

        elif name == "static":
            if self.page_static is None:
                self.page_static = GSTestEstaticoPage(self.netManager, parent=self)
                self.idx_static = self.stack.addWidget(self.page_static)
                # se quiser, também conecta com eventos de rede
                # self.netManager.netChanged.connect(self.page_static.onNetChanged)
            self.stack.setCurrentWidget(self.page_static)
            if hasattr(self.page_static, "resume"):
                self.page_static.resume()

        elif name == "analysis":
            if self.page_analysis is None:
                self.page_analysis = DataAnalysisPage(parent=self)
                self.idx_analysis = self.stack.addWidget(self.page_analysis)
            self.stack.setCurrentWidget(self.page_analysis)


        elif name == "sim":
            if self.page_sim is None:
                self.page_sim = SimuladorApp()  
                self.idx_sim = self.stack.addWidget(self.page_sim)
            self.stack.setCurrentWidget(self.page_sim)

        elif name == "maps":
            # sempre recriar
            if self.page_maps is not None:
                self.stack.removeWidget(self.page_maps)
                self.page_maps.deleteLater()
                self.page_maps = None
            self.page_maps = MapsManagerPage(self.netManager.get_status(), parent=self)
            self.idx_maps = self.stack.addWidget(self.page_maps)
            self.netManager.netChanged.connect(self.page_maps.onNetChanged)
            self.stack.setCurrentWidget(self.page_maps)
            if hasattr(self.page_maps, "resume"):
                self.page_maps.resume()

        # Status
        self.status.showMessage(msg, 2000)

    def _pause_all(self):
        """Pausa timers/render de todas as páginas pesadas"""
        for p in [self.page_gs_single, self.page_maps]:
            if p and hasattr(p, "pause"):
                p.pause()


    # ---------- NET ----------
    def _check_net(self):
        """Chamado a cada 5s pelo timer"""
        changed = self.netManager.update()
        if changed:
            print(f"[DEBUG][Main] Internet mudou: {self.netManager.get_status()}")
            self._update_net_label()

            # notifica páginas
            if hasattr(self.page_gs_single, "onNetChanged"):
                self.page_gs_single.onNetChanged(self.netManager.get_status())
            if hasattr(self.page_maps, "onNetChanged"):
                self.page_maps.onNetChanged(self.netManager.get_status())

    def _update_net_label(self):
        """Atualiza texto e cor da label do status"""
        if self.netManager.forceOffline:
            self.lbl_net.setText("Offline Mode")
            self.lbl_net.setStyleSheet("color:orange; font-weight:600;")
        elif self.netManager.hasNet:
            self.lbl_net.setText("Online Mode")
            self.lbl_net.setStyleSheet("color:green; font-weight:600;")
        else:
            self.lbl_net.setText("Offline Mode")
            self.lbl_net.setStyleSheet("color:red; font-weight:600;")

def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
