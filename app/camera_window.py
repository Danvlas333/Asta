# app/camera_window.py - Окно камеры с детекцией лиц через OpenCV DNN (без PyTorch)
import cv2
import numpy as np
from datetime import datetime
import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QMessageBox, QCheckBox, 
    QSpinBox, QFormLayout, QGroupBox, QComboBox,
    QProgressBar
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap

from app.config import STYLES
from app.network import ConnectionManager
from app.workers import CameraWorker

class FaceDetectorDNN:
    """Детектор лиц на основе OpenCV DNN с YOLO или SSD моделями"""
    
    def __init__(self, model_type='yolov3_face', conf_threshold=0.5):
        """
        Инициализация детектора
        
        Args:
            model_type: тип модели
            conf_threshold: порог уверенности
        """
        self.conf_threshold = conf_threshold
        self.nms_threshold = 0.4
        self.model_type = model_type
        self.net = None
        self.classes = ['face']
        
        # Размеры входного изображения для разных моделей
        self.model_configs = {
            'yolov3_face': {
                'config': 'models/yolov3-face.cfg',
                'weights': 'models/yolov3-face.weights',
                'input_size': (416, 416),
                'scale': 1/255.0,
                'swap_rb': True
            },
            'tiny_yolo': {
                'config': 'models/yolov3-tiny.cfg',
                'weights': 'models/yolov3-tiny.weights',
                'input_size': (416, 416),
                'scale': 1/255.0,
                'swap_rb': True
            },
            'opencv_face_detector': {
                'config': 'models/opencv_face_detector.pbtxt',
                'weights': 'models/opencv_face_detector_uint8.pb',
                'input_size': (300, 300),
                'scale': 1.0,
                'swap_rb': False,
                'mean': (104.0, 177.0, 123.0)
            },
            'haarcascade': {
                'cascade': 'models/haarcascade_frontalface_default.xml',
                'input_size': None,
                'scale': None,
                'swap_rb': None
            }
        }
        
        # Загрузка модели
        self.load_model(model_type)
        
    def load_model(self, model_type):
        """Загрузка выбранной модели"""
        try:
            if model_type == 'haarcascade':
                # Используем каскады Haar (самый легкий вариант)
                model_path = self.model_configs[model_type]['cascade']
                if os.path.exists(model_path):
                    self.detector = cv2.CascadeClassifier(model_path)
                    self.net = None  # Не используем DNN для каскадов
                    print(f"Загружен Haar cascade: {model_path}")
                else:
                    # Используем встроенный каскад OpenCV
                    self.detector = cv2.CascadeClassifier(
                        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                    )
                    print("Используется встроенный Haar cascade")
            else:
                # Используем DNN модель
                config = self.model_configs[model_type]
                config_path = config['config']
                weights_path = config['weights']
                
                if os.path.exists(config_path) and os.path.exists(weights_path):
                    self.net = cv2.dnn.readNetFromDarknet(config_path, weights_path)
                    print(f"Загружена модель {model_type}: {config_path}")
                else:
                    # Если файлы моделей не найдены, используем каскад
                    print(f"Файлы модели {model_type} не найдены, используется Haar cascade")
                    self.detector = cv2.CascadeClassifier(
                        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                    )
                    self.net = None
                    
        except Exception as e:
            print(f"Ошибка загрузки модели {model_type}: {e}")
            # Используем каскад по умолчанию
            self.detector = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            self.net = None
    
    def detect_faces_dnn(self, frame):
        """Обнаружение лиц с использованием DNN"""
        if self.net is None:
            return frame, []
            
        config = self.model_configs[self.model_type]
        input_size = config['input_size']
        
        # Подготовка изображения для DNN
        blob = cv2.dnn.blobFromImage(
            frame, 
            scalefactor=config['scale'],
            size=input_size,
            mean=config.get('mean', (0, 0, 0)),
            swapRB=config['swap_rb'],
            crop=False
        )
        
        # Прямой проход через сеть
        self.net.setInput(blob)
        outputs = self.net.forward(self.get_output_layers())
        
        # Размеры исходного изображения
        height, width = frame.shape[:2]
        faces = []
        boxes = []
        confidences = []
        
        # Обработка выходных данных
        for output in outputs:
            for detection in output:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]
                
                if confidence > self.conf_threshold and class_id == 0:  # class_id 0 для лица
                    # Координаты ограничивающего прямоугольника
                    center_x = int(detection[0] * width)
                    center_y = int(detection[1] * height)
                    w = int(detection[2] * width)
                    h = int(detection[3] * height)
                    
                    # Координаты левого верхнего угла
                    x = int(center_x - w / 2)
                    y = int(center_y - h / 2)
                    
                    boxes.append([x, y, w, h])
                    confidences.append(float(confidence))
        
        # Применение Non-Maximum Suppression
        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.nms_threshold)
        
        annotated_frame = frame.copy()
        
        if len(indices) > 0:
            for i in indices.flatten():
                x, y, w, h = boxes[i]
                confidence = confidences[i]
                
                # Добавление лица в список
                faces.append({
                    'bbox': (x, y, x + w, y + h),
                    'confidence': confidence,
                    'class': 0
                })
                
                # Отрисовка рамки
                color = (0, 255, 0)
                cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), color, 2)
                
                # Подпись с уверенностью
                label = f"Face: {confidence:.2f}"
                cv2.putText(annotated_frame, label, (x, y - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        return annotated_frame, faces
    
    def detect_faces_haar(self, frame):
        """Обнаружение лиц с использованием каскадов Haar"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Обнаружение лиц
        faces_rect = self.detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        annotated_frame = frame.copy()
        faces = []
        
        for (x, y, w, h) in faces_rect:
            # Добавление лица в список (без confidence для Haar)
            faces.append({
                'bbox': (x, y, x + w, y + h),
                'confidence': 1.0,  # Haar не дает уверенность
                'class': 0
            })
            
            # Отрисовка рамки
            color = (0, 255, 0)
            cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), color, 2)
            
            # Подпись
            label = "Face"
            cv2.putText(annotated_frame, label, (x, y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        return annotated_frame, faces
    
    def get_output_layers(self):
        """Получение выходных слоев сети"""
        layer_names = self.net.getLayerNames()
        try:
            output_layers = [layer_names[i - 1] for i in self.net.getUnconnectedOutLayers()]
        except:
            output_layers = [layer_names[i[0] - 1] for i in self.net.getUnconnectedOutLayers()]
        return output_layers
    
    def detect_faces(self, frame):
        """
        Обнаружение лиц в кадре
        
        Args:
            frame: входное изображение (BGR)
            
        Returns:
            tuple: (frame с отрисованными ограничивающими рамками, список лиц)
        """
        try:
            if self.net is not None:
                return self.detect_faces_dnn(frame)
            else:
                return self.detect_faces_haar(frame)
        except Exception as e:
            print(f"Ошибка детекции: {e}")
            return frame, []
    
    def set_confidence_threshold(self, conf_threshold):
        """Установка порога уверенности"""
        self.conf_threshold = conf_threshold
        
    def set_model(self, model_type):
        """Смена модели"""
        self.model_type = model_type
        self.load_model(model_type)

class FaceDetectionWorker(QThread):
    """Рабочий поток для обработки детекции лиц"""
    
    frame_processed = pyqtSignal(np.ndarray, list)  # Обработанный кадр и список лиц
    detection_info = pyqtSignal(dict)  # Информация о детекции
    
    def __init__(self):
        super().__init__()
        self.detector = None
        self.current_frame = None
        self.running = False
        self.enabled = True
        self.confidence = 0.5
        
    def set_detector(self, detector):
        """Установка детектора"""
        self.detector = detector
        
    def process_frame(self, frame):
        """Обработка кадра"""
        self.current_frame = frame
        
        if not self.running:
            self.start()
            
    def run(self):
        """Основной цикл обработки"""
        self.running = True
        
        while self.running and self.current_frame is not None:
            if self.detector and self.enabled:
                # Обнаружение лиц
                processed_frame, faces = self.detector.detect_faces(self.current_frame)
                
                # Отправка обработанного кадра
                self.frame_processed.emit(processed_frame, faces)
                
                # Отправка статистики
                stats = {
                    'faces_detected': len(faces),
                    'timestamp': datetime.now().strftime("%H:%M:%S"),
                    'model_type': self.detector.model_type
                }
                if faces:
                    confidences = [face['confidence'] for face in faces]
                    stats['avg_confidence'] = np.mean(confidences)
                    stats['max_confidence'] = np.max(confidences)
                    
                self.detection_info.emit(stats)
                
            else:
                # Если детекция отключена, отправляем оригинальный кадр
                self.frame_processed.emit(self.current_frame, [])
                
            # Небольшая задержка для предотвращения перегрузки
            self.msleep(10)
            
    def stop(self):
        """Остановка потока"""
        self.running = False
        self.wait()

class CameraViewer(QWidget):
    """Окно просмотра камеры с детекцией лиц"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📷 Видео с Raspberry Pi - Детекция лиц")
        self.resize(900, 700)
        
        # Инициализация детектора
        self.detector = None
        self.face_detection_worker = None
        self.current_faces = []
        self.detection_stats = {}
        
        self._init_ui()
        self._init_timers()
        self._init_detector()
        
        # Проверка статуса камеры
        QTimer.singleShot(100, self.check_camera_status)
        
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        main_layout = QVBoxLayout()
        
        # Панель управления
        main_layout.addLayout(self._create_control_panel())
        
        # Основной контейнер
        content_layout = QHBoxLayout()
        
        # Левая панель - видео
        left_panel = QVBoxLayout()
        left_panel.addWidget(self._create_video_display())
        left_panel.addLayout(self._create_info_panel())
        content_layout.addLayout(left_panel)
        
        # Правая панель - настройки детекции
        content_layout.addWidget(self._create_detection_panel())
        
        main_layout.addLayout(content_layout)
        
        # Панель статистики
        main_layout.addLayout(self._create_stats_panel())
        
        self.setLayout(main_layout)
        
    def _create_control_panel(self):
        """Создание панели управления"""
        layout = QHBoxLayout()
        
        self.status_label = QLabel("Статус: Не подключено")
        self.status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        self.start_btn = QPushButton("▶️ Запустить камеру")
        self.start_btn.clicked.connect(self.start_camera)
        self.start_btn.setStyleSheet(STYLES["success_button"])
        layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏹️ Остановить")
        self.stop_btn.clicked.connect(self.stop_camera)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(STYLES["danger_button"])
        layout.addWidget(self.stop_btn)
        
        self.snapshot_btn = QPushButton("📸 Снимок")
        self.snapshot_btn.clicked.connect(self.take_snapshot)
        self.snapshot_btn.setEnabled(False)
        self.snapshot_btn.setStyleSheet(STYLES["info_button"])
        layout.addWidget(self.snapshot_btn)
        
        return layout
        
    def _create_video_display(self):
        """Создание окна отображения видео"""
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #000;
                border: 2px solid #6c757d;
                border-radius: 5px;
            }
        """)
        self.video_label.setText("Нет сигнала")
        
        return self.video_label
        
    def _create_detection_panel(self):
        """Создание панели настроек детекции"""
        group_box = QGroupBox("Настройки детекции лиц")
        group_box.setMaximumWidth(250)
        layout = QFormLayout()
        
        # Включение/отключение детекции
        self.detection_enabled = QCheckBox("Включить детекцию лиц")
        self.detection_enabled.setChecked(True)
        self.detection_enabled.stateChanged.connect(self.toggle_detection)
        layout.addRow(self.detection_enabled)
        
        # Выбор модели
        model_layout = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.addItems(["haarcascade", "opencv_face_detector", "tiny_yolo", "yolov3_face"])
        self.model_combo.currentTextChanged.connect(self.change_model)
        model_layout.addWidget(QLabel("Модель:"))
        model_layout.addWidget(self.model_combo)
        layout.addRow(model_layout)
        
        # Порог уверенности
        self.confidence_spin = QSpinBox()
        self.confidence_spin.setRange(1, 99)
        self.confidence_spin.setValue(50)
        self.confidence_spin.setSuffix("%")
        self.confidence_spin.valueChanged.connect(self.update_confidence)
        layout.addRow("Порог уверенности:", self.confidence_spin)
        
        # Информация о модели
        self.model_info_label = QLabel("Модель: Haar Cascade (встроенная)\nСтатус: Готово ✓")
        self.model_info_label.setWordWrap(True)
        layout.addRow(self.model_info_label)
        
        group_box.setLayout(layout)
        return group_box
        
    def _create_info_panel(self):
        """Создание информационной панели"""
        layout = QHBoxLayout()
        
        self.fps_label = QLabel("FPS: --")
        self.resolution_label = QLabel("Разрешение: --")
        self.timestamp_label = QLabel("Время: --")
        
        layout.addWidget(self.fps_label)
        layout.addWidget(self.resolution_label)
        layout.addWidget(self.timestamp_label)
        layout.addStretch()
        
        return layout
        
    def _create_stats_panel(self):
        """Создание панели статистики"""
        layout = QHBoxLayout()
        
        self.faces_count_label = QLabel("Лиц обнаружено: 0")
        self.faces_count_label.setStyleSheet("font-weight: bold; color: #28a745;")
        
        self.avg_confidence_label = QLabel("Средняя уверенность: --")
        self.max_confidence_label = QLabel("Макс. уверенность: --")
        
        self.model_type_label = QLabel("Модель: Haar Cascade")
        
        layout.addWidget(self.faces_count_label)
        layout.addWidget(self.avg_confidence_label)
        layout.addWidget(self.max_confidence_label)
        layout.addWidget(self.model_type_label)
        layout.addStretch()
        
        return layout
        
    def _init_timers(self):
        """Инициализация таймеров"""
        # Таймер для периодической проверки соединения
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_camera_status)
        self.status_timer.start(5000)
        
        # Таймер для расчета FPS
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps)
        self.fps_timer.start(1000)
        
        # Счетчик кадров для FPS
        self.frame_count = 0
        self.fps = 0
        
        # Таймер для обновления статистики
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats_display)
        self.stats_timer.start(100)
        
    def _init_detector(self):
        """Инициализация детектора"""
        try:
            # Создаем папку для моделей если ее нет
            os.makedirs('models', exist_ok=True)
            
            # Инициализация детектора с Haar cascade (самый надежный вариант)
            self.detector = FaceDetectorDNN('haarcascade', 0.5)
            
            # Инициализация рабочего потока
            self.face_detection_worker = FaceDetectionWorker()
            self.face_detection_worker.set_detector(self.detector)
            self.face_detection_worker.frame_processed.connect(self.display_processed_frame)
            self.face_detection_worker.detection_info.connect(self.update_detection_stats)
            
        except Exception as e:
            print(f"Ошибка инициализации детектора: {e}")
            self.model_info_label.setText(f"Ошибка: {str(e)}")
            self.detection_enabled.setEnabled(False)
        
    def toggle_detection(self, state):
        """Включение/отключение детекции"""
        if self.face_detection_worker:
            self.face_detection_worker.enabled = (state == Qt.Checked)
            
    def update_confidence(self, value):
        """Обновление порога уверенности"""
        confidence = value / 100.0
        if self.detector:
            self.detector.set_confidence_threshold(confidence)
        if self.face_detection_worker:
            self.face_detection_worker.confidence = confidence
            
    def change_model(self, model_name):
        """Смена модели"""
        try:
            if self.detector:
                self.detector.set_model(model_name)
                
            self.model_info_label.setText(f"Модель: {model_name}\nСтатус: Загружена ✓")
            self.model_type_label.setText(f"Модель: {model_name}")
            
        except Exception as e:
            self.model_info_label.setText(f"Ошибка загрузки модели: {str(e)}")
            
    def check_camera_status(self):
        """Проверка статуса камеры"""
        status = ConnectionManager.get_server_status()
        if status:
            camera_running = status.get("camera_running", False)
            self._update_camera_status(camera_running)
        else:
            self._update_camera_status(False)
            
    def _update_camera_status(self, is_running: bool):
        """Обновление статуса камеры"""
        if is_running:
            self.status_label.setText("Статус: Камера работает")
            self.status_label.setStyleSheet("font-weight: bold; color: green;")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.snapshot_btn.setEnabled(True)
            self._start_stream()
        else:
            self.status_label.setText("Статус: Камера остановлена")
            self.status_label.setStyleSheet("font-weight: bold; color: orange;")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.snapshot_btn.setEnabled(False)
            self._stop_stream()
            
    def _start_stream(self):
        """Запуск получения видеопотока"""
        if hasattr(self, 'camera_worker') and self.camera_worker.isRunning():
            return
            
        self.camera_worker = CameraWorker("stream")
        self.camera_worker.frame_ready.connect(self.process_frame_for_detection)
        self.camera_worker.error_occurred.connect(self.on_stream_error)
        self.camera_worker.start()
        
    def _stop_stream(self):
        """Остановка получения видеопотока"""
        if hasattr(self, 'camera_worker') and self.camera_worker.isRunning():
            self.camera_worker.stop()
            
        if self.face_detection_worker:
            self.face_detection_worker.stop()
            
        self.video_label.setText("Нет сигнала")
        
    def process_frame_for_detection(self, frame_data):
        """Обработка кадра для детекции"""
        self.frame_count += 1
        self.current_frame_data = frame_data  # Сохраняем для снимков
        
        # Декодирование JPEG
        nparr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is not None:
            # Обновление информации о разрешении
            height, width = frame.shape[:2]
            self.resolution_label.setText(f"Разрешение: {width}x{height}")
            self.timestamp_label.setText(f"Время: {datetime.now().strftime('%H:%M:%S')}")
            
            # Отправка кадра в рабочий поток для детекции
            if self.face_detection_worker and self.detection_enabled.isChecked():
                self.face_detection_worker.process_frame(frame.copy())
            else:
                # Если детекция отключена, отображаем оригинальный кадр
                self.display_original_frame(frame)
                
    def display_processed_frame(self, processed_frame, faces):
        """Отображение обработанного кадра с детекцией"""
        self.current_faces = faces
        
        # Конвертация BGR в RGB
        rgb_image = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
        
        # Создание QImage
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        # Масштабирование изображения
        pixmap = QPixmap.fromImage(qt_image)
        pixmap = pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.video_label.setPixmap(pixmap)
        
    def display_original_frame(self, frame):
        """Отображение оригинального кадра без детекции"""
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        pixmap = pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video_label.setPixmap(pixmap)
        
    def update_fps(self):
        """Обновление FPS"""
        self.fps = self.frame_count
        self.frame_count = 0
        self.fps_label.setText(f"FPS: {self.fps}")
        
    def update_detection_stats(self, stats):
        """Обновление статистики детекции"""
        self.detection_stats = stats
        
    def update_stats_display(self):
        """Обновление отображения статистики"""
        if hasattr(self, 'detection_stats'):
            faces_count = self.detection_stats.get('faces_detected', 0)
            self.faces_count_label.setText(f"Лиц обнаружено: {faces_count}")
            
            if faces_count > 0:
                avg_conf = self.detection_stats.get('avg_confidence', 0)
                max_conf = self.detection_stats.get('max_confidence', 0)
                model_type = self.detection_stats.get('model_type', 'Unknown')
                
                self.avg_confidence_label.setText(f"Средняя уверенность: {avg_conf:.2f}")
                self.max_confidence_label.setText(f"Макс. уверенность: {max_conf:.2f}")
                self.model_type_label.setText(f"Модель: {model_type}")
            else:
                self.avg_confidence_label.setText("Средняя уверенность: --")
                self.max_confidence_label.setText("Макс. уверенность: --")
                
    def on_stream_error(self, error_msg):
        """Обработка ошибки потока"""
        self.status_label.setText(f"Статус: {error_msg}")
        self.status_label.setStyleSheet("font-weight: bold; color: red;")
        self.video_label.setText(f"Ошибка: {error_msg}")
        
    def start_camera(self):
        """Запуск камеры на Raspberry Pi"""
        result = ConnectionManager.start_camera()
        if result["success"]:
            self.status_label.setText("Статус: Запускается...")
            self.start_btn.setEnabled(False)
            
            # Проверка статуса через 2 секунды
            QTimer.singleShot(2000, self.check_camera_status)
        else:
            QMessageBox.warning(
                self, 
                "Ошибка", 
                f"Не удалось запустить камеру: {result.get('error', 'Неизвестная ошибка')}"
            )
            
    def stop_camera(self):
        """Остановка камеры на Raspberry Pi"""
        result = ConnectionManager.stop_camera()
        if result["success"]:
            self.status_label.setText("Статус: Останавливается...")
            self.stop_btn.setEnabled(False)
            
            # Остановка потока
            self._stop_stream()
            
            # Проверка статуса через 2 секунды
            QTimer.singleShot(2000, self.check_camera_status)
        else:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Не удалось остановить камеру: {result.get('error', 'Неизвестная ошибка')}"
            )
            
    def take_snapshot(self):
        """Сохранение снимка"""
        if not hasattr(self, 'current_frame_data'):
            QMessageBox.warning(self, "Ошибка", "Нет текущего кадра для снимка")
            return
            
        try:
            # Декодирование JPEG
            nparr = np.frombuffer(self.current_frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                # Применение детекции если включено
                if self.detector and self.detection_enabled.isChecked():
                    frame, faces = self.detector.detect_faces(frame)
                    faces_count = len(faces)
                else:
                    faces_count = 0
                
                # Сохранение файла
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"snapshot_{timestamp}.jpg"
                cv2.imwrite(filename, frame)
                
                QMessageBox.information(
                    self,
                    "Снимок сохранен",
                    f"Снимок сохранен как: {filename}\nЛиц обнаружено: {faces_count}"
                )
                
        except Exception as e:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Не удалось сохранить снимок: {str(e)}"
            )
            
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        self._stop_stream()
        
        if hasattr(self, 'status_timer'):
            self.status_timer.stop()
        if hasattr(self, 'fps_timer'):
            self.fps_timer.stop()
        if hasattr(self, 'stats_timer'):
            self.stats_timer.stop()
        if self.face_detection_worker:
            self.face_detection_worker.stop()
            
        event.accept()