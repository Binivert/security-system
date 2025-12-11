#!/usr/bin/env python3
"""Audio components."""

import threading
from queue import Queue, Empty

from PyQt6.QtCore import QThread

from config import Config

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    import pygame
    pygame.mixer.init()
    PYGAME_AVAILABLE = True
except Exception:
    PYGAME_AVAILABLE = False


class TTSEngine(QThread):
    def __init__(self):
        super().__init__()
        self.running = False
        self.queue = Queue()
        self.engine = None
    
    def run(self):
        self.running = True
        if TTS_AVAILABLE:
            try:
                self.engine = pyttsx3.init()
                self.engine.setProperty('rate', 150)
            except Exception:
                self.engine = None
        
        while self.running:
            try:
                text = self.queue.get(timeout=0.5)
                if self.engine:
                    try:
                        self.engine.say(text)
                        self.engine.runAndWait()
                    except Exception:
                        pass
            except Empty:
                continue
    
    def stop(self):
        self.running = False
    
    def speak(self, text: str):
        try:
            self.queue.put_nowait(text)
        except Exception:
            pass


class ContinuousAlarm:
    def __init__(self, config: Config):
        self.config = config
        self.is_playing = False
        self.is_muted = False
        self._thread = None
        self._stop = threading.Event()
    
    def start(self):
        if self.is_playing or self.is_muted:
            return
        self.is_playing = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        self.is_playing = False
        self._stop.set()
    
    def mute(self):
        self.is_muted = True
        self.stop()
    
    def unmute(self):
        self.is_muted = False
    
    def _loop(self):
        while not self._stop.is_set() and self.is_playing:
            if not self.is_muted:
                self._beep()
            self._stop.wait(0.5)
    
    def _beep(self):
        if PYGAME_AVAILABLE:
            try:
                import numpy as np
                sr = 44100
                dur = 0.15
                freq = self.config.ALARM_FREQUENCY
                t = np.linspace(0, dur, int(sr * dur), False)
                wave = np.sin(2 * np.pi * freq * t) * 0.4
                wave = (wave * 32767).astype(np.int16)
                stereo = np.column_stack((wave, wave))
                sound = pygame.sndarray.make_sound(stereo)
                sound.play()
            except Exception:
                pass
