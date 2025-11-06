import cv2
from PyQt5 import QtWidgets, QtGui, QtCore

class VideoWidget(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 480)
        self.cap = cv2.VideoCapture(0)  # ajustar índice / dispositivo correto
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        self.timer.start(30)  # ~33 ms → ~30 fps

    def next_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return
        # converter BGR → RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qt_img = QtGui.QImage(frame.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qt_img)
        self.setPixmap(pix)

    def closeEvent(self, event):
        self.cap.release()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    w = VideoWidget()
    w.show()
    app.exec_()
