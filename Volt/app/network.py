# app/network.py - Модуль работы с сетью (исправленная версия)
import requests
import urllib3
import socket
import time
from typing import Optional, Dict, Any

# Отключаем предупреждения о небезопасных запросах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ConnectionManager:
    """Менеджер подключения к локальному серверу на ПК"""

    _base_url = None

    @classmethod
    def _get_base_url(cls) -> str:
        """Получение базового URL с динамическим определением IP"""
        if cls._base_url:
            return cls._base_url

        try:
            # Пробуем получить локальный IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 1))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = '127.0.0.1'

        cls._base_url = f"http://{local_ip}:5000"
        return cls._base_url

    @classmethod
    def _get_endpoint(cls, endpoint_name: str) -> str:
        """Получение полного URL для эндпоинта"""
        base_url = cls._get_base_url()
        endpoints = {
            "hand": f"{base_url}/hand",
            "face": f"{base_url}/face",
            "face_expression": f"{base_url}/face_expression",
            "status": f"{base_url}/status",
            "health": f"{base_url}/health",
            "camera_start": f"{base_url}/camera/start",
            "camera_stop": f"{base_url}/camera/stop",
            "camera_stream": f"{base_url}/camera/stream",
            "camera_snapshot": f"{base_url}/camera/snapshot",
            "test": f"{base_url}/test",
        }
        return endpoints.get(endpoint_name, f"{base_url}/{endpoint_name}")

    @staticmethod
    def check_connection(timeout: float = 2) -> bool:
        """Проверяет доступность сервера"""
        try:
            health_url = ConnectionManager._get_endpoint("health")
            print(f"🔍 Проверка соединения с {health_url}")

            response = requests.get(
                health_url,
                timeout=timeout,
                verify=False
            )
            print(f"📡 Ответ сервера: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Ошибка подключения: {type(e).__name__}: {e}")
            return False

    @staticmethod
    def get_server_status() -> Optional[Dict[str, Any]]:
        """Получает статус сервера"""
        try:
            status_url = ConnectionManager._get_endpoint("status")
            print(f"📊 Запрос статуса с {status_url}")

            response = requests.get(
                status_url,
                timeout=3,
                verify=False
            )
            if response.status_code == 200:
                return response.json()
            print(f"❌ Ошибка статуса: {response.status_code}")
            return None
        except Exception as e:
            print(f"❌ Ошибка получения статуса: {e}")
            return None

    @staticmethod
    def send_command(endpoint_name: str, data: Dict[str, Any], timeout: float = 2.0) -> Dict[str, Any]:
        """Отправка команды на сервер"""
        endpoint = ConnectionManager._get_endpoint(endpoint_name)

        print(f"📤 Отправка на {endpoint_name}: {endpoint}")
        print(f"📦 Данные: {data}")

        try:
            response = requests.post(
                endpoint,
                json=data,
                timeout=timeout,
                verify=False,
                headers={'Content-Type': 'application/json'}
            )

            print(f"📥 Ответ от сервера ({response.status_code}): {response.text[:100]}")

            if response.status_code == 200:
                try:
                    json_data = response.json()
                    return {
                        "success": True,
                        "status_code": response.status_code,
                        "data": json_data,
                        "error": None
                    }
                except Exception as json_error:
                    print(f"⚠️ Ошибка парсинга JSON: {json_error}")
                    return {
                        "success": True,
                        "status_code": response.status_code,
                        "data": {"message": response.text},
                        "error": None
                    }
            else:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "data": None,
                    "error": f"HTTP ошибка {response.status_code}: {response.text}"
                }

        except requests.exceptions.Timeout:
            error_msg = "Таймаут при отправке команды"
            print(f"⏰ {error_msg}")
            return {
                "success": False,
                "status_code": 408,
                "data": None,
                "error": error_msg
            }
        except requests.exceptions.ConnectionError:
            error_msg = "Ошибка соединения с сервером"
            print(f"🔌 {error_msg}")
            return {
                "success": False,
                "status_code": 503,
                "data": None,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Неизвестная ошибка: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "status_code": 500,
                "data": None,
                "error": error_msg
            }

    @staticmethod
    def send_hand_command(angles: Dict[str, int]) -> Dict[str, Any]:
        """Отправка команды для руки"""
        print(f"🖐️ Отправка команды для руки: {angles}")
        return ConnectionManager.send_command("hand", angles)

    @staticmethod
    def send_face_command(angles: Dict[str, int]) -> Dict[str, Any]:
        """Отправка команды для лица"""
        print(f"😊 Отправка команды для лица: {angles}")
        return ConnectionManager.send_command("face", angles)

    @staticmethod
    def send_face_expression(expression: str) -> Dict[str, Any]:
        """Отправка выражения лица"""
        print(f"🎭 Отправка выражения лица: {expression}")
        return ConnectionManager.send_command("face_expression", {"expression": expression})

    @staticmethod
    def start_camera() -> Dict[str, Any]:
        """Запуск камеры"""
        print("📷 Запуск камеры")
        return ConnectionManager.send_command("camera_start", {})

    @staticmethod
    def stop_camera() -> Dict[str, Any]:
        """Остановка камеры"""
        print("⏹️ Остановка камеры")
        return ConnectionManager.send_command("camera_stop", {})

    @staticmethod
    def get_camera_stream():
        """Получение потока с камеры"""
        try:
            endpoint = ConnectionManager._get_endpoint("camera_stream")
            print(f"📹 Получение потока камеры: {endpoint}")

            return requests.get(
                endpoint,
                stream=True,
                timeout=5,
                verify=False
            )
        except Exception as e:
            print(f"❌ Ошибка получения потока камеры: {e}")
            return None

    @staticmethod
    def get_camera_snapshot():
        """Получение снимка с камеры"""
        try:
            endpoint = ConnectionManager._get_endpoint("camera_snapshot")
            print(f"📸 Получение снимка: {endpoint}")

            response = requests.get(
                endpoint,
                timeout=5,
                verify=False
            )
            return response if response.status_code == 200 else None
        except Exception as e:
            print(f"❌ Ошибка получения снимка: {e}")
            return None

    @staticmethod
    def test_connection():
        """Тестовый запрос к серверу"""
        try:
            endpoint = ConnectionManager._get_endpoint("test")
            print(f"🧪 Тестовый запрос: {endpoint}")

            response = requests.get(endpoint, timeout=2, verify=False)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"❌ Тестовый запрос не удался: {e}")
            return None

    @staticmethod
    def get_config() -> Dict[str, Any]:
        """Получение конфигурации"""
        try:
            from app.config import LOCAL_IP
            base_url = ConnectionManager._get_base_url()

            return {
                "local_ip": LOCAL_IP,
                "base_url": base_url,
                "raspberry_ip": LOCAL_IP,  # Для обратной совместимости
                "endpoints": {
                    "hand": f"{base_url}/hand",
                    "face": f"{base_url}/face",
                    "face_expression": f"{base_url}/face_expression",
                    "status": f"{base_url}/status",
                    "health": f"{base_url}/health",
                    "camera_start": f"{base_url}/camera/start",
                    "camera_stop": f"{base_url}/camera/stop",
                    "camera_stream": f"{base_url}/camera/stream",
                    "camera_snapshot": f"{base_url}/camera/snapshot",
                }
            }
        except Exception as e:
            print(f"⚠️ Ошибка загрузки конфигурации: {e}")
            base_url = ConnectionManager._get_base_url()
            return {
                "local_ip": "127.0.0.1",
                "base_url": base_url,
                "endpoints": {
                    "hand": f"{base_url}/hand",
                    "face": f"{base_url}/face",
                    "face_expression": f"{base_url}/face_expression",
                    "status": f"{base_url}/status",
                    "health": f"{base_url}/health",
                    "camera_start": f"{base_url}/camera/start",
                    "camera_stop": f"{base_url}/camera/stop",
                    "camera_stream": f"{base_url}/camera/stream",
                    "camera_snapshot": f"{base_url}/camera/snapshot",
                }
            }