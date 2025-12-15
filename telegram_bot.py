#!/usr/bin/env python3
"""Telegram Bot - With synchronous photo sending for immediate alerts."""

import requests
import time
import json
from typing import Optional, Dict
from pathlib import Path
import threading
from queue import Queue, Empty

from PyQt6.QtCore import QThread, pyqtSignal

from config import Config


class TelegramBot(QThread):
    """Telegram bot with sync and async sending."""

    message_received = pyqtSignal(str, str)

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.running = False
        self.last_update_id = 0

        self.is_armed = False
        self.is_recording = False
        self.is_muted = False

        self._send_queue: Queue = Queue()
        self._sender_thread: Optional[threading.Thread] = None

        self.button_commands = {
            "🔒 Arm System": ("arm", ""),
            "🔓 Disarm": ("disarm", ""),
            "📸 Snapshot": ("snap", ""),
            "⏺ Record": ("record", ""),
            "⏹ Stop Recording": ("stoprecord", ""),
            "🔇 Mute": ("mute", ""),
            "🔊 Unmute": ("unmute", ""),
            "📊 Status": ("status", ""),
            "👤 Reload Faces": ("reload_faces", ""),
        }

    def run(self):
        self.running = True

        self._sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self._sender_thread.start()

        while self.running:
            try:
                self._poll_updates()
            except Exception as e:
                print(f"[Telegram] Poll error: {e}")
                time.sleep(5)

    def stop(self):
        self.running = False
        self._send_queue.put(None)

    def _sender_loop(self):
        """Process send queue for non-critical messages."""
        while self.running:
            try:
                item = self._send_queue.get(timeout=1)
                if item is None:
                    break

                msg_type, data = item

                if msg_type == 'text':
                    self._send_text_internal(data['text'], data.get('reply_markup'), data.get('parse_mode', 'Markdown'))
                elif msg_type == 'photo':
                    self._send_photo_internal(data['path'], data.get('caption'))
            except Empty:
                continue
            except Exception as e:
                print(f"[Telegram] Sender error: {e}")

    def _poll_updates(self):
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                'offset': self.last_update_id + 1,
                'timeout': 30,
                'allowed_updates': ['message']
            }

            resp = requests.get(url, params=params, timeout=35)
            if resp.status_code != 200:
                return

            data = resp.json()
            if not data.get('ok'):
                return

            for update in data.get('result', []):
                self.last_update_id = update['update_id']
                self._handle_update(update)
        except requests.exceptions.Timeout:
            pass
        except Exception as e:
            print(f"[Telegram] Update error: {e}")
            time.sleep(2)

    def _handle_update(self, update: Dict):
        if 'message' not in update:
            return

        msg = update['message']
        text = msg.get('text', '').strip()

        if not text:
            return

        print(f"[Telegram] Received: {text}")

        if text in self.button_commands:
            cmd, args = self.button_commands[text]
            print(f"[Telegram] Button command: {cmd}")
            self.message_received.emit(cmd, args)
            return

        if text.startswith('/'):
            parts = text[1:].split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ''

            if cmd in ['start', 'menu', 'help']:
                self.send_main_menu()
            else:
                self.message_received.emit(cmd, args)
            return

        self.send_message(f"Unknown command. Use the buttons below or type /menu")

    def _send_text_internal(self, text: str, reply_markup: Optional[Dict] = None, parse_mode: str = 'Markdown'):
        """Send text message (internal)."""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            if reply_markup:
                data['reply_markup'] = json.dumps(reply_markup)

            resp = requests.post(url, json=data, timeout=30)
            if resp.status_code == 200:
                print(f"[Telegram] Text sent")
            else:
                print(f"[Telegram] Text send failed: {resp.status_code}")
        except Exception as e:
            print(f"[Telegram] Send text error: {e}")

    def _send_photo_internal(self, path: str, caption: Optional[str] = None) -> bool:
        """Send photo (internal)."""
        if not Path(path).exists():
            print(f"[Telegram] Photo not found: {path}")
            return False

        for attempt in range(3):
            try:
                url = f"{self.base_url}/sendPhoto"
                data = {'chat_id': self.chat_id}
                if caption:
                    data['caption'] = caption
                    data['parse_mode'] = 'Markdown'

                with open(path, 'rb') as f:
                    files = {'photo': f}
                    resp = requests.post(url, data=data, files=files, timeout=60)

                if resp.status_code == 200:
                    print(f"[Telegram] Photo sent!")
                    return True
                else:
                    print(f"[Telegram] Photo attempt {attempt+1} failed: {resp.status_code}")
            except Exception as e:
                print(f"[Telegram] Photo attempt {attempt+1} error: {e}")

            if attempt < 2:
                time.sleep(0.5)

        return False

    def send_photo_sync(self, path: str, caption: str) -> bool:
        """Send photo SYNCHRONOUSLY - blocks until sent.
        
        Use this for critical alerts that must be sent immediately.
        """
        print(f"[Telegram] Sending photo SYNC: {path}")
        return self._send_photo_internal(path, caption)

    def send_message(self, text: str, photo_path: Optional[str] = None):
        """Send a message (queued, async)."""
        if photo_path and Path(photo_path).exists():
            self._send_queue.put(('photo', {'path': photo_path, 'caption': text}))
        else:
            self._send_queue.put(('text', {'text': text}))

    def send_alert_with_photo(self, text: str, photo_path: str):
        """Send alert with photo (queued, async)."""
        if Path(photo_path).exists():
            self._send_queue.put(('photo', {'path': photo_path, 'caption': text}))
        else:
            self._send_queue.put(('text', {'text': text + "\n\n(Photo not available)"}))

    def send_snapshot(self, photo_path: str):
        """Send snapshot photo (queued)."""
        if Path(photo_path).exists():
            self._send_queue.put(('photo', {'path': photo_path, 'caption': '📸 *Snapshot*'}))

    def update_state(self, armed: bool, recording: bool, muted: bool):
        self.is_armed = armed
        self.is_recording = recording
        self.is_muted = muted

    def send_main_menu(self):
        """Send main menu with reply keyboard buttons."""
        status = "🔒 *ARMED*" if self.is_armed else "🔓 *DISARMED*"
        rec_status = " | ⏺ Recording" if self.is_recording else ""

        text = f"""🛡️ *Security System*

Status: {status}{rec_status}

Use the buttons below:"""

        arm_btn = {'text': '🔓 Disarm'} if self.is_armed else {'text': '🔒 Arm System'}
        rec_btn = {'text': '⏹ Stop Recording'} if self.is_recording else {'text': '⏺ Record'}
        mute_btn = {'text': '🔊 Unmute'} if self.is_muted else {'text': '🔇 Mute'}

        keyboard = {
            'keyboard': [
                [arm_btn],
                [{'text': '📸 Snapshot'}, rec_btn],
                [mute_btn, {'text': '📊 Status'}],
                [{'text': '👤 Reload Faces'}],
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False
        }

        self._send_queue.put(('text', {'text': text, 'reply_markup': keyboard}))
