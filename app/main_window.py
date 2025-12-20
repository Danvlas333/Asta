# app/main_window.py - Главное окно приложения
import time
from typing import Optional, Dict
from PyQt5.QtWidgets import (
    QWidget, QLabel, QSlider, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTextEdit, QGroupBox, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont

from app.config import (
    HAND_GESTURES, FACE_EXPRESSIONS, SERVO_LIMITS, STYLES,
    RASPBERRY_IP
)
from app.network import ConnectionManager
from app.audio import VoiceSynth
from app.animators import MouthAnimator, HandAnimator
from app.workers import NetworkWorker, AIWorker
from app.local_nlp import AstaLLM

class HandControl(QWidget):
    """Главное окно управления робо-рукой и лицом"""
    
    # Сигналы
    log_signal = pyqtSignal(str, str)  # Сигнал для безопасного логирования из потоков
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Аста — робо-рука и лицо с ИИ и голосом")
        self.resize(1000, 1200)
        
        # Инициализация компонентов
        self._init_components()
        self._init_ui()
        
        # Подключение сигналов
        self.log_signal.connect(self._log_handler)
        
        # Список активных рабочих потоков
        self.active_workers = []
        
        # Запуск проверки соединения
        QTimer.singleShot(100, self.check_connection_on_startup)
        
    def _init_components(self):
        """Инициализация компонентов приложения"""
        # Голосовой синтезатор
        self.voice_synth = VoiceSynth()
        self.voice_synth.started_speaking.connect(self.on_speech_started)
        self.voice_synth.finished_speaking.connect(self.on_speech_finished)
        self.voice_synth.error_occurred.connect(self.on_speech_error)
        
        # Аниматор рта (передаем синтезатор для синхронизации)
        self.mouth_animator = MouthAnimator(self.voice_synth)
        self.hand_animator = HandAnimator(log_callback=self.safe_log)
        
        # Локальная нейросеть
        self.has_llm = False
        self.llm = None
        self._init_llm()
        
        # Управление кнопками
        self.button_locks = {}
        
        # Таймер для периодической проверки соединения
        self.connection_timer = None
        
        # Статусы
        self.server_available = False
        self.hand_connected = False
        self.face_connected = False
        
        print("✅ Компоненты инициализированы")

    def _init_llm(self):
        """Инициализация локальной нейросети"""
        try:
            print("🧠 Инициализация локальной нейросети...")
            self.llm = AstaLLM()
            self.has_llm = True
            
            # Проверяем тип загрузки
            if self.llm.is_model_loaded():
                self.safe_log("Система", "✅ Полноценная нейросеть загружена")
                # Тестируем нейросеть
                test_response = self.llm.generate_answer("Привет")
                self.safe_log("Система", f"🤖 Тест нейросети: '{test_response[:50]}...'")
            else:
                self.safe_log("Система", "✅ Резервная система ИИ загружена")
                test_response = self.llm.generate_answer("Привет")
                self.safe_log("Система", f"🤖 Тест резервной системы: '{test_response}'")
                
        except Exception as e:
            print(f"❌ Ошибка инициализации нейросети: {e}")
            self.safe_log("Система", f"❌ Ошибка загрузки ИИ: {e}")
            self.safe_log("Система", "⚠️ ИИ-функции будут недоступны")
            self.has_llm = False

    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        main_layout = QVBoxLayout()
        
        # Заголовок
        main_layout.addLayout(self._create_header())
        
        # Чат
        main_layout.addWidget(self._create_chat())
        
        # Поле ввода
        main_layout.addLayout(self._create_input())
        
        # Жесты руки
        main_layout.addWidget(self._create_hand_gestures())
        
        # Выражения лица
        main_layout.addWidget(self._create_face_expressions())
        
        # Ручное управление рукой
        main_layout.addWidget(self._create_manual_hand_control())
        
        # Ручное управление лицом
        main_layout.addWidget(self._create_manual_face_control())
        
        # Панель информации
        main_layout.addWidget(self._create_info_panel())
        
        self.setLayout(main_layout)
        
        print("✅ Интерфейс создан")

    def _create_header(self):
        """Создание заголовка с информацией о соединении"""
        layout = QHBoxLayout()
        
        # Заголовок
        title_label = QLabel("🤖 Аста - Робо-рука и лицо с ИИ")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title_label)
        
        # Индикатор соединения
        self.connection_status = QLabel("●")
        self.connection_status.setStyleSheet("color: red; font-size: 20px;")
        
        layout.addStretch()
        layout.addWidget(QLabel("Соединение:"))
        layout.addWidget(self.connection_status)
        
        # Кнопка проверки
        check_btn = QPushButton("Проверить")
        check_btn.clicked.connect(self.check_connection)
        check_btn.setStyleSheet(STYLES["info_button"])
        layout.addWidget(check_btn)
        
        return layout
        
    def _create_chat(self):
        """Создание чата"""
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Напишите вопрос для ИИ или используйте кнопки управления...")
        self.chat.setStyleSheet(STYLES["chat_window"])
        
        # Начальное сообщение
        self.chat.append('<span style="color:#888">[Добро пожаловать!]</span> <b style="color:#E53935">Система</b>: Привет! Я Аста - робот-помощник. Задайте мне вопрос или используйте кнопки управления.')
        
        return self.chat
        
    def _create_input(self):
        """Создание поля ввода"""
        layout = QHBoxLayout()
        
        self.input = QLineEdit()
        self.input.setPlaceholderText("Введите вопрос и нажмите Enter...")
        self.input.returnPressed.connect(self.on_user_message)
        self.input.setStyleSheet("""
            padding: 10px;
            border: 2px solid #007bff;
            border-radius: 8px;
            font-size: 12pt;
            background-color: white;
        """)
        
        send_btn = QPushButton("➤ Отправить")
        send_btn.setFixedWidth(120)
        send_btn.clicked.connect(self.on_user_message)
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 15px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #0056b3;
                transform: scale(1.05);
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        # Кнопка теста ИИ
        test_ai_btn = QPushButton("🤖 Тест ИИ")
        test_ai_btn.setFixedWidth(100)
        test_ai_btn.clicked.connect(self.test_ai_functionality)
        test_ai_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7B1FA2;
                transform: scale(1.05);
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        test_ai_btn.setToolTip("Протестировать работу ИИ с случайным вопросом")
        
        layout.addWidget(self.input, 4)  # 80% ширины
        layout.addWidget(send_btn, 1)    # 20% ширины
        layout.addWidget(test_ai_btn, 1) # 20% ширины
        
        return layout
        
    def _create_hand_gestures(self):
        """Создание панели жестов руки"""
        group = QGroupBox("🖐️ Управление жестами руки")
        group.setStyleSheet(STYLES["group_box"])
        layout = QVBoxLayout()
        
        buttons_layout = QHBoxLayout()
        for name in HAND_GESTURES.keys():
            btn = self._create_gesture_button(name)
            buttons_layout.addWidget(btn)
        
        layout.addLayout(buttons_layout)
        group.setLayout(layout)
        return group
        
    def _create_gesture_button(self, gesture_name):
        """Создание кнопки жеста"""
        btn = QPushButton(gesture_name)
        # Создаем уникальное имя для кнопки
        btn_name = f"gesture_{gesture_name}"
        # Убираем эмодзи для создания валидного имени объекта
        for emoji in ['🖐️', '👋', '👌', '👍', '☝️', '✊', '🎭', '😊', '😮', '😢', '😉', '😠', '💬']:
            btn_name = btn_name.replace(emoji, '')
        btn_name = btn_name.strip('_').replace(' ', '_')
        btn.setObjectName(btn_name)
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
                border-color: #007bff;
                transform: scale(1.05);
            }
            QPushButton:disabled {
                background-color: #adb5bd;
                color: #6c757d;
            }
        """)
        return btn
        
    def _create_face_expressions(self):
        """Создание панели выражений лица"""
        group = QGroupBox("🎭 Выражения лица")
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
        """Создание кнопки выражения лица"""
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
                transform: scale(1.05);
            }
            QPushButton:disabled {
                background-color: #adb5bd;
                color: #6c757d;
            }
        """)
        return btn
        
    def _create_manual_hand_control(self):
        """Создание панели ручного управления рукой"""
        group = QGroupBox("🎛️ Ручное управление рукой")
        group.setStyleSheet(STYLES["group_box"])
        layout = QVBoxLayout()
        
        # Плечо
        shoulder_layout = QHBoxLayout()
        shoulder_layout.addWidget(QLabel("Плечо (0-50):"))
        self.shoulder_slider = QSlider(Qt.Horizontal)
        self.shoulder_slider.setRange(0, 50)
        self.shoulder_slider.setValue(0)
        self.shoulder_label = QLabel("0")
        self.shoulder_slider.valueChanged.connect(lambda v: self.shoulder_label.setText(str(v)))
        shoulder_layout.addWidget(self.shoulder_slider)
        shoulder_layout.addWidget(self.shoulder_label)
        layout.addLayout(shoulder_layout)
        
        # Пальцы
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
        
        # Кнопки управления
        layout.addLayout(self._create_hand_control_buttons())
        
        group.setLayout(layout)
        return group
        
    def _create_finger_slider(self, name, key):
        """Создание слайдера для пальца"""
        layout = QHBoxLayout()
        label = QLabel(name)
        label.setFixedWidth(250)
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)
        
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 180)
        
        # Начальные значения
        if key in ["f4", "f5"]:
            slider.setValue(180)  # Инвертированные пальцы открыты при 180
        else:
            slider.setValue(0)    # Обычные пальцы открыты при 0
            
        value_label = QLabel(str(slider.value()))
        value_label.setFixedWidth(40)
        value_label.setStyleSheet("font-weight: bold; color: #007bff;")
        slider.valueChanged.connect(lambda v, lbl=value_label: lbl.setText(str(v)))
        
        layout.addWidget(slider, 3)  # 75% ширины
        layout.addWidget(value_label, 1)  # 25% ширины
        self.finger_sliders[key] = slider
        
        return layout
        
    def _create_hand_control_buttons(self):
        """Создание кнопок управления рукой"""
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
                transform: scale(1.05);
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
                transform: scale(1.05);
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
                transform: scale(1.05);
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        layout.addWidget(apply_hand_btn)
        layout.addWidget(test_hand_btn)
        layout.addWidget(reset_hand_btn)
        
        return layout
        
    def _create_manual_face_control(self):
        """Создание панели ручного управления лицом"""
        group = QGroupBox("😊 Ручное управление лицом")
        group.setStyleSheet(STYLES["group_box"])
        layout = QVBoxLayout()
        
        # Глаза
        layout.addLayout(self._create_eyes_control())
        
        # Рот
        layout.addLayout(self._create_mouth_control())
        
        # Кнопки управления
        layout.addLayout(self._create_face_control_buttons())
        
        group.setLayout(layout)
        return group
        
    def _create_eyes_control(self):
        """Создание управления глазами"""
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
        """Создание управления ртом"""
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
        """Создание кнопок управления лицом"""
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
                transform: scale(1.05);
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
                transform: scale(1.05);
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        layout.addWidget(apply_face_btn)
        layout.addWidget(reset_face_btn)
        
        return layout
        
    def _create_info_panel(self):
        """Создание информационной панели"""
        group = QGroupBox("📊 Информация и статус")
        group.setStyleSheet(STYLES["group_box"])
        layout = QVBoxLayout()
        
        # Статус сервера
        self.status_text = QLabel("Инициализация...")
        self.status_text.setStyleSheet("color: #6c757d; font-style: italic; font-size: 11pt;")
        layout.addWidget(self.status_text)
        
        # Дополнительная информация
        self.info_text = QLabel()
        self.info_text.setStyleSheet("color: #495057; font-size: 10pt;")
        layout.addWidget(self.info_text)
        
        # Статус ИИ
        self.ai_status_text = QLabel()
        self.ai_status_text.setStyleSheet("color: #17a2b8; font-size: 10pt; font-weight: bold;")
        layout.addWidget(self.ai_status_text)
        
        group.setLayout(layout)
        return group
        
    # ============== Обработчики событий ==============
    
    @pyqtSlot(str, str)
    def _log_handler(self, sender: str, msg: str):
        """Обработчик сигнала логирования (выполняется в основном потоке)"""
        prefix = {
            "Ты": '<b style="color:#1E88E5">👤 Ты</b>',
            "Аста": '<b style="color:#43A047">🤖 Аста</b>',
            "Система": '<b style="color:#E53935">⚙️ Система</b>',
        }.get(sender, f'<b>{sender}</b>')
        
        timestamp = time.strftime("%H:%M:%S")
        self.chat.append(f'<span style="color:#888">[{timestamp}]</span> {prefix}: {msg}')
        
        # Прокрутка вниз
        scrollbar = self.chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def safe_log(self, sender: str, msg: str):
        """Безопасное логирование из любого потока"""
        self.log_signal.emit(sender, msg)
        
    def create_gesture_handler(self, gesture_name, button):
        """Создает обработчик для жеста с блокировкой кнопки"""
        def handler():
            if self.button_locks.get(button, False):
                return
                
            self.button_locks[button] = True
            button.setEnabled(False)
            
            # Выполняем жест
            self.execute_hand_animation(gesture_name)
            
            # Разблокируем кнопку через 1 секунду
            QTimer.singleShot(1000, lambda: self.unlock_button(button))
            
        return handler
        
    def create_face_handler(self, expression, button):
        """Создает обработчик для выражения лица с блокировкой кнопки"""
        def handler():
            if self.button_locks.get(button, False):
                return
                
            self.button_locks[button] = True
            button.setEnabled(False)
            
            # Выполняем выражение
            self.execute_face_expression(expression)
            
            # Разблокируем кнопку через 0.5 секунды
            QTimer.singleShot(500, lambda: self.unlock_button(button))
            
        return handler
        
    def unlock_button(self, button):
        """Разблокирует кнопку"""
        self.button_locks[button] = False
        button.setEnabled(True)
        
    def check_connection_on_startup(self):
        """Проверка соединения при запуске"""
        self.safe_log("Система", "🔌 Проверка соединения с Raspberry Pi...")
        
        # Проверяем статус ИИ
        if self.has_llm:
            if self.llm and self.llm.is_model_loaded():
                self.ai_status_text.setText("✅ Используется полноценная нейросеть")
            else:
                self.ai_status_text.setText("✅ Используется резервная система ИИ")
        else:
            self.ai_status_text.setText("❌ ИИ не доступен")
        
        if ConnectionManager.check_connection():
            status = ConnectionManager.get_server_status()
            if status:
                self.hand_connected = status.get("hand_connected", False)
                self.face_connected = status.get("face_connected", False)
                camera_running = status.get("camera_running", False)
                
                hand_status = "✅ подключен" if self.hand_connected else "❌ не подключен"
                face_status = "✅ подключен" if self.face_connected else "❌ не подключен"
                camera_status = "✅ работает" if camera_running else "⏸️ остановлена"
                
                self.safe_log("Система", f"✅ Сервер доступен")
                self.safe_log("Система", f"   Рука: {hand_status}")
                self.safe_log("Система", f"   Лицо: {face_status}")
                self.safe_log("Система", f"   Камера: {camera_status}")
                
                self.status_text.setText(f"✅ Соединение установлено | Рука: {'✓' if self.hand_connected else '✗'} | Лицо: {'✓' if self.face_connected else '✗'}")
                self.connection_status.setStyleSheet("color: green; font-size: 20px;")
                self.info_text.setText(f"IP: {RASPBERRY_IP} | Сервер работает")
                self.server_available = True
            else:
                self.safe_log("Система", "✅ Сервер доступен (статус не получен)")
                self.status_text.setText("✅ Сервер доступен")
                self.connection_status.setStyleSheet("color: green; font-size: 20px;")
                self.info_text.setText(f"IP: {RASPBERRY_IP} | Сервер работает")
                self.server_available = True
        else:
            self.safe_log("Система", "❌ Сервер недоступен. Проверьте:")
            self.safe_log("Система", f"  • IP адрес: {RASPBERRY_IP}")
            self.safe_log("Система", "  • Сетевое соединение")
            self.safe_log("Система", "  • Запущен ли flask_controller.py на Raspberry Pi")
            self.status_text.setText("❌ Сервер недоступен")
            self.connection_status.setStyleSheet("color: red; font-size: 20px;")
            self.info_text.setText(f"IP: {RASPBERRY_IP} | Сервер недоступен")
            self.server_available = False
            
            # Откладываем показ диалога до полной инициализации
            QTimer.singleShot(500, self.show_connection_warning)
        
        # Запускаем периодическую проверку соединения
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.check_connection_periodically)
        self.connection_timer.start(10000)  # 10 секунд
        
        # Приветственное сообщение от Асты
        QTimer.singleShot(1000, self.send_welcome_message)
        
    def send_welcome_message(self):
        """Отправка приветственного сообщения"""
        if self.has_llm:
            welcome_msg = self.llm.generate_answer("Привет, представься")
            self.safe_log("Аста", welcome_msg)
        else:
            self.safe_log("Аста", "Привет! Я Аста - робот-помощник. Задайте мне вопрос или используйте кнопки управления!")
        
    def show_connection_warning(self):
        """Показывает предупреждение о соединении"""
        QMessageBox.warning(
            self,
            "Ошибка соединения",
            f"Не удалось подключиться к Raspberry Pi по адресу {RASPBERRY_IP}:5000\n\n"
            "Проверьте:\n"
            "1. Правильность IP адреса\n"
            "2. Сетевое соединение\n"
            "3. Запущен ли flask_controller.py на Raspberry Pi\n\n"
            "Вы можете продолжать работать с ИИ в автономном режиме."
        )
        
    def check_connection(self):
        """Проверка соединения"""
        if ConnectionManager.check_connection():
            self.connection_status.setStyleSheet("color: green; font-size: 20px;")
            self.status_text.setText("✅ Соединение установлено")
            self.info_text.setText(f"IP: {RASPBERRY_IP} | Сервер работает")
            self.server_available = True
            
            # Обновляем статус соединений
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
            self.info_text.setText(f"IP: {RASPBERRY_IP} | Сервер недоступен")
            self.server_available = False
            self.safe_log("Система", "❌ Нет соединения с сервером")
            
    def check_connection_periodically(self):
        """Периодическая проверка соединения"""
        self.check_connection()
        
    def on_speech_started(self):
        """Обработка начала речи"""
        self.safe_log("Система", "🔊 Озвучиваю ответ...")
        self.status_text.setText("🔊 Воспроизведение речи...")
        
    def on_speech_finished(self):
        """Обработка окончания речи"""
        self.mouth_animator.stop_animation()
        self.status_text.setText("✅ Речь завершена")
        
    def on_speech_error(self, error_msg):
        """Обработка ошибки речи"""
        self.safe_log("Система", f"❌ Ошибка синтеза речи: {error_msg}")
        self.status_text.setText("❌ Ошибка речи")
        
    def on_user_message(self):
        """Обработка сообщения пользователя"""
        user_msg = self.input.text().strip()
        if not user_msg:
            return
            
        self.input.clear()
        self.safe_log("Ты", user_msg)
        
        if not self.has_llm:
            self.safe_log("Система", "⚠️ ИИ-функции недоступны. Модуль local_nlp не загружен.")
            self.safe_log("Аста", "Извините, мои функции ИИ временно недоступны. Попробуйте использовать кнопки управления.")
            self.status_text.setText("⚠️ ИИ не доступен")
            return
        
        # Показываем статус обработки
        self.status_text.setText("🤔 Обработка запроса...")
        
        # Создаем рабочий поток для ИИ
        self.ai_worker = AIWorker(self.llm, user_msg)
        self.ai_worker.finished.connect(self.on_ai_response)
        
        # Добавляем в список активных рабочих
        self.active_workers.append(self.ai_worker)
        
        self.ai_worker.start()
        
    def test_ai_functionality(self):
        """Тестирование функциональности ИИ"""
        test_questions = [
            "Привет! Как дела?",
            "Что ты умеешь?",
            "Расскажи о себе",
            "Кто ты?",
            "Ты робот?",
            "Как работает искусственный интеллект?",
            "Что такое нейросеть?",
            "Расскажи что-нибудь интересное о роботах",
            "Какие у тебя есть функции?",
            "Помоги мне понять технологии"
        ]
        
        import random
        test_question = random.choice(test_questions)
        
        self.input.setText(test_question)
        self.safe_log("Система", f"🔍 Тестирую ИИ с вопросом: '{test_question}'")
        self.on_user_message()
        
    def on_ai_response(self, result, success):
        """Обработка ответа от ИИ"""
        if not success:
            self.safe_log("Система", f"❌ Ошибка обработки ИИ: {result}")
            self.status_text.setText(f"❌ Ошибка: {result}")
            return
            
        if "error" in result:
            self.safe_log("Система", f"❌ Ошибка ИИ: {result['error']}")
            self.status_text.setText("❌ Ошибка ИИ")
        else:
            ai_response = result["answer"]
            self.process_ai_response(ai_response, "local")

    def process_ai_response(self, ai_response: str, source: str):
        """Обработка и озвучивание ответа ИИ"""
        self.safe_log("Аста", ai_response)
        
        # Добавляем информацию об источнике в статус
        source_text = {
            "local": "(локальный ИИ)",
            "openai": "(OpenAI)",
            "local_fallback": "(резервный ИИ)",
            "network": "(сетевой ИИ)",
            "unknown": ""
        }.get(source, f"({source})")
        
        self.status_text.setText(f"🎤 Говорю {source_text}...")
        
        # Запускаем голос и анимацию
        self.voice_synth.speak(ai_response)
        self.mouth_animator.start_speaking_animation(ai_response)

    def execute_hand_animation(self, gesture_name):
        """Выполнение жеста руки"""
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Жест не выполнен.")
            return
            
        if gesture_name in HAND_GESTURES:
            sequences = HAND_GESTURES[gesture_name]
            self.hand_animator.execute_gesture_sequence(gesture_name, sequences)
            
    def execute_face_expression(self, expression: str):
        """Выполнение выражения лица"""
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Выражение не установлено.")
            return
            
        if expression in FACE_EXPRESSIONS:
            name = FACE_EXPRESSIONS[expression]["name"]
            self.safe_log("Система", f"🎭 Устанавливаю выражение лица: {name}")
            self.status_text.setText(f"🎭 Выражение: {name}")
            
            self.net_worker = NetworkWorker(
                ConnectionManager.send_face_expression,
                expression,
                operation_name="Выражение лица"
            )
            self.net_worker.finished.connect(self.on_network_response)
            
            # Добавляем в список активных рабочих
            self.active_workers.append(self.net_worker)
            
            self.net_worker.start()
        
    def test_open_palm(self):
        """Тест открытой ладони"""
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Тест не выполнен.")
            return
            
        # Блокируем кнопку
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
        self.safe_log("Система", "⚡ ТЕСТ: Открытая ладонь - все пальцы открыты")
        self.status_text.setText("⚡ Тест: Открытая ладонь")
        
    def reset_hand(self):
        """Сброс руки в начальное положение"""
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Сброс не выполнен.")
            return
            
        # Блокируем кнопку
        reset_btn = self.findChild(QPushButton, "reset_hand")
        if reset_btn:
            reset_btn.setEnabled(False)
            QTimer.singleShot(1000, lambda: reset_btn.setEnabled(True))
            
        # Начальные значения (открытая ладонь)
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
        self.safe_log("Система", "🔄 Сброс руки в начальное положение")
        self.status_text.setText("🔄 Сброс руки...")
        
    def apply_manual_hand(self):
        """Применяет углы из ручного управления"""
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Команда не отправлена.")
            return
            
        # Блокируем кнопку
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
        self.safe_log("Система", f"⚡ Ручное управление рукой")
        self.status_text.setText("⚡ Отправка на руку...")
        
    def apply_manual_face(self):
        """Применяет углы лица"""
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Команда не отправлена.")
            return
            
        # Блокируем кнопку
        apply_btn = self.findChild(QPushButton, "apply_face")
        if apply_btn:
            apply_btn.setEnabled(False)
            QTimer.singleShot(1000, lambda: apply_btn.setEnabled(True))
            
        angles = {
            "eyes": self.eyes_slider.value(),
            "mouth": self.mouth_slider.value()
        }
        self.send_face_command(angles)
        self.safe_log("Система", f"😊 Ручное управление лицом")
        self.status_text.setText("😊 Отправка на лицо...")
        
    def reset_face(self):
        """Сброс лица в нейтральное положение"""
        if not self.server_available:
            self.safe_log("Система", "⚠️ Сервер недоступен. Сброс не выполнен.")
            return
            
        # Блокируем кнопку
        reset_btn = self.findChild(QPushButton, "reset_face")
        if reset_btn:
            reset_btn.setEnabled(False)
            QTimer.singleShot(1000, lambda: reset_btn.setEnabled(True))
            
        # Устанавливаем нейтральные значения
        self.eyes_slider.setValue(90)
        self.mouth_slider.setValue(0)
        
        angles = {
            "eyes": 90,
            "mouth": 0
        }
        self.send_face_command(angles)
        self.safe_log("Система", "🔄 Сброс лица в нейтральное положение")
        self.status_text.setText("🔄 Сброс лица...")
        
    def send_hand_command(self, angles: dict):
        """Отправка команды для руки"""
        self.net_worker = NetworkWorker(
            ConnectionManager.send_hand_command,
            angles,
            operation_name="Управление рукой"
        )
        self.net_worker.finished.connect(self.on_network_response)
        
        # Добавляем в список активных рабочих
        self.active_workers.append(self.net_worker)
        
        self.net_worker.start()
        
    def send_face_command(self, angles: dict):
        """Отправка команды для лица"""
        self.net_worker = NetworkWorker(
            ConnectionManager.send_face_command,
            angles,
            operation_name="Управление лицом"
        )
        self.net_worker.finished.connect(self.on_network_response)
        
        # Добавляем в список активных рабочих
        self.active_workers.append(self.net_worker)
        
        self.net_worker.start()
        
    def on_network_response(self, result, success, operation_name):
        """Обработка сетевого ответа"""
        if success:
            try:
                if isinstance(result, dict):
                    if result.get("success"):
                        self.safe_log("Система", f"✅ {operation_name}: Успешно")
                        self.status_text.setText(f"✅ {operation_name}: Успешно")
                    else:
                        error_msg = result.get("error", "Неизвестная ошибка")
                        self.safe_log("Система", f"❌ {operation_name}: {error_msg}")
                        self.status_text.setText(f"❌ Ошибка: {error_msg}")
                else:
                    self.safe_log("Система", f"✅ {operation_name}: {result}")
                    self.status_text.setText(f"✅ {operation_name}: Успешно")
            except Exception as e:
                self.safe_log("Система", f"❌ {operation_name}: Ошибка обработки ответа - {e}")
                self.status_text.setText(f"❌ Ошибка обработки")
        else:
            self.safe_log("Система", f"❌ {operation_name}: {result}")
            self.status_text.setText(f"❌ Сетевая ошибка")
            self.check_connection()  # Проверяем соединение при ошибке
            
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        # Останавливаем все потоки
        if hasattr(self, 'voice_synth') and self.voice_synth.is_currently_speaking():
            self.voice_synth.stop()
        
        # Останавливаем аниматоры
        if hasattr(self, 'mouth_animator'):
            self.mouth_animator.stop_animation()
        if hasattr(self, 'hand_animator'):
            self.hand_animator.stop()
        
        # Останавливаем таймеры
        if hasattr(self, 'connection_timer'):
            self.connection_timer.stop()
        
        # Останавливаем все рабочие потоки
        for worker in self.active_workers:
            try:
                if worker.isRunning():
                    if hasattr(worker, 'stop'):
                        worker.stop()
                    else:
                        worker.quit()
                        worker.wait(1000)
            except:
                pass
        
        self.active_workers.clear()
        
        # Прощальное сообщение
        self.safe_log("Система", "👋 Завершение работы...")
        
        event.accept()