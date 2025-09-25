# URD_APP

O **URD_APP** é uma aplicação em desenvolvimento voltada para operações de telemetria, testes estáticos e análise de voos.  
Atualmente, encontra-se em sua **versão inicial**, ainda com alguns bugs conhecidos e funcionalidades em evolução.  

O objetivo principal do projeto é integrar diferentes módulos de **Ground Station (GS)** e **análise de dados**, oferecendo uma interface unificada e intuitiva.

---

## 📂 Páginas do Aplicativo

### 🔹 GS Flight (Single)
Interface principal de voo em tempo real.  
- Recebe telemetria completa e exibe **gráficos de altitude, pressão e empuxo**.  
- Mostra a **orientação 3D do foguete** em tempo real.  
- Exibe **mapas online e offline** com as coordenadas do foguete.  
- Inclui terminal de comunicação para monitoramento das mensagens enviadas e recebidas.  
- Todos os dados recebidos são **salvos em arquivos de log**.  

---

### 🔹 GS Flight (Dual) – *Em desenvolvimento*
Versão expandida da GS para monitorar **dois voos em paralelo**.  
- Ainda em fase inicial de implementação.  
- Futuramente permitirá acompanhamento lado a lado de dois canais de telemetria.  

---

### 🔹 GS Static Test
Ground Station para análise em tempo real dos **testes estáticos de motores**.  
- Exibe telemetria de **empuxo e pressão em tempo real**.  
- Inclui **botões de ignição** e de **teste de comunicação**.  
- Todos os dados recebidos são **salvos em arquivos de log**.  

---

### 🔹 Data Analysis
Ferramenta para **análise pós-coleta de dados**.  
- Funciona tanto para análises de **voos** quanto de **testes estáticos**.  
- Permite carregar arquivos de log e gerar gráficos de desempenho.  
- Atualmente faltam diversas funcionalidades, incluindo a **exportação de dados**.  

---

### 🔹 Simulator
Módulo de simulação de telemetria.  
- Permite simular dentro do microcontrolador um voo real do foguete **Arace**.  
- Útil para testar o aplicativo sem hardware conectado.  
- Depende de uma biblioteca ainda não lançada, logo **não está 100% utilizável**.  

---

### 🔹 Map Manager
Gerenciador de mapas offline.  
- Permite **baixar mapas** para utilização na **GS Flight** em cenários sem internet.  

---

## ⚠️ Status Atual
- Esta versão inicial está em **fase de testes**.  
- Algumas funcionalidades podem apresentar erros ou comportamento inesperado.  
- Feedbacks e contribuições são bem-vindos!  

---

## 📌 Próximos Passos
- Finalizar a **GS Dual**.  
- Melhorar estabilidade e desempenho geral.  
- Adicionar funcionalidades ao módulo de **Data Analysis**.  
- Refinar a interface gráfica e navegação.  

---

## 📂 Estrutura do Projeto

Abaixo está a estrutura principal do código-fonte do **URD_APP**:

URD_APP/
├── .venv/ # Ambiente virtual Python
├── build/ # Arquivos de build
├── build.ps1 # Script para build no Windows
├── LICENSE # Licença do projeto
├── logo.ico # Ícone da aplicação
├── logo.png # Logo utilizada na interface
├── main.py # Arquivo principal de inicialização
├── README.md / README.txt
├── requirements.txt # Dependências do projeto
├── URD_APP.spec # Especificações para build (PyInstaller)
└── views/ # Views e layouts da aplicação
         ├── config_dialog.py # Janela de configurações da GS Flight
         ├── data_analysis.py # Página Data Analysis
         ├── gs_flight_single.py # Página GS Flight (Single)
         ├── gs_static_test.py # Página GS Static Test
         ├── logger.py # Gerenciamento de logs
         ├── map_widget.py # Widget de mapas (online/offline)
         ├── maps_manager.py # Gerenciador de mapas
         ├── net_manager.py # Gerenciador de rede
         ├── rocket_3d.py # Renderização 3D do foguete
         ├── simulator.py # Módulo de simulação
         └── three.min.js # Biblioteca JS (Three.js) usada no 3D

---

## ⚙️ Comandos Úteis

### 🔹 Ativar ambiente virtual
- **Windows (PowerShell):**
.\.venv\Scripts\Activate.ps1
Caso de erro, enviar esse comando antes:
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

Para desativar o ambiente virtual:
deactivate

Instala todas as bibliotecas necessárias listadas no requirements.txt:
pip install -r requirements.txt

Executa o aplicativo principal em modo desenvolvimento:
python main.py

Cria um .exe com a biblioteca pyinstaller (Windows):
pyinstaller --onefile --windowed --name URD_APP --icon=logo.ico --add-data "logo.png;." --add-data "views;views" main.py


