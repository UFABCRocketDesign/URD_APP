import os, math
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView



class Rocket3DView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._initialized = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web = QWebEngineView()
        layout.addWidget(self.web)

        # conecta para só marcar como pronto quando carregar
        self.web.loadFinished.connect(self._on_load_finished)

        self._init_html()

    def _on_load_finished(self, ok: bool):
        if ok:
            self._initialized = True
            # pode rodar setup adicional se quiser, tipo iniciar a renderização
            self.resume()


    def _init_html(self):
        base_dir = os.path.dirname(__file__)
        js_three = os.path.join(base_dir, "three.min.js")

        with open(js_three, "r", encoding="utf-8") as f:
            three_js = f.read()


        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8"/>
        <title>Rocket3D</title>
        <style>
          html, body {{ margin: 0; height: 100%; background: white; overflow: hidden; }}
          canvas {{ display: block; }}
        </style>
        </head>
        <body>
        <script>
        {three_js}
        </script>

        <script>
        var scene = new THREE.Scene();
        scene.background = new THREE.Color(0xffffff);

        var camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.set(4, 4, 4);
        camera.lookAt(0,0,0);

        var renderer = new THREE.WebGLRenderer({{antialias:true}});
        renderer.setSize(window.innerWidth, window.innerHeight);
        document.body.appendChild(renderer.domElement);

        // Luz
        scene.add(new THREE.AmbientLight(0xffffff, 0.8));
        var light = new THREE.DirectionalLight(0xffffff, 1);
        light.position.set(5,5,5).normalize();
        scene.add(light);

        // Eixos + grid
        scene.add(new THREE.AxesHelper(2));
        scene.add(new THREE.GridHelper(10, 20, 0x000000, 0xaaaaaa));

        // ---- MINI FOGUETE ----
        var rocket = new THREE.Group();

        // Corpo (cilindro) - laranja
        var bodyGeometry = new THREE.CylinderGeometry(0.3, 0.3, 2, 32);
        var bodyMaterial = new THREE.MeshPhongMaterial({{color: 0xff6600}});
        var body = new THREE.Mesh(bodyGeometry, bodyMaterial);
        rocket.add(body);

        // Nariz (cone) - laranja
        var noseGeometry = new THREE.ConeGeometry(0.3, 0.8, 32);
        var noseMaterial = new THREE.MeshPhongMaterial({{color: 0xff6600}});
        var nose = new THREE.Mesh(noseGeometry, noseMaterial);
        nose.position.y = 1.4;
        rocket.add(nose);

        // Aletas (4 caixas) - pretas
        var finGeometry = new THREE.BoxGeometry(0.5, 0.8, 0.1); // mais finas e compridas
        var finMaterial = new THREE.MeshPhongMaterial({{color: 0x000000}});
        for (let i = 0; i < 4; i++) {{
            var fin = new THREE.Mesh(finGeometry, finMaterial);
            fin.position.y = -0.7;  // subiu um pouco
            fin.rotation.y = i * Math.PI / 2;
            fin.position.x = Math.cos(i * Math.PI / 2) * 0.35;
            fin.position.z = Math.sin(i * Math.PI / 2) * 0.35;
            rocket.add(fin);  
        }}

        scene.add(rocket);

        // --- Render loop ---
        var animId;

        function animate() {{
            animId = requestAnimationFrame(animate);
            renderer.render(scene, camera);
        }}

        function pauseRender() {{
            if (animId) cancelAnimationFrame(animId);
            animId = null;
        }}

        function resumeRender() {{
            if (!animId) animate();
        }}


        // API para Python
        //function updateRocket(qw,qx,qy,qz){{
        //    if(!rocket) return;
        //    var q = new THREE.Quaternion(qx,qy,qz,qw);
        //    rocket.setRotationFromQuaternion(q);
        //}}
        //window.updateRocket = updateRocket;

        // API para Python (agora recebe ângulos de Euler em radianos)
        function updateRocket(roll, pitch, yaw) {{
            if (!rocket) return;


            rocket.rotation.set(roll, pitch, yaw, 'ZYX');
        }}

        window.updateRocket = updateRocket;
        // --- CRIA O EIXO VISUAL ---
        const axesHelper = new THREE.AxesHelper(1); // tamanho 5
        scene.add(axesHelper);

        // --- FUNÇÃO PRA CRIAR TEXTO 2D ---
        function makeTextSprite(message, color = "#ffffff", fontSize = 100) {{
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d");
        context.font = `${{fontSize}}px Arial`;
        const textWidth = context.measureText(message).width;
        canvas.width = textWidth;
        canvas.height = fontSize * 1.2;
        context.font = `${{fontSize}}px Arial`;
        context.fillStyle = color;
        context.fillText(message, 0, fontSize);
        
        const texture = new THREE.CanvasTexture(canvas);
        const spriteMaterial = new THREE.SpriteMaterial({{ map: texture }});
        const sprite = new THREE.Sprite(spriteMaterial);
        sprite.scale.set(0.5, 0.25, 1); // ajuste de tamanho
        return sprite;
        }}

        // --- ADICIONA OS RÓTULOS ---
        const labelX = makeTextSprite("X", "#ff0000");
        labelX.position.set(1.5, 0, 0);

        const labelY = makeTextSprite("Y", "#00ff00");
        labelY.position.set(0, 1.5, 0);

        const labelZ = makeTextSprite("Z", "#0000ff");
        labelZ.position.set(0, 0, 1.5);

        scene.add(labelX);
        scene.add(labelY);
        scene.add(labelZ);
        // Resize
        window.addEventListener('resize', function(){{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }});
        </script>
        </body>
        </html>
        """
        self.web.setHtml(html)

    # def set_orientation(self, qw: float, qx: float, qy: float, qz: float):
    #     js = f"if (typeof updateRocket !== 'undefined') updateRocket({qw},{qx},{qy},{qz});"
    #     self.web.page().runJavaScript(js)


    def set_orientation(self, roll: float, pitch: float, yaw: float, degrees: bool = False):
        """
        Atualiza a orientação do foguete no visualizador 3D.
        Agora envia ângulos de Euler (roll, pitch, yaw) em radianos para o JS.
        Se degrees=True, converte de graus para radianos antes de enviar.
        """
        if degrees:
            roll = math.radians(roll)
            pitch = math.radians(pitch)
            yaw = math.radians(yaw)

        js = (
            f"if (typeof updateRocket !== 'undefined') "
            f"updateRocket({roll}, {pitch}, {yaw});"
        )
        self.web.page().runJavaScript(js)

    def pause(self):
        """Pausa a renderização (usado quando troca de página)."""
        if hasattr(self, "web"):
            self.web.page().runJavaScript("if(window.pauseRender) pauseRender();")

    def resume(self):
        """Retoma a renderização (usado quando volta para a página)."""
        if hasattr(self, "web"):
            self.web.page().runJavaScript("if(window.resumeRender) resumeRender();")
    def reset(self):
        """Reinicia a cena 3D"""
        self._init_html()