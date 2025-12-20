# main.py - Главный файл запуска
import sys
from PyQt5.QtWidgets import QApplication
from app.main_window import HandControl
from app.camera_window import CameraViewer

def main():
    """Главная функция запуска приложения"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    print("=" * 50)
    print("🤖 Запуск приложения Аста - Робо-рука и лицо")
    print("=" * 50)
    
    # Запуск основного окна управления
    main_window = HandControl()
    main_window.show()
    
    # Запуск окна камеры (опционально)
    # camera_window = CameraViewer()
    # camera_window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()