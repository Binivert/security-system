#!/usr/bin/env python3
"""Telegram bot with inline keyboard buttons."""

import requests
import time
import json
from pathlib import Path
from threading import Lock

from PyQt6.QtCore import QThread, pyqtSignal

from config import Config


class TelegramBot(QThread):
    message_received = pyqtSignal(str, str)
    
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.running = False
        self.last_update_id = 0
        self._lock = Lock()
        
        self.is_armed = False
        self.is_recording = False
        self.is_muted = False
        self._connected = False
    
    def run(self):
        self.running = True
        self._test_connection()
        
        while self.running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._process_update(update)
            except Exception:
                pass
            time.sleep(1)
    
    def _test_connection(self):
        try:
            r = requests.get(f"{self.base_url}/getMe", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('ok'):
                    self._connected = True
                    return True
        except Exception:
            pass
        self._connected = False
        return False
    
    def stop(self):
        self.running = False
    
    def _get_updates(self):
        try:
            r = requests.get(
                f"{self.base_url}/getUpdates",
                params={'offset': self.last_update_id + 1, 'timeout': 30},
                timeout=35
            )
            data = r.json()
            if data.get('ok'):
                updates = data.get('result', [])
                if updates:
                    self.last_update_id = updates[-1]['update_id']
                return updates
        except Exception:
            pass
        return []
    
    def _process_update(self, update: dict):
        if 'callback_query' in update:
            cb = update['callback_query']
            data = cb.get('data', '')
            cb_id = cb.get('id')
            self._answer_callback(cb_id)
            self._handle_command(data)
            return
        
        msg = update.get('message', {})
        text = msg.get('text', '').strip()
        if text:
            if text.startswith('/'):
                text = text[1:]
            self._handle_command(text)
    
    def _handle_command(self, text: str):
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ''
        
        self.message_received.emit(cmd, args)
        
        if cmd in ['start', 'menu']:
            self.send_main_menu()
        elif cmd == 'help':
            self.send_help()
        elif cmd == 'settings':
            self.send_settings_menu()
    
    def _answer_callback(self, cb_id: str):
        try:
            requests.post(
                f"{self.base_url}/answerCallbackQuery",
                json={'callback_query_id': cb_id},
                timeout=5
            )
        except Exception:
            pass
    
    def send_message(self, text: str, photo_path: str = None, reply_markup: dict = None):
        with self._lock:
            try:
                if reply_markup is None:
                    reply_markup = self._get_quick_buttons()
                
                if photo_path and Path(photo_path).exists():
                    url = f"{self.base_url}/sendPhoto"
                    with open(photo_path, 'rb') as f:
                        data = {
                            'chat_id': self.chat_id,
                            'caption': text,
                            'parse_mode': 'Markdown'
                        }
                        if reply_markup:
                            data['reply_markup'] = json.dumps(reply_markup)
                        requests.post(url, data=data, files={'photo': f}, timeout=30)
                else:
                    url = f"{self.base_url}/sendMessage"
                    data = {
                        'chat_id': self.chat_id,
                        'text': text,
                        'parse_mode': 'Markdown'
                    }
                    if reply_markup:
                        data['reply_markup'] = json.dumps(reply_markup)
                    requests.post(url, json=data, timeout=10)
            except Exception:
                pass
    
    def send_main_menu(self):
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '🔓 Disarm' if self.is_armed else '🔒 Arm', 
                     'callback_data': 'disarm' if self.is_armed else 'arm'},
                    {'text': '📸 Snapshot', 'callback_data': 'snap'}
                ],
                [
                    {'text': '⏹ Stop Rec' if self.is_recording else '⏺ Record', 
                     'callback_data': 'stoprecord' if self.is_recording else 'record'},
                    {'text': '🔊 Unmute' if self.is_muted else '🔇 Mute', 
                     'callback_data': 'unmute' if self.is_muted else 'mute'}
                ],
                [
                    {'text': '📊 Status', 'callback_data': 'status'},
                    {'text': '📈 Stats', 'callback_data': 'stats'}
                ],
                [
                    {'text': '📋 Log', 'callback_data': 'log'},
                    {'text': '⚙️ Settings', 'callback_data': 'settings'}
                ],
                [
                    {'text': '🔄 Reload Faces', 'callback_data': 'reload_faces'}
                ]
            ]
        }
        self.send_message("🛡️ *Security Control Panel*", reply_markup=keyboard)
    
    def send_settings_menu(self):
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '🌙 Night ON', 'callback_data': 'nightmode on'},
                    {'text': '☀️ Night OFF', 'callback_data': 'nightmode off'}
                ],
                [
                    {'text': '🔽 Low', 'callback_data': 'sensitivity low'},
                    {'text': '➖ Med', 'callback_data': 'sensitivity medium'},
                    {'text': '🔼 High', 'callback_data': 'sensitivity high'}
                ],
                [
                    {'text': '🔙 Back', 'callback_data': 'menu'}
                ]
            ]
        }
        self.send_message("⚙️ *Settings*", reply_markup=keyboard)
    
    def send_help(self):
        self.send_main_menu()
    
    def _get_quick_buttons(self) -> dict:
        return {
            'inline_keyboard': [
                [
                    {'text': '📸', 'callback_data': 'snap'},
                    {'text': '📊', 'callback_data': 'status'},
                    {'text': '🎛️', 'callback_data': 'menu'}
                ]
            ]
        }
    
    def update_state(self, is_armed: bool, is_recording: bool, is_muted: bool):
        self.is_armed = is_armed
        self.is_recording = is_recording
        self.is_muted = is_muted
