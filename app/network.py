# app/network.py - Модуль работы с сетью
import requests
import urllib3
import socket
from typing import Optional, Dict, Any
from app.config import ENDPOINTS

# Отключаем предупреждения о небезопасных запросах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ConnectionManager:
    """Менеджер подключения к Raspberry Pi"""
    
    @staticmethod
    def check_connection(timeout: float = 2) -> bool:
        """Проверяет доступность сервера"""
        try:
            response = requests.get(
                ENDPOINTS["health"], 
                timeout=timeout, 
                verify=False
            )
            return response.status_code == 200
        except (requests.exceptions.RequestException, socket.timeout):
            return False
    
    @staticmethod
    def get_server_status() -> Optional[Dict[str, Any]]:
        """Получает статус сервера"""
        try:
            response = requests.get(
                ENDPOINTS["status"], 
                timeout=2, 
                verify=False
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Ошибка получения статуса: {e}")
            return None
    
    @staticmethod
    def send_command(endpoint: str, data: Dict[str, Any], timeout: float = 2.0) -> Dict[str, Any]:
        """Отправка команды на сервер"""
        try:
            response = requests.post(
                endpoint,
                json=data,
                timeout=timeout,
                verify=False
            )
            return {
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "data": response.json() if response.status_code == 200 else None,
                "error": None
            }
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "status_code": 408,
                "data": None,
                "error": "Таймаут при отправке команды"
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "status_code": 503,
                "data": None,
                "error": "Ошибка соединения"
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": 500,
                "data": None,
                "error": str(e)
            }
    
    @staticmethod
    def send_hand_command(angles: Dict[str, int]) -> Dict[str, Any]:
        """Отправка команды для руки"""
        return ConnectionManager.send_command(ENDPOINTS["hand"], angles)
    
    @staticmethod
    def send_face_command(angles: Dict[str, int]) -> Dict[str, Any]:
        """Отправка команды для лица"""
        return ConnectionManager.send_command(ENDPOINTS["face"], angles)
    
    @staticmethod
    def send_face_expression(expression: str) -> Dict[str, Any]:
        """Отправка выражения лица"""
        return ConnectionManager.send_command(
            ENDPOINTS["face_expression"],
            {"expression": expression}
        )
    
    @staticmethod
    def start_camera() -> Dict[str, Any]:
        """Запуск камеры"""
        return ConnectionManager.send_command(ENDPOINTS["camera_start"], {})
    
    @staticmethod
    def stop_camera() -> Dict[str, Any]:
        """Остановка камеры"""
        return ConnectionManager.send_command(ENDPOINTS["camera_stop"], {})
    
    @staticmethod
    def get_camera_stream():
        """Получение потока с камеры"""
        try:
            return requests.get(
                ENDPOINTS["camera_stream"],
                stream=True,
                timeout=5,
                verify=False
            )
        except Exception as e:
            print(f"Ошибка получения потока камеры: {e}")
            return None
    
    @staticmethod
    def get_camera_snapshot():
        """Получение снимка с камеры"""
        try:
            response = requests.get(
                ENDPOINTS["camera_snapshot"],
                timeout=5,
                verify=False
            )
            return response if response.status_code == 200 else None
        except Exception as e:
            print(f"Ошибка получения снимка: {e}")
            return None
    
    @staticmethod
    def get_ai_response(user_message: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Получение ответа от ИИ (локального или API)"""
        try:
            # Попробуем использовать локальный ИИ сначала
            try:
                from app.local_nlp import AstaLLM
                llm = AstaLLM()
                response = llm.generate_answer(user_message)
                return {
                    "success": True,
                    "answer": response,
                    "source": "local"
                }
            except ImportError as e:
                print(f"Локальный ИИ не доступен: {e}")
                # Если локального ИИ нет, используем API
                # Раскомментируйте следующий код если нужно использовать OpenAI API
                """
                import openai
                openai.api_key = "YOUR_API_KEY"
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Ты Аста - дружелюбный робот-помощник."},
                        {"role": "user", "content": user_message}
                    ],
                    max_tokens=150,
                    temperature=0.7
                )
                return {
                    "success": True,
                    "answer": response.choices[0].message.content,
                    "source": "openai"
                }
                """
                return {
                    "success": False,
                    "error": "Локальный ИИ не доступен",
                    "source": "none"
                }
                
        except Exception as e:
            print(f"Ошибка получения ответа от ИИ: {e}")
            return {
                "success": False,
                "error": str(e),
                "source": "error"
            }
    
    @staticmethod
    def get_config() -> Dict[str, Any]:
        """Получение конфигурации"""
        from app.config import get_config
        return get_config()