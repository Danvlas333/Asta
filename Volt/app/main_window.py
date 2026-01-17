# app/main_window.py – Вольт без автоматического махания
import time
import random
import threading
from typing import Optional, Dict
from PyQt5.QtWidgets import (
    QWidget, QLabel, QSlider, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTextEdit, QGroupBox, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont

from app.config import (
    HAND_GESTURES, FACE_EXPRESSIONS, SERVO_LIMITS, STYLES,
    LOCAL_IP, WELCOME_GESTURE_LOOP, WELCOME_TEXT
)
from app.network import ConnectionManager
from app.audio import VoiceSynth
from app.animators import MouthAnimator, HandAnimator
from app.workers import NetworkWorker, AIWorker

try:
    from app.ollama_nlp import VoltOllama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

# ---------- новое окно камеры ----------
from app.camera_window import CameraViewer


class VoltControl(QWidget):
    log_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚡ Вольт – робо-рука и лицо (без авто-махания)")
        self.resize(1000, 1200)
        self._init_components()
        self._init_ui()
        self.log_signal.connect(self._log_handler)
        self.active_workers = []
        self.is_waving = False
        QTimer.singleShot(100, self.check_connection_on_startup)

    # ---------- компоненты ----------
    def _init_components(self):
        self.voice_synth = VoiceSynth()
        self.voice_synth.started_speaking.connect(self.on_speech_started)
        self.voice_synth.finished_speaking.connect(self.on_speech_finished)
        self.voice_synth.error_occurred.connect(self.on_speech_error)

        self.mouth_animator = MouthAnimator(self.voice_synth)
        self.hand_animator = HandAnimator(log_callback=self.safe_log)

        self.has_llm = False
        self.llm = None
        self._init_llm()

        self.button_locks = {}
        self.connection_timer = None
        self.server_available = False
        self.hand_connected = False
        self.face_connected = False

        # окно камеры
        self.cam_window: Optional[CameraViewer] = None
        print("✅ Компоненты Вольта инициализированы")

    # ---------- LLM ----------
    def _init_llm(self):
        try:
            if OLLAMA_AVAILABLE:
                self.llm = VoltOllama("phi3:mini")
                self.has_llm = True
                if self.llm.is_model_loaded():
                    model_info = self.llm.get_model_info()
                    self.safe_log("Система", f"✅ Вольт: Ollama загружена ({model_info['name']})")
                else:
                    self.safe_log("Система", "⚡ Вольт: резервная система ИИ")
            else:
                self.safe_log("Система", "❌ Ollama не доступен")
                self.has_llm = False
        except Exception as e:
            print(f"❌ Ошибка загрузки ИИ Вольта: {e}")
            self.safe_log("Система", "🔧 Используется резервная система")
            self.has_llm = False

    # ---------- UI ----------
    def _init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.addLayout(self._create_header())
        main_layout.addWidget(self._create_chat())
        main_layout.addLayout(self._create_input())
        main_layout.addWidget(self._create_hand_gestures())
        main_layout.addWidget(self._create_face_expressions())
        main_layout.addWidget(self._create_manual_hand_control())
        main_layout.addWidget(self._create_manual_face_control())
        main_layout.addWidget(self._create_info_panel())
        self.setLayout(main_layout)
        print("✅ Интерфейс Вольта создан")

    # ---------- header ----------
    def _create_header(self):
        layout = QHBoxLayout()
        title = QLabel("⚡ Вольт – робо-рука и лицо")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #FF6B00;")
        layout.addWidget(title)

        self.connection_status = QLabel("●")
        self.connection_status.setStyleSheet("color: red; font-size: 20px;")
        layout.addStretch()
        layout.addWidget(QLabel("Соединение:"))
        layout.addWidget(self.connection_status)

        check_btn = QPushButton("Проверить")
        check_btn.clicked.connect(self.check_connection)
        check_btn.setStyleSheet(STYLES["info_button"])
        layout.addWidget(check_btn)

        # кнопка камеры
        cam_btn = QPushButton("📷 Камера")
        cam_btn.clicked.connect(self.open_camera_window)
        cam_btn.setStyleSheet(STYLES["primary_button"])
        layout.addWidget(cam_btn)

        return layout

    # ---------- chat ----------
    def _create_chat(self):
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Напишите вопрос для Вольта...")
        self.chat.setStyleSheet(STYLES["chat_window"])
        self.chat.append(
            '<span style="color:#888">[Добро пожаловать!]</span> <b style="color:#FF6B00">⚡ Система</b>: Привет! Я Вольт – энергичный робот-помощник.')
        return self.chat

    # ---------- input ----------
    def _create_input(self):
        layout = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Введите вопрос для Вольта и нажмите Enter...")
        self.input.returnPressed.connect(self.on_user_message)
        self.input.setStyleSheet("""
            padding: 10px;
            border: 2px solid #FF6B00;
            border-radius: 8px;
            font-size: 12pt;
            background-color: white;
        """)
        send_btn = QPushButton("⚡ Отправить")
        send_btn.clicked.connect(self.on_user_message)
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF6B00;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 15px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #E55A00;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        layout.addWidget(self.input, 4)
        layout.addWidget(send_btn, 1)
        return layout

    # ---------- жесты ----------
    def _create_hand_gestures(self):
        group = QGroupBox("🖐️ Управление жестами руки")
        group.setStyleSheet(STYLES["group_box"])
        layout = QVBoxLayout()
        buttons_layout = QHBoxLayout()
        for name in HAND_GESTURES.keys():
            btn = self._create_gesture_button(name)
            buttons_layout.addWidget(btn)

        # приветствие – только вручную
        welcome_btn = QPushButton("🎤 Приветствие")
        welcome_btn.clicked.connect(self.execute_welcome_sequence)
        welcome_btn.setStyleSheet(STYLES["primary_button"])
        buttons_layout.addWidget(welcome_btn)

        layout.addLayout(buttons_layout)
        group.setLayout(layout)
        return group

    def _create_gesture_button(self, gesture_name):
        btn = QPushButton(gesture_name)
        btn.setObjectName(f"gesture_{gesture_name}".replace("🖐️", "").replace("👋", "").replace("👌", "").replace("👍", "").replace("☝️", "").replace("✊", "").replace("🎤", "").strip())
        self.button_locks[btn] = False
        btn.clicked.connect(self.create_gesture_handler(gesture_name, btn))
        btn.setStyleSheet("""
            QPushButton {
                padding: 12px;
                margin: 3px;
                border: 2px solid #6c757d;
                border-radius: 8px;
                background-color: #e9ecef;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #d4d6d8;
                border-color: #FF6B00;
            }
            QPushButton:disabled {
                background-color: #adb5bd;
                color: #6c757d;
            }
        """)
        return btn

    # ---------- выражения ----------
    def _create_face_expressions(self):
        group = QGroupBox("🎭 Выражения лица Вольта")
        group.setStyleSheet(STYLES["group_box"])
        layout = QVBoxLayout()
        buttons_layout = QHBoxLayout()
        for expression_key, expression_data in FACE_EXPRESSIONS.items():
            btn = self._create_face_button(expression_key, expression_data["name"])
            buttons_layout.addWidget(btn)
        layout.addLayout(buttons_layout)
        group.setLayout(layout)
        return group

    def _create_face_button(self, expression, display_name):
        btn = QPushButton(display_name)
        btn.setObjectName(f"face_{expression}")
        self.button_locks[btn] = False
        btn.clicked.connect(self.create_face_handler(expression, btn))
        btn.setStyleSheet("""
            QPushButton {
                padding: 12px;
                margin: 3px;
                border: 2px solid #6c757d;
                border-radius: 8px;
                background-color: #e9ecef;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #d4d6d8;
                border-color: #28a745;
            }
            QPushButton:disabled {
                background-color: #adb5bd;
                color: #6c757d;
            }
        """)
        return btn

    # ---------- ручное управление ----------
    def _create_manual_hand_control(self):
        group = QGroupBox("🎛️ Ручное управление рукой Вольта")
        group.setStyleSheet(STYLES["group_box"])
        layout = QVBoxLayout()

        shoulder_layout = QHBoxLayout()
        shoulder_layout.addWidget(QLabel("Плечо (0-90):"))
        self.shoulder_slider = QSlider(Qt.Horizontal)
        self.shoulder_slider.setRange(0, 90)
        self.shoulder_slider.setValue(0)
        self.shoulder_label = QLabel("0")
        self.shoulder_slider.valueChanged.connect(lambda v: self.shoulder_label.setText(str(v)))
        shoulder_layout.addWidget(self.shoulder_slider)
        shoulder_layout.addWidget(self.shoulder_label)
        layout.addLayout(shoulder_layout)

        self.finger_sliders = {}
        fingers = [
            ("Безымянный (f1) 0=откр, 180=сжат", "f1"),
            ("Мизинец (f2) 0=откр, 180=сжат", "f2"),
            ("Кисть (f3) 0=откр, 180=сжат", "f3"),
            ("Указательный (f4) 0=сжат, 180=откр", "f4"),
            ("Средний (f5) 0=сжат, 180=откр", "f5"),
            ("Большой (f6) 0=откр, 180=сжат", "f6")
        ]
        for name, key in fingers:
            layout.addLayout(self._create_finger_slider(name, key))

        layout.addLayout(self._create_hand_control_buttons())
        group.setLayout(layout)
        return group

    def _create_finger_slider(self, name, key):
        layout = QHBoxLayout()
        label = QLabel(name)
        label.setFixedWidth(250)
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 180)
        if key in ["f4", "f5"]:
            slider.setValue(180)
        else:
            slider.setValue(0)
        value_label = QLabel(str(slider.value()))
        value_label.setFixedWidth(40)
        value_label.setStyleSheet("font-weight: bold; color: #FF6B00;")
        slider.valueChanged.connect(lambda v, lbl=value_label: lbl.setText(str(v)))
        layout.addWidget(slider, 3)
        layout.addWidget(value_label, 1)
        self.finger_sliders[key] = slider
        return layout

    def _create_hand_control_buttons(self):
        layout = QHBoxLayout()
        apply_hand_btn = QPushButton("Применить к руке")
        apply_hand_btn.setObjectName("apply_hand")
        self.button_locks[apply_hand_btn] = False
        apply_hand_btn.clicked.connect(self.apply_manual_hand)
        apply_hand_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        test_hand_btn = QPushButton("Тест: Открытая ладонь")
        test_hand_btn.setObjectName("test_hand")
        self.button_locks[test_hand_btn] = False
        test_hand_btn.clicked.connect(self.test_open_palm)
        test_hand_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #138496;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        reset_hand_btn = QPushButton("Сбросить руку")
        reset_hand_btn.setObjectName("reset_hand")
        self.button_locks[reset_hand_btn] = False
        reset_hand_btn.clicked.connect(self.reset_hand)
        reset_hand_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: black;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #e0a800;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        layout.addWidget(apply_hand_btn)
        layout.addWidget(test_hand_btn)
        layout.addWidget(reset_hand_btn)
        return layout

    # ---------- лицо ----------
    def _create_manual_face_control(self):
        group = QGroupBox("😊 Ручное управление лицом Вольта")
        group.setStyleSheet(STYLES["group_box"])
        layout = QVBoxLayout()
        layout.addLayout(self._create_eyes_control())
        layout.addLayout(self._create_mouth_control())
        layout.addLayout(self._create_face_control_buttons())
        group.setLayout(layout)
        return group

    def _create_eyes_control(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel("👀 Глаза (70-110):"))
        self.eyes_slider = QSlider(Qt.Horizontal)
        self.eyes_slider.setRange(70, 110)
        self.eyes_slider.setValue(90)
        self.eyes_label = QLabel("90")
        self.eyes_label.setFixedWidth(40)
        self.eyes_label.setStyleSheet("font-weight: bold; color: #28a745;")
        self.eyes_slider.valueChanged.connect(lambda v: self.eyes_label.setText(str(v)))
        layout.addWidget(self.eyes_slider)
        layout.addWidget(self.eyes_label)
        return layout

    def _create_mouth_control(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel("👄 Рот (0-80):"))
        self.mouth_slider = QSlider(Qt.Horizontal)
        self.mouth_slider.setRange(0, 80)
        self.mouth_slider.setValue(0)
        self.mouth_label = QLabel("0")
        self.mouth_label.setFixedWidth(40)
        self.mouth_label.setStyleSheet("font-weight: bold; color: #dc3545;")
        self.mouth_slider.valueChanged.connect(lambda v: self.mouth_label.setText(str(v)))
        layout.addWidget(self.mouth_slider)
        layout.addWidget(self.mouth_label)
        return layout

    def _create_face_control_buttons(self):
        layout = QHBoxLayout()
        apply_face_btn = QPushButton("Применить к лицу")
        apply_face_btn.setObjectName("apply_face")
        self.button_locks[apply_face_btn] = False
        apply_face_btn.clicked.connect(self.apply_manual_face)
        apply_face_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        reset_face_btn = QPushButton("Сбросить лицо")
        reset_face_btn.setObjectName("reset_face")
        self.button_locks[reset_face_btn] = False
        reset_face_btn.clicked.connect(self.reset_face)
        reset_face_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: black;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #e0a800;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        layout.addWidget(apply_face_btn)
        layout.addWidget(reset_face_btn)
        return layout

    # ---------- инфо ----------
    def _create_info_panel(self):
        group = QGroupBox("📊 Информация и статус Вольта")
        group.setStyleSheet(STYLES["group_box"])
        layout = QVBoxLayout()
        self.status_text = QLabel("Инициализация Вольта...")
        self.status_text.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11pt;")
        layout.addWidget(self.status_text)
        self.info_text = QLabel()
        self.info_text.setStyleSheet("color: #495057; font-size: 10pt;")
        layout.addWidget(self.info_text)
        self.ai_status_text = QLabel()
        self.ai_status_text.setStyleSheet("color: #FF6B00; font-size: 10pt; font-weight: bold;")
        layout.addWidget(self.ai_status_text)
        group.setLayout(layout)
        return group

    # ---------- СЛОТЫ ----------
    @pyqtSlot(str, str)
    def _log_handler(self, sender: str, msg: str):
        prefix = {
            "Ты": '<b style="color:#1E88E5">👤 Ты</b>',
            "Вольт": '<b style="color:#FF6B00">⚡ Вольт</b>',
            "Система": '<b style="color:#E53935">⚙️ Система</b>',
        }.get(sender, f'<b>{sender}</b>')
        timestamp = time.strftime("%H:%M:%S")
        self.chat.append(f'<span style="color:#888">[{timestamp}]</span> {prefix}: {msg}')
        scrollbar = self.chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def safe_log(self, sender: str, msg: str):
        self.log_signal.emit(sender, msg)

    def create_gesture_handler(self, gesture_name, button):
        def handler():
            if self.button_locks.get(button, False):
                return
            self.button_locks[button] = True
            button.setEnabled(False)
            self.execute_hand_animation(gesture_name)
            QTimer.singleShot(1000, lambda: self.unlock_button(button))
        return handler

    def create_face_handler(self, expression, button):
        def handler():
            if self.button_locks.get(button, False):
                return
            self.button_locks[button] = True
            button.setEnabled(False)
            self.execute_face_expression(expression)
            QTimer.singleShot(500, lambda: self.unlock_button(button))
        return handler

    def unlock_button(self, button):
        self.button_locks[button] = False
        button.setEnabled(True)

    # ---------- КАМЕРА ----------
    @pyqtSlot()
    def open_camera_window(self):
        if self.cam_window is None:
            self.cam_window = CameraViewer()
            self.cam_window.closed.connect(self.on_cam_closed)
        self.cam_window.show()
        self.cam_window.raise_()
        self.cam_window.activateWindow()

    @pyqtSlot()
    def on_cam_closed(self):
        self.cam_window = None

    # ---------- ПРИВЕТСТВИЕ – ТОЛЬКО ВРУЧНУЮ ----------
    def execute_welcome_sequence(self):
        """Махание + речь только по кнопке"""
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Приветствие не выполнено.")
            return

        # улыбка
        self.execute_face_expression("happy")

        # подъём
        self.hand_animator.execute_gesture_sequence(
            "🎤 Приветствие-подъём", [["90,0,0,180,180,180,0"]]
        )

        # цикличное махание + речь
        self.is_waving = True
        threading.Thread(target=self.wave_loop, daemon=True).start()

        self.voice_synth.speak(WELCOME_TEXT)
        self.mouth_animator.start_speaking_animation(WELCOME_TEXT)

        self.voice_synth.finished_speaking.connect(self.stop_wave)

        self.safe_log("Вольт", "🎤 Вольт приветствует аудиторию!")
        self.status_text.setText("🎤 Приветствие выполняется...")

    def wave_loop(self):
        while self.is_waving:
            self.hand_animator.execute_gesture_sequence(
                "🎤 Приветствие-цикл", WELCOME_GESTURE_LOOP
            )
            time.sleep(0.1)

    def stop_wave(self):
        self.is_waving = False
        self.hand_animator.execute_gesture_sequence(
            "🎤 Приветствие-финал", [["0,0,0,180,180,180,0"]]
        )
        self.voice_synth.finished_speaking.disconnect(self.stop_wave)

    # ---------- СТАРТ ----------
    def check_connection_on_startup(self):
        self.safe_log("Система", "🔌 Проверка соединения...")
        if self.has_llm and self.llm:
            model_info = self.llm.get_model_info() if hasattr(self.llm, 'get_model_info') else {}
            if model_info.get('loaded', False):
                self.ai_status_text.setText(f"⚡ Используется Ollama: {model_info['name']}")
            else:
                self.ai_status_text.setText("⚡ Резервная система Вольта")
        else:
            self.ai_status_text.setText("❌ ИИ Вольта не доступен")

        if ConnectionManager.check_connection():
            status = ConnectionManager.get_server_status()
            if status:
                self.hand_connected = status.get("hand_connected", False)
                self.face_connected = status.get("face_connected", False)
                hand_status = "✅ подключен" if self.hand_connected else "❌ не подключен"
                face_status = "✅ подключен" if self.face_connected else "❌ не подключен"
                self.safe_log("Система", f"✅ Сервер доступен | Рука: {hand_status} | Лицо: {face_status}")
                self.status_text.setText(f"✅ Соединение установлено")
                self.connection_status.setStyleSheet("color: green; font-size: 20px;")
                self.info_text.setText(f"IP: {LOCAL_IP} | Сервер работает")
                self.server_available = True
            else:
                self.safe_log("Система", "✅ Сервер доступен (статус не получен)")
                self.server_available = True
        else:
            self.safe_log("Система", "❌ Сервер недоступен")
            self.server_available = False
            QTimer.singleShot(500, self.show_connection_warning)

        # таймер периодической проверки
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.check_connection_periodically)
        self.connection_timer.start(10000)

        # ❗❗❗ убрали автоматическое махание ❗❗❗
        # QTimer.singleShot(1000, self.send_welcome_message)  <-- УДАЛЕНО
        QTimer.singleShot(1500, self.send_hello_once)

    def send_hello_once(self):
        """Только текст, без махания"""
        if self.has_llm:
            welcome = self.llm.generate_answer("Привет, представься как Вольт - энергичный робот-помощник")
            self.safe_log("Вольт", welcome)
        else:
            self.safe_log("Вольт", "Привет! Я Вольт - энергичный робот-помощник. Задайте вопрос или нажмите кнопки управления.")

    # ---------- остальные методы ----------
    def show_connection_warning(self):
        QMessageBox.warning(
            self,
            "Ошибка соединения Вольта",
            f"Не удалось подключиться к серверу по адресу {LOCAL_IP}:5000\n\n"
            "Проверьте:\n"
            "1. Правильность IP\n"
            "2. Сетевое соединение\n"
            "3. Запущен ли pc_controller.py на ПК\n\n"
            "Можно продолжать в автономном режиме."
        )

    def check_connection(self):
        if ConnectionManager.check_connection():
            self.connection_status.setStyleSheet("color: green; font-size: 20px;")
            self.status_text.setText("✅ Соединение установлено")
            self.info_text.setText(f"IP: {LOCAL_IP} | Сервер работает")
            self.server_available = True
            status = ConnectionManager.get_server_status()
            if status:
                self.hand_connected = status.get("hand_connected", False)
                self.face_connected = status.get("face_connected", False)
                hand_status = "✅ подключен" if self.hand_connected else "❌ не подключен"
                face_status = "✅ подключен" if self.face_connected else "❌ не подключен"
                self.safe_log("Система", f"✅ Соединение восстановлено | Рука: {hand_status} | Лицо: {face_status}")
            else:
                self.safe_log("Система", "✅ Соединение с сервером восстановлено")
        else:
            self.connection_status.setStyleSheet("color: red; font-size: 20px;")
            self.status_text.setText("❌ Соединение потеряно")
            self.info_text.setText(f"IP: {LOCAL_IP} | Сервер недоступен")
            self.server_available = False
            self.safe_log("Система", "❌ Нет соединения с сервером")

    def check_connection_periodically(self):
        self.check_connection()

    # ---------- речь ----------
    def on_speech_started(self):
        self.safe_log("Система", "🔊 Вольт озвучивает ответ...")
        self.status_text.setText("🔊 Воспроизведение речи Вольта...")

    def on_speech_finished(self):
        self.mouth_animator.stop_animation()
        self.status_text.setText("✅ Речь Вольта завершена")

    def on_speech_error(self, error_msg):
        self.safe_log("Система", f"❌ Ошибка синтеза речи Вольта: {error_msg}")
        self.status_text.setText("❌ Ошибка речи Вольта")

    # ---------- ИИ ----------
    def on_user_message(self):
        user_msg = self.input.text().strip()
        if not user_msg:
            return
        self.input.clear()
        self.safe_log("Ты", user_msg)
        if not self.has_llm:
            self.safe_log("Система", "⚠️ ИИ-функции Вольта недоступны.")
            self.safe_log("Вольт", "Извините, мои функции ИИ временно недоступны.")
            self.status_text.setText("⚠️ ИИ Вольта не доступен")
            return
        self.status_text.setText("🤔 Вольт обрабатывает запрос...")
        self.ai_worker = AIWorker(self.llm, user_msg)
        self.ai_worker.finished.connect(self.on_ai_response)
        self.active_workers.append(self.ai_worker)
        self.ai_worker.start()

    def on_ai_response(self, result, success):
        if not success:
            self.safe_log("Система", f"❌ Ошибка обработки ИИ Вольта: {result}")
            self.status_text.setText(f"❌ Ошибка: {result}")
            return
        if "error" in result:
            self.safe_log("Система", f"❌ Ошибка ИИ Вольта: {result['error']}")
            self.status_text.setText("❌ Ошибка ИИ Вольта")
        else:
            ai_response = result["answer"]
            self.process_ai_response(ai_response, "local")

    def process_ai_response(self, ai_response: str, source: str):
        self.safe_log("Вольт", ai_response)
        source_text = {"local": "(локальный ИИ)", "ollama": "(Ollama)", "fallback": "(резервный ИИ)"}.get(source, f"({source})")
        self.status_text.setText(f"🎤 Вольт говорит {source_text}...")
        self.voice_synth.speak(ai_response)
        self.mouth_animator.start_speaking_animation(ai_response)

    # ---------- жесты / выражения ----------
    def execute_hand_animation(self, gesture_name):
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Жест не выполнен.")
            return
        if gesture_name in HAND_GESTURES:
            sequences = HAND_GESTURES[gesture_name]
            self.hand_animator.execute_gesture_sequence(gesture_name, sequences)

    def execute_face_expression(self, expression: str):
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Выражение не установлено.")
            return
        if expression in FACE_EXPRESSIONS:
            name = FACE_EXPRESSIONS[expression]["name"]
            self.safe_log("Система", f"🎭 Вольт устанавливает выражение: {name}")
            self.status_text.setText(f"🎭 Выражение Вольта: {name}")
            self.net_worker = NetworkWorker(
                ConnectionManager.send_face_expression,
                expression,
                operation_name="Выражение лица Вольта"
            )
            self.net_worker.finished.connect(self.on_network_response)
            self.active_workers.append(self.net_worker)
            self.net_worker.start()

    # ---------- ручные команды ----------
    def test_open_palm(self):
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Тест не выполнен.")
            return
        test_btn = self.findChild(QPushButton, "test_hand")
        if test_btn:
            test_btn.setEnabled(False)
            QTimer.singleShot(1000, lambda: test_btn.setEnabled(True))
        angles = {
            "wrist": 30,
            "f1": 0,
            "f2": 0,
            "f3": 0,
            "f4": 180,
            "f5": 180,
            "f6": 0,
        }
        self.send_hand_command(angles)
        self.safe_log("Система", "⚡ ТЕСТ Вольта: Открытая ладонь")
        self.status_text.setText("⚡ Тест Вольта: Открытая ладонь")

    def reset_hand(self):
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Сброс не выполнен.")
            return
        reset_btn = self.findChild(QPushButton, "reset_hand")
        if reset_btn:
            reset_btn.setEnabled(False)
            QTimer.singleShot(1000, lambda: reset_btn.setEnabled(True))
        self.shoulder_slider.setValue(0)
        for key, slider in self.finger_sliders.items():
            if key in ["f4", "f5"]:
                slider.setValue(180)
            else:
                slider.setValue(0)
        angles = {
            "wrist": 0,
            "f1": 0,
            "f2": 0,
            "f3": 0,
            "f4": 180,
            "f5": 180,
            "f6": 0,
        }
        self.send_hand_command(angles)
        self.safe_log("Система", "🔄 Вольт сбрасывает руку в начальное положение")
        self.status_text.setText("🔄 Сброс руки Вольта...")

    def apply_manual_hand(self):
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Команда не отправлена.")
            return
        apply_btn = self.findChild(QPushButton, "apply_hand")
        if apply_btn:
            apply_btn.setEnabled(False)
            QTimer.singleShot(1000, lambda: apply_btn.setEnabled(True))
        angles = {
            "wrist": self.shoulder_slider.value(),
            "f1": self.finger_sliders["f1"].value(),
            "f2": self.finger_sliders["f2"].value(),
            "f3": self.finger_sliders["f3"].value(),
            "f4": self.finger_sliders["f4"].value(),
            "f5": self.finger_sliders["f5"].value(),
            "f6": self.finger_sliders["f6"].value(),
        }
        self.send_hand_command(angles)
        self.safe_log("Система", f"⚡ Ручное управление рукой Вольта")
        self.status_text.setText("⚡ Отправка на руку Вольта...")

    def apply_manual_face(self):
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Команда не отправлена.")
            return
        apply_btn = self.findChild(QPushButton, "apply_face")
        if apply_btn:
            apply_btn.setEnabled(False)
            QTimer.singleShot(1000, lambda: apply_btn.setEnabled(True))
        angles = {
            "eyes": self.eyes_slider.value(),
            "mouth": self.mouth_slider.value()
        }
        self.send_face_command(angles)
        self.safe_log("Система", f"😊 Ручное управление лицом Вольта")
        self.status_text.setText("😊 Отправка на лицо Вольта...")

    def reset_face(self):
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Сброс не выполнен.")
            return
        reset_btn = self.findChild(QPushButton, "reset_face")
        if reset_btn:
            reset_btn.setEnabled(False)
            QTimer.singleShot(1000, lambda: reset_btn.setEnabled(True))
        self.eyes_slider.setValue(90)
        self.mouth_slider.setValue(0)
        angles = {
            "eyes": 90,
            "mouth": 0
        }
        self.send_face_command(angles)
        self.safe_log("Система", "🔄 Вольт сбрасывает лицо в нейтральное положение")
        self.status_text.setText("🔄 Сброс лица Вольта...")

    # ---------- сетевые вызовы ----------
    def send_hand_command(self, angles: dict):
        self.net_worker = NetworkWorker(
            ConnectionManager.send_hand_command,
            angles,
            operation_name="Управление рукой Вольта"
        )
        self.net_worker.finished.connect(self.on_network_response)
        self.active_workers.append(self.net_worker)
        self.net_worker.start()

    def send_face_command(self, angles: dict):
        self.net_worker = NetworkWorker(
            ConnectionManager.send_face_command,
            angles,
            operation_name="Управление лицом Вольта"
        )
        self.net_worker.finished.connect(self.on_network_response)
        self.active_workers.append(self.net_worker)
        self.net_worker.start()

    def on_network_response(self, result, success, operation_name):
        print(f"📨 Ответ для Вольта: success={success}, result={result}")
        if success:
            if isinstance(result, dict) and result.get("success"):
                self.safe_log("Система", f"✅ {operation_name}: Успешно")
                self.status_text.setText(f"✅ {operation_name}: Успешно")
            else:
                error_msg = result.get("error", "Неизвестная ошибка")
                self.safe_log("Система", f"❌ {operation_name}: {error_msg}")
                self.status_text.setText(f"❌ Ошибка: {error_msg}")
        else:
            error_msg = result if isinstance(result, str) else "Сетевая ошибка"
            self.safe_log("Система", f"❌ {operation_name}: {error_msg}")
            self.status_text.setText("❌ Сетевая ошибка Вольта")
            self.check_connection()

    # ---------- закрытие ----------
    def closeEvent(self, event):
        if hasattr(self, 'voice_synth') and self.voice_synth.is_currently_speaking():
            self.voice_synth.stop()
        if hasattr(self, 'mouth_animator'):
            self.mouth_animator.stop_animation()
        if hasattr(self, 'hand_animator'):
            self.hand_animator.stop()
        if hasattr(self, 'connection_timer'):
            self.connection_timer.stop()
        if self.cam_window:
            self.cam_window.close()
        for worker in self.active_workers:
            try:
                if worker.isRunning():
                    worker.quit()
                    worker.wait(1000)
            except:
                pass
        self.active_workers.clear()
        self.safe_log("Система", "👋 Вольт завершает работу...")
        event.accept()