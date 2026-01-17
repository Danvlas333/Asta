# pc_controller.py - Исправленная версия с правильной инициализацией переменных
from flask import Flask, request, jsonify, Response
import serial
import time
import threading
import cv2
import numpy as np
from datetime import datetime
import os

# ----------- новые сервы для поворота глаз ----------
EYE_PAN_MIN,  EYE_PAN_MAX  = 70, 110   # лево-право
EYE_TILT_MIN, EYE_TILT_MAX = 60, 100  # вверх-вниз
CAM_W, CAM_H = 640, 480               # разрешение камеры (можно подхватить из cv2)
app = Flask(__name__)

# Настройки для Arduino руки - COM порты Windows
HAND_SERIAL_PORT = 'COM3'  # Порт для управления рукой
HAND_BAUD_RATE = 115200
hand_arduino = None

# Настройки для Arduino лица
FACE_SERIAL_PORT = 'COM4'  # Порт для управления лицом
FACE_BAUD_RATE = 9600
face_arduino = None

# Настройки для камеры (внешняя камера через индекс 1)
CAMERA_INDEX = 0  # 1 - внешняя камера, 0 - встроенная камера
camera = None
camera_lock = threading.Lock()
camera_running = False
latest_frame = None

# Ограничения для лица
EYE_MIN = 70
EYE_MAX = 110
EYE_CENTER = 90
MOUTH_MIN = 0
MOUTH_MAX = 80

# Блокировка для потокобезопасности
serial_lock = threading.Lock()


def init_camera():
    """Инициализация камеры"""
    global camera, camera_running
    try:
        # Пробуем разные индексы камер
        for idx in [CAMERA_INDEX, 0, 2, 3]:
            try:
                camera = cv2.VideoCapture(idx)
                # Проверяем, работает ли камера
                if camera.isOpened():
                    # Пытаемся получить кадр
                    for _ in range(5):  # Делаем несколько попыток
                        ret, frame = camera.read()
                        if ret:
                            # Устанавливаем параметры камеры
                            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                            camera.set(cv2.CAP_PROP_FPS, 30)

                            camera_running = True
                            print(f"✅ Камера подключена (индекс {idx})")
                            return True
            except Exception as e:
                print(f"Камера индекс {idx} недоступна: {e}")
                if camera:
                    camera.release()
                continue

        print("❌ Не удалось подключить ни одну камеру")
        return False
    except Exception as e:
        print(f"Ошибка инициализации камеры: {e}")
        return False


def camera_thread_func():
    """Функция потока для получения кадров с камеры"""
    global camera, camera_running, latest_frame

    while camera_running:
        try:
            with camera_lock:
                if camera and camera.isOpened():
                    ret, frame = camera.read()
                    if ret:
                        # Ресайзим для экономии пропускной способности
                        frame = cv2.resize(frame, (320, 240))
                        latest_frame = frame
                    else:
                        print("⚠️ Не удалось получить кадр с камеры")
                        # Пытаемся переподключить камеру
                        time.sleep(1)
                else:
                    time.sleep(0.1)
                    continue
        except Exception as e:
            print(f"Ошибка в потоке камеры: {e}")
            time.sleep(0.1)

        time.sleep(0.033)  # ~30 FPS


def init_hand_arduino():
    """Инициализация Arduino для руки"""
    global hand_arduino
    try:
        # Закрываем соединение если оно уже открыто
        if hand_arduino and hand_arduino.is_open:
            hand_arduino.close()

        print(f"🔄 Подключение к Arduino Hand на {HAND_SERIAL_PORT}...")
        hand_arduino = serial.Serial(
            port=HAND_SERIAL_PORT,
            baudrate=HAND_BAUD_RATE,
            timeout=1,
            write_timeout=1,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE
        )
        time.sleep(2)  # Даем время Arduino на инициализацию

        # Очищаем буфер
        if hand_arduino.is_open:
            hand_arduino.reset_input_buffer()
            hand_arduino.reset_output_buffer()

            # Тестовая команда для проверки связи
            test_command = "0,0,0,0,180,180,0\n"
            with serial_lock:
                hand_arduino.write(test_command.encode('utf-8'))
                hand_arduino.flush()
                time.sleep(0.1)

            # Проверяем ответ от Arduino
            time.sleep(0.5)
            if hand_arduino.in_waiting > 0:
                response = hand_arduino.readline().decode('utf-8', errors='ignore').strip()
                print(f"📨 Ответ от Hand Arduino: {response}")

            print(f"✅ Arduino Hand подключён на {HAND_SERIAL_PORT}")
            return True
        else:
            print(f"❌ Не удалось открыть порт {HAND_SERIAL_PORT}")
            return False

    except serial.SerialException as e:
        print(f"❌ Ошибка подключения к Arduino Hand: {e}")
        hand_arduino = None
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        hand_arduino = None
        return False


def init_face_arduino():
    """Инициализация Arduino для лица"""
    global face_arduino
    try:
        # Закрываем соединение если оно уже открыто
        if face_arduino and face_arduino.is_open:
            face_arduino.close()

        print(f"🔄 Подключение к Arduino Face на {FACE_SERIAL_PORT}...")
        face_arduino = serial.Serial(
            port=FACE_SERIAL_PORT,
            baudrate=FACE_BAUD_RATE,
            timeout=1,
            write_timeout=1,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE
        )
        time.sleep(2)  # Даем время Arduino на инициализацию

        # Очищаем буфер
        if face_arduino.is_open:
            face_arduino.reset_input_buffer()
            face_arduino.reset_output_buffer()

            # Тестовая команда для проверки связи
            test_command = "E90 M0\n"
            with serial_lock:
                face_arduino.write(test_command.encode('utf-8'))
                face_arduino.flush()
                time.sleep(0.1)

            # Проверяем ответ от Arduino
            time.sleep(0.5)
            if face_arduino.in_waiting > 0:
                response = face_arduino.readline().decode('utf-8', errors='ignore').strip()
                print(f"📨 Ответ от Face Arduino: {response}")

            print(f"✅ Arduino Face подключён на {FACE_SERIAL_PORT}")
            return True
        else:
            print(f"❌ Не удалось открыть порт {FACE_SERIAL_PORT}")
            return False

    except serial.SerialException as e:
        print(f"❌ Ошибка подключения к Arduino Face: {e}")
        face_arduino = None
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        face_arduino = None
        return False


def send_to_hand_arduino(data_str):
    """Отправка данных на Arduino руки"""
    # ИСПРАВЛЕНО: Проверяем инициализацию переменной
    global hand_arduino

    if hand_arduino is None or not hand_arduino.is_open:
        # Пытаемся переподключиться
        if not init_hand_arduino():
            return False, "Arduino Hand не подключен"

    try:
        # Убеждаемся, что строка заканчивается новой строкой
        if not data_str.endswith('\n'):
            data_str += '\n'

        with serial_lock:
            cmd_bytes = data_str.encode('utf-8')
            hand_arduino.write(cmd_bytes)
            hand_arduino.flush()
            time.sleep(0.05)

            # Ждем ответа от Arduino
            time.sleep(0.1)
            if hand_arduino.in_waiting > 0:
                response = hand_arduino.readline().decode('utf-8', errors='ignore').strip()
                print(f"📨 Ответ на команду руки: {response}")

        return True, "Команда отправлена"
    except Exception as e:
        print(f"❌ Ошибка отправки на Hand Arduino: {e}")
        # Пытаемся переподключиться
        hand_arduino = None
        return False, f"Ошибка отправки: {e}"


def send_to_face_arduino(data_str):
    """Отправка данных на Arduino лица"""
    # ИСПРАВЛЕНО: Проверяем инициализацию переменной
    global face_arduino

    if face_arduino is None:
        # Переменная не инициализирована
        if not init_face_arduino():
            return False, "Arduino Face не инициализирован"
    elif not face_arduino.is_open:
        # Порт закрыт
        if not init_face_arduino():
            return False, "Arduino Face не подключен"

    try:
        # Убеждаемся, что строка заканчивается новой строкой
        if not data_str.endswith('\n'):
            data_str += '\n'

        with serial_lock:
            cmd_bytes = data_str.encode('utf-8')
            face_arduino.write(cmd_bytes)
            face_arduino.flush()
            time.sleep(0.1)

            # Ждем ответа от Arduino
            time.sleep(0.1)
            if face_arduino.in_waiting > 0:
                response = face_arduino.readline().decode('utf-8', errors='ignore').strip()
                print(f"📨 Ответ на команду лица: {response}")

        return True, "Команда отправлена"
    except Exception as e:
        print(f"❌ Ошибка отправки на Face Arduino: {e}")
        # Пытаемся переподключиться
        face_arduino = None
        return False, f"Ошибка отправки: {e}"


def add_cors_headers(response):
    """Добавляем CORS заголовки вручную"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response


@app.before_request
def before_request():
    """Проверка перед каждым запросом"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)


# Эндпоинты для руки
@app.route('/hand', methods=['POST', 'OPTIONS'])
def set_hand():
    """Управление рукой"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)

    try:
        data = request.json
        if not data:
            response = jsonify({
                "status": "error",
                "message": "Нет данных в запросе"
            })
            return add_cors_headers(response), 400

        # Извлекаем углы с значениями по умолчанию
        wrist = int(data.get('wrist', 0))
        f1 = int(data.get('f1', 0))
        f2 = int(data.get('f2', 0))
        f3 = int(data.get('f3', 0))
        f4 = int(data.get('f4', 180))  # По умолчанию открыт
        f5 = int(data.get('f5', 180))  # По умолчанию открыт
        f6 = int(data.get('f6', 0))

        # Применяем ограничения
        wrist = max(0, min(90, wrist))
        f1 = max(0, min(180, f1))
        f2 = max(0, min(180, f2))
        f3 = max(0, min(180, f3))
        f4 = max(0, min(180, f4))
        f5 = max(0, min(180, f5))
        f6 = max(0, min(180, f6))

        # Формируем команду для Arduino
        command = f"{wrist},{f1},{f2},{f3},{f4},{f5},{f6}"

        # Отправляем команду
        success, message = send_to_hand_arduino(command)

        response = jsonify({
            "status": "success" if success else "error",
            "message": message,
            "angles": {
                "wrist": wrist,
                "f1": f1,
                "f2": f2,
                "f3": f3,
                "f4": f4,
                "f5": f5,
                "f6": f6
            },
            "timestamp": time.time()
        })

        return add_cors_headers(response)

    except Exception as e:
        print(f"❌ Ошибка обработки команды руки: {e}")
        response = jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 400


# Эндпоинты для лица
@app.route('/face', methods=['POST', 'OPTIONS'])
def set_face():
    """Управление лицом"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)

    try:
        data = request.json
        if not data:
            response = jsonify({
                "status": "error",
                "message": "Нет данных в запросе"
            })
            return add_cors_headers(response), 400

        command = ""

        # Обработка глаз
        if 'eyes' in data:
            eyes = int(data['eyes'])
            eyes = max(EYE_MIN, min(eyes, EYE_MAX))
            command += f"E{eyes} "

        # Обработка рта
        if 'mouth' in data:
            mouth = int(data['mouth'])
            mouth = max(MOUTH_MIN, min(mouth, MOUTH_MAX))
            command += f"M{mouth}"

        if command:
            success, message = send_to_face_arduino(command.strip())

            response = jsonify({
                "status": "success" if success else "error",
                "message": message,
                "timestamp": time.time()
            })

            return add_cors_headers(response)
        else:
            response = jsonify({
                "status": "error",
                "message": "Нет корректных команд для лица",
                "timestamp": time.time()
            })
            return add_cors_headers(response), 400

    except Exception as e:
        print(f"❌ Ошибка обработки команды лица: {e}")
        response = jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 400


@app.route('/face_expression', methods=['POST', 'OPTIONS'])
def set_face_expression():
    """Предустановленные выражения лица"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)

    try:
        data = request.json
        if not data:
            response = jsonify({
                "status": "error",
                "message": "Нет данных в запросе"
            })
            return add_cors_headers(response), 400

        expression = data.get('expression', '').lower()

        expressions = {
            "neutral": {"eyes": EYE_CENTER, "mouth": MOUTH_MIN},
            "happy": {"eyes": 85, "mouth": 60},
            "surprise": {"eyes": EYE_MAX, "mouth": 40},
            "sad": {"eyes": EYE_MIN, "mouth": 20},
            "blink": {"eyes": 100, "mouth": MOUTH_MIN},
            "angry": {"eyes": 75, "mouth": 10},
            "talking": {"eyes": EYE_CENTER, "mouth": 60}
        }

        if expression in expressions:
            angles = expressions[expression]
            command = f"E{angles['eyes']} M{angles['mouth']}"

            success, message = send_to_face_arduino(command)

            response = jsonify({
                "status": "success" if success else "error",
                "message": message,
                "expression": expression,
                "timestamp": time.time()
            })

            return add_cors_headers(response)
        else:
            response = jsonify({
                "status": "error",
                "message": f"Неизвестное выражение: {expression}",
                "timestamp": time.time()
            })
            return add_cors_headers(response), 400

    except Exception as e:
        print(f"❌ Ошибка выражения лица: {e}")
        response = jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 400


# Эндпоинты для камеры
@app.route('/camera/start', methods=['POST', 'OPTIONS'])
def start_camera():
    """Запуск камеры"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)

    global camera_running, camera_thread

    try:
        if not camera_running:
            if init_camera():
                camera_running = True
                # Запускаем поток камеры
                camera_thread = threading.Thread(target=camera_thread_func, daemon=True)
                camera_thread.start()

                response = jsonify({
                    "status": "success",
                    "message": "Камера запущена",
                    "timestamp": time.time()
                })
            else:
                response = jsonify({
                    "status": "error",
                    "message": "Не удалось инициализировать камеру",
                    "timestamp": time.time()
                })
                return add_cors_headers(response), 500
        else:
            response = jsonify({
                "status": "success",
                "message": "Камера уже запущена",
                "timestamp": time.time()
            })

        return add_cors_headers(response)

    except Exception as e:
        print(f"❌ Ошибка запуска камеры: {e}")
        response = jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 500


@app.route('/camera/stop', methods=['POST', 'OPTIONS'])
def stop_camera():
    """Остановка камеры"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)

    global camera_running, camera

    try:
        camera_running = False
        time.sleep(0.1)  # Даем время потоку завершиться

        if camera:
            with camera_lock:
                camera.release()
                camera = None

        response = jsonify({
            "status": "success",
            "message": "Камера остановлена",
            "timestamp": time.time()
        })

        return add_cors_headers(response)

    except Exception as e:
        print(f"❌ Ошибка остановки камеры: {e}")
        response = jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 500


@app.route('/camera/stream')
def camera_stream():
    """Потоковое видео с камеры (MJPEG)"""

    def generate():
        global latest_frame

        while camera_running:
            if latest_frame is not None:
                try:
                    # Кодируем кадр в JPEG
                    ret, jpeg = cv2.imencode('.jpg', latest_frame,
                                             [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ret:
                        # Формируем MJPEG кадр
                        frame_bytes = jpeg.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' +
                               frame_bytes + b'\r\n')
                except Exception as e:
                    print(f"❌ Ошибка кодирования кадра: {e}")

            time.sleep(0.033)  # ~30 FPS

    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/camera/snapshot')
def camera_snapshot():
    """Получение одного снимка с камеры"""
    global latest_frame

    if not camera_running or latest_frame is None:
        response = jsonify({
            "status": "error",
            "message": "Камера не запущена или нет кадра",
            "timestamp": time.time()
        })
        return add_cors_headers(response), 503

    try:
        # Кодируем кадр в JPEG
        ret, jpeg = cv2.imencode('.jpg', latest_frame)
        if ret:
            # Возвращаем изображение
            return Response(jpeg.tobytes(),
                            mimetype='image/jpeg')
        else:
            response = jsonify({
                "status": "error",
                "message": "Ошибка кодирования изображения",
                "timestamp": time.time()
            })
            return add_cors_headers(response), 500
    except Exception as e:
        print(f"❌ Ошибка получения снимка: {e}")
        response = jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 500


# Эндпоинт для проверки статуса
@app.route('/status', methods=['GET'])
def get_status():
    """Получение статуса подключения"""
    # Проверяем подключения
    hand_connected = False
    face_connected = False

    try:
        if hand_arduino is not None and hand_arduino.is_open:
            hand_connected = True
        else:
            # Пробуем переподключиться
            hand_connected = init_hand_arduino()
    except:
        hand_connected = False

    try:
        if face_arduino is not None and face_arduino.is_open:
            face_connected = True
        else:
            # Пробуем переподключиться
            face_connected = init_face_arduino()
    except:
        face_connected = False

    status = {
        "hand_connected": hand_connected,
        "face_connected": face_connected,
        "camera_running": camera_running,
        "hand_port": HAND_SERIAL_PORT,
        "face_port": FACE_SERIAL_PORT,
        "camera_index": CAMERA_INDEX,
        "server": "running",
        "timestamp": time.time()
    }

    response = jsonify(status)
    return add_cors_headers(response)


# Эндпоинт для тестирования
@app.route('/test', methods=['GET'])
def test():
    """Тестовый эндпоинт"""
    response = jsonify({
        "status": "ok",
        "message": "Сервер Flask работает на ПК",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time()
    })
    return add_cors_headers(response)


# Эндпоинт для отправки произвольной команды (для отладки)
@app.route('/debug/send', methods=['POST', 'OPTIONS'])
def debug_send():
    """Отправка произвольной команды для отладки"""
    if request.method == 'OPTIONS':
        response = app.make_response('')
        return add_cors_headers(response)

    try:
        data = request.json
        if not data:
            response = jsonify({
                "status": "error",
                "message": "Нет данных в запросе"
            })
            return add_cors_headers(response), 400

        command = data.get('command', '')
        target = data.get('target', 'hand')

        if target == 'hand':
            success, message = send_to_hand_arduino(command)
        else:
            success, message = send_to_face_arduino(command)

        response = jsonify({
            "status": "success" if success else "error",
            "message": message,
            "timestamp": time.time()
        })
        return add_cors_headers(response)
    except Exception as e:
        response = jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        })
        return add_cors_headers(response), 400


@app.after_request
def after_request(response):
    """Добавляем CORS заголовки ко всем ответам"""
    return add_cors_headers(response)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check эндпоинт"""
    response = jsonify({
        "status": "healthy",
        "timestamp": time.time()
    })
    return add_cors_headers(response)

# -------------------------------------------------
#  поиск лица → движение глаз
# -------------------------------------------------
def face_to_servo(x_px, y_px, w_px=640, h_px=480):
    """
    Переводит координаты центра лица (px) в углы сервоприводов.
    Возвращает (eye_pan, eye_tilt) в градусах.
    """
    # нормализуем 0..1
    nx = max(0., min(1., x_px / w_px))
    ny = max(0., min(1., y_px / h_px))

    # линейно интерполируем в диапазон сервы
    pan  = EYE_PAN_MIN  + (1 - nx) * (EYE_PAN_MAX  - EYE_PAN_MIN)  # 1-nx чтобы лево=70
    tilt = EYE_TILT_MIN + ny      * (EYE_TILT_MAX - EYE_TILT_MIN)

    return int(round(pan)), int(round(tilt))


@app.route('/face_look', methods=['POST', 'OPTIONS'])
def face_look():
    """Пусть глаза смотрят на координаты лица"""
    if request.method == 'OPTIONS':
        return add_cors_headers(Response(''))

    data = request.json or {}
    x = int(data.get('x', 320))   # центр кадра по умолчанию
    y = int(data.get('y', 240))

    pan, tilt = face_to_servo(x, y)

    # формируем команду для «лицевого» Arduino
    cmd = f"E{pan} T{tilt}\n"   # E – уже использовалось для глаз, T – tilt
    ok, msg = send_to_face_arduino(cmd)

    return add_cors_headers(jsonify({
        "status": "success" if ok else "error",
        "angles": {"pan": pan, "tilt": tilt},
        "message": msg
    }))

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Запуск сервера для робо-руки и лица на ПК")
    print("=" * 50)
    print(f"📍 Порт руки: {HAND_SERIAL_PORT}")
    print(f"📍 Порт лица: {FACE_SERIAL_PORT}")
    print(f"📷 Камера: индекс {CAMERA_INDEX}")
    print("=" * 50)

    # Инициализация Arduino при запуске
    print("\n🔄 Инициализация Arduino...")
    hand_initialized = init_hand_arduino()
    face_initialized = init_face_arduino()

    if hand_initialized:
        print("✅ Arduino Hand: готов к работе")
    else:
        print("⚠️ Arduino Hand: не подключен")

    if face_initialized:
        print("✅ Arduino Face: готов к работе")
    else:
        print("⚠️ Arduino Face: не подключен")

    print("\n📡 Доступные эндпоинты:")
    print("  POST /hand              - Управление рукой")
    print("  POST /face              - Управление лицом")
    print("  POST /face_expression   - Выражения лица")
    print("  POST /camera/start      - Запуск камеры")
    print("  POST /camera/stop       - Остановка камеры")
    print("  GET  /camera/stream     - Потоковое видео (MJPEG)")
    print("  GET  /camera/snapshot   - Один снимок с камеры")
    print("  GET  /status            - Статус подключения")
    print("  GET  /health            - Health check")
    print("\n🌐 Сервер запущен на http://0.0.0.0:5000")
    print("   Локальный доступ: http://localhost:5000")
    print("   Сетевой доступ: http://ваш-ip:5000")
    print("=" * 50)

    try:
        app.run(
            host='0.0.0.0',
            port=5000,
            threaded=True,
            debug=False,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n🛑 Остановка сервера...")
        camera_running = False
        if camera:
            camera.release()
        if hand_arduino and hand_arduino.is_open:
            hand_arduino.close()
        if face_arduino and face_arduino.is_open:
            face_arduino.close()
        print("✅ Сервер остановлен")
    except Exception as e:
        print(f"\n❌ Ошибка запуска сервера: {e}")