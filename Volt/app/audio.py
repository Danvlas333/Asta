# app/audio.py - Модуль синтеза речи с отслеживанием длительности
import threading
import subprocess
import platform
import time
from PyQt5.QtCore import QThread, pyqtSignal

class VoiceSynth(QThread):
    """Синтезатор речи"""
    
    finished_speaking = pyqtSignal()
    started_speaking = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.current_text = ""
        self.is_speaking = False
        self.system_platform = platform.system()
        self.stop_flag = threading.Event()
        self.process = None
        self.speech_duration = 0
        self.start_time = 0
        
    def speak(self, text: str) -> None:
        """Озвучивание текста"""
        if self.is_speaking:
            self.stop()
            
        self.current_text = text
        self.is_speaking = True
        self.stop_flag.clear()
        self.speech_duration = self._estimate_speech_duration(text)
        self.start()
        
    def _estimate_speech_duration(self, text: str) -> float:
        """Оценка длительности речи"""
        # Примерная скорость речи: 150 слов в минуту = 2.5 слова в секунду
        word_count = len(text.split())
        base_duration = word_count / 2.5
        
        # Минимальная и максимальная длительность
        duration = max(1.0, min(base_duration, 15.0))
        
        # Добавляем запас для безопасности
        return duration * 1.3  # +30% запаса
        
    def run(self) -> None:
        """Запуск синтеза речи в отдельном потоке"""
        try:
            self.start_time = time.time()
            self.started_speaking.emit()
            
            if self.system_platform == "Windows":
                self._speak_windows()
            elif self.system_platform == "Darwin":
                self._speak_macos()
            else:
                self._speak_linux()
                
        except Exception as e:
            self.error_occurred.emit(f"Ошибка синтеза речи: {e}")
        finally:
            self.is_speaking = False
            self.finished_speaking.emit()
            
    def _speak_windows(self) -> None:
        """Синтез речи на Windows"""
        try:
            ps_command = f'''
            Add-Type -AssemblyName System.Speech
            $speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
            $speaker.SelectVoice("Microsoft Irina Desktop")
            $speaker.Rate = 1
            $speaker.Volume = 85
            $speaker.Speak("{self._escape_text(self.current_text)}")
            '''
            self.process = subprocess.Popen(
                ["powershell", "-Command", ps_command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Ожидаем завершения процесса или сигнала остановки
            while self.process.poll() is None and not self.stop_flag.is_set():
                time.sleep(0.1)
                
            if self.stop_flag.is_set() and self.process:
                self.process.terminate()
                self.process.wait(timeout=1)
                
        except Exception as e:
            raise Exception(f"Ошибка Windows TTS: {e}")
        finally:
            self.process = None
            
    def _speak_linux(self) -> None:
        """Синтез речи на Linux"""
        try:
            self.process = subprocess.Popen(
                ["espeak", "-v", "ru", "-s", "150", self.current_text],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            while self.process.poll() is None and not self.stop_flag.is_set():
                time.sleep(0.1)
                
            if self.stop_flag.is_set() and self.process:
                self.process.terminate()
                self.process.wait(timeout=1)
                
        except Exception as e:
            raise Exception(f"Ошибка Linux TTS: {e}")
        finally:
            self.process = None
            
    def _speak_macos(self) -> None:
        """Синтез речи на macOS"""
        try:
            self.process = subprocess.Popen(
                ["say", "-v", "Milena", "-r", "180", self.current_text],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            while self.process.poll() is None and not self.stop_flag.is_set():
                time.sleep(0.1)
                
            if self.stop_flag.is_set() and self.process:
                self.process.terminate()
                self.process.wait(timeout=1)
                
        except Exception as e:
            raise Exception(f"Ошибка macOS TTS: {e}")
        finally:
            self.process = None
            
    def _escape_text(self, text: str) -> str:
        """Экранирование специальных символов в тексте"""
        return text.replace('"', '\\"').replace("'", "\\'")
    
    def stop(self) -> None:
        """Остановка синтеза речи"""
        if self.is_speaking:
            self.stop_flag.set()
            self.is_speaking = False
            
            # Завершаем процесс
            if self.process:
                self.process.terminate()
                self.process.wait(timeout=1)
            
            # Останавливаем поток
            self.quit()
            self.wait(2000)
            
    def is_currently_speaking(self) -> bool:
        """Проверка, говорит ли сейчас синтезатор"""
        return self.is_speaking
        
    def get_elapsed_time(self) -> float:
        """Получение прошедшего времени с начала речи"""
        if self.is_speaking:
            return time.time() - self.start_time
        return 0
        
    def get_estimated_duration(self) -> float:
        """Получение оцененной длительности речи"""
        return self.speech_duration
        
    def get_remaining_time(self) -> float:
        """Получение оставшегося времени речи"""
        if self.is_speaking:
            elapsed = self.get_elapsed_time()
            return max(0, self.speech_duration - elapsed)
        return 0