# views/post_flight.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

class PostFlightPage(QWidget):
    """Placeholder for post-flight analysis UI."""
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Pós-Flight Analysis — (placeholder)"))
        lay.addWidget(QLabel("Carregar logs, plotar, filtros, exportar relatório…"))
        lay.addStretch(1)
        lay.addWidget(QPushButton("Abrir arquivo (futuro)"))
