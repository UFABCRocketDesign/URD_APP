# views/map_widget.py
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, Signal, Slot

import http.server, socketserver, threading, os

import math, pathlib

def num2deg(x, y, z):
    """Converte tile x/y/z em lat/lon (canto NW do tile)."""
    n = 2.0 ** z
    lon_deg = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def get_tile_bounds(tile_folder: str):
    """Lê pasta de tiles e retorna (z, lat_min, lon_min, lat_max, lon_max)."""
    path = pathlib.Path(tile_folder)
    zooms = [int(p.name) for p in path.iterdir() if p.is_dir() and p.name.isdigit()]
    if not zooms:
        return None

    z = max(zooms)  # pega o maior zoom disponível
    xs = [int(p.name) for p in (path / str(z)).iterdir() if p.is_dir()]
    if not xs:
        return None

    min_x, max_x = min(xs), max(xs)
    ys = []
    for x in xs:
        ys.extend(int(f.stem) for f in (path / str(z) / str(x)).glob("*.png"))
    if not ys:
        return None

    min_y, max_y = min(ys), max(ys)

    # canto superior esquerdo e inferior direito
    lat_max, lon_min = num2deg(min_x, min_y, z)
    lat_min, lon_max = num2deg(max_x+1, max_y+1, z)

    return z, lat_min, lon_min, lat_max, lon_max

class TileServer:
    def __init__(self, folder, port=8081):
        self.folder = folder
        self.port = port
        self.httpd = None
        self.thread = None

    def start(self):
        handler = http.server.SimpleHTTPRequestHandler
        self.httpd = socketserver.TCPServer(("", self.port), handler)
        os.chdir(self.folder)  # serve a pasta
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()


class MapWidget(QWebEngineView):
    def __init__(self, offline: bool = False, satellite = False, tile_folder: str = None, parent=None):
        super().__init__(parent)
        self.offline = offline
        self.tile_folder = tile_folder
        self.is_satellite = satellite


        self._init_map()

    def _init_map(self):
        if self.offline and self.tile_folder:
            bounds = get_tile_bounds(self.tile_folder)

            if not hasattr(self, "server"):
                self.server = TileServer(self.tile_folder, port=8081)
                self.server.start()

            if not bounds:
                html = "<html><body>❌ Nenhum tile válido encontrado.</body></html>"
                self.setHtml(html)
                return

            z, lat_min, lon_min, lat_max, lon_max = bounds
            lat_c = (lat_min + lat_max) / 2
            lon_c = (lon_min + lon_max) / 2

            tile_layer = f"""
                L.tileLayer('http://localhost:8081/{{z}}/{{x}}/{{y}}.png', {{
                    minZoom: {max(z-3, 1)},
                    maxZoom: {min(z+3, 19)},
                    noWrap: true,
                    attribution: 'Offline Tiles'
                }}).addTo(map);
            """




        elif self.offline:
            # offline sem tiles → mensagem clara
            html = """
            <html><body style='background:#222;color:#eee;display:flex;
            align-items:center;justify-content:center;font-family:sans-serif'>
            MAPA OFFLINE: Tiles não carregados<br/>
            </body></html>
            """
            self.setHtml(html)
            return
        else:
            if self.is_satellite:
                tile_layer = "L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {attribution: 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'}).addTo(map);"
            else:
                tile_layer = "L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);"

            lat_c = 0
            lon_c = 0
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8"/>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <style>html,body,#map{{margin:0;height:100%;}}</style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                var map = L.map('map').setView([{lat_c}, {lon_c}], 0);
                {tile_layer}


                var rocketMarker = null;
                var baseMarker = null;
                var pathPoly = L.polyline([], {{color: '#1e88e5'}}).addTo(map);
                var baseLine = null;
                var lockView = true;

                function addPoint(lat, lon) {{
                    var ll = [lat, lon];
                    pathPoly.addLatLng(ll);

                    if (!rocketMarker) {{
                        rocketMarker = L.circleMarker(ll, {{
                            radius: 7,
                            color: "#2e7d32",
                            fillColor: "#66bb6a",
                            fillOpacity: 0.9
                        }}).bindTooltip("Foguete", {{permanent:true, direction:"top"}}).addTo(map);
                    }} else {{
                        rocketMarker.setLatLng(ll);
                    }}

                    if (lockView) map.setView(ll, Math.max(map.getZoom(), 14));

                    if (baseMarker) {{
                        if (baseLine) map.removeLayer(baseLine);
                        baseLine = L.polyline([baseMarker.getLatLng(), rocketMarker.getLatLng()], {{color: '#ff9800'}}).addTo(map);
                    }}
                }}

                function setBase(lat, lon, zoom) {{
                    if (baseMarker) map.removeLayer(baseMarker);
                    baseMarker = L.circleMarker([lat, lon], {{
                        radius: 8,
                        color: "#b71c1c",
                        fillColor: "#f44336",
                        fillOpacity: 0.9
                    }}).bindTooltip("Base", {{permanent:true, direction:"top"}}).addTo(map);

                    // Centraliza no ponto com zoom arbitrário
                    map.setView([lat, lon], zoom);

                    if (rocketMarker) {{
                        if (baseLine) map.removeLayer(baseLine);
                        baseLine = L.polyline([baseMarker.getLatLng(), rocketMarker.getLatLng()], {{color: '#ff9800'}}).addTo(map);
                    }}
                }}
                

                function setPosition(lat, lon, z) {{
                    map.setView([lat, lon], z);
                }}

                // Botão de cadeado 🔒/🔓
                var lockControl = L.control({{position: 'topright'}});
                lockControl.onAdd = function(map) {{
                    var div = L.DomUtil.create('div', 'leaflet-control-lock');
                    div.innerHTML = "🔒";
                    div.style.background = "white";
                    div.style.padding = "4px";
                    div.style.cursor = "pointer";
                    div.onclick = function() {{
                        lockView = !lockView;
                        div.innerHTML = lockView ? "🔒" : "🔓";
                    }};
                    return div;
                }};
                lockControl.addTo(map);


                                // Rosa dos ventos triangular (8 direções), centralizada e espaçada
                var compass = L.control({{position: 'bottomright'}});
                compass.onAdd = function(map) {{
                    var div = L.DomUtil.create('div', 'compass');
                    div.innerHTML = `
                        <div style="position:relative;width:80px;height:80px;border:2px solid black;border-radius:50%;text-align:center;font-weight:bold;font-size:11px;line-height:1.1; transform: translateX(-15px);">
                            <!-- Norte -->
                            <div style="position:absolute;top:-12px;left:50%;transform:translateX(-50%);">▲<br/>N</div>
                            <!-- Sul -->
                            <div style="position:absolute;bottom:-12px;left:50%;transform:translateX(-50%) rotate(180deg);">▲<br/>S</div>
                            <!-- Leste -->
                            <div style="position:absolute;top:50%;right:-6px;transform:translateY(-50%) rotate(90deg);">▲<br/>L</div>
                            <!-- Oeste -->
                            <div style="position:absolute;top:50%;left:-6px;transform:translateY(-50%) rotate(-90deg);">▲<br/>O</div>

                            <!-- Nordeste -->
                            <div style="position:absolute;top:6px;right:6px;transform:rotate(45deg);">▲<br/>NE</div>
                            <!-- Sudeste -->
                            <div style="position:absolute;bottom:6px;right:6px;transform:rotate(135deg);">▲<br/>SE</div>
                            <!-- Sudoeste -->
                            <div style="position:absolute;bottom:6px;left:6px;transform:rotate(-135deg);">▲<br/>SO</div>
                            <!-- Noroeste -->
                            <div style="position:absolute;top:6px;left:6px;transform:rotate(-45deg);">▲<br/>NO</div>
                        </div>`;
                    return div;
                }};
                compass.addTo(map);

                // Controle de Zoom no canto inferior esquerdo
                var zoomLabel = L.control({{position:'bottomleft'}});
                zoomLabel.onAdd = function() {{
                    var div = L.DomUtil.create('div', 'zoom-label');
                    div.style.background = 'white';
                    div.style.padding = '4px 6px';
                    div.style.border = '1px solid #ccc';
                    div.style.fontFamily = 'sans-serif';
                    div.style.fontSize = '12px';
                    div.innerText = "Zoom: " + map.getZoom();
                    map.on('zoomend', function() {{
                        div.innerText = "Zoom: " + map.getZoom();
                    }});
                    return div;
                }};
                zoomLabel.addTo(map);

                window.addPoint = addPoint;
                window.setBase = setBase;
                window.setPosition = setPosition;
            </script>
        </body>
        </html>
        """
        self.setHtml(html)

    # Métodos Python → JS
    def add_point(self, lat, lon):
        self.page().runJavaScript(f"addPoint({lat}, {lon});")


    def set_base(self, lat, lon, zoom=12):
        self.page().runJavaScript(f"setBase({lat}, {lon}, {zoom});")


    def set_position(self, lat, lon, z=12):
        self.page().runJavaScript(f"setPosition({lat}, {lon}, {z});")

    def set_offline(self, offline: bool, tile_folder: str = None):
        self.offline = offline
        if tile_folder:
            self.tile_folder = tile_folder
        self._init_map()

    def toggle_map(self, state):
        if self.is_satellite:
            tile_layer = "L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);"
            self.is_satellite = False
        else:
            tile_layer = "L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {attribution: 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'}).addTo(map);"
            self.is_satellite = True

        self._init_map()
