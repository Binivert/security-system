#!/usr/bin/env python3
"""Audio module - Simple WAV file alarm.

Put your alarm.wav file in the 'audio/' folder.
The alarm will play on loop when triggered and stop INSTANTLY when stopped.
"""

import threading
import time
import sys
import os
from pathlib import Path
from typing import Optional
from queue import Queue, Empty

from PyQt6.QtCore import QThread

from config import Config

# Check for pygame (for better audio looping)
PYGAME_AVAILABLE = False
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    pass

# Check for pyttsx3
TTS_AVAILABLE = False
try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    pass

# Check for winsound (Windows only)
WINSOUND_AVAILABLE = False
if sys.platform == 'win32':
    try:
        import winsound
        WINSOUND_AVAILABLE = True
    except ImportError:
        pass


class TTSEngine(QThread):
    """Text-to-speech engine with queue."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        super().__init__()
        self._initialized = True
        self._running = False
        self._queue: Queue = Queue()
        self._engine = None
        self._engine_lock = threading.Lock()

    def run(self):
        self._running = True

        if TTS_AVAILABLE:
            try:
                self._engine = pyttsx3.init()
                self._engine.setProperty('rate', 150)
                self._engine.setProperty('volume', 0.9)
            except Exception as e:
                print(f"[TTS] Init error: {e}")
                self._engine = None

        while self._running:
            try:
                text = self._queue.get(timeout=0.5)
                if text is None:
                    break
                self._speak_internal(text)
            except Empty:
                continue
            except Exception as e:
                print(f"[TTS] Error: {e}")

    def _speak_internal(self, text: str):
        if not self._engine:
            return

        with self._engine_lock:
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as e:
                print(f"[TTS] Speak error: {e}")

    def speak(self, text: str):
        if not text:
            return

        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except:
                break

        self._queue.put(text)

    def stop(self):
        self._running = False
        self._queue.put(None)


class WavAlarm:
    """Simple WAV file alarm.
    
    Put your alarm.wav file in the 'audio/' folder.
    
    - Plays alarm.wav on LOOP when start() is called
    - Stops INSTANTLY when stop() is called
    - No delays, no blocking
    
    Usage:
        alarm = WavAlarm()
        alarm.start()  # Starts playing immediately
        alarm.stop()   # Stops INSTANTLY
    """

    def __init__(self, config: Config = None):
        self.config = config
        self._is_playing = False
        self._is_muted = False
        
        # Find alarm.wav file
        self.audio_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "audio"
        self.alarm_file = self.audio_dir / "alarm.wav"
        
        # Create audio directory if it doesn't exist
        self.audio_dir.mkdir(exist_ok=True)
        
        # Pygame for better looping
        self.pygame_sound = None
        if PYGAME_AVAILABLE:
            pygame.mixer.init()
            if self.alarm_file.exists():
                try:
                    self.pygame_sound = pygame.mixer.Sound(str(self.alarm_file))
                except:
                    self.pygame_sound = None
        
        # Check if alarm file exists
        if self.alarm_file.exists():
            print(f"[Alarm] Found alarm file: {self.alarm_file}")
        else:
            print(f"[Alarm] WARNING: No alarm.wav found at {self.alarm_file}")
            print(f"[Alarm] Please put an alarm.wav file in the 'audio/' folder")
    
    @property
    def is_playing(self) -> bool:
        return self._is_playing
    
    @property
    def is_muted(self) -> bool:
        return self._is_muted
    
    def start(self):
        """Start playing the alarm WAV file on loop."""
        if self._is_playing:
            return  # Already playing
        
        if self._is_muted:
            self._is_playing = True
            print("[Alarm] Started (muted)")
            return
        
        if not self.alarm_file.exists():
            print(f"[Alarm] Cannot start - no alarm.wav file found")
            self._is_playing = True  # Mark as playing for UI
            return
        
        self._is_playing = True
        
        if self.pygame_sound and not self._is_muted:
            try:
                self.pygame_sound.play(loops=-1)  # Loop indefinitely
                print("[Alarm] STARTED - Playing alarm.wav on seamless loop with pygame")
                return
            except Exception as e:
                print(f"[Alarm] Pygame error: {e}")
        
        if WINSOUND_AVAILABLE:
            try:
                # Play WAV file on loop, asynchronously (non-blocking)
                # SND_ASYNC = play in background
                # SND_LOOP = loop continuously
                # SND_FILENAME = play from file
                winsound.PlaySound(
                    str(self.alarm_file),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP
                )
                print("[Alarm] STARTED - Playing alarm.wav on loop")
            except Exception as e:
                print(f"[Alarm] Error starting: {e}")
        else:
            print("[Alarm] Started (no audio available)")
    
    def stop(self):
        """Stop the alarm INSTANTLY."""
        if not self._is_playing:
            return  # Already stopped
        
        self._is_playing = False
        
        if self.pygame_sound:
            try:
                self.pygame_sound.stop()
                print("[Alarm] STOPPED (pygame)")
                return
            except Exception as e:
                print(f"[Alarm] Pygame stop error: {e}")
        
        if WINSOUND_AVAILABLE:
            try:
                # Stop ALL sounds immediately
                # SND_PURGE stops any playing sound
                winsound.PlaySound(None, winsound.SND_PURGE)
                print("[Alarm] STOPPED")
            except Exception as e:
                print(f"[Alarm] Error stopping: {e}")
        else:
            print("[Alarm] Stopped")
    
    def mute(self):
        """Mute the alarm."""
        self._is_muted = True
        if self._is_playing:
            if self.pygame_sound:
                try:
                    pygame.mixer.pause()
                    print("[Alarm] Muted (pygame)")
                    return
                except:
                    pass
            # Stop the sound but keep is_playing True
            if WINSOUND_AVAILABLE:
                try:
                    winsound.PlaySound(None, winsound.SND_PURGE)
                except:
                    pass
        print("[Alarm] Muted")
    
    def unmute(self):
        """Unmute the alarm."""
        self._is_muted = False
        if self._is_playing:
            if self.pygame_sound:
                try:
                    pygame.mixer.unpause()
                    print("[Alarm] Unmuted (pygame)")
                    return
                except:
                    pass
            # Resume playing
            if WINSOUND_AVAILABLE and self.alarm_file.exists():
                try:
                    winsound.PlaySound(
                        str(self.alarm_file),
                        winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP
                    )
                except:
                    pass
        print("[Alarm] Unmuted")


# Alias for backward compatibility
ContinuousAlarm = WavAlarm
    
