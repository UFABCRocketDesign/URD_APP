import sys, os, time, platform, psutil
os.system("cls" if os.name == "nt" else "clear")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QToolButton,
    QVBoxLayout, QGridLayout, QStackedWidget, QToolBar, QStatusBar,
    QSizePolicy, QPushButton, QFrame, QScrollArea
)

from views.net_manager import NetManager
from views.gs_flight_single import GSFlightSinglePage
from views.gs_flight_rasp import GSFlightRaspPage
from views.maps_manager import MapsManagerPage
from views.gs_static_test import GSTestEstaticoPage
from views.data_analysis import DataAnalysisPage
from views.simulator import URDSimulatorPage
from views.general_settings_dialog import GeneralSettingsDialog

APP_TITLE = "URD — App"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path: str) -> str:
    return os.path.join(BASE_DIR, relative_path)

def get_system_temperature() -> str:
    os_system = platform.system().lower()

    # Linux / Raspberry Pi
    if os_system == "linux":
        thermal_path = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(thermal_path):
            try:
                with open(thermal_path, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                temp_c = int(raw) / 1000.0
                return f"{temp_c:.1f}°C"
            except Exception:
                pass

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for entries in temps.values():
                    for entry in entries:
                        if getattr(entry, "current", None) is not None:
                            return f"{entry.current:.1f}°C"
        except Exception:
            pass

        return "N/A"

    # Windows
    if os_system == "windows":
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for entries in temps.values():
                    for entry in entries:
                        if getattr(entry, "current", None) is not None:
                            return f"{entry.current:.1f}°C"
        except Exception:
            pass

        return "N/A"

    return "N/A"


def get_system_secondary_info() -> str:
    os_system = platform.system().lower()

    # Windows -> bateria
    if os_system == "windows":
        try:
            batt = psutil.sensors_battery()
            if batt is not None:
                return f"Bat: {batt.percent:.0f}%"
        except Exception:
            pass
        return "Bat: N/A"

    # Linux / Raspberry -> RAM
    if os_system == "linux":
        try:
            ram = psutil.virtual_memory()
            return f"RAM: {ram.percent:.0f}%"
        except Exception:
            pass
        return "RAM: N/A"

    return "N/A"

def play_startup_chime():
    import platform
    import time

    os_system = platform.system().lower()

    try:
        if os_system == "windows":
            import winsound

            notes = [
                (780, 30),
                (1040, 45),
            ]

            for freq, dur in notes:
                winsound.Beep(freq, dur)

        elif os_system == "linux":
            from gpiozero import Buzzer

            buzzer = None
            try:
                buzzer = Buzzer(6)

                steps = [70, 55, 40, 30]
                for ms in steps:
                    buzzer.on()
                    time.sleep(ms / 1000.0)
                    buzzer.off()
                    time.sleep(0.015)

            finally:
                if buzzer is not None:
                    try:
                        buzzer.off()
                    except Exception:
                        pass
                    try:
                        buzzer.close()
                    except Exception:
                        pass

    except Exception:
        pass
    
def wrap_in_scroll(widget: QWidget) -> QWidget:
    page = QWidget()
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(widget)

    outer.addWidget(scroll)
    return page


def build_dark_grey_stylesheet() -> str:
    return """
    QMainWindow, QWidget {
        background-color: #2b2b2b;
        color: #e8e8e8;
        font-size: 12px;
    }

    QToolBar {
        background-color: #3a3a3a;
        border: none;
        spacing: 6px;
        padding: 4px 8px;
    }

    QToolBar QWidget {
        background: transparent;
    }

    QStatusBar {
        background-color: #2b2b2b;
        color: #cfcfcf;
        border-top: 1px solid #3a3a3a;
    }

    QLabel {
        color: #e8e8e8;
        background: transparent;
    }

    QPushButton, QToolButton {
        background-color: #3a3a3a;
        color: #f2f2f2;
        border: 1px solid #4a4a4a;
        border-radius: 8px;
        padding: 6px 10px;
    }

    QPushButton:hover, QToolButton:hover {
        background-color: #7b2cff;
        border: 1px solid #7b2cff;
        color: #ffffff;
    }

    QPushButton:pressed, QToolButton:pressed {
        background-color: #5f1fd1;
        border: 1px solid #5f1fd1;
        color: #ffffff;
    }

    QPlainTextEdit, QTextEdit {
        background-color: #111111;
        color: #dddddd;
        border: 1px solid #444444;
        border-radius: 8px;
    }

    QLineEdit, QComboBox {
        background-color: #353535;
        color: #e8e8e8;
        border: 1px solid #4a4a4a;
        border-radius: 8px;
        padding: 4px 6px;
    }

    QLineEdit:focus, QComboBox:focus {
        border: 1px solid #7b2cff;
    }

    QGroupBox {
        border: 1px solid #4a4a4a;
        border-radius: 10px;
        margin-top: 10px;
        padding-top: 10px;
        font-weight: 600;
        color: #f0f0f0;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px 0 4px;
    }

    QMenu {
        background-color: #2f2f2f;
        color: #f0f0f0;
        border: 1px solid #4a4a4a;
    }

    QMenu::item:selected {
        background-color: #7b2cff;
        color: #ffffff;
    }

    QCheckBox {
        color: #f0f0f0;
        background: transparent;
    }

    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 1px solid #000000;
        border-radius: 4px;
        background: #353535;
    }

    QCheckBox::indicator:hover {
        border: 1px solid #7b2cff;
        background: #4a3a66;
    }

    QCheckBox::indicator:checked {
        background: #7b2cff;
        border: 1px solid #000000;
        image: url(:/qt-project.org/styles/commonstyle/images/checkbox_checked.png);
    }

    QCheckBox::indicator:checked:hover {
        background: #8d46ff;
        border: 1px solid #000000;
        image: url(:/qt-project.org/styles/commonstyle/images/checkbox_checked.png);
    }

    QScrollArea {
        border: none;
        background: transparent;
    }

    QScrollBar:vertical, QScrollBar:horizontal {
        background: #232323;
    }
    """


def build_light_stylesheet() -> str:
    return """
    QMainWindow, QWidget {
        background-color: #f3f3f3;
        color: #202020;
        font-size: 12px;
    }

    QToolBar {
        background-color: #e7e7e7;
        border: none;
        spacing: 6px;
        padding: 4px 8px;
    }

    QToolBar QWidget {
        background: transparent;
    }

    QStatusBar {
        background-color: #efefef;
        color: #404040;
        border-top: 1px solid #d0d0d0;
    }

    QLabel {
        color: #202020;
        background: transparent;
    }

    QPushButton, QToolButton {
        background-color: #ffffff;
        color: #202020;
        border: 1px solid #cfcfcf;
        border-radius: 8px;
        padding: 6px 10px;
    }

    QPushButton:hover, QToolButton:hover {
        background-color: #7b2cff;
        border: 1px solid #7b2cff;
        color: #ffffff;
    }

    QPushButton:pressed, QToolButton:pressed {
        background-color: #5f1fd1;
        border: 1px solid #5f1fd1;
        color: #ffffff;
    }

    QPlainTextEdit, QTextEdit {
        background-color: #ffffff;
        color: #222222;
        border: 1px solid #d2d2d2;
        border-radius: 8px;
    }

    QLineEdit, QComboBox {
        background-color: #ffffff;
        color: #202020;
        border: 1px solid #d0d0d0;
        border-radius: 8px;
        padding: 4px 6px;
    }

    QLineEdit:focus, QComboBox:focus {
        border: 1px solid #7b2cff;
    }

    QGroupBox {
        border: 1px solid #d0d0d0;
        border-radius: 10px;
        margin-top: 10px;
        padding-top: 10px;
        font-weight: 600;
        color: #202020;
        background-color: #fafafa;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px 0 4px;
    }

    QMenu {
        background-color: #ffffff;
        color: #202020;
        border: 1px solid #d0d0d0;
    }

    QMenu::item:selected {
        background-color: #7b2cff;
        color: #ffffff;
    }

    QCheckBox {
        color: #202020;
        background: transparent;
    }

    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 1px solid #000000;
        border-radius: 4px;
        background: #ffffff;
    }

    QCheckBox::indicator:hover {
        border: 1px solid #7b2cff;
        background: #efe5ff;
    }

    QCheckBox::indicator:checked {
        background: #7b2cff;
        border: 1px solid #000000;
        image: url(:/qt-project.org/styles/commonstyle/images/checkbox_checked.png);
    }

    QCheckBox::indicator:checked:hover {
        background: #8d46ff;
        border: 1px solid #000000;
        image: url(:/qt-project.org/styles/commonstyle/images/checkbox_checked.png);
    }

    QScrollArea {
        border: none;
        background: transparent;
    }

    QScrollBar:vertical, QScrollBar:horizontal {
        background: #e2e2e2;
    }
    """


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 750)
        self.setWindowIcon(QIcon(resource_path("logo.ico")))

        self._light_theme_enabled = False

        self.netManager = NetManager()
        self.netManager.netChanged.connect(lambda _status: self._update_net_label())

        self.timer_net = QTimer(self)
        self.timer_net.timeout.connect(self._check_net)
        self.timer_net.start(2000)
        
        self.timer_sysinfo = QTimer(self)
        self.timer_sysinfo.timeout.connect(self._update_system_info)
        self.timer_sysinfo.start(5000)

        # Toolbar
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setMinimumHeight(44)
        tb.setMaximumHeight(44)
        self.addToolBar(tb)

        self.btn_back = QToolButton()
        self.btn_back.setText("←")
        self.btn_back.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_back.setMinimumSize(38, 34)
        self.btn_back.setMaximumSize(38, 34)
        self.btn_back.setStyleSheet("""
            QToolButton {
                background-color: #4a4a4a;
                color: #f2f2f2;
                border: 1px solid #5a5a5a;
                border-radius: 8px;
                font-size: 18px;
                font-weight: 600;
                padding: 0px;
                margin: 0px;
                text-align: center;
            }
            QToolButton:hover {
                background-color: #5a5a5a;
            }
            QToolButton:pressed {
                background-color: #666666;
            }
        """)
        tb.addWidget(self.btn_back)

        spacer0 = QWidget()
        spacer0.setAttribute(Qt.WA_TranslucentBackground)
        spacer0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer0)

        self.lbl_sys_left = QLabel("Temp: N/A")
        self.lbl_sys_left.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.lbl_sys_left.setMinimumHeight(30)
        self.lbl_sys_left.setStyleSheet("""
            QLabel {
                background: transparent;
                font-size: 12px;
                font-weight: 700;
                padding-left: 6px;
                padding-right: 6px;
            }
        """)
        tb.addWidget(self.lbl_sys_left)
        
        spacer1 = QWidget()
        spacer1.setAttribute(Qt.WA_TranslucentBackground)
        spacer1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer1)

        self.lbl_net = QLabel()
        self.lbl_net.setAlignment(Qt.AlignCenter)
        self.lbl_net.setMinimumHeight(30)
        self.lbl_net.setStyleSheet("""
            QLabel {
                background: transparent;
                font-size: 12px;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
            }
        """)
        tb.addWidget(self.lbl_net)
        self._update_net_label()

        spacer2 = QWidget()
        spacer2.setAttribute(Qt.WA_TranslucentBackground)
        spacer2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer2)

        self.lbl_sys_right = QLabel("N/A")
        self.lbl_sys_right.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.lbl_sys_right.setMinimumHeight(30)
        self.lbl_sys_right.setStyleSheet("""
            QLabel {
                background: transparent;
                font-size: 12px;
                font-weight: 700;
                padding-left: 6px;
                padding-right: 6px;
            }
        """)
        tb.addWidget(self.lbl_sys_right)
        
        spacer3 = QWidget()
        spacer3.setAttribute(Qt.WA_TranslucentBackground)
        spacer3.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer3)


        self.btn_settings = QToolButton()
        self.btn_settings.setText("⋮")
        self.btn_settings.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_settings.setMinimumSize(38, 34)
        self.btn_settings.setMaximumSize(38, 34)
        self.btn_settings.setStyleSheet("""
            QToolButton {
                background-color: #4a4a4a;
                color: #f2f2f2;
                border: 1px solid #5a5a5a;
                border-radius: 8px;
                font-size: 18px;
                font-weight: 600;
                padding: 0px;
                margin: 0px;
                text-align: center;
            }
            QToolButton:hover {
                background-color: #5a5a5a;
            }
            QToolButton:pressed {
                background-color: #666666;
            }
        """)
        tb.addWidget(self.btn_settings)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.page_home = self._build_home()
        self.idx_home = self.stack.addWidget(self.page_home)

        self.page_gs_single = None
        self.page_gs_rasp = None
        self.page_static = None
        self.page_analysis = None
        self.page_sim = None
        self.page_maps = None

        self.btn_back.clicked.connect(lambda: self._go_page("home", "Home"))
        self.btn_settings.clicked.connect(self._open_general_settings)

        self._go_page("home", "Home")
        self.set_light_theme_enabled(False)
        
        self._update_system_info()

    def _update_system_info(self):
        temp = get_system_temperature()
        other = get_system_secondary_info()

        self.lbl_sys_left.setText(f"Temp: {temp}")
        self.lbl_sys_right.setText(other)
        
    def set_light_theme_enabled(self, enabled: bool):
        self._light_theme_enabled = bool(enabled)

        app = QApplication.instance()
        if not app:
            return

        if self._light_theme_enabled:
            app.setStyleSheet(build_light_stylesheet())
        else:
            app.setStyleSheet(build_dark_grey_stylesheet())

        self._update_net_label()

    def _open_general_settings(self):
        dlg = GeneralSettingsDialog(self, parent=self)
        dlg.exec()

    def _build_home(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content_widget = QWidget()
        content = QVBoxLayout(content_widget)
        content.setContentsMargins(20, 20, 20, 20)
        content.setSpacing(18)

        content.addStretch(1)

        logo = QLabel()
        pix = QPixmap(resource_path("logo.png"))
        self.setWindowIcon(QIcon(resource_path("logo.ico")))

        if not pix.isNull():
            pix = pix.scaled(320, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo.setPixmap(pix)

        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("background: transparent;")
        content.addWidget(logo, alignment=Qt.AlignCenter)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        btn_gs_single = QPushButton("GS Flight (Notebook)")
        btn_gs_rasp   = QPushButton("GS Flight (Rasp)")
        btn_static    = QPushButton("GS Teste Estático")
        btn_analysis  = QPushButton("Data Analysis")
        btn_sim       = QPushButton("Simulador")
        btn_maps      = QPushButton("Gerenciar Mapas")

        buttons = [btn_gs_single, btn_gs_rasp, btn_static, btn_analysis, btn_sim, btn_maps]
        positions = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)]

        for b, (r, c) in zip(buttons, positions):
            grid.addWidget(b, r, c)
            b.setMinimumHeight(46)
            b.setCursor(Qt.PointingHandCursor)

        content.addLayout(grid)
        content.addStretch(1)

        scroll.setWidget(content_widget)
        page_layout.addWidget(scroll)

        btn_gs_single.clicked.connect(lambda: self._go_page("gs_single", "GS Flight (Notebook)"))
        btn_gs_rasp.clicked.connect(lambda: self._go_page("gs_rasp", "GS Flight (Rasp)"))
        btn_static.clicked.connect(lambda: self._go_page("static", "GS Teste Estático"))
        btn_analysis.clicked.connect(lambda: self._go_page("analysis", "Data Analysis"))
        btn_sim.clicked.connect(lambda: self._go_page("sim", "Simulador"))
        btn_maps.clicked.connect(lambda: self._go_page("maps", "Gerenciar Mapas"))

        return page

    def _go_page(self, name: str, msg: str):
        self._pause_all()

        if name == "home":
            self.stack.setCurrentIndex(self.idx_home)

        elif name == "config":
            self.stack.setCurrentIndex(self.idx_general_cfg)

        elif name == "gs_single":
            if self.page_gs_single is None:
                page = GSFlightSinglePage(self.netManager, parent=self)
                wrapped = wrap_in_scroll(page)
                wrapped._inner_page = page
                self.page_gs_single = wrapped
                self.idx_gs_single = self.stack.addWidget(self.page_gs_single)
                self.netManager.netChanged.connect(page.onNetChanged)
            self.stack.setCurrentWidget(self.page_gs_single)
            target = getattr(self.page_gs_single, "_inner_page", self.page_gs_single)
            if hasattr(target, "resume"):
                target.resume()

        elif name == "gs_rasp":
            if self.page_gs_rasp is None:
                page = GSFlightRaspPage(self.netManager, parent=self)
                wrapped = wrap_in_scroll(page)
                wrapped._inner_page = page
                self.page_gs_rasp = wrapped
                self.idx_gs_rasp = self.stack.addWidget(self.page_gs_rasp)
                self.netManager.netChanged.connect(page.onNetChanged)
            self.stack.setCurrentWidget(self.page_gs_rasp)
            target = getattr(self.page_gs_rasp, "_inner_page", self.page_gs_rasp)
            if hasattr(target, "resume"):
                target.resume()

        elif name == "static":
            if self.page_static is None:
                page = GSTestEstaticoPage(self.netManager, parent=self)
                wrapped = wrap_in_scroll(page)
                wrapped._inner_page = page
                self.page_static = wrapped
                self.idx_static = self.stack.addWidget(self.page_static)
            self.stack.setCurrentWidget(self.page_static)
            target = getattr(self.page_static, "_inner_page", self.page_static)
            if hasattr(target, "resume"):
                target.resume()

        elif name == "analysis":
            if self.page_analysis is None:
                page = DataAnalysisPage(parent=self)
                wrapped = wrap_in_scroll(page)
                wrapped._inner_page = page
                self.page_analysis = wrapped
                self.idx_analysis = self.stack.addWidget(self.page_analysis)
            self.stack.setCurrentWidget(self.page_analysis)
            target = getattr(self.page_analysis, "_inner_page", self.page_analysis)
            if hasattr(target, "resume"):
                target.resume()

        elif name == "sim":
            if self.page_sim is None:
                page = URDSimulatorPage()
                wrapped = wrap_in_scroll(page)
                wrapped._inner_page = page
                self.page_sim = wrapped
                self.idx_sim = self.stack.addWidget(self.page_sim)
            self.stack.setCurrentWidget(self.page_sim)
            target = getattr(self.page_sim, "_inner_page", self.page_sim)
            if hasattr(target, "resume"):
                target.resume()

        elif name == "maps":
            if self.page_maps is not None:
                self.stack.removeWidget(self.page_maps)
                self.page_maps.deleteLater()
                self.page_maps = None

            page = MapsManagerPage(self.netManager.get_status(), parent=self)
            wrapped = wrap_in_scroll(page)
            wrapped._inner_page = page
            self.page_maps = wrapped
            self.idx_maps = self.stack.addWidget(self.page_maps)
            self.netManager.netChanged.connect(page.onNetChanged)
            self.stack.setCurrentWidget(self.page_maps)

            target = getattr(self.page_maps, "_inner_page", self.page_maps)
            if hasattr(target, "resume"):
                target.resume()

        self.status.showMessage(msg, 2000)

    def _pause_all(self):
        for p in [
            self.page_gs_single,
            self.page_gs_rasp,
            self.page_maps,
            self.page_static,
            self.page_analysis,
            self.page_sim,
        ]:
            if not p:
                continue

            target = getattr(p, "_inner_page", p)

            if hasattr(target, "pause"):
                target.pause()

    def _check_net(self):
        changed = self.netManager.update()
        if changed:
            print(f"[DEBUG][Main] Internet mudou: {self.netManager.get_status()}")

    def _update_net_label(self):
        if self.netManager.forceOffline:
            color = "#ffb74d"
            text = "Offline Mode"
        elif self.netManager.hasNet:
            color = "#81c784"
            text = "Online Mode"
        else:
            color = "#e57373"
            text = "Offline Mode"

        self.lbl_net.setText(text)
        self.lbl_net.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                color: {color};
                font-size: 12px;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
            }}
        """)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    win = MainWindow()

    if sys.platform.startswith("linux"):
        win.setWindowFlags(Qt.FramelessWindowHint)
        win.showFullScreen()
    else:
        win.showMaximized()

    # QTimer.singleShot(250, play_startup_chime)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()