# # views/map_widget.py

from __future__ import annotations

import os
import math
import pathlib
import threading
import socket
import http.server
import socketserver
import re
from functools import partial

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEnginePage,
    QWebEngineUrlRequestInterceptor,
    QWebEngineSettings,
)


def num2deg(x: int, y: int, z: int):
    """Converte tile x/y/z em lat/lon (canto NW do tile)."""
    n = 2.0 ** z
    lon_deg = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def _safe_int_from_stem(stem: str):
    """
    Aceita nomes como "123", "123@2x", "123-something".
    Retorna int ou None.
    """
    m = re.match(r"^(\d+)", stem)
    if not m:
        return None
    return int(m.group(1))


def get_tile_info(tile_folder: str):
    """
    Lê pasta de tiles e retorna:
    (min_zoom, max_zoom, lat_min, lon_min, lat_max, lon_max)

    Estrutura esperada: {z}/{x}/{y}.png
    """
    path = pathlib.Path(tile_folder)
    if not path.exists():
        return None

    zooms = sorted(
        int(p.name) for p in path.iterdir()
        if p.is_dir() and p.name.isdigit()
    )
    if not zooms:
        return None

    min_z, max_z = zooms[0], zooms[-1]

    # bounds calculado no maior zoom disponível (melhor precisão)
    z = max_z
    z_path = path / str(z)
    if not z_path.exists():
        return None

    xs = []
    for p in z_path.iterdir():
        if p.is_dir() and p.name.isdigit():
            xs.append(int(p.name))
    if not xs:
        return None

    min_x, max_x = min(xs), max(xs)

    ys = []
    for x in xs:
        for f in (z_path / str(x)).glob("*.*"):
            if not f.is_file():
                continue
            y = _safe_int_from_stem(f.stem)
            if y is not None:
                ys.append(y)

    if not ys:
        return None

    min_y, max_y = min(ys), max(ys)

    # canto superior esquerdo e inferior direito
    lat_max, lon_min = num2deg(min_x, min_y, z)
    lat_min, lon_max = num2deg(max_x + 1, max_y + 1, z)

    return (min_z, max_z, lat_min, lon_min, lat_max, lon_max)


def _find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class TileServer:
    def __init__(self, folder: str, port: int | None = None):
        self.folder = folder
        self.port = port or _find_free_port()
        self.httpd = None
        self.thread = None

    def start(self):
        handler = partial(http.server.SimpleHTTPRequestHandler, directory=self.folder)
        self.httpd = _ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
            except Exception:
                pass
            try:
                self.httpd.server_close()
            except Exception:
                pass
        self.httpd = None
        self.thread = None


class OfflineRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """
    Quando enabled=True:
      - bloqueia qualquer http/https que NÃO seja localhost/127.0.0.1
      - permite file://, qrc:// e o tile server local
    """
    def __init__(self, enabled: bool = False, parent=None):
        super().__init__(parent)
        self.enabled = enabled

    def interceptRequest(self, info):
        if not self.enabled:
            return

        url = info.requestUrl()
        scheme = url.scheme().lower()

        if scheme in ("http", "https"):
            host = url.host().lower()
            if host not in ("localhost", "127.0.0.1"):
                info.block(True)


class DebugPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(f"[JS] {sourceID}:{lineNumber} {message}")


class MapWidget(QWebEngineView):
    def __init__(
        self,
        offline: bool = False,
        satellite: bool = False,
        tile_folder: str | None = None,
        parent=None,
    ):
        super().__init__(parent)

        self.offline = offline
        self.tile_folder = tile_folder
        self.is_satellite = satellite

        self._base_order = ["dark", "light", "sat"]
        self._base_key = "dark" if not satellite else "sat"

        self._tile_server: TileServer | None = None
        self._tile_folder_served: str | None = None

        self._profile = QWebEngineProfile(f"MapProfile-{id(self)}", self)
        self._interceptor = OfflineRequestInterceptor(enabled=self.offline, parent=self._profile)
        self._profile.setUrlRequestInterceptor(self._interceptor)

        self._page = DebugPage(self._profile, self._profile)
        self.setPage(self._page)

        settings = self.page().settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)

        self._init_map()

    # -------------------------
    # lifecycle / server control
    # -------------------------
    def _ensure_tile_server(self, folder: str):
        folder = os.path.abspath(folder)

        if self._tile_server and self._tile_folder_served == folder:
            return

        if self._tile_server:
            self._tile_server.stop()
            self._tile_server = None
            self._tile_folder_served = None

        self._tile_server = TileServer(folder)
        self._tile_folder_served = folder
        self._tile_server.start()

    def _stop_tile_server(self):
        if self._tile_server:
            self._tile_server.stop()
        self._tile_server = None
        self._tile_folder_served = None

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    # -------------------------
    # paths / assets
    # -------------------------
    def _get_assets_dir(self) -> str:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        return os.path.join(base_dir, "assets")

    def _get_leaflet_sources(self, is_offline: bool) -> tuple[str, str]:
        if is_offline:
            return "leaflet/leaflet.css", "leaflet/leaflet.js"
        return (
            "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
            "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
        )

    # -------------------------
    # offline / online context
    # -------------------------
    def _offline_error_html(self, message: str) -> str:
        return f"""
        <html><body style="background:#111;color:#eee;display:flex;align-items:center;
        justify-content:center;font-family:sans-serif">
        {message}
        </body></html>
        """

    def _get_offline_tiles_context(self):
        if not self.tile_folder:
            self._stop_tile_server()
            return {
                "ok": False,
                "html": self._offline_error_html("❌🔌 MODO OFFLINE<br/>Tiles não carregados"),
            }

        folder = self.tile_folder
        pack_light = os.path.join(folder, "light")
        pack_dark = os.path.join(folder, "dark")
        pack_sat = os.path.join(folder, "sat")

        is_pack = os.path.isdir(pack_light) or os.path.isdir(pack_dark) or os.path.isdir(pack_sat)

        def _info_for(sub: str):
            p = os.path.join(folder, sub) if is_pack else folder
            return get_tile_info(p)

        info = _info_for("light") or _info_for("dark") or _info_for("sat")
        if not info:
            self._stop_tile_server()
            return {
                "ok": False,
                "html": self._offline_error_html(
                    "❌ Tiles offline não encontrados (estrutura {z}/{x}/{y}.png)"
                ),
            }

        self._ensure_tile_server(folder)
        port = self._tile_server.port
        print(f"[TileServer] http://127.0.0.1:{port}/  folder={self._tile_folder_served}")

        min_z, max_z, lat_min, lon_min, lat_max, lon_max = info

        return {
            "ok": True,
            "mode": "offline",
            "view_init_js": "var map = L.map('map');",
            "map_config_js": f"""
                {{
                    isPack: {str(is_pack).lower()},
                    root: 'http://127.0.0.1:{port}/',
                    minZoom: {min_z},
                    maxZoom: {max_z}
                }}
            """,
            "after_layers_js": f"""
                var bounds = L.latLngBounds([[{lat_min}, {lon_min}], [{lat_max}, {lon_max}]]);
                map.fitBounds(bounds, {{padding:[20,20]}});
                map.setMaxZoom({max_z});
            """,
        }

    def _get_online_tiles_context(self):
        self._stop_tile_server()
        return {
            "ok": True,
            "mode": "online",
            "view_init_js": "var map = L.map('map').setView([0, 0], 2);",
            "map_config_js": """
                {
                    isPack: false,
                    root: '',
                    minZoom: 0,
                    maxZoom: 19
                }
            """,
            "after_layers_js": """
                map.setMaxZoom(19);
            """,
        }

    def _get_map_context(self, is_offline: bool):
        if is_offline:
            return self._get_offline_tiles_context()
        return self._get_online_tiles_context()

    # -------------------------
    # HTML builders
    # -------------------------
    def _build_style_block(self) -> str:
        return """
        <style>
          #compassRoot{
            width:80px;
            height:80px;
            pointer-events:none;
            user-select:none;
          }

          /* tema: light = bússola clara (pra dark/sat) */
          #compassRoot[data-theme="light"]{
            color:#ffffff;
            filter: drop-shadow(0 0 2px rgba(0,0,0,0.55));
          }

          /* tema: dark = bússola escura (pra light) */
          #compassRoot[data-theme="dark"]{
            color:#111111;
            filter: drop-shadow(0 0 2px rgba(255,255,255,0.50));
          }

          html, body, #map {
        margin: 0;
        height: 100%;
        }

        #map {
        position: relative;
        }

        /* HUD central */
        #centerHud {
        position: absolute;
        top: 8px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 9000;
        background: rgba(255,255,255,0.96);
        border: 1px solid #cfcfcf;
        padding: 4px 10px;
        font-family: sans-serif;
        font-size: 12px;
        font-weight: 600;
        border-radius: 6px;
        color: #222;
        box-shadow: 0 2px 6px rgba(0,0,0,0.18);
        pointer-events: none;
        }

        /* garante que os containers dos controles sempre fiquem acima */
        .leaflet-top,
        .leaflet-bottom {
        z-index: 10000 !important;
        pointer-events: none;
        }

        /* e os controles em si continuam clicáveis */
        .leaflet-top .leaflet-control,
        .leaflet-bottom .leaflet-control {
        z-index: 10001 !important;
        pointer-events: auto !important;
        }

        /* seus botões customizados */
        .leaflet-control-urd-btn {
        background: rgba(255,255,255,0.96);
        border: 1px solid #cfcfcf;
        border-radius: 8px;
        padding: 6px 12px;
        cursor: pointer;
        font-family: sans-serif;
        font-size: 12px;
        font-weight: 500;
        line-height: 1.2;
        box-shadow: 0 2px 6px rgba(0,0,0,0.18);
        user-select: none;
        color: #222;
        text-align: center;
        }

        .leaflet-control-urd-btn:hover {
        background: #f7f7f7;
        }

        .leaflet-control-urd-btn-bottom-center {
        min-width: 100px;
        }

        .leaflet-control-lock-btn {
        min-width: 32px;
        padding: 4px 8px;
        font-size: 16px;
        font-weight: 700;
        }

        .zoom-label-box {
        min-width: 80px;
        }
        </style>
        """

    def _build_base_layers_js(self) -> str:
        return """
            function makeTileLayer(url, options) {
              return L.tileLayer(url, options || {});
            }

            function buildBaseLayers(mode, cfg) {
              var baseLayers = {};

              if (mode === "offline") {
                function mkOffline(rel) {
                  var prefix = rel ? (rel + "/") : "";
                  var url = cfg.root + prefix + "{z}/{x}/{y}.png";
                  return makeTileLayer(url, {
                    minZoom: cfg.minZoom,
                    maxZoom: cfg.maxZoom,
                    noWrap: true,
                    tms: false,
                    attribution: 'Offline Tiles'
                  });
                }

                if (cfg.isPack) {
                  baseLayers.light = mkOffline("light");
                  baseLayers.dark  = mkOffline("dark");
                  baseLayers.sat   = mkOffline("sat");
                } else {
                  baseLayers.light = mkOffline("");
                  baseLayers.dark  = baseLayers.light;
                  baseLayers.sat   = baseLayers.light;
                }
              } else {
                baseLayers.light = makeTileLayer(
                  'https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png',
                  { maxZoom: 19, attribution: '© OSM © CARTO' }
                );

                baseLayers.dark = makeTileLayer(
                  'https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png',
                  { maxZoom: 19, attribution: '© OSM © CARTO' }
                );

                baseLayers.sat = makeTileLayer(
                  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                  { maxZoom: 19, attribution: 'Tiles © Esri' }
                );
              }

              return baseLayers;
            }
        """

    def _build_map_script(self, context: dict, base_key: str) -> str:
        return f"""
        <script>
          {context["view_init_js"]}

          {self._build_base_layers_js()}

          var mapMode = "{context["mode"]}";
          var mapCfg = {context["map_config_js"]};
          var baseLayers = buildBaseLayers(mapMode, mapCfg);

          {context["after_layers_js"]}

          var rocketMarker = null;
          var baseMarker = null;
          var pathPoly = L.polyline([], {{color: '#1e88e5'}}).addTo(map);
          var baseLine = null;
          var lockView = true;

          var baseOrder = ["dark", "light", "sat"];
          var currentBase = "%BASE_KEY%";

          function baseLabel(name){{
            if (name === "dark") return "Dark Map";
            if (name === "light") return "Light Map";
            if (name === "sat") return "Satellite Map";
            return "Map";
          }}

          function nextBaseLabel(name){{
            var idx = baseOrder.indexOf(name);
            if (idx < 0) idx = 0;
            idx = (idx + 1) % baseOrder.length;
            return baseLabel(baseOrder[idx]);
          }}

          var cycleBtnDiv = null;
          function updateCycleMapButton(){{
            if (!cycleBtnDiv) return;
            cycleBtnDiv.innerHTML = nextBaseLabel(currentBase);
            cycleBtnDiv.title = "Trocar tipo de mapa";
          }}

          function compassThemeFor(baseName){{
            if (baseName === "light") return "dark";
            return "light";
          }}

          function setCompassTheme(theme){{
            var el = document.getElementById("compassRoot");
            if (!el) return;
            el.setAttribute("data-theme", theme);
          }}

          function setBaseLayer(name){{
            if (!baseLayers || !baseLayers[name]) return;

            if (currentBase && baseLayers[currentBase] && map.hasLayer(baseLayers[currentBase])) {{
              map.removeLayer(baseLayers[currentBase]);
            }}

            currentBase = name;
            baseLayers[currentBase].addTo(map);

            setCompassTheme(compassThemeFor(currentBase));
            updateCycleMapButton();
          }}

          function cycleBaseLayer(){{
            var idx = baseOrder.indexOf(currentBase);
            if (idx < 0) idx = 0;
            idx = (idx + 1) % baseOrder.length;
            setBaseLayer(baseOrder[idx]);
          }}

          window.setBaseLayer = setBaseLayer;
          window.cycleBaseLayer = cycleBaseLayer;

          function addPoint(lat, lon) {{
            var ll = [lat, lon];
            pathPoly.addLatLng(ll);

            if (!rocketMarker) {{
              rocketMarker = L.circleMarker(ll, {{
                radius: 7, color: "#2e7d32",
                fillColor: "#66bb6a", fillOpacity: 0.9
              }}).bindTooltip("Foguete", {{permanent:true, direction:"top"}}).addTo(map);
            }} else {{
              rocketMarker.setLatLng(ll);
            }}

            if (lockView) {{
              if (map.getZoom() < 14) map.setZoom(14);
              map.panTo(ll, {{animate:false}});
            }}

            if (baseMarker) {{
              if (baseLine) map.removeLayer(baseLine);
              baseLine = L.polyline([baseMarker.getLatLng(), rocketMarker.getLatLng()], {{
                color: '#ff9800'
              }}).addTo(map);
            }}
          }}

          function setBase(lat, lon, zoom) {{
            if (baseMarker) map.removeLayer(baseMarker);
            baseMarker = L.circleMarker([lat, lon], {{
              radius: 8, color: "#b71c1c",
              fillColor: "#f44336", fillOpacity: 0.9
            }}).bindTooltip("Base", {{permanent:true, direction:"top"}}).addTo(map);

            if (lockView) {{
              map.setView([lat, lon], zoom);
            }}

            if (rocketMarker) {{
              if (baseLine) map.removeLayer(baseLine);
              baseLine = L.polyline([baseMarker.getLatLng(), rocketMarker.getLatLng()], {{
                color: '#ff9800'
              }}).addTo(map);
            }}
          }}

          function setPosition(lat, lon, z) {{
            map.setView([lat, lon], z);
          }}

          var lockControl = L.control({{position: 'topright'}});
          lockControl.onAdd = function(map) {{
            var div = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-urd-btn leaflet-control-lock-btn');
            div.innerHTML = "🔒";
            div.title = "Travar/destravar mapa";
            L.DomEvent.disableClickPropagation(div);
            L.DomEvent.on(div, 'click', function() {{
              lockView = !lockView;
              div.innerHTML = lockView ? "🔒" : "🔓";
            }});
            return div;
          }};
          lockControl.addTo(map);

          var cycleMapControl = L.control({{position: 'bottomleft'}});
          cycleMapControl.onAdd = function(map) {{
            cycleBtnDiv = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-urd-btn leaflet-control-urd-btn-bottom-center');
            cycleBtnDiv.title = "Trocar tipo de mapa";
            L.DomEvent.disableClickPropagation(cycleBtnDiv);
            L.DomEvent.on(cycleBtnDiv, 'click', function() {{
              cycleBaseLayer();
            }});
            updateCycleMapButton();
            return cycleBtnDiv;
          }};
          cycleMapControl.addTo(map);

          var compass = L.control({{position:'bottomright'}});
          compass.onAdd = function(map){{
            var div = L.DomUtil.create('div');
            div.id = "compassRoot";
            div.setAttribute("data-theme","light");

            div.innerHTML = `
              <svg viewBox="0 0 120 120" width="80" height="80"
                  xmlns="http://www.w3.org/2000/svg" aria-label="Compass">

                <circle cx="60" cy="60" r="38"
                        fill="none" stroke="currentColor" stroke-width="4" opacity="0.95"/>

                <g fill="currentColor" opacity="0.95">
                  <polygon points="60,26 66,40 60,36 54,40"/>
                  <polygon points="60,94 66,80 60,84 54,80"/>
                  <polygon points="94,60 80,54 84,60 80,66"/>
                  <polygon points="26,60 40,54 36,60 40,66"/>
                </g>

                <g fill="currentColor" opacity="0.75">
                  <polygon points="84.0416,35.9584 81.9203,45.1508 74.8492,38.0797"/>
                  <polygon points="84.0416,84.0416 74.8492,81.9203 81.9203,74.8492"/>
                  <polygon points="35.9584,84.0416 38.0797,74.8492 45.1508,81.9203"/>
                  <polygon points="35.9584,35.9584 45.1508,38.0797 38.0797,45.1508"/>
                </g>

                <circle cx="60" cy="60" r="6" fill="currentColor" opacity="0.15"/>

                <g font-family="sans-serif" font-size="10" font-weight="800" fill="currentColor">
                  <text x="60" y="10"  text-anchor="middle">N</text>
                  <text x="98" y="24"  text-anchor="middle">NE</text>
                  <text x="114" y="64" text-anchor="middle">E</text>
                  <text x="98" y="110" text-anchor="middle">SE</text>
                  <text x="60" y="118" text-anchor="middle">S</text>
                  <text x="22" y="110" text-anchor="middle">SW</text>
                  <text x="6"  y="64"  text-anchor="middle">W</text>
                  <text x="22" y="24"  text-anchor="middle">NW</text>
                </g>
              </svg>
            `;
            return div;
          }};
          compass.addTo(map);

          setBaseLayer(currentBase);

          var zoomLabel = L.control({{position:'bottomleft'}});
          zoomLabel.onAdd = function() {{
            var div = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-urd-btn zoom-label-box');
            div.innerText = "Zoom: " + map.getZoom();
            map.on('zoomend', function() {{
              div.innerText = "Zoom: " + map.getZoom();
            }});
            return div;
          }};
          zoomLabel.addTo(map);

          function updateCenterHud(){{
            var c = map.getCenter();
            document.getElementById('centerHud').innerText =
              `${{c.lat.toFixed(6)}}, ${{c.lng.toFixed(6)}}`;
          }}

          map.on('move zoom', updateCenterHud);
          updateCenterHud();

          function setViewLL(lat, lon, z){{
            if (z === undefined || z === null) z = map.getZoom();
            map.setView([lat, lon], z);
          }}

          function getView(){{
            var c = map.getCenter();
            return {{lat: c.lat, lon: c.lng, zoom: map.getZoom()}};
          }}

          function resetMap(){{
            if (rocketMarker){{ map.removeLayer(rocketMarker); rocketMarker = null; }}
            if (baseMarker){{ map.removeLayer(baseMarker); baseMarker = null; }}
            if (baseLine){{ map.removeLayer(baseLine); baseLine = null; }}
            pathPoly.setLatLngs([]);
          }}

          window.getBaseLayer = function(){{ return currentBase; }};

          window.setBaseLayer = setBaseLayer;
          window.cycleBaseLayer = cycleBaseLayer;
          window.getBaseLayer = function(){{ return currentBase; }};

          window.setViewLL = setViewLL;
          window.getView = getView;
          window.resetMap = resetMap;

          window.addPoint = addPoint;
          window.setBase = setBase;
          window.setPosition = setPosition;
        </script>
        """.replace("%BASE_KEY%", base_key)

    def _build_html(self, leaflet_css: str, leaflet_js: str, context: dict, base_key: str) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8"/>
          <link rel="stylesheet" href="{leaflet_css}"/>
          <script src="{leaflet_js}"></script>
          <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
          {self._build_style_block()}
        </head>
        <body>
          <div id="centerHud"></div>
          <div id="map"></div>
          {self._build_map_script(context, base_key)}
        </body>
        </html>
        """

    # -------------------------
    # main map builder
    # -------------------------
    def _init_map(self):
        is_offline = bool(self.offline)
        self._interceptor.enabled = is_offline

        leaflet_css, leaflet_js = self._get_leaflet_sources(is_offline)
        base_key = getattr(self, "_base_key", "dark")
        context = self._get_map_context(is_offline)

        if not context["ok"]:
            self.setHtml(context["html"])
            return

        html = self._build_html(
            leaflet_css=leaflet_css,
            leaflet_js=leaflet_js,
            context=context,
            base_key=base_key,
        )

        if is_offline:
            assets_dir = self._get_assets_dir()
            self.setHtml(html, QUrl.fromLocalFile(os.path.join(assets_dir, "")))
        else:
            self.setHtml(html)

    def cleanup(self):
        try:
            self._stop_tile_server()
        except Exception:
            pass

        try:
            old_page = self.page()
            if old_page:
                old_page.triggerAction(QWebEnginePage.Stop)
                self.setPage(QWebEnginePage(QWebEngineProfile.defaultProfile(), self))
                old_page.deleteLater()
        except Exception:
            pass

    # -------------------------
    # Python -> JS
    # -------------------------
    def add_point(self, lat, lon):
        self.page().runJavaScript(f"addPoint({lat}, {lon});")

    def set_base(self, lat, lon, zoom=12):
        self.page().runJavaScript(f"setBase({lat}, {lon}, {zoom});")

    def set_position(self, lat, lon, z=12):
        self.page().runJavaScript(f"setPosition({lat}, {lon}, {z});")

    def set_view(self, lat: float, lon: float, zoom: int | None = None):
        if zoom is None:
            self.page().runJavaScript(f"setViewLL({lat}, {lon});")
        else:
            self.page().runJavaScript(f"setViewLL({lat}, {lon}, {zoom});")

    def get_view(self, callback):
        js = (
            "(()=>{"
            "  try{"
            "    const el = document.getElementById('centerHud');"
            "    if (el && el.innerText) {"
            "      const z = (window.map && window.map.getZoom) ? window.map.getZoom() : 0;"
            "      return el.innerText + '|' + z;"
            "    }"
            "    if (!window.map) return '';"
            "    const c = window.map.getCenter();"
            "    const z = window.map.getZoom ? window.map.getZoom() : 0;"
            "    return c.lat.toFixed(6) + ', ' + c.lng.toFixed(6) + '|' + z;"
            "  }catch(e){ return ''; }"
            "})()"
        )
        self.page().runJavaScript(js, callback)

    def reset_map(self):
        self.page().runJavaScript("resetMap();")

    # -------------------------
    # toggles
    # -------------------------
    def set_offline(self, offline: bool, tile_folder: str | None = None):
        self.offline = bool(offline)
        if tile_folder is not None:
            self.tile_folder = tile_folder
        self._init_map()

    def toggle_map(self):
        self.page().runJavaScript("cycleBaseLayer();")
        self.page().runJavaScript("getBaseLayer();")





# from __future__ import annotations

# import os
# import math
# import pathlib
# import threading
# import socket
# import http.server
# import socketserver
# import re
# from functools import partial

# from PySide6.QtCore import QUrl
# from PySide6.QtWebEngineWidgets import QWebEngineView
# from PySide6.QtWebEngineCore import (
#     QWebEngineProfile,
#     QWebEnginePage,
#     QWebEngineUrlRequestInterceptor,
# )

# from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineProfile
# from PySide6.QtCore import QUrl, QTimer


# def num2deg(x: int, y: int, z: int):
#     """Converte tile x/y/z em lat/lon (canto NW do tile)."""
#     n = 2.0 ** z
#     lon_deg = x / n * 360.0 - 180.0
#     lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
#     lat_deg = math.degrees(lat_rad)
#     return lat_deg, lon_deg


# def _safe_int_from_stem(stem: str):
#     """
#     Aceita nomes como "123", "123@2x", "123-something".
#     Retorna int ou None.
#     """
#     m = re.match(r"^(\d+)", stem)
#     if not m:
#         return None
#     return int(m.group(1))


# def get_tile_info(tile_folder: str):
#     """
#     Lê pasta de tiles e retorna:
#     (min_zoom, max_zoom, lat_min, lon_min, lat_max, lon_max)

#     Estrutura esperada: {z}/{x}/{y}.png
#     """
#     path = pathlib.Path(tile_folder)
#     if not path.exists():
#         return None

#     zooms = sorted(
#         int(p.name) for p in path.iterdir()
#         if p.is_dir() and p.name.isdigit()
#     )
#     if not zooms:
#         return None

#     min_z, max_z = zooms[0], zooms[-1]

#     # bounds calculado no maior zoom disponível (melhor precisão)
#     z = max_z
#     z_path = path / str(z)
#     if not z_path.exists():
#         return None

#     xs = []
#     for p in z_path.iterdir():
#         if p.is_dir() and p.name.isdigit():
#             xs.append(int(p.name))
#     if not xs:
#         return None

#     min_x, max_x = min(xs), max(xs)

#     ys = []
#     for x in xs:
#         for f in (z_path / str(x)).glob("*.*"):
#             if not f.is_file():
#                 continue
#             # aceita png/jpg/etc, desde que o nome comece com número
#             y = _safe_int_from_stem(f.stem)
#             if y is not None:
#                 ys.append(y)

#     if not ys:
#         return None

#     min_y, max_y = min(ys), max(ys)

#     # canto superior esquerdo e inferior direito
#     lat_max, lon_min = num2deg(min_x, min_y, z)
#     lat_min, lon_max = num2deg(max_x + 1, max_y + 1, z)

#     return (min_z, max_z, lat_min, lon_min, lat_max, lon_max)


# def _find_free_port():
#     s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     s.bind(("127.0.0.1", 0))
#     port = s.getsockname()[1]
#     s.close()
#     return port


# class _ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
#     daemon_threads = True
#     allow_reuse_address = True


# class TileServer:
#     def __init__(self, folder: str, port: int | None = None):
#         self.folder = folder
#         self.port = port or _find_free_port()
#         self.httpd = None
#         self.thread = None

#     def start(self):
#         # NÃO usar os.chdir (isso quebra o app inteiro)
#         handler = partial(http.server.SimpleHTTPRequestHandler, directory=self.folder)
#         self.httpd = _ThreadingHTTPServer(("127.0.0.1", self.port), handler)
#         self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
#         self.thread.start()

#     def stop(self):
#         if self.httpd:
#             try:
#                 self.httpd.shutdown()
#             except Exception:
#                 pass
#             try:
#                 self.httpd.server_close()
#             except Exception:
#                 pass
#         self.httpd = None
#         self.thread = None


# class OfflineRequestInterceptor(QWebEngineUrlRequestInterceptor):
#     """
#     Quando enabled=True:
#       - bloqueia qualquer http/https que NÃO seja localhost/127.0.0.1
#       - permite file://, qrc:// e o tile server local
#     """
#     def __init__(self, enabled: bool = False, parent=None):
#         super().__init__(parent)
#         self.enabled = enabled

#     def interceptRequest(self, info):
#         if not self.enabled:
#             return

#         url = info.requestUrl()
#         scheme = url.scheme().lower()

#         if scheme in ("http", "https"):
#             host = url.host().lower()
#             if host not in ("localhost", "127.0.0.1"):
#                 info.block(True)

# from PySide6.QtWebEngineCore import QWebEnginePage
# class DebugPage(QWebEnginePage):
#     def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
#         print(f"[JS] {sourceID}:{lineNumber} {message}")


# class MapWidget(QWebEngineView):
#     def __init__(self, offline: bool = False, satellite: bool = False,
#                  tile_folder: str | None = None, parent=None):
#         super().__init__(parent)

#         self.offline = offline                 # "forced offline" (offline real)
#         self.tile_folder = tile_folder
#         self.is_satellite = satellite

#         self._base_order = ["dark", "light", "sat"]
#         self._base_key = "dark" if not satellite else "sat"

#         self._tile_server: TileServer | None = None
#         self._tile_folder_served: str | None = None

#         self._profile = QWebEngineProfile(f"MapProfile-{id(self)}", self)
#         self._interceptor = OfflineRequestInterceptor(enabled=self.offline, parent=self._profile)
#         self._profile.setUrlRequestInterceptor(self._interceptor)

#         self._page = DebugPage(self._profile, self._profile)  # ou QWebEnginePage(...)
#         self.setPage(self._page)

#         # permitir file:// acessar http://127.0.0.1
#         s = self.page().settings()
#         s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
#         s.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)

#         self._init_map()

#     # -------------------------
#     # lifecycle / server control
#     # -------------------------
#     def _ensure_tile_server(self, folder: str):
#         folder = os.path.abspath(folder)

#         if self._tile_server and self._tile_folder_served == folder:
#             return  # já ok

#         # trocar pasta => reinicia server
#         if self._tile_server:
#             self._tile_server.stop()
#             self._tile_server = None
#             self._tile_folder_served = None

#         self._tile_server = TileServer(folder)
#         self._tile_folder_served = folder
#         self._tile_server.start()

#     def _stop_tile_server(self):
#         if self._tile_server:
#             self._tile_server.stop()
#         self._tile_server = None
#         self._tile_folder_served = None

#     def closeEvent(self, event):
#         self.cleanup()
#         super().closeEvent(event)

#     # -------------------------
#     # main map builder
#     # -------------------------
#     def _init_map(self):
#         is_offline = bool(self.offline)
#         self._interceptor.enabled = is_offline

#         BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
#         ASSETS_DIR = os.path.join(BASE_DIR, "assets")

#         if is_offline:
#             leaflet_css = "leaflet/leaflet.css"
#             leaflet_js = "leaflet/leaflet.js"
#         else:
#             leaflet_css = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
#             leaflet_js = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"

#         base_key = getattr(self, "_base_key", "dark")

#         tile_layer_js = ""
#         view_init_js = "var map = L.map('map').setView([0, 0], 2);"

#         # -------- OFFLINE --------
#         if is_offline:
#             if not self.tile_folder:
#                 self._stop_tile_server()
#                 self.setHtml(
#                     """
#                     <html><body style="background:#111;color:#eee;display:flex;align-items:center;
#                     justify-content:center;font-family:sans-serif">
#                     ❌🔌 MODO OFFLINE<br/>Tiles não carregados
#                     </body></html>
#                     """
#                 )
#                 return

#             folder = self.tile_folder
#             pack_light = os.path.join(folder, "light")
#             pack_dark  = os.path.join(folder, "dark")
#             pack_sat   = os.path.join(folder, "sat")

#             is_pack = os.path.isdir(pack_light) or os.path.isdir(pack_dark) or os.path.isdir(pack_sat)

#             def _info_for(sub):
#                 p = os.path.join(folder, sub) if is_pack else folder
#                 return get_tile_info(p)

#             # tenta achar info usando uma pasta que exista
#             info = _info_for("light") or _info_for("dark") or _info_for("sat")

#             if not info:
#                 self._stop_tile_server()
#                 self.setHtml(
#                     """
#                     <html><body style="background:#111;color:#eee;display:flex;align-items:center;
#                     justify-content:center;font-family:sans-serif">
#                     ❌ Tiles offline não encontrados (estrutura {z}/{x}/{y}.png)
#                     </body></html>
#                     """
#                 )
#                 return

#             self._ensure_tile_server(folder)
#             port = self._tile_server.port
#             print(f"[TileServer] http://127.0.0.1:{self._tile_server.port}/  folder={self._tile_folder_served}")


#             min_z, max_z, lat_min, lon_min, lat_max, lon_max = info

#             tile_layer_js = f"""
#                 var baseLayers = {{}};

#                 // offline: se for pack, usa subpastas; senão usa direto
#                 var isPack = {str(is_pack).lower()};
#                 var root = 'http://127.0.0.1:{port}/';

#                 function mkOffline(name, rel) {{
#                     var url = root + rel + '/{{z}}/{{x}}/{{y}}.png';
#                     return L.tileLayer(url, {{
#                         minZoom: {min_z},
#                         maxZoom: {max_z},
#                         noWrap: true,
#                         tms: false,
#                         attribution: 'Offline Tiles'
#                     }});
#                 }}

#                 if (isPack) {{
#                     baseLayers.light = mkOffline('light', 'light');
#                     baseLayers.dark  = mkOffline('dark',  'dark');
#                     baseLayers.sat   = mkOffline('sat',   'sat');
#                 }} else {{
#                     // compat: pasta antiga (um único tileset)
#                     baseLayers.light = mkOffline('single', '');
#                     baseLayers.dark  = baseLayers.light;
#                     baseLayers.sat   = baseLayers.light;
#                 }}

#                 // bounds do tileset que achamos
#                 var bounds = L.latLngBounds([[{lat_min}, {lon_min}], [{lat_max}, {lon_max}]]);
#                 map.fitBounds(bounds, {{padding:[20,20]}});
#                 map.setMaxZoom({max_z});
#             """

#             view_init_js = "var map = L.map('map');"


#         # -------- ONLINE --------
#         else:
#             self._stop_tile_server()

#             tile_layer_js = """
#                 var baseLayers = {};

#                 baseLayers.light = L.tileLayer(
#                   'https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png',
#                   { maxZoom: 19, attribution: '© OSM © CARTO' }
#                 );

#                 baseLayers.dark = L.tileLayer(
#                   'https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png',
#                   { maxZoom: 19, attribution: '© OSM © CARTO' }
#                 );

#                 baseLayers.sat = L.tileLayer(
#                   'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
#                   { maxZoom: 19, attribution: 'Tiles © Esri' }
#                 );

#                 map.setMaxZoom(19);
#             """


#         html = f"""
#         <!DOCTYPE html>
#         <html>
#         <head>
#           <meta charset="utf-8"/>
#           <link rel="stylesheet" href="{leaflet_css}"/>
#           <script src="{leaflet_js}"></script>
#           <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
#           <style>
#             #compassRoot{{
#             width:80px;
#             height:80px;
#             pointer-events:none;
#             user-select:none;
#             }}

#             /* tema: light = bússola clara (pra dark/sat) */
#             #compassRoot[data-theme="light"]{{
#             color:#ffffff;
#             filter: drop-shadow(0 0 2px rgba(0,0,0,0.55));
#             }}

#             /* tema: dark = bússola escura (pra light) */
#             #compassRoot[data-theme="dark"]{{
#             color:#111111;
#             filter: drop-shadow(0 0 2px rgba(255,255,255,0.50));
#             }}
          
#             #centerHud{{
#             position:absolute;
#             top:8px;
#             left:50%;
#             transform:translateX(-50%);
#             z-index:9999;
#             background: rgba(255,255,255,0.96);
#             border:1px solid #cfcfcf;
#             padding:4px 10px;
#             font-family:sans-serif;
#             font-size:12px;
#             font-weight:600;
#             border-radius:6px;
#             color:#222;
#             box-shadow: 0 2px 6px rgba(0,0,0,0.18);
#             pointer-events:none;
#             }}
#             html,body,#map{{margin:0;height:100%;}}

#             .leaflet-control-urd-btn {{
#             background: rgba(255,255,255,0.96);
#             border: 1px solid #cfcfcf;
#             border-radius: 8px;
#             padding: 6px 12px;
#             cursor: pointer;
#             font-family: sans-serif;
#             font-size: 12px;
#             font-weight: 500;
#             line-height: 1.2;
#             box-shadow: 0 2px 6px rgba(0,0,0,0.18);
#             user-select: none;
#             color: #222;
#             text-align: center;
#             }}

#             .leaflet-control-urd-btn:hover {{
#             background: #f7f7f7;
#             }}

#             .leaflet-control-urd-btn-bottom-center {{
#             min-width: 100px;
#             }}

#             .leaflet-control-lock-btn {{
#             min-width: 32px;
#             padding: 4px 8px;
#             font-size: 16px;
#             font-weight: 700;
#             }}

#             .zoom-label-box {{
#             min-width: 80px;
#             }}
            
#           </style>
#         </head>
#         <body>
#           <div id="centerHud"></div>
#           <div id="map"></div>
#           <script>
#             {view_init_js}
#             {tile_layer_js}

#             var rocketMarker = null;
#             var baseMarker = null;
#             var pathPoly = L.polyline([], {{color: '#1e88e5'}}).addTo(map);
#             var baseLine = null;
#             var lockView = true;

#            baseOrder = ["dark", "light", "sat"];
#            currentBase = "%BASE_KEY%";

#             function baseLabel(name){{
#             if (name === "dark") return "Dark Map";
#             if (name === "light") return "Light Map";
#             if (name === "sat") return "Satellite Map";
#             return "Map";
#             }}

#             function nextBaseLabel(name){{
#             var idx = baseOrder.indexOf(name);
#             if (idx < 0) idx = 0;
#             idx = (idx + 1) % baseOrder.length;
#             return baseLabel(baseOrder[idx]);
#             }}

#             var cycleBtnDiv = null;
#             function updateCycleMapButton(){{
#             if (!cycleBtnDiv) return;
#             cycleBtnDiv.innerHTML = nextBaseLabel(currentBase);
#             cycleBtnDiv.title = "Trocar tipo de mapa";
#             }}

#             function compassThemeFor(baseName){{
#             if (baseName === "light") return "dark"; // mapa claro => bússola escura
#             return "light";                          // dark/sat => bússola clara
#             }}

#             function setCompassTheme(theme){{
#             var el = document.getElementById("compassRoot");
#             if (!el) return;
#             el.setAttribute("data-theme", theme);
#             }}

#             function setBaseLayer(name){{
#             if (!baseLayers || !baseLayers[name]) return;

#             if (currentBase && baseLayers[currentBase] && map.hasLayer(baseLayers[currentBase])) {{
#                 map.removeLayer(baseLayers[currentBase]);
#             }}

#             currentBase = name;
#             baseLayers[currentBase].addTo(map);

#             setCompassTheme(compassThemeFor(currentBase));
#             updateCycleMapButton();
#             }}

#             function cycleBaseLayer(){{
#             var idx = baseOrder.indexOf(currentBase);
#             if (idx < 0) idx = 0;
#             idx = (idx + 1) % baseOrder.length;
#             setBaseLayer(baseOrder[idx]);
#             }}

#             window.setBaseLayer = setBaseLayer;
#             window.cycleBaseLayer = cycleBaseLayer;

#             function addPoint(lat, lon) {{
#             var ll = [lat, lon];
#             pathPoly.addLatLng(ll);

#             if (!rocketMarker) {{
#                 rocketMarker = L.circleMarker(ll, {{
#                 radius: 7, color: "#2e7d32",
#                 fillColor: "#66bb6a", fillOpacity: 0.9
#                 }}).bindTooltip("Foguete", {{permanent:true, direction:"top"}}).addTo(map);
#             }} else {{
#                 rocketMarker.setLatLng(ll);
#             }}

#             // ✅ só segue o foguete se estiver travado
#             if (lockView) {{
#                 // mantém o zoom do usuário; só sobe para 14 se estiver abaixo
#                 if (map.getZoom() < 14) map.setZoom(14);
#                 map.panTo(ll, {{animate:false}});
#             }}

#             if (baseMarker) {{
#                 if (baseLine) map.removeLayer(baseLine);
#                 baseLine = L.polyline([baseMarker.getLatLng(), rocketMarker.getLatLng()], {{
#                 color: '#ff9800'
#                 }}).addTo(map);
#             }}
#             }}

#             function setBase(lat, lon, zoom) {{
#             if (baseMarker) map.removeLayer(baseMarker);
#             baseMarker = L.circleMarker([lat, lon], {{
#                 radius: 8, color: "#b71c1c",
#                 fillColor: "#f44336", fillOpacity: 0.9
#             }}).bindTooltip("Base", {{permanent:true, direction:"top"}}).addTo(map);

#             // ✅ só centraliza na base se estiver travado
#             if (lockView) {{
#                 map.setView([lat, lon], zoom);
#             }}

#             if (rocketMarker) {{
#                 if (baseLine) map.removeLayer(baseLine);
#                 baseLine = L.polyline([baseMarker.getLatLng(), rocketMarker.getLatLng()], {{
#                 color: '#ff9800'
#                 }}).addTo(map);
#             }}
#             }}

#             function setPosition(lat, lon, z) {{
#               map.setView([lat, lon], z);
#             }}

#             // Botão de cadeado 🔒/🔓
#             var lockControl = L.control({{position: 'topright'}});
#             lockControl.onAdd = function(map) {{
#             var div = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-urd-btn leaflet-control-lock-btn');
#             div.innerHTML = "🔒";
#             div.title = "Travar/destravar mapa";
#             L.DomEvent.disableClickPropagation(div);
#             L.DomEvent.on(div, 'click', function() {{
#                 lockView = !lockView;
#                 div.innerHTML = lockView ? "🔒" : "🔓";
#             }});
#             return div;
#             }};
#             lockControl.addTo(map);

#             var cycleMapControl = L.control({{position: 'bottomleft'}});
#             cycleMapControl.onAdd = function(map) {{
#                 cycleBtnDiv = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-urd-btn leaflet-control-urd-btn-bottom-center');
#                 cycleBtnDiv.title = "Trocar tipo de mapa";
#                 L.DomEvent.disableClickPropagation(cycleBtnDiv);
#                 L.DomEvent.on(cycleBtnDiv, 'click', function() {{
#                     cycleBaseLayer();
#                 }});
#                 updateCycleMapButton();
#                 return cycleBtnDiv;
#             }};
#             cycleMapControl.addTo(map);

#             var compass = L.control({{position:'bottomright'}});
#             compass.onAdd = function(map){{
#             var div = L.DomUtil.create('div');
#             div.id = "compassRoot";
#             div.setAttribute("data-theme","light"); // será atualizado pelo setBaseLayer

#             div.innerHTML = `
#                 <svg viewBox="0 0 120 120" width="80" height="80"
#                     xmlns="http://www.w3.org/2000/svg" aria-label="Compass">

#                 <!-- ring -->
#                 <circle cx="60" cy="60" r="38"
#                         fill="none" stroke="currentColor" stroke-width="4" opacity="0.95"/>

#                 <!-- main arrows (inward) -->
#                 <g fill="currentColor" opacity="0.95">
#                     <polygon points="60,26 66,40 60,36 54,40"/>   <!-- N -->
#                     <polygon points="60,94 66,80 60,84 54,80"/>   <!-- S -->
#                     <polygon points="94,60 80,54 84,60 80,66"/>   <!-- E -->
#                     <polygon points="26,60 40,54 36,60 40,66"/>   <!-- W -->
#                 </g>

#                 <!-- diagonal arrows (true triangles, RADIAL) -->
#                 <g fill="currentColor" opacity="0.75">
#                     <polygon points="84.0416,35.9584 81.9203,45.1508 74.8492,38.0797"/> <!-- NE -->
#                     <polygon points="84.0416,84.0416 74.8492,81.9203 81.9203,74.8492"/> <!-- SE -->
#                     <polygon points="35.9584,84.0416 38.0797,74.8492 45.1508,81.9203"/> <!-- SW -->
#                     <polygon points="35.9584,35.9584 45.1508,38.0797 38.0797,45.1508"/> <!-- NW -->
#                 </g>

#                 <!-- center -->
#                 <circle cx="60" cy="60" r="6" fill="currentColor" opacity="0.15"/>

#                 <!-- labels OUTSIDE the ring -->
#                 <g font-family="sans-serif" font-size="10" font-weight="800" fill="currentColor">
#                     <text x="60" y="10"  text-anchor="middle">N</text>
#                     <text x="98" y="24"  text-anchor="middle">NE</text>
#                     <text x="114" y="64" text-anchor="middle">E</text>
#                     <text x="98" y="110" text-anchor="middle">SE</text>
#                     <text x="60" y="118" text-anchor="middle">S</text>
#                     <text x="22" y="110" text-anchor="middle">SW</text>
#                     <text x="6"  y="64"  text-anchor="middle">W</text>
#                     <text x="22" y="24"  text-anchor="middle">NW</text>
#                 </g>
#                 </svg>
#             `;
#             return div;
#             }};
#             compass.addTo(map);

#             setBaseLayer(currentBase);
        
#             // Zoom label
#             var zoomLabel = L.control({{position:'bottomleft'}});
#             zoomLabel.onAdd = function() {{
#             var div = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-urd-btn zoom-label-box');
#             div.innerText = "Zoom: " + map.getZoom();
#             map.on('zoomend', function() {{
#                 div.innerText = "Zoom: " + map.getZoom();
#             }});
#             return div;
#             }};
#             zoomLabel.addTo(map);
            
#             function updateCenterHud(){{
#             var c = map.getCenter();
#             document.getElementById('centerHud').innerText =
#                 `${{c.lat.toFixed(6)}}, ${{c.lng.toFixed(6)}}`;
#             }}
#             map.on('move zoom', updateCenterHud);
#             updateCenterHud();

#             function setViewLL(lat, lon, z){{
#             if (z === undefined || z === null) z = map.getZoom();
#             map.setView([lat, lon], z);
#             }}

#             function getView(){{
#             var c = map.getCenter();
#             return {{lat: c.lat, lon: c.lng, zoom: map.getZoom()}};
#             }}

#             function resetMap(){{
#             if (rocketMarker){{ map.removeLayer(rocketMarker); rocketMarker = null; }}
#             if (baseMarker){{ map.removeLayer(baseMarker); baseMarker = null; }}
#             if (baseLine){{ map.removeLayer(baseLine); baseLine = null; }}
#             pathPoly.setLatLngs([]);
#             }}

#             window.getBaseLayer = function(){{ return currentBase; }};

#             window.setBaseLayer = setBaseLayer;
#             window.cycleBaseLayer = cycleBaseLayer;
#             window.getBaseLayer = function(){{ return currentBase; }};

#             window.setViewLL = setViewLL;
#             window.getView = getView;
#             window.resetMap = resetMap;

#             window.addPoint = addPoint;
#             window.setBase = setBase;
#             window.setPosition = setPosition;
#           </script>
#         </body>
#         </html>
#         """
#         html = html.replace("%BASE_KEY%", base_key)

#         if is_offline:
#             # Base URL local para Leaflet local funcionar (assets/leaflet/...)
#             self.setHtml(html, QUrl.fromLocalFile(os.path.join(ASSETS_DIR, "")))
#         else:
#             self.setHtml(html)

#     def cleanup(self):
#         # Para servidor de tiles (se estiver rodando)
#         try:
#             self._stop_tile_server()
#         except Exception:
#             pass

#         # Solta o profile antigo com segurança (evita o warning)
#         try:
#             old_page = self.page()
#             if old_page:
#                 old_page.triggerAction(QWebEnginePage.Stop)

#                 # DETACH: coloca uma page "neutra" com o defaultProfile
#                 self.setPage(QWebEnginePage(QWebEngineProfile.defaultProfile(), self))

#                 # Agora pode deletar a page antiga (que tinha o profile custom)
#                 old_page.deleteLater()
#         except Exception:
#             pass

#     # -------------------------
#     # Python -> JS
#     # -------------------------
#     def add_point(self, lat, lon):
#         self.page().runJavaScript(f"addPoint({lat}, {lon});")

#     def set_base(self, lat, lon, zoom=12):
#         self.page().runJavaScript(f"setBase({lat}, {lon}, {zoom});")

#     def set_position(self, lat, lon, z=12):
#         self.page().runJavaScript(f"setPosition({lat}, {lon}, {z});")

#     def set_view(self, lat: float, lon: float, zoom: int | None = None):
#         if zoom is None:
#             self.page().runJavaScript(f"setViewLL({lat}, {lon});")
#         else:
#             self.page().runJavaScript(f"setViewLL({lat}, {lon}, {zoom});")

#     def get_view(self, callback):
#         js = (
#             "(()=>{"
#             "  try{"
#             "    const el = document.getElementById('centerHud');"
#             "    if (el && el.innerText) {"
#             "      const z = (window.map && window.map.getZoom) ? window.map.getZoom() : 0;"
#             "      return el.innerText + '|' + z;"
#             "    }"
#             "    if (!window.map) return '';"
#             "    const c = window.map.getCenter();"
#             "    const z = window.map.getZoom ? window.map.getZoom() : 0;"
#             "    return c.lat.toFixed(6) + ', ' + c.lng.toFixed(6) + '|' + z;"
#             "  }catch(e){ return ''; }"
#             "})()"
#         )
#         self.page().runJavaScript(js, callback)

#     def reset_map(self):
#         self.page().runJavaScript("resetMap();")


#     # -------------------------
#     # toggles
#     # -------------------------
#     def set_offline(self, offline: bool, tile_folder: str | None = None):
#         self.offline = bool(offline)
#         if tile_folder is not None:
#             self.tile_folder = tile_folder
#         self._init_map()

#     def toggle_map(self):
#         self.page().runJavaScript("cycleBaseLayer();")
#         self.page().runJavaScript("getBaseLayer();")