# net_manager.py
import socket
from PySide6.QtCore import QObject, Signal

class NetManager(QObject):
    # Sinal emitido sempre que o estado mudar
    netChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hasNet = self._check_connection()
        self.forceOffline = False  # se True, ignora internet real

    def _check_connection(self, host="8.8.8.8", port=53, timeout=2) -> bool:
        """Tenta conexão rápida com DNS Google para checar internet."""
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception:
            return False

    def update(self):
        """
        Atualiza `hasNet`. Se o estado mudar, emite o sinal.
        """
        if self.forceOffline:
            new_status = False
        else:
            new_status = self._check_connection()

        if new_status != self.hasNet:
            self.hasNet = new_status
            self.netChanged.emit(self.hasNet)  # 🔔 emite mudança
            return True
        return False

    def get_status(self) -> bool:
        """
        Obtém o status atual de rede.
        Se estiver em modo offline forçado → sempre False.
        """
        return False if self.forceOffline else self.hasNet

    def set_force_offline(self, enabled: bool):
        """
        Ativa ou desativa o modo offline forçado.
        """
        self.forceOffline = enabled
        if enabled and self.hasNet:
            self.hasNet = False
            self.netChanged.emit(False)  # 🔔 avisa que foi forçado
