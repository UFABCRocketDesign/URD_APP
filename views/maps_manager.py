# views/maps_manager.py
import math, os, requests, json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QFileDialog, QHBoxLayout, QDoubleSpinBox, QMessageBox, QSizePolicy, QInputDialog, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView

from views.net_manager import NetManager

# ---------------- Funções auxiliares ----------------
def deg2num(lat, lon, zoom):
    """Converte lat/lon em coordenadas de tile (x,y)."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int(
        (1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n
    )
    return (xtile, ytile)

def expand_bounds(lat_min, lon_min, lat_max, lon_max, extra_km):
        # ~111 km por grau de latitude
        dlat = extra_km / 111.0  

        # longitude varia com a latitude → 111*cos(lat)
        lat_c = (lat_min + lat_max) / 2
        dlon = extra_km / (111.0 * math.cos(math.radians(lat_c)))

        return (lat_min - dlat, lon_min - dlon, lat_max + dlat, lon_max + dlon)



# ---------------- Thread para baixar tiles ----------------
class TileDownloader(QThread):
    progress = Signal(int, int)  # baixados, total
    finished = Signal(str)       # mensagem final
    failed = Signal(str)         # erro

    def __init__(self, lat_min, lon_min, lat_max, lon_max, zoom, folder_dark, folder_light):
        super().__init__()
        self.lat_min, self.lon_min = lat_min, lon_min
        self.lat_max, self.lon_max = lat_max, lon_max
        self.zoom = zoom
        self.folder_dark = folder_dark
        self.folder_light = folder_light



    def run(self):
        try:
            x_min, y_max = deg2num(self.lat_min, self.lon_min, self.zoom)
            x_max, y_min = deg2num(self.lat_max, self.lon_max, self.zoom)

            tiles = [
                (x, y)
                for x in range(min(x_min, x_max), max(x_min, x_max) + 1)
                for y in range(min(y_min, y_max), max(y_min, y_max) + 1)
            ]

            total = len(tiles)
            done = 0

            for (x, y) in tiles:
                urls = {
                    self.folder_light: f"https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{self.zoom}/{x}/{y}.png",
                    self.folder_dark:  f"https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{self.zoom}/{x}/{y}.png"
                }
                for target_folder, url in urls.items():
                    path = os.path.join(target_folder, str(self.zoom), str(x))
                    os.makedirs(path, exist_ok=True)
                    file_path = os.path.join(path, f"{y}.png")

                    if not os.path.exists(file_path):
                        try:
                            r = requests.get(url, timeout=10)
                            if r.status_code == 200:
                                with open(file_path, "wb") as f:
                                    f.write(r.content)
                        except Exception as e:
                            self.failed.emit(f"Erro ao baixar {url}: {e}")
                            return


                done += 1
                self.progress.emit(done*2, total*2)


            self.finished.emit(f"Download concluído! {total} tiles salvos em:\n{self.folder_light}\n{self.folder_dark}")


        except Exception as e:
            self.failed.emit(str(e))


# ---------------- Página principal ----------------
class MapsManagerPage(QWidget):
    def __init__(self, has_web: bool, parent=None):
        super().__init__(parent)
        self.has_web = has_web
        
        self._build_ui()

        

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Gerenciador de Mapas Online")
        title.setStyleSheet("font-size:18px; font-weight:bold; margin-bottom:6px;")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        

        # ---------- Controles de navegação ----------
        coord_row = QHBoxLayout()
        coord_row.setSpacing(4)

        self.lat = QDoubleSpinBox(); self.lat.setRange(-90, 90); self.lat.setDecimals(6)
        self.lon = QDoubleSpinBox(); self.lon.setRange(-180, 180); self.lon.setDecimals(6)
        btn_go = QPushButton("Ir para ponto")

        coord_row.addWidget(QLabel("Lat:")); coord_row.addWidget(self.lat)
        spacer1 = QWidget()
        spacer1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        coord_row.addWidget(spacer1, stretch=1)
        coord_row.addWidget(QLabel("Lon:")); coord_row.addWidget(self.lon)
        spacer2 = QWidget()
        spacer2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        coord_row.addWidget(spacer2, stretch=3)
        coord_row.addWidget(btn_go)
        root.addLayout(coord_row)

        # ---------- Mapa ----------

        # Mensagem offline (criada sempre)
        self.msg_offline = QLabel("❌ Este módulo só funciona online.\nAtive a internet para usar.")
        self.msg_offline.setAlignment(Qt.AlignCenter)
        self.msg_offline.setStyleSheet("font-size:16px; color:red;")
        
        self.map = QWebEngineView()
        self._init_map()
        if not self.has_web:
            self.map.hide()
            self.msg_offline.show()
        else:
            self.msg_offline.hide()
            self.map.show()


        root.addWidget(self.msg_offline, stretch=1)
        root.addWidget(self.map, stretch=1)

        # ---------- Botões ----------
        self.btn_save = QPushButton("Salvar mapas da região visível")
        root.addWidget(self.btn_save)

        # ---------- Barra de progresso ----------
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        # conexões
        self.btn_save.clicked.connect(self._save_tiles)
        btn_go.clicked.connect(self._go_to_region)

    def _init_map(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8"/>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
          html, body, #map { margin:0; height:100%; }
          .zoom-label {
            background:white;
            padding:4px 6px;
            border:1px solid #ccc;
            font-family:sans-serif;
            font-size:12px;
          }
        </style>
        </head>
        <body>
        <div id="map"></div>
        <script>
          var map = L.map('map').setView([0,0], 2);

          var cartoDark = L.tileLayer(
            'https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}{r}.png',
            { maxZoom: 30, attribution: '© OpenStreetMap contributors © CARTO' }
            ).addTo(map);


          function getBounds() {
            var b = map.getBounds();
            var result = {
              latMin: b.getSouth(),
              lonMin: b.getWest(),
              latMax: b.getNorth(),
              lonMax: b.getEast(),
              zoom: map.getZoom()
            };
            return JSON.stringify(result);
          }
          function goTo(lat, lon) { map.setView([lat, lon], 12); }
          window.getBounds = getBounds;
          window.goTo = goTo;

          // Mostrador de zoom
          var zoomLabel = L.control({position:'bottomright'});
          zoomLabel.onAdd = function() {
            this._div = L.DomUtil.create('div', 'zoom-label');
            this.update();
            return this._div;
          };
          zoomLabel.update = function() {
            this._div.innerHTML = "Zoom: " + map.getZoom() + "/30";
          };
          zoomLabel.addTo(map);
          map.on('zoomend', function() { zoomLabel.update(); });

          map.whenReady(function(){ document.title="MAP_READY"; });
        </script>
        </body>
        </html>
        """
        self.map.setHtml(html)

    def _save_tiles(self):
        if not self.has_web:
            QMessageBox.warning(self, "Erro", "Este recurso só funciona online.")
            return

        self.map.page().runJavaScript("getBounds();", self._on_bounds_received)

    def _on_bounds_received(self, bounds):
        if not bounds:
            QMessageBox.warning(self, "Erro", "Não foi possível obter a região do mapa.")
            return

        try:
            bounds = json.loads(bounds)
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Falha ao converter bounds: {e}")
            return

        zoom = bounds["zoom"]

        if zoom < 12:
            QMessageBox.warning(self, "Erro", f"O zoom atual é {zoom}, mínimo permitido é 12.")
            return

        # pedir nome base
        name, ok = QInputDialog.getText(self, "Nome do mapa", "Digite um nome base para este mapa:")
        if not ok or not name.strip():
            return
        name = name.strip().replace(" ", "_")

        # pedir pasta raiz
        base_folder = QFileDialog.getExistingDirectory(self, "Escolher pasta para salvar mapas")
        if not base_folder:
            return

        folder_dark = os.path.join(base_folder, name + "Dark")
        folder_light = os.path.join(base_folder, name + "Light")
        os.makedirs(folder_dark, exist_ok=True)
        os.makedirs(folder_light, exist_ok=True)

        lat_min, lon_min = bounds["latMin"], bounds["lonMin"]
        lat_max, lon_max = bounds["latMax"], bounds["lonMax"]

        # Expande 5 km em cada direção
        lat_min, lon_min, lat_max, lon_max = expand_bounds(lat_min, lon_min, lat_max, lon_max, extra_km=8)


        # barra de progresso
        self.progress.setVisible(True)
        self.progress.setValue(0)

        # cria lista de níveis
        zooms = [zoom-2, zoom-1, zoom, zoom+1, zoom+2]
        zooms = [z for z in zooms if z >= 1 and z <= 19]

        self.downloaders = []  # guarda referência para não perder os threads

        for z in zooms:
            dl = TileDownloader(lat_min, lon_min, lat_max, lon_max, z, folder_dark, folder_light)
            dl.progress.connect(self._update_progress)
            dl.finished.connect(self._download_finished)
            dl.failed.connect(self._download_failed)
            self.downloaders.append(dl)
            dl.start()

    def _update_progress(self, done, total):
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def _download_finished(self, msg):
        self.progress.setVisible(False)
        QMessageBox.information(self, "Sucesso", msg)

    def _download_failed(self, msg):
        self.progress.setVisible(False)
        QMessageBox.warning(self, "Erro", msg)

    def _go_to_region(self):
        lat, lon = self.lat.value(), self.lon.value()
        self.map.page().runJavaScript(f"goTo({lat:.6f}, {lon:.6f});")
    

    def onNetChanged(self, status: bool):
        self.has_web = status
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
            self._init_map()  # reinit o mapa só quando voltar online
    
    
    