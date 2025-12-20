# main.py — запуск проекта Шина
import sys
import os
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.main_window import HandControl
from app.camera_window import CameraViewer

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    print("=" * 50)
    print("🤖 Запуск Шина — робо-рука, лицо, ИИ и камера")
    print("=" * 50)

    main_window = HandControl()
    main_window.show()

    sys.exit(app.exec_())
    
if __name__ == "__main__":
    main()