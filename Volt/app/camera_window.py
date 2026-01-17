import sys, cv2, requests, threading, time
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore    import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui     import QImage, QPixmap
from ultralytics     import YOLO          # pip install ultralytics

CAMERA_ID = 0        # поменяйте, если у вас внешняя
SERVER    = "http://localhost:5000"


class CameraViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📷 Ultralytics + Вольт-глаза")
        self.resize(640, 530)

        self.model   = YOLO("model.pt")   # самая лёгкая, есть `face` если нужно
        self.cap     = cv2.VideoCapture(CAMERA_ID)
        self.timer   = QTimer()
        self.timer.timeout.connect(self.next_frame)

        self.running = False               # флаг «следить»
        self.lock    = threading.Lock()

        self._init_ui()

    # ---------- UI ----------
    def _init_ui(self):
        self.label = QLabel()
        self.label.setFixedSize(640, 480)
        self.label.setStyleSheet("border:2px solid #444;")

        self.btn_start = QPushButton("Начать слежение")
        self.btn_stop  = QPushButton("Завершить")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self.start_follow)
        self.btn_stop.clicked.connect(self.stop_follow)

        h = QHBoxLayout()
        h.addWidget(self.btn_start)
        h.addWidget(self.btn_stop)

        v = QVBoxLayout(self)
        v.addWidget(self.label)
        v.addLayout(h)

    # ---------- кнопки ----------
    @pyqtSlot()
    def start_follow(self):
        self.running = True
        self.timer.start(30)              # ~30 FPS
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    @pyqtSlot()
    def stop_follow(self):
        self.running = False
        self.timer.stop()
        # вернуть глаза в центр
        requests.post(SERVER + "/face_look",
                      json={"x": 320, "y": 240}, timeout=0.2)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    # ---------- кадр ----------
    def next_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return
        h, w = frame.shape[:2]

        # YOLO: classes=0 – только person
        results = self.model(frame, classes=[0], verbose=False)
        boxes   = results[0].boxes.xyxy.cpu().numpy()   # [x1,y1,x2,y2,conf]

        best = None
        if len(boxes):
            # берём самый большой bbox (ближайший)
            areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
            idx   = areas.argmax()
            x1, y1, x2, y2 = map(int, boxes[idx][:4])
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            best   = (cx, cy, x1, y1, x2, y2)

        # рисуем
        if best:
            cx, cy, x1, y1, x2, y2 = best
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)

            # шлём на Вольта в отдельном потоке, чтобы не тормозить GUI
            if self.running:
                threading.Thread(target=self.send_eyes,
                                 args=(cx, cy, w, h), daemon=True).start()

        # показ
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = QImage(rgb.data, w, h, QImage.Format_RGB888)
        self.label.setPixmap(QPixmap.fromImage(img))

    # ---------- отправка ----------
    def send_eyes(self, x, y, w, h):
        try:
            requests.post(SERVER + "/face_look",
                          json={"x": x, "y": y}, timeout=0.15)
        except Exception as e:
            print("Ошибка отправки /face_look:", e)

    # ---------- выход ----------
    def closeEvent(self, event):
        self.stop_follow()
        self.cap.release()
        event.accept()


# ---------- маленький тест ----------
if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication
    app = QApplication([])
    win = CameraViewer()
    win.show()
    app.exec_()