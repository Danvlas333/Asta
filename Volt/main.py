import sys
import os
from PyQt5.QtWidgets import QApplication


sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# ИСПРАВЛЕНО: импортируем VoltControl вместо HandControl
from app.main_window import VoltControl

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    print("=" * 50)
    print("⚡ Запуск Вольта — робо-рука, лицо, ИИ Ollama и камера")
    print("=" * 50)

    # Проверяем доступность Ollama
    try:
        import ollama
        print("✅ Ollama доступен")
        # Проверяем модели
        models = ollama.list()
        print(f"📦 Доступные модели: {[m['name'] for m in models['models']]}")
    except ImportError:
        print("❌ Модуль ollama не установлен. Установите: pip install ollama")
    except Exception as e:
        print(f"⚠️ Ошибка проверки Ollama: {e}")

    # ИСПРАВЛЕНО: создаем VoltControl вместо HandControl
    main_window = VoltControl()
    main_window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()