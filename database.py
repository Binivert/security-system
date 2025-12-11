#!/usr/bin/env python3
"""Database management."""

import sqlite3
from datetime import date
from typing import Dict, List, Optional
from threading import Lock

from config import Config


class DatabaseManager:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.BASE_DIR / "security.db"
        self._lock = Lock()
        self._init()
    
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init(self):
        with self._lock:
            conn = self._conn()
            c = conn.cursor()
            
            c.execute('''CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                description TEXT,
                snapshot_path TEXT,
                person_count INTEGER DEFAULT 0
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE NOT NULL,
                detections INTEGER DEFAULT 0,
                alerts INTEGER DEFAULT 0,
                breaches INTEGER DEFAULT 0,
                trusted INTEGER DEFAULT 0,
                unknown INTEGER DEFAULT 0
            )''')
            
            conn.commit()
            conn.close()
    
    def log_event(self, event_type: str, description: str, snapshot_path: str = None, person_count: int = 0):
        with self._lock:
            try:
                conn = self._conn()
                conn.execute(
                    'INSERT INTO events (event_type, description, snapshot_path, person_count) VALUES (?, ?, ?, ?)',
                    (event_type, description, snapshot_path, person_count)
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
    
    def get_recent_events(self, limit: int = 10) -> List[Dict]:
        with self._lock:
            try:
                conn = self._conn()
                rows = conn.execute('SELECT * FROM events ORDER BY timestamp DESC LIMIT ?', (limit,)).fetchall()
                conn.close()
                return [dict(r) for r in rows]
            except Exception:
                return []
    
    def update_daily_stats(self, detections=0, alerts=0, breaches=0, trusted=0, unknown=0):
        with self._lock:
            try:
                today = date.today().isoformat()
                conn = self._conn()
                c = conn.cursor()
                
                c.execute('SELECT id FROM daily_stats WHERE date = ?', (today,))
                if c.fetchone():
                    c.execute('''UPDATE daily_stats SET
                        detections = detections + ?,
                        alerts = alerts + ?,
                        breaches = breaches + ?,
                        trusted = trusted + ?,
                        unknown = unknown + ?
                        WHERE date = ?''', (detections, alerts, breaches, trusted, unknown, today))
                else:
                    c.execute('''INSERT INTO daily_stats (date, detections, alerts, breaches, trusted, unknown)
                        VALUES (?, ?, ?, ?, ?, ?)''', (today, detections, alerts, breaches, trusted, unknown))
                
                conn.commit()
                conn.close()
            except Exception:
                pass
    
    def get_daily_stats(self, target_date: str = None) -> Optional[Dict]:
        with self._lock:
            try:
                if not target_date:
                    target_date = date.today().isoformat()
                conn = self._conn()
                row = conn.execute('SELECT * FROM daily_stats WHERE date = ?', (target_date,)).fetchone()
                conn.close()
                return dict(row) if row else {'detections': 0, 'alerts': 0, 'breaches': 0, 'trusted': 0, 'unknown': 0}
            except Exception:
                return None
