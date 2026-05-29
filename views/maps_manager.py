# views/maps_manager.py
import math, os, requests, json, time, shutil
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QFileDialog, QHBoxLayout, QDoubleSpinBox, QMessageBox,
    QInputDialog, QProgressBar, QSpinBox, QGridLayout, QFrame, QVBoxLayout
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWebEngineWidgets import QWebEngineView


# ---------------- Funções auxiliares ----------------
def deg2num(lat, lon, zoom):
    """Converte lat/lon em coordenadas de tile (x,y)."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return (xtile, ytile)

def clamp(v, a, b):
    return max(a, min(b, v))

def bounds_from_center_km(lat_c, lon_c, radius_km):
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.1, math.cos(math.radians(lat_c))))
    lat_min = clamp(lat_c - dlat, -89.999999, 89.999999)
    lat_max = clamp(lat_c + dlat, -89.999999, 89.999999)
    lon_min = clamp(lon_c - dlon, -179.999999, 179.999999)
    lon_max = clamp(lon_c + dlon, -179.999999, 179.999999)
    return (lat_min, lon_min, lat_max, lon_max)

def safe_name(s: str):
    s = (s or "").strip().replace(" ", "_")
    return "".join(ch for ch in s if ch.isalnum() or ch in ("_", "-", "."))

def fmt_gb(gib: float) -> str:
    if gib < 0.1:
        return f"{gib*1024:.0f} MB"
    if gib < 10:
        return f"{gib:.2f} GB"
    return f"{gib:.1f} GB"

def estimate_tiles_and_size(center_lat: float, center_lon: float, radius_km: float, zoom_min: int, zoom_max: int):
    zmin, zmax = min(zoom_min, zoom_max), max(zoom_min, zoom_max)
    zmin, zmax = int(clamp(zmin, 1, 19)), int(clamp(zmax, 1, 19))
    lat_min, lon_min, lat_max, lon_max = bounds_from_center_km(center_lat, center_lon, radius_km)

    tiles_total = 0
    for z in range(zmin, zmax + 1):
        x_min, y_max = deg2num(lat_min, lon_min, z)
        x_max, y_min = deg2num(lat_max, lon_max, z)
        x0, x1 = min(x_min, x_max), max(x_min, x_max)
        y0, y1 = min(y_min, y_max), max(y_min, y_max)
        tiles_total += (x1 - x0 + 1) * (y1 - y0 + 1)

    per_layer = tiles_total
    total_files = tiles_total * 3

    # faixa de tamanho (mín–máx) por tile (KB): light, dark, sat
    kb_min = (8 + 8 + 25)        # ~41KB por tile (leve)
    kb_max = (30 + 30 + 180)     # ~240KB por tile (pior caso comum)
    bytes_min = tiles_total * kb_min * 1024
    bytes_max = tiles_total * kb_max * 1024
    gib_min = bytes_min / (1024**3)
    gib_max = bytes_max / (1024**3)

    return {
        "tiles_per_layer": per_layer,
        "total_files": total_files,
        "gib_min": gib_min,
        "gib_max": gib_max,
        "zoom_min": zmin,
        "zoom_max": zmax
    }


# ---------------- Thread para baixar tiles ----------------
class TilePackDownloader(QThread):
    layer_progress = Signal(str, int, int, int)  # layer, done, total, zoom
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, center_lat, center_lon, radius_km, zoom_min, zoom_max, pack_folder):
        super().__init__()
        self.center_lat = float(center_lat)
        self.center_lon = float(center_lon)
        self.radius_km = float(radius_km)
        self.zoom_min = int(zoom_min)
        self.zoom_max = int(zoom_max)
        self.pack_folder = pack_folder

        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "URD-GS-MapsManager/1.0"})

        self.sources = {
            "light": "https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png",
            "dark":  "https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png",
            "sat":   "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        }
        self.layers = ["light", "dark", "sat"]
        self._stop = False

    def request_stop(self):
        self._stop = True

    def _download_one(self, url, out_path):
        if os.path.exists(out_path):
            return True
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            # timeout separado ajuda a fechar o app mais rápido
            r = self._session.get(url, timeout=(3, 8))
            if r.status_code == 200 and r.content:
                with open(out_path, "wb") as f:
                    f.write(r.content)
                return True
            return False
        except Exception:
            return False

    def run(self):
        try:
            lat_min, lon_min, lat_max, lon_max = bounds_from_center_km(self.center_lat, self.center_lon, self.radius_km)

            for k in self.layers:
                os.makedirs(os.path.join(self.pack_folder, k), exist_ok=True)

            zmin = int(clamp(min(self.zoom_min, self.zoom_max), 1, 19))
            zmax = int(clamp(max(self.zoom_min, self.zoom_max), 1, 19))
            zooms = list(range(zmin, zmax + 1))

            tiles_per_zoom = {}
            tiles_total = 0
            for z in zooms:
                x_min, y_max = deg2num(lat_min, lon_min, z)
                x_max, y_min = deg2num(lat_max, lon_max, z)
                x0, x1 = min(x_min, x_max), max(x_min, x_max)
                y0, y1 = min(y_min, y_max), max(y_min, y_max)
                tiles = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
                tiles_per_zoom[z] = tiles
                tiles_total += len(tiles)

            if tiles_total <= 0:
                self.failed.emit("Nenhum tile calculado (bounds inválidos).")
                return

            per_layer_total = tiles_total
            layer_done = {k: 0 for k in self.layers}

            for layer in self.layers:
                self.layer_progress.emit(layer, 0, per_layer_total, zmin)

            last_emit_layer = {k: 0 for k in self.layers}
            emit_every = 25
            last_status_time = 0.0

            for z in zooms:
                if self._stop:
                    self.failed.emit("Download cancelado.")
                    return

                tiles = tiles_per_zoom[z]
                self.status.emit(f"Baixando zoom {z} ({len(tiles)} tiles por camada)")

                for (x, y) in tiles:
                    if self._stop:
                        self.failed.emit("Download cancelado.")
                        return

                    for layer in self.layers:
                        url = self.sources[layer].format(z=z, x=x, y=y)
                        out_dir = os.path.join(self.pack_folder, layer, str(z), str(x))
                        out_path = os.path.join(out_dir, f"{y}.png")

                        ok = self._download_one(url, out_path)
                        if not ok:
                            self.failed.emit(f"Falha ao baixar: {url}")
                            return

                        layer_done[layer] += 1

                        now = time.time()
                        if (now - last_status_time) > 0.15:
                            last_status_time = now
                            self.status.emit(f"{layer.upper()} | z{z} | x{x} y{y}")

                        if (layer_done[layer] - last_emit_layer[layer]) >= emit_every:
                            last_emit_layer[layer] = layer_done[layer]
                            self.layer_progress.emit(layer, layer_done[layer], per_layer_total, z)

            for layer in self.layers:
                self.layer_progress.emit(layer, per_layer_total, per_layer_total, zmax)

            meta = {
                "center": [self.center_lat, self.center_lon],
                "radius_km": self.radius_km,
                "zoom_min": zmin,
                "zoom_max": zmax,
                "zooms": zooms,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "layers": self.layers
            }
            try:
                with open(os.path.join(self.pack_folder, "meta.json"), "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            self.status.emit("Concluído.")
            self.finished.emit(
                "Download concluído!\n\n"
                f"Pasta do pacote:\n{self.pack_folder}\n\n"
                f"Camadas: light / dark / sat\n"
                f"Zoom: {zmin} → {zmax}\n"
                f"Raio: {self.radius_km:.1f} km\n"
                f"Tiles por camada: {per_layer_total}"
            )

        except Exception as e:
            self.failed.emit(str(e))


# ---------------- Serviço global (continua mesmo se sair da página) ----------------
class MapsDownloadService(QObject):
    started = Signal()
    layer_progress = Signal(str, int, int, int)
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.downloader: TilePackDownloader | None = None

        self.last_status = "pronto"
        self.layer_state = {
            "light": {"done": 0, "total": 1, "zoom": 0},
            "dark":  {"done": 0, "total": 1, "zoom": 0},
            "sat":   {"done": 0, "total": 1, "zoom": 0},
        }
        self._pending_popup = None  # ("success"/"error"/"info", message)

    def is_running(self) -> bool:
        return bool(self.downloader and self.downloader.isRunning())

    def pending_popup(self):
        return self._pending_popup

    def pop_pending_popup(self):
        p = self._pending_popup
        self._pending_popup = None
        return p

    def start_download(self, center_lat, center_lon, radius_km, zoom_min, zoom_max, pack_folder) -> bool:
        if self.is_running():
            return False

        self.downloader = TilePackDownloader(center_lat, center_lon, radius_km, zoom_min, zoom_max, pack_folder)
        self.downloader.layer_progress.connect(self._on_layer_progress)
        self.downloader.status.connect(self._on_status)
        self.downloader.finished.connect(self._on_finished)
        self.downloader.failed.connect(self._on_failed)

        self.last_status = "preparando..."
        self._pending_popup = None

        self.started.emit()
        self.downloader.start()
        return True

    def cancel(self):
        if self.downloader and self.downloader.isRunning():
            self.downloader.request_stop()

    def shutdown(self, wait_ms: int = 15000):
        self.cancel()
        d = self.downloader
        if d and d.isRunning():
            d.wait(wait_ms)

    def _on_layer_progress(self, layer, done, total, zoom):
        layer = (layer or "").lower()
        if layer in self.layer_state:
            self.layer_state[layer]["done"] = int(done)
            self.layer_state[layer]["total"] = int(max(1, total))
            self.layer_state[layer]["zoom"] = int(zoom)
        self.layer_progress.emit(layer, done, total, zoom)

    def _on_status(self, text):
        self.last_status = text or ""
        self.status.emit(self.last_status)

    def _on_finished(self, msg):
        self._pending_popup = ("success", msg)
        self.finished.emit(msg)

    def _on_failed(self, msg):
        kind = "info" if (msg or "").strip().lower() == "download cancelado." else "error"
        self._pending_popup = (kind, msg)
        self.failed.emit(msg)


_DOWNLOAD_SERVICE = MapsDownloadService()
_SHUTDOWN_HOOK_INSTALLED = False

def install_maps_shutdown_hook():
    global _SHUTDOWN_HOOK_INSTALLED
    if _SHUTDOWN_HOOK_INSTALLED:
        return
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        app.aboutToQuit.connect(lambda: _DOWNLOAD_SERVICE.shutdown(15000))
        _SHUTDOWN_HOOK_INSTALLED = True


# ---------------- Página principal ----------------
class MapsManagerPage(QWidget):
    def __init__(self, has_web: bool, parent=None):
        super().__init__(parent)
        self.has_web = has_web
        self._build_ui()
        install_maps_shutdown_hook()
        self._attach_download_service()
        self._restore_download_ui_if_needed()

    def _attach_download_service(self):
        _DOWNLOAD_SERVICE.started.connect(self._on_service_started)
        _DOWNLOAD_SERVICE.layer_progress.connect(self._update_layer_progress)
        _DOWNLOAD_SERVICE.status.connect(self._update_status)
        _DOWNLOAD_SERVICE.finished.connect(self._on_service_finished)
        _DOWNLOAD_SERVICE.failed.connect(self._on_service_failed)

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # --- Topo: título + help ---
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        ph = QLabel("")
        ph.setFixedWidth(28)

        title = QLabel("Gerenciador de Mapas")
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        title.setAlignment(Qt.AlignCenter)

        self.btn_help = QPushButton("?")
        self.btn_help.setFixedSize(28, 28)
        self.btn_help.setToolTip("Manual de uso")

        title_row.addWidget(ph)
        title_row.addStretch(1)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.btn_help)
        root.addLayout(title_row)

        # --- Linha 1: Lat/Lon com título dentro do container ---
        nav_frame = QFrame()
        nav_frame.setFrameShape(QFrame.StyledPanel)
        nav_outer = QVBoxLayout(nav_frame)
        nav_outer.setContentsMargins(8, 8, 8, 8)
        nav_outer.setSpacing(6)

        nav_title = QLabel("Navegação")
        nav_title.setAlignment(Qt.AlignHCenter)
        nav_title.setStyleSheet("font-weight:600; color:#444;")
        nav_outer.addWidget(nav_title)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(10)

        self.lat = QDoubleSpinBox()
        self.lat.setRange(-90, 90)
        self.lat.setDecimals(6)
        self.lat.setSingleStep(0.000100)
        self.lat.setFixedWidth(190)

        self.lon = QDoubleSpinBox()
        self.lon.setRange(-180, 180)
        self.lon.setDecimals(6)
        self.lon.setSingleStep(0.000100)
        self.lon.setFixedWidth(190)

        self.btn_go = QPushButton("Ir")
        self.btn_go.setFixedWidth(90)
        self.btn_go.setMinimumHeight(32)

        lat_box = QVBoxLayout()
        lat_lbl = QLabel("Lat")
        lat_lbl.setAlignment(Qt.AlignHCenter)
        lat_box.addWidget(lat_lbl)
        lat_box.addWidget(self.lat, alignment=Qt.AlignHCenter)

        lon_box = QVBoxLayout()
        lon_lbl = QLabel("Lon")
        lon_lbl.setAlignment(Qt.AlignHCenter)
        lon_box.addWidget(lon_lbl)
        lon_box.addWidget(self.lon, alignment=Qt.AlignHCenter)

        btn_box = QVBoxLayout()
        btn_box.addWidget(QLabel(""), alignment=Qt.AlignHCenter)
        btn_box.addWidget(self.btn_go, alignment=Qt.AlignHCenter)

        nav_row.addStretch(1)
        nav_row.addLayout(lat_box)
        nav_row.addSpacing(6)
        nav_row.addLayout(lon_box)
        nav_row.addSpacing(10)
        nav_row.addLayout(btn_box)
        nav_row.addStretch(1)

        nav_outer.addLayout(nav_row)
        root.addWidget(nav_frame)

        # --- Linha 2: parâmetros do download + estimativa com GB ---
        dl_frame = QFrame()
        dl_frame.setFrameShape(QFrame.StyledPanel)
        dl_layout = QGridLayout(dl_frame)
        dl_layout.setContentsMargins(8, 8, 8, 8)
        dl_layout.setHorizontalSpacing(8)
        dl_layout.setVerticalSpacing(4)

        self.radius_km = QDoubleSpinBox()
        self.radius_km.setRange(1.0, 300.0)
        self.radius_km.setDecimals(1)
        self.radius_km.setSingleStep(5.0)
        self.radius_km.setValue(50.0)
        self.radius_km.setSuffix(" km")
        self.radius_km.setFixedWidth(140)

        self.zoom_min = QSpinBox()
        self.zoom_min.setRange(1, 19)
        self.zoom_min.setValue(12)
        self.zoom_min.setFixedWidth(70)

        self.zoom_max = QSpinBox()
        self.zoom_max.setRange(1, 19)
        self.zoom_max.setValue(16)
        self.zoom_max.setFixedWidth(70)

        self.lbl_estimate = QLabel("Estimativa: --")
        self.lbl_estimate.setStyleSheet("color:#666;")

        dl_layout.addWidget(QLabel("Raio"), 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        dl_layout.addWidget(self.radius_km, 0, 1, alignment=Qt.AlignVCenter)
        dl_layout.addWidget(QLabel("Zoom mín"), 0, 2, alignment=Qt.AlignRight | Qt.AlignVCenter)
        dl_layout.addWidget(self.zoom_min, 0, 3, alignment=Qt.AlignVCenter)
        dl_layout.addWidget(QLabel("Zoom máx"), 0, 4, alignment=Qt.AlignRight | Qt.AlignVCenter)
        dl_layout.addWidget(self.zoom_max, 0, 5, alignment=Qt.AlignVCenter)
        dl_layout.addWidget(self.lbl_estimate, 0, 6, alignment=Qt.AlignVCenter)
        dl_layout.setColumnStretch(6, 1)
        root.addWidget(dl_frame)

        # --- Mapa ---
        self.msg_offline = QLabel("Sem internet. Conecte para visualizar e baixar mapas.")
        self.msg_offline.setAlignment(Qt.AlignCenter)
        self.msg_offline.setStyleSheet("font-size:14px; color:#b00020;")

        self.map = QWebEngineView()
        self._init_map()

        if not self.has_web:
            self.map.hide()
            self.msg_offline.show()
        else:
            self.msg_offline.hide()
            self.map.show()

        root.addWidget(self.msg_offline, stretch=0)
        root.addWidget(self.map, stretch=1)

        # --- Botão baixar ---
        self.btn_save = QPushButton("Baixar pacote offline")
        self.btn_save.setMinimumHeight(34)
        root.addWidget(self.btn_save)

        # --- Progresso (escondido até começar) ---
        self.prog_frame = QFrame()
        self.prog_frame.setFrameShape(QFrame.StyledPanel)
        prog_layout = QGridLayout(self.prog_frame)
        prog_layout.setContentsMargins(8, 8, 8, 8)
        prog_layout.setHorizontalSpacing(8)
        prog_layout.setVerticalSpacing(6)

        self.pb_light = QProgressBar()
        self.pb_dark = QProgressBar()
        self.pb_sat = QProgressBar()

        self.pb_light.setStyleSheet("QProgressBar::chunk{background:#2d7dd2;}")
        self.pb_dark.setStyleSheet("QProgressBar::chunk{background:#6f42c1;}")
        self.pb_sat.setStyleSheet("QProgressBar::chunk{background:#2ca24f;}")

        self.lbl_light = QLabel("Light")
        self.lbl_dark = QLabel("Dark")
        self.lbl_sat = QLabel("Satélite")

        prog_layout.addWidget(self.lbl_light, 0, 0)
        prog_layout.addWidget(self.pb_light, 0, 1)
        prog_layout.addWidget(self.lbl_dark, 1, 0)
        prog_layout.addWidget(self.pb_dark, 1, 1)
        prog_layout.addWidget(self.lbl_sat, 2, 0)
        prog_layout.addWidget(self.pb_sat, 2, 1)

        self.lbl_status = QLabel("Status: pronto")
        self.lbl_status.setStyleSheet("color:#666;")
        prog_layout.addWidget(self.lbl_status, 3, 0, 1, 2)

        self.btn_cancel = QPushButton("Cancelar download")
        prog_layout.addWidget(self.btn_cancel, 4, 0, 1, 2, alignment=Qt.AlignRight)

        self.prog_frame.hide()
        root.addWidget(self.prog_frame)

        # conexões
        self.btn_help.clicked.connect(self._show_help)
        self.btn_save.clicked.connect(self._save_tiles)
        self.btn_go.clicked.connect(self._go_to_region)
        self.btn_cancel.clicked.connect(self._cancel_download)

        self.radius_km.valueChanged.connect(self._refresh_estimate)
        self.zoom_min.valueChanged.connect(self._refresh_estimate)
        self.zoom_max.valueChanged.connect(self._refresh_estimate)

        self._refresh_estimate()

    def _show_help(self):
        txt = (
            "Como usar:\n\n"
            "1) Navegue no mapa e deixe o local desejado no centro.\n"
            "2) Ajuste o raio (km) e o intervalo de zoom do pacote.\n"
            "3) Clique em “Baixar pacote offline”.\n\n"
            "Dicas:\n"
            "- As linhas no centro ajudam a alinhar o ponto base.\n"
            "- O ponto base é o centro do mapa (ponto vermelho).\n"
            "- Duplo-clique alterna preview (light/dark/satélite).\n"
            "- Você pode trocar de página: o download continua.\n"
        )
        QMessageBox.information(self, "Manual", txt)

    # ---------- Mapa (Leaflet) ----------
    def _init_map(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
          html, body { margin:0; height:100%; }
          #wrap { position:relative; height:100%; }
          #map { height:100%; }

          /* crosshair no centro (até as bordas) */
          #crossV, #crossH {
            position:absolute;
            z-index:9998;
            pointer-events:none;
            background: rgba(208,0,0,0.28);
          }
          #crossV { top:0; bottom:0; width:1px; left:50%; transform:translateX(-0.5px); }
          #crossH { left:0; right:0; height:1px; top:50%; transform:translateY(-0.5px); }

          /* topo central com coordenadas do centro */
          #centerInfo {
            position:absolute;
            top:8px;
            left:50%;
            transform:translateX(-50%);
            z-index:9999;
            background:rgba(255,255,255,0.92);
            border:1px solid rgba(0,0,0,0.15);
            border-radius:10px;
            padding:6px 10px;
            font-family:sans-serif;
            font-size:12px;
            pointer-events:none;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            white-space:nowrap;
            display:flex;
            align-items:center;
            gap:8px;
          }
          #dot {
            width:8px; height:8px;
            border-radius:999px;
            background:#d00000;
            box-shadow:0 0 0 2px rgba(208,0,0,0.18);
            flex:0 0 auto;
          }

          .zoom-label {
            background:white;
            padding:4px 6px;
            border:1px solid #ccc;
            border-radius:8px;
            font-family:sans-serif;
            font-size:12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
          }
        </style>
        </head>
        <body>
        <div id="wrap">
          <div id="centerInfo"><span id="dot"></span><span id="centerTxt">Centro: --</span></div>
          <div id="crossV"></div>
          <div id="crossH"></div>
          <div id="map"></div>
        </div>

        <script>
          var map = L.map('map', { doubleClickZoom:false }).setView([0,0], 3);

          var baseLayers = {};
          baseLayers.light = L.tileLayer(
            'https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png',
            { maxZoom: 19, attribution: '© OSM © CARTO' }
          );
          baseLayers.dark = L.tileLayer(
            'https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png',
            { maxZoom: 19, attribution: '© OSM © CARTO' }
          );
          baseLayers.sat = L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            { maxZoom: 19, attribution: 'Tiles © Esri' }
          );

          var order = ["light","dark","sat"];
          var idx = 1; // começa em dark
          baseLayers[order[idx]].addTo(map);

          function cycleBase(){
            map.removeLayer(baseLayers[order[idx]]);
            idx = (idx + 1) % order.length;
            baseLayers[order[idx]].addTo(map);
          }

          // marcador no centro (menor)
          var centerMarker = L.circleMarker(map.getCenter(), {
            radius: 4,
            color: "#d00000",
            weight: 2,
            fillColor: "#d00000",
            fillOpacity: 0.80,
            interactive: false
          }).addTo(map);

          function updateCenterInfo(){
            var c = map.getCenter();
            var z = map.getZoom();
            document.getElementById('centerTxt').textContent =
              "Centro: " + c.lat.toFixed(6) + ", " + c.lng.toFixed(6) + "  |  Zoom: " + z;
            centerMarker.setLatLng(c);
          }

          function getViewInfo() {
            var b = map.getBounds();
            var c = map.getCenter();
            return JSON.stringify({
              latMin: b.getSouth(),
              lonMin: b.getWest(),
              latMax: b.getNorth(),
              lonMax: b.getEast(),
              centerLat: c.lat,
              centerLon: c.lng,
              zoom: map.getZoom()
            });
          }

          function goTo(lat, lon) { map.setView([lat, lon], map.getZoom()); }

          window.getBounds = getViewInfo;
          window.goTo = goTo;
          window.cycleBase = cycleBase;

          var zoomLabel = L.control({position:'bottomright'});
          zoomLabel.onAdd = function() {
            this._div = L.DomUtil.create('div', 'zoom-label');
            this.update();
            return this._div;
          };
          zoomLabel.update = function() { this._div.innerHTML = "Zoom: " + map.getZoom() + "/19"; };
          zoomLabel.addTo(map);

          map.on('zoomend', function() { zoomLabel.update(); updateCenterInfo(); });
          map.on('moveend', function() { updateCenterInfo(); });
          map.on('dblclick', function(){ cycleBase(); });

          map.whenReady(function(){ updateCenterInfo(); document.title="MAP_READY"; });
        </script>
        </body>
        </html>
        """
        self.map.setHtml(html)

    # ---------- Estimativa ----------
    def _refresh_estimate(self):
        est = estimate_tiles_and_size(
            center_lat=float(self.lat.value()),
            center_lon=float(self.lon.value()),
            radius_km=float(self.radius_km.value()),
            zoom_min=int(self.zoom_min.value()),
            zoom_max=int(self.zoom_max.value())
        )
        self.lbl_estimate.setText(
            f"Estimativa: {est['tiles_per_layer']} tiles/camada ({est['total_files']} arquivos) | "
            f"~{fmt_gb(est['gib_min'])} – {fmt_gb(est['gib_max'])}"
        )

    # ---------- Download / Confirmações ----------
    def _save_tiles(self):
        if not self.has_web:
            QMessageBox.warning(self, "Erro", "Conecte à internet para baixar os mapas.")
            return
        if _DOWNLOAD_SERVICE.is_running():
            QMessageBox.warning(self, "Em andamento", "Já existe um download em andamento.")
            return

        self.map.page().runJavaScript("getBounds();", self._on_bounds_received)

    def _on_bounds_received(self, bounds):
        if not bounds:
            QMessageBox.warning(self, "Erro", "Não foi possível obter a região do mapa.")
            return

        try:
            data = json.loads(bounds)
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Falha ao converter dados do mapa: {e}")
            return

        center_lat = float(data.get("centerLat", 0.0))
        center_lon = float(data.get("centerLon", 0.0))

        name, ok = QInputDialog.getText(self, "Nome do pacote", "Nome da pasta do pacote:")
        if not ok:
            return
        name = safe_name(name)
        if not name:
            return

        base_folder = QFileDialog.getExistingDirectory(self, "Escolher pasta para salvar")
        if not base_folder:
            return

        pack_folder = os.path.join(base_folder, name)
        os.makedirs(pack_folder, exist_ok=True)

        radius_km = float(self.radius_km.value())
        zoom_min = int(self.zoom_min.value())
        zoom_max = int(self.zoom_max.value())

        est = estimate_tiles_and_size(center_lat, center_lon, radius_km, zoom_min, zoom_max)

        # espaço livre em disco
        try:
            free_bytes = shutil.disk_usage(base_folder).free
            free_gib = free_bytes / (1024**3)
        except Exception:
            free_gib = None

        THRESHOLD_GIB = 5.0
        need_confirm = est["gib_max"] >= THRESHOLD_GIB

        not_enough = False
        if free_gib is not None and free_gib < (est["gib_max"] * 1.15):
            not_enough = True

        info_lines = [
            f"Centro: {center_lat:.6f}, {center_lon:.6f}",
            f"Raio: {radius_km:.1f} km",
            f"Zoom: {est['zoom_min']} → {est['zoom_max']}",
            f"Arquivos: {est['total_files']}",
            f"Tamanho estimado: ~{fmt_gb(est['gib_min'])} – {fmt_gb(est['gib_max'])}",
        ]
        if free_gib is not None:
            info_lines.append(f"Espaço livre no disco: {fmt_gb(free_gib)}")

        if not_enough:
            r = QMessageBox.warning(
                self, "Pouco espaço em disco",
                "Parece que o pacote pode não caber com segurança.\n\n" + "\n".join(info_lines) +
                "\n\nDeseja continuar mesmo assim?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if r != QMessageBox.Yes:
                return
        elif need_confirm:
            r = QMessageBox.question(
                self, "Pacote grande",
                "Esse download pode ficar grande.\n\n" + "\n".join(info_lines) +
                "\n\nDeseja continuar?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if r != QMessageBox.Yes:
                return

        ok = _DOWNLOAD_SERVICE.start_download(
            center_lat=center_lat,
            center_lon=center_lon,
            radius_km=radius_km,
            zoom_min=zoom_min,
            zoom_max=zoom_max,
            pack_folder=pack_folder
        )
        if not ok:
            QMessageBox.warning(self, "Em andamento", "Já existe um download em andamento.")
            return

    def _cancel_download(self):
        _DOWNLOAD_SERVICE.cancel()

    # ---------- UI de progresso (persistente) ----------
    def _progress_bar_for_layer(self, layer: str):
        layer = (layer or "").lower()
        if layer == "light":
            return self.pb_light
        if layer == "dark":
            return self.pb_dark
        return self.pb_sat

    def _on_service_started(self):
        self._show_progress_frame()
        self._restore_download_ui_if_needed()

    def _update_layer_progress(self, layer: str, done: int, total: int, zoom: int):
        self._show_progress_frame()
        pb = self._progress_bar_for_layer(layer)
        total = max(1, int(total))
        done = int(clamp(done, 0, total))
        pb.setMaximum(total)
        pb.setValue(done)
        pct = (done / total) * 100.0
        pb.setFormat(f"{pct:.1f}%  ({done}/{total})  z{int(zoom)}")

    def _update_status(self, text: str):
        self._show_progress_frame()
        self.lbl_status.setText(f"Status: {text}")

    def _on_service_finished(self, msg: str):
        QMessageBox.information(self, "Sucesso", msg)
        self.prog_frame.hide()

    def _on_service_failed(self, msg: str):
        if (msg or "").strip().lower() == "download cancelado.":
            QMessageBox.information(self, "Cancelado", "Download cancelado.")
        else:
            QMessageBox.warning(self, "Erro", msg)
        self.prog_frame.hide()

    def _restore_download_ui_if_needed(self):
        if _DOWNLOAD_SERVICE.is_running():
            self._show_progress_frame()
            self.lbl_status.setText(f"Status: {_DOWNLOAD_SERVICE.last_status}")
            for layer, st in _DOWNLOAD_SERVICE.layer_state.items():
                self._update_layer_progress(layer, st["done"], st["total"], st["zoom"])

        pending = _DOWNLOAD_SERVICE.pending_popup()
        if pending is not None:
            kind, msg = _DOWNLOAD_SERVICE.pop_pending_popup()
            if kind == "success":
                QMessageBox.information(self, "Sucesso", msg)
            elif kind == "info":
                QMessageBox.information(self, "Info", msg)
            else:
                QMessageBox.warning(self, "Erro", msg)

    def _show_progress_frame(self):
        if not self.prog_frame.isVisible():
            for pb in (self.pb_light, self.pb_dark, self.pb_sat):
                if pb.maximum() <= 1 and pb.value() == 0:
                    pb.setMaximum(1)
                    pb.setValue(0)
                    pb.setFormat("0%")
            self.prog_frame.show()

    # ---------- Navegação ----------
    def _go_to_region(self):
        lat, lon = self.lat.value(), self.lon.value()
        self.map.page().runJavaScript(f"goTo({lat:.6f}, {lon:.6f});")

    def onNetChanged(self, status: bool):
        self.has_web = status

        # se ficou offline, cancela download
        if not status and _DOWNLOAD_SERVICE.is_running():
            _DOWNLOAD_SERVICE.cancel()

        self.changeMode(status)

    def changeMode(self, status: bool):
        if not status:
            self.map.hide()
            self.msg_offline.show()
            self.btn_save.setEnabled(False)
        else:
            self.msg_offline.hide()
            self.map.show()
            self.btn_save.setEnabled(True)
            self._init_map()