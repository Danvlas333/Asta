# app/workers.py - Модуль фоновых задач
from PyQt5.QtCore import QThread, pyqtSignal
from typing import Any, Callable

class NetworkWorker(QThread):
    """Рабочий поток для сетевых операций"""
    
    finished = pyqtSignal(object, bool, str)
    
    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.operation_name = kwargs.pop('operation_name', 'Операция')
        self._is_running = True

    def run(self) -> None:
        """Запуск рабочего потока"""
        try:
            if self._is_running:
                result = self.func(*self.args, **self.kwargs)
                if self._is_running:  # Проверяем еще раз
                    self.finished.emit(result, True, self.operation_name)
        except Exception as e:
            if self._is_running:
                self.finished.emit(str(e), False, self.operation_name)
        finally:
            self._is_running = False
            
    def stop(self):
        """Остановка потока"""
        self._is_running = False
        self.quit()
        self.wait(1000)

class AIWorker(QThread):
    """Рабочий поток для ИИ-операций"""
    
    finished = pyqtSignal(dict, bool)
    
    def __init__(self, llm, user_msg: str):
        super().__init__()
        self.llm = llm
        self.user_msg = user_msg
        self._is_running = True

    def run(self) -> None:
        """Запуск ИИ-обработки"""
        try:
            if self._is_running and self.llm:
                print(f"🤖 Обработка ИИ запроса: '{self.user_msg}'")
                response = self.llm.generate_answer(self.user_msg)
                print(f"🤖 Ответ ИИ: '{response}'")
                if self._is_running:
                    self.finished.emit({"answer": response}, True)
            elif self._is_running:
                self.finished.emit({"error": "ИИ не инициализирован"}, False)
        except Exception as e:
            if self._is_running:
                print(f"❌ Ошибка ИИ: {e}")
                self.finished.emit({"error": str(e)}, False)
        finally:
            self._is_running = False
            
    def stop(self):
        """Остановка потока"""
        self._is_running = False
        self.quit()
        self.wait(1000)

class CameraWorker(QThread):
    """Рабочий поток для операций с камерой"""
    
    frame_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, operation: str, **kwargs):
        super().__init__()
        self.operation = operation
        self.kwargs = kwargs
        self._is_running = False
        
    def run(self) -> None:
        """Запуск операции с камерой"""
        self._is_running = True
        
        try:
            if self.operation == "stream" and self._is_running:
                self._stream_camera()
            elif self.operation == "snapshot" and self._is_running:
                self._take_snapshot()
        except Exception as e:
            if self._is_running:
                self.error_occurred.emit(str(e))
        finally:
            self._is_running = False
            
    def _stream_camera(self) -> None:
        """Потоковое видео с камеры"""
        from app.network import ConnectionManager
        
        stream = ConnectionManager.get_camera_stream()
        if not stream:
            self.error_occurred.emit("Не удалось получить поток камеры")
            return
            
        bytes_buffer = b''
        while self._is_running:
            try:
                chunk = stream.raw.read(1024)
                if not chunk:
                    break
                
                bytes_buffer += chunk
                a = bytes_buffer.find(b'\xff\xd8')  # Начало JPEG
                b = bytes_buffer.find(b'\xff\xd9')  # Конец JPEG
                
                if a != -1 and b != -1:
                    jpg_data = bytes_buffer[a:b+2]
                    bytes_buffer = bytes_buffer[b+2:]
                    
                    if self._is_running:
                        self.frame_ready.emit(jpg_data)
                    
            except Exception as e:
                if self._is_running:
                    self.error_occurred.emit(f"Ошибка чтения кадра: {e}")
                continue
                
        # Закрываем соединение
        try:
            stream.close()
        except:
            pass
            
    def _take_snapshot(self) -> None:
        """Получение снимка с камеры"""
        from app.network import ConnectionManager
        
        response = ConnectionManager.get_camera_snapshot()
        if response and self._is_running:
            self.frame_ready.emit(response.content)
        elif self._is_running:
            self.error_occurred.emit("Не удалось получить снимок")
            
    def stop(self) -> None:
        """Остановка рабочего потока"""
        self._is_running = False
        self.quit()
        self.wait(2000)