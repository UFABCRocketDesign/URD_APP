# URD_APP

O **URD_APP** é uma aplicação em desenvolvimento pelo Departamento de Sistemas Embarcados, voltada para oferecer uma interface integrada que facilite as operações de telemetria de voo, testes estáticos, análise de dados e simulações.
Atualmente, encontra-se em sua **versão inicial**, com diversas funcionalidades em fase de aprimoramento.  

---

## 📂 Páginas do Aplicativo

### 🔹 GS Flight (Single)
Interface principal de voo em tempo real.  
- Recebe telemetria completa e exibe **gráficos de altitude, coordenadas e informações importantes**.  
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
Ground Station para análise em tempo real dos **testes estáticos**.  
- Exibe telemetria de **empuxo e pressão em tempo real**.  
- Inclui **botões de ignição** e de **teste de ping (comunicação)**.  
- Todos os dados recebidos são **salvos em arquivos de log**.  

---

### 🔹 Data Analysis
Ferramenta para **análise de dados**.  
- Funciona tanto para análises de **voos** quanto de **testes estáticos**.  
- Permite carregar arquivos de log e gerar gráficos de desempenho.  
- Atualmente faltam diversas funcionalidades, incluindo a **exportação de dados**.  

---

### 🔹 Simulator
Módulo de simulação de voo.  
- Permite simular dentro do microcontrolador um voo real sem sair do chão, com os dados de voo do **Arace** na IREC 2025.  
- Depende de uma biblioteca ainda não lançada, logo **não está 100% utilizável**.  

---

### 🔹 Map Manager
Gerenciador de mapas online.  
- Permite **baixar mapas** para utilização na **GS Flight**.
- Funciona apenas online e necessita de alguns ajustes ainda.  

---

## ⚠️ Status Atual
- Esta versão inicial está em **fase de testes**.  
- Algumas funcionalidades podem apresentar erros ou comportamento inesperado. 
- Faltam vários ajustes ainda em algumas funcionalidades. 
- Feedbacks e contribuições são bem-vindos!  

---

## 📌 Próximos Passos
- Finalizar a **GS Dual**.  
- Melhorar estabilidade e desempenho geral.  
- Adicionar funcionalidades ao módulo de **Data Analysis**.  
- Refinar o modulo **GS Flight**.  
- Ajustar o modulo **Map Manager**.
- Finalizar o modulo **Simulator**.


---

## 📂 Estrutura do Projeto

Abaixo está a estrutura principal do código-fonte do **URD_APP**:
```bash
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
```
---

## ⚙️ Comandos Úteis

### 🔹 Ativar ambiente virtual
- **Windows (PowerShell):** 
```powershell
.\.venv\Scripts\Activate.ps1
```

> ⚠️ Caso dê erro de execução, rode antes:
> ```powershell
> Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```


### 🔹 Desativar ambiente virtual
- **Windows (PowerShell):**
```powershell
deactivate
```

### 🔹 Instala todas as bibliotecas necessárias listadas no requirements.txt:
- **Windows (PowerShell):**
```powershell
pip install -r requirements.txt
```

### 🔹 Executa o aplicativo principal em modo desenvolvimento:
- **Windows (PowerShell):**
```powershell
python main.py
```

### 🔹 Cria um .exe com a biblioteca pyinstaller (Windows):
- **Windows (PowerShell):**
```powershell
pyinstaller --onefile --windowed --name URD_APP --icon=logo.ico --add-data "logo.png;." --add-data "views;views" main.py
```








