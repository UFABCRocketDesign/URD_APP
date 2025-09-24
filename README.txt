RocketGS — Skeleton (PySide6)

Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1

pyinstaller --onefile --windowed --name URD_APP --icon=logo.ico --add-data "logo.png;." --add-data "views;views" main.py

Estrutura
---------
RocketGS/
  main.py
  requirements.txt
  build.ps1
  views/
    gs_flight.py
    gs_static_test.py
    post_flight.py
    simulator.py

Como rodar
----------
1) Abra o PowerShell nesta pasta
2) Crie/ative o venv e instale deps:
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt

3) Execute:
   python main.py

Como gerar o .exe
-----------------
pip install pyinstaller
pyinstaller --name RocketGS --noconsole --onedir main.py --collect-all PySide6

O executável ficará em: dist\RocketGS\RocketGS.exe

Adicionando novos módulos
-------------------------
- Crie um arquivo em views/ (ex.: views\config.py com class ConfigPage(QWidget))
- Importe no main.py e adicione no QStackedWidget.
- Crie um novo "tile" na HomePage chamando on_select com uma nova tag.
