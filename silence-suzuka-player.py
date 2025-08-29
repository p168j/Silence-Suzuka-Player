#!/usr/bin/env python3
"""
Silence Auto-Player (mpv edition)
- mpv backend for fast streaming and near-instant next/prev
- System-wide silence monitor (auto-play on silence)
- AFK monitor (auto-pause on inactivity)
- Tray icon + tooltip reflecting playback state
- Saved playlist management (save/load)
- Theme styling (Dark) and optional thumbnails
"""

import sys
import os
import json
import time
import logging
import zipfile
import qtawesome as qta
from PySide6.QtGui import QIcon
from pathlib import Path
from datetime import datetime

from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QSize, QRectF

def load_svg_icon(path, size=QSize(18, 18)):
    renderer = QSvgRenderer(path)
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
    painter.end()
    return QIcon(pixmap)

def playlist_icon_for_type(item_type):
    if item_type == 'youtube':
        return load_svg_icon('icons/youtube-fa7.svg', QSize(28, 28))
    elif item_type == 'bilibili':
        return load_svg_icon('icons/bilibili-fa7.svg', QSize(28, 28))
    elif item_type == 'local':
        return "🎬"
    else:
        return "🎵"

# Initialize logging
def setup_logging(level='INFO'):
    logs_dir = Path(__file__).parent / 'logs'
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / 'silence_player.log'
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

# Initialize with default level (will be updated from settings)
logger = setup_logging()

# Debug banner
logger.info("Starting Silence Auto-Player (mpv)...")
# logger.info(f"Python version: {sys.version}")

# Dependencies
required = []

try:
    from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedLayout,
    QPushButton, QLabel, QSlider, QFileDialog, QMessageBox, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QStatusBar, QMenu,
    QSystemTrayIcon, QStyle, QDialog, QFormLayout, QDialogButtonBox, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QTabWidget, QToolTip, QGraphicsDropShadowEffect, QSpacerItem, QGridLayout
    )
    from PySide6.QtCore import Qt, QTimer, QSize, QThread, Signal, QEvent, QPropertyAnimation, QEasingCurve, Property
    from PySide6.QtGui import QIcon, QPixmap, QKeySequence, QShortcut, QAction, QPainter, QColor, QPen, QBrush, QFont, QFontDatabase
    print("✓ PySide6 imported")
    try:
        from PySide6.QtSvg import QSvgRenderer
        print("✓ QtSvg imported")
    except Exception as e:
        QSvgRenderer = None
        print(f"⚠ QtSvg not available: {e}")
except Exception as e:
    print(f"✗ PySide6 import failed: {e}")
    print("pip install PySide6")
    required.append("PySide6")

try:
    from mpv import MPV
    print("✓ python-mpv imported")
except Exception as e:
    print(f"✗ python-mpv import failed: {e}")
    print("pip install python-mpv")
    required.append("python-mpv")

try:
    import yt_dlp
    print("✓ yt-dlp imported")
except Exception as e:
    print(f"✗ yt-dlp import failed: {e}")
    print("pip install yt-dlp")
    required.append("yt-dlp")

try:
    import requests  # Optional for thumbnails
    HAVE_REQUESTS = True
    print("✓ requests imported")
except Exception as e:
    HAVE_REQUESTS = False
    print(f"⚠ requests not available (thumbnails disabled): {e}")

if required:
    print("\n❌ Missing required modules: " + ", ".join(required))
    input("\nPress Enter to exit...")
    sys.exit(1)

APP_DIR = Path(__file__).parent
CFG_CURRENT = APP_DIR / 'current.json'
CFG_POS = APP_DIR / 'positions.json'
CFG_PLAYLISTS = APP_DIR / 'playlists.json'
CFG_SETTINGS = APP_DIR / 'config.json'
CFG_STATS = APP_DIR / 'stats.json'
COOKIES_BILI = APP_DIR / 'cookies.txt'
CFG_COMPLETED = APP_DIR / 'completed.json'


# --- Monitors ---
class SystemAudioMonitor(QThread):
    silenceDetected = Signal()
    audioStateChanged = Signal(bool)
    rmsUpdated = Signal(float)

    def __init__(self, silence_duration_s=300.0, silence_threshold=0.03, resume_threshold=None, monitor_system_output=True, device_id=None, parent=None):
        super().__init__(parent)
        self.silence_duration_s = float(silence_duration_s)
        self.threshold = float(silence_threshold)
        try:
            self.resume_threshold = float(resume_threshold) if (resume_threshold is not None) else float(silence_threshold) * 1.5
        except Exception:
            self.resume_threshold = float(silence_threshold) * 1.5
        self.monitor_system_output = bool(monitor_system_output)
        self.device_id = device_id
        self._is_running = True
        self._last_state_is_silent = False
        self._silence_counter = 0.0
        self._restart_requested = False
        self._ema_rms = 0.0
        self._last_rms_emit = 0.0
        try:
            import sounddevice as sd
            self._sd = sd
            # print("✓ sounddevice available for system audio monitoring")
        except Exception as e:
            self._sd = None
            print(f"✗ sounddevice unavailable: {e}")

    def stop(self):
        self._is_running = False

    def update_settings(self, silence_duration_s=None, silence_threshold=None, resume_threshold=None, monitor_system_output=None, device_id=None):
        """Update monitoring settings and restart if needed"""
        if silence_duration_s is not None:
            self.silence_duration_s = float(silence_duration_s)
        if silence_threshold is not None:
            self.threshold = float(silence_threshold)
        if resume_threshold is not None:
            try:
                self.resume_threshold = float(resume_threshold)
            except Exception:
                pass
        restart = False
        if monitor_system_output is not None:
            old_mode = self.monitor_system_output
            self.monitor_system_output = bool(monitor_system_output)
            restart = restart or (old_mode != self.monitor_system_output)
        if device_id is not None and device_id != self.device_id:
            self.device_id = device_id
            restart = True
        if restart and self._is_running:
            self._restart_monitor()

    def _restart_monitor(self):
        """Internal method to restart monitoring with new settings"""
        # Signal the run loop to break the current stream and reopen with new settings
        self._restart_requested = True

    def run(self):
        if not self._sd:
            return
        try:
            import numpy as np
        except Exception:
            print("✗ numpy unavailable, disabling system audio monitoring")
            return

        while self._is_running:
            try:
                # Determine device to monitor
                # Use fixed device if provided; default to 46 as per user environment
                monitor_device = self.device_id if self.device_id is not None else 46
                device_type = 'input'
                
                if self.monitor_system_output and hasattr(self._sd, 'query_devices'):
                    # Try to find WASAPI loopback device on Windows
                    try:
                        import platform
                        if platform.system() == 'Windows':
                            devices = self._sd.query_devices()
                            for i, dev in enumerate(devices):
                                if dev.get('name', '').lower().find('stereo mix') != -1 or \
                                   dev.get('name', '').lower().find('what u hear') != -1 or \
                                   (dev.get('hostapi_name', '') == 'Windows WASAPI' and 
                                    dev.get('max_input_channels', 0) > 0 and 
                                    'loopback' in dev.get('name', '').lower()):
                                    monitor_device = i
                                    print(f"✓ Using WASAPI loopback device: {dev['name']}")
                                    break
                            
                            # If no explicit loopback found, try default output as input (WASAPI feature)
                            if monitor_device is None:
                                try:
                                    # On Windows with WASAPI, we can monitor the default output
                                    default_out = self._sd.query_devices(kind='output')
                                    if default_out and default_out.get('hostapi_name') == 'Windows WASAPI':
                                        # Use default input but configure for loopback monitoring
                                        monitor_device = None  # Use default input
                                        print("✓ Using default WASAPI device for system audio monitoring")
                                except Exception:
                                    pass
                    except Exception as e:
                        print(f"WASAPI loopback detection failed: {e}")
                
                # Fallback to specified device or default microphone
                if monitor_device is None:
                    monitor_device = self.device_id
                    if not self.monitor_system_output:
                        print("✓ Using microphone for audio monitoring")
                    else:
                        print("⚠ WASAPI loopback not available, falling back to microphone")

                # Configure device and backend specifics
                try:
                    import platform as _plat
                except Exception:
                    _plat = None
                extra_settings = None
                device_query_kind = 'input'
                try:
                    if _plat and _plat.system() == 'Windows' and bool(self.monitor_system_output):
                        # Prefer default output device for WASAPI loopback
                        try:
                            di = self._sd.default.device
                            if isinstance(di, (list, tuple)) and len(di) >= 2 and di[1] is not None:
                                monitor_device = di[1]
                        except Exception:
                            pass
                        # Enable WASAPI loopback if available
                        try:
                            extra_settings = self._sd.WasapiSettings(loopback=True)
                            device_query_kind = 'output'
                        except Exception:
                            extra_settings = None
                            device_query_kind = 'input'
                    else:
                        extra_settings = None
                        device_query_kind = 'input'
                except Exception:
                    extra_settings = None
                    device_query_kind = 'input'

                try:
                    device_info = self._sd.query_devices(monitor_device, device_query_kind)
                except Exception:
                    # Fallback to default device of the requested kind
                    try:
                        device_info = self._sd.query_devices(kind=device_query_kind)
                        monitor_device = None
                    except Exception:
                        device_info = {'default_samplerate': 44100}
                        monitor_device = None
                samplerate = int(device_info.get('default_samplerate', 44100))
                channels = 2 if extra_settings is not None else 1

                def audio_callback(indata, frames, time_info, status):
                    if status:
                        pass
                    # Use RMS (Root Mean Square) with light smoothing to reduce flapping
                    rms = float(np.sqrt(np.mean(indata**2)))
                    # Exponential moving average
                    try:
                        self._ema_rms = 0.2 * rms + 0.8 * float(getattr(self, '_ema_rms', 0.0))
                    except Exception:
                        self._ema_rms = rms
                    # Emit live RMS periodically for Settings meter
                    try:
                        now = time.time(); last = float(getattr(self, '_last_rms_emit', 0.0))
                        if (now - last) > 0.1:
                            self._last_rms_emit = now
                            self.rmsUpdated.emit(float(max(0.0, min(1.0, self._ema_rms))))
                    except Exception:
                        pass
                    # Hysteresis: use higher resume_threshold to flip from silent->active
                    rt = None
                    try:
                        rt = float(getattr(self, 'resume_threshold', self.threshold * 1.5))
                    except Exception:
                        rt = self.threshold * 1.5
                    if self._last_state_is_silent:
                        is_silent = (self._ema_rms < rt)
                    else:
                        is_silent = (self._ema_rms < self.threshold)
                    
                    if is_silent != self._last_state_is_silent:
                        self.audioStateChanged.emit(bool(is_silent))
                        self._last_state_is_silent = is_silent
                    
                    if is_silent:
                        self._silence_counter += len(indata) / samplerate
                    else:
                        self._silence_counter = 0.0
                    
                    if self._silence_counter > self.silence_duration_s:
                        self.silenceDetected.emit()
                        self._silence_counter = 0.0

                with self._sd.InputStream(device=monitor_device, samplerate=samplerate,
                                          channels=channels, callback=audio_callback, blocksize=1024, extra_settings=extra_settings):
                    while self._is_running:
                        if getattr(self, '_restart_requested', False):
                            break
                        self.msleep(100)
                if getattr(self, '_restart_requested', False):
                    # Clear flag and continue to reopen stream with updated settings
                    self._restart_requested = False
                    continue
                        
            except Exception as e:
                print(f"SystemAudioMonitor error: {e}")
                self.audioStateChanged.emit(False)
                self.msleep(3000)


class AFKMonitor(QThread):
    userIsAFK = Signal()

    def __init__(self, timeout_minutes=15, parent=None):
        super().__init__(parent)
        self.timeout_seconds = int(timeout_minutes) * 60
        self.last_input_time = time.time()
        self._is_running = True

    def update_activity(self, *args):
        self.last_input_time = time.time()

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            from pynput import mouse, keyboard
        except Exception as e:
            print(f"✗ pynput unavailable for AFK monitor: {e}")
            return
        mouse_listener = mouse.Listener(on_move=self.update_activity, on_click=self.update_activity, on_scroll=self.update_activity)
        keyboard_listener = keyboard.Listener(on_press=self.update_activity)
        mouse_listener.start(); keyboard_listener.start()
        try:
            while self._is_running:
                if time.time() - self.last_input_time > self.timeout_seconds:
                    self.userIsAFK.emit()
                    self.last_input_time = time.time()
                self.msleep(2000)
        finally:
            try:
                mouse_listener.stop(); keyboard_listener.stop()
            except Exception:
                pass


# --- Thumbnail fetcher ---
class ThumbnailFetcher(QThread):
    thumbnailReady = Signal(QPixmap)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        if not HAVE_REQUESTS or not self.url:
            return
        try:
            r = requests.get(self.url, timeout=6)
            if r.status_code == 200:
                pm = QPixmap(); pm.loadFromData(r.content)
                if not pm.isNull():
                    self.thumbnailReady.emit(pm)
        except Exception as e:
            print(f"Thumbnail fetch error: {e}")

class PlaylistLoaderThread(QThread):
    itemsReady = Signal(list)
    error = Signal(str)

    def __init__(self, url: str, kind: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.kind = kind  # 'youtube' or 'bilibili' or 'local'

    def run(self):
        try:
            import yt_dlp
        except Exception as e:
            self.error.emit(f"yt-dlp not available: {e}")
            return
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
            'socket_timeout': 60,
            'retries': 3,
            'playliststart': 1,
            'playlistend': 10000,
        }
        if self.kind == 'bilibili':
            ydl_opts['cookiefile'] = str(COOKIES_BILI)
        try:
            import urllib.parse as up
            target_url = self.url
            if self.kind == 'youtube' and ('list=' in self.url):
                try:
                    u = up.urlparse(self.url)
                    qs = up.parse_qs(u.query)
                    lid = (qs.get('list') or [''])[0]
                    if lid:
                        target_url = f"https://www.youtube.com/playlist?list={lid}"
                except Exception:
                    pass
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
        except Exception as e:
            self.error.emit(f"Failed to load playlist: {e}")
            return
        try:
            if info is None:
                self.itemsReady.emit([]); return
            # If this is a playlist with 'entries'
            if isinstance(info, dict) and info.get('entries'):
                playlist_title = info.get('title') or self.url
                entries = list(info.get('entries') or [])
                chunk = []
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    idv = entry.get('id') or ''
                    u = entry.get('webpage_url') or entry.get('url') or idv
                    if not u:
                        continue
                    # Normalize to full URL when extractor returns IDs only
                    if self.kind == 'bilibili' and not (u.startswith('http://') or u.startswith('https://')):
                        u = f"https://www.bilibili.com/video/{idv or u}"
                    if self.kind == 'youtube' and not (u.startswith('http://') or u.startswith('https://')):
                        u = f"https://www.youtube.com/watch?v={idv or u}"
                    title = entry.get('title') or u
                    chunk.append({'title': title, 'url': u, 'type': self.kind, 'playlist': playlist_title, 'playlist_key': info.get('id') or self.url})
                    if len(chunk) >= 25:
                        self.itemsReady.emit(chunk); chunk = []
                if chunk:
                    self.itemsReady.emit(chunk)
            else:
                # Single video fallback
                self.itemsReady.emit([{'title': info.get('title') or self.url, 'url': self.url, 'type': self.kind}])
        except Exception as e:
            self.error.emit(str(e)); return
        

class TitleResolveWorker(QThread):
    titleResolved = Signal(str, str)  # url, title
    error = Signal(str)

    def __init__(self, items: list, kind: str, parent=None):
        super().__init__(parent)
        self.items = items or []
        self.kind = kind

    def run(self):
        try:
            import yt_dlp
        except Exception as e:
            self.error.emit(f"yt-dlp not available: {e}"); return
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'socket_timeout': 10,
        }
        if self.kind == 'bilibili':
            ydl_opts['cookiefile'] = str(COOKIES_BILI)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for it in self.items:
                    try:
                        url = it.get('url'); title = it.get('title')
                        if not url or (title and title != url):
                            continue
                        info = ydl.extract_info(url, download=False)
                        t2 = info.get('title') if isinstance(info, dict) else None
                        if t2:
                            self.titleResolved.emit(url, t2)
                    except Exception:
                        continue
        except Exception as e:
            self.error.emit(str(e))

# --- Utility ---
def format_time(ms: int) -> str:
    s = max(0, ms // 1000)
    return f"{s // 60}:{s % 60:02d}"

# Simple human readable duration helper
def human_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds//60}m {seconds%60}s"
    return f"{seconds//3600}h {(seconds%3600)//60}m"

# --- Stats heatmap widget ---
class StatsHeatmapWidget(QWidget):
    daySelected = Signal(object)  # 'YYYY-MM-DD' or None

    def __init__(self, daily_map: dict, theme: str = 'dark', parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._theme = theme or 'dark'
        import datetime as dt
        self._dt = dt
        self._today = dt.date.today()
        # start one year back aligned to Sunday
        one_year_ago = self._today.replace(year=self._today.year - 1)
        # Align to previous Sunday (GitHub-style weeks start on Sunday)
        offset = (one_year_ago.weekday() + 1) % 7  # weekday(): Mon=0..Sun=6
        self._start = one_year_ago - dt.timedelta(days=offset)
        # Parse daily seconds
        self._daily = {}
        for k, v in (daily_map or {}).items():
            try:
                y, m, d = [int(x) for x in k.split('-')]
                self._daily[self._dt.date(y, m, d)] = float(v or 0)
            except Exception:
                continue
        self._selected = None
        self._compute_levels()
        self._cell = 12
        self._gap = 2
        self._top = 24
        self._left = 36
        self.setMinimumSize(self.sizeHint())

    def sizeHint(self):
        weeks = self._weeks_count()
        width = self._left + weeks * (self._cell + self._gap)
        height = self._top + 7 * (self._cell + self._gap)
        return QSize(width, height)

    def _weeks_count(self):
        delta = self._today - self._start
        return max(1, (delta.days // 7) + 1)

    def _compute_levels(self):
        vals = [v for v in self._daily.values() if v > 0]
        self._vmax = max(vals) if vals else 0.0
        # Level thresholds at ~0, 10%, 30%, 60%, 100%
        self._thresholds = [0,
                            0.10 * self._vmax,
                            0.30 * self._vmax,
                            0.60 * self._vmax,
                            1.00 * self._vmax]

    def _level(self, v: float) -> int:
        if v <= 0:
            return 0
        for i in range(1, 5):
            if v <= self._thresholds[i]:
                return i
        return 4

    def _palette(self):
        if self._theme == 'vinyl':
            # warm light scale
            return [QColor(224, 217, 200), QColor(255, 227, 190), QColor(246, 196, 148), QColor(235, 150, 95), QColor(206, 90, 52)]
        # dark scale similar to GitHub greens
        return [QColor(32, 32, 32), QColor(40, 66, 52), QColor(48, 98, 72), QColor(64, 135, 98), QColor(88, 171, 126)]

    def _date_at(self, x: int, y: int):
        col = (x - self._left) // (self._cell + self._gap)
        row = (y - self._top) // (self._cell + self._gap)
        if col < 0 or row < 0 or row > 6:
            return None
        dt = self._start + self._dt.timedelta(days=int(col) * 7 + int(row))
        if dt > self._today:
            return None
        return dt

    def mouseMoveEvent(self, e):
        try:
            x, y = int(e.position().x()), int(e.position().y())
            gp = e.globalPosition().toPoint()
        except AttributeError:
            x, y = e.x(), e.y()
            gp = e.globalPos()
        dt = self._date_at(x, y)
        if not dt:
            QToolTip.hideText(); return
        v = self._daily.get(dt, 0)
        QToolTip.showText(gp, f"{dt.isoformat()} — {human_duration(v)}", self)

    def mousePressEvent(self, e):
        try:
            x, y = int(e.position().x()), int(e.position().y())
        except AttributeError:
            x, y = e.x(), e.y()
        dt = self._date_at(x, y)
        if dt is None:
            self._selected = None
            self.daySelected.emit(None)
        else:
            if self._selected == dt:
                self._selected = None
                self.daySelected.emit(None)
            else:
                self._selected = dt
                self.daySelected.emit(dt.isoformat())
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        pal = self._palette()
        # Month labels
        p.setPen(QColor(180, 180, 180) if self._theme != 'vinyl' else QColor(90, 70, 60))
        p.setFont(QFont(p.font().family(), 8))
        self._draw_month_labels(p)
        # Cells
        for w in range(self._weeks_count()):
            for r in range(7):
                dt = self._start + self._dt.timedelta(days=w * 7 + r)
                if dt > self._today:
                    continue
                v = self._daily.get(dt, 0)
                lvl = self._level(v)
                rect_x = self._left + w * (self._cell + self._gap)
                rect_y = self._top + r * (self._cell + self._gap)
                p.fillRect(rect_x, rect_y, self._cell, self._cell, QBrush(pal[lvl]))
                # Selection outline
                if self._selected == dt:
                    pen = QPen(QColor(255, 255, 255) if self._theme != 'vinyl' else QColor(60, 40, 30))
                    pen.setWidth(2)
                    p.setPen(pen)
                    p.drawRect(rect_x, rect_y, self._cell, self._cell)
        p.end()

    def _draw_month_labels(self, p: QPainter):
        weeks = self._weeks_count()
        seen = set()
        for w in range(weeks):
            dt = self._start + self._dt.timedelta(days=w * 7)
            if dt.month in seen or dt > self._today:
                continue
            seen.add(dt.month)
            label = dt.strftime('%b')
            x = self._left + w * (self._cell + self._gap)
            p.drawText(x, 12, label)

# --- Custom slider with hover effects ---
class HoverSlider(QSlider):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self._hover_scale = 1.0

        # Animation object
        self._animation = QPropertyAnimation(self, b"hoverScale")
        self._animation.setDuration(150)  # match transitions.html
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._animation.stop()
        self._animation.setStartValue(self._hover_scale)
        self._animation.setEndValue(1.2)  # 20% bigger
        self._animation.start()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._animation.stop()
        self._animation.setStartValue(self._hover_scale)
        self._animation.setEndValue(1.0)
        self._animation.start()

    def getHoverScale(self):
        return self._hover_scale

    def setHoverScale(self, value):
        self._hover_scale = value
        self.update()

    hoverScale = Property(float, getHoverScale, setHoverScale)

    def paintEvent(self, event):
        # Draw default
        super().paintEvent(event)

        # Then overlay our scaled thumb
        from PySide6.QtWidgets import QStyleOptionSlider
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        opt = QStyleOptionSlider()
        self.initStyleOption(opt)

        handle_rect = self.style().subControlRect(
            QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self
        )

        # Scale outwards
        scale_offset = (self._hover_scale - 1.0) * (handle_rect.width() / 2)
        scaled_rect = handle_rect.adjusted(
            -scale_offset, -scale_offset, scale_offset, scale_offset
        )

        # Match transitions.html (brown thumb)
        handle_color = QColor(74, 44, 42)  # #4a2c2a
        painter.setBrush(QBrush(handle_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(scaled_rect)


# --- Playlist tree with drag-and-drop reorder ---
class ClickableLabel(QLabel):
    clicked = Signal()
    def mousePressEvent(self, event):
        try:
            self.clicked.emit()
        except Exception:
            pass
        super().mousePressEvent(event)

class PlaylistTree(QTreeWidget):
    def __init__(self, player):
        super().__init__()
        self.player = player
        self.setHeaderHidden(True)
        self.setObjectName('playlistTree')
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)

    def dropEvent(self, event):
        # Only process reorder when not in grouped view
        super().dropEvent(event)
        try:
            if getattr(self.player, 'grouped_view', False):
                return
            root = self.topLevelItem(0)
            if not root:
                return
            new_playlist = []
            for i in range(root.childCount()):
                child = root.child(i)
                data = child.data(0, Qt.UserRole)
                if isinstance(data, tuple) and data[0] == 'current':
                    # data[2] holds the original item dict
                    new_playlist.append(data[2])
            if len(new_playlist) == len(self.player.playlist) and new_playlist:
                self.player.playlist = new_playlist
                self.player._save_current_playlist()
                # Refresh to update indices bound to items
                self.player._refresh_playlist_widget()
        except Exception as e:
            print(f"Drag-and-drop reorder error: {e}")


# --- Player ---
class MediaPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Silence Suzuka Player")
        self.setGeometry(100, 100, 1180, 760)

        # Icons
        self.play_icon = QIcon(str(APP_DIR / 'icons/play_white.svg')) if (APP_DIR / 'icons/play_white.svg').exists() else self.style().standardIcon(QStyle.SP_MediaPlay)
        self.pause_icon = QIcon(str(APP_DIR / 'icons/pause_white.svg')) if (APP_DIR / 'icons/pause_white.svg').exists() else self.style().standardIcon(QStyle.SP_MediaPause)
        self.next_icon = QIcon(str(APP_DIR / 'icons/next.svg')) if (APP_DIR / 'icons/next.svg').exists() else self.style().standardIcon(QStyle.SP_MediaSkipForward)
        self.prev_icon = QIcon(str(APP_DIR / 'icons/previous.svg')) if (APP_DIR / 'icons/previous.svg').exists() else self.style().standardIcon(QStyle.SP_MediaSkipBackward)
        # Optional SVG icons for shuffle/repeat/volume
        self.shuffle_icon = QIcon(str(APP_DIR / 'icons/shuffle.svg')) if (APP_DIR / 'icons/shuffle.svg').exists() else QIcon()
        self.repeat_icon = QIcon(str(APP_DIR / 'icons/repeat.svg')) if (APP_DIR / 'icons/repeat.svg').exists() else QIcon()
        self.volume_icon = QIcon(str(APP_DIR / 'icons/volume.svg')) if (APP_DIR / 'icons/volume.svg').exists() else QIcon()

        # State
        self.playlist = []  # list of dicts {title, url, type}
        # Up Next collapsed state (persisted)
        self.up_next_collapsed = False
        self.current_index = -1
        self.playback_positions = {}
        self.saved_playlists = {}
        self.session_start_time = None
        self.last_position_update = 0
        self.auto_play_enabled = True
        self.afk_timeout_minutes = 15
        self.silence_duration_s = 300.0  # 5 minutes
        self.show_thumbnails = False
        self.theme = 'vinyl'
        # Playback modes
        self.shuffle_mode = False
        self.repeat_mode = False
        # Completion threshold (percent)
        self.completed_percent = 95
        # Skip completed items automatically when starting playback
        self.skip_completed = False
        # View filter: hide completed items
        self.unwatched_only = False
        # Monitor settings (persisted)
        self.monitor_system_output = True
        self.silence_threshold = 0.03
        self.resume_threshold = 0.045
        self._last_system_is_silent = True
        self.monitor_device_id = -1
        # User scrubbing flag for slider
        self._user_scrubbing = False
        # Completed items tracking (URLs)
        self.completed_urls = set()
        # Background title resolver workers (to update missing titles without blocking)
        self._title_workers = []
        self._last_resume_save = time.time()
        self._last_play_pos_ms = 0
        self._last_saved_pos_ms = {}
        self._resume_target_ms = 0
        self._resume_enforce_until = 0.0
        # One-off bypass for completed skipping (used by "Play From Beginning")
        self._force_play_ignore_completed = False
        # Playback model (Queue vs Scoped Library)
        self.playback_model = 'scoped'
        self.play_scope = None  # None = Library; ('group', key) = playlist group
        # Clipboard URL prompt state
        self._last_clipboard_offer = ""
        # Logging level (persisted)
        self.log_level = 'INFO'
        
        self.theme = 'vinyl'   # Vinyl theme default
        self.show_up_next = False   # Hide Up Next panel by default
        self._init_fonts()
        self._build_ui()
        self._setup_keyboard_shortcuts()
        if self.theme == 'vinyl':
            self._apply_vinyl_theme()
        else:
            self._apply_dark_theme()
        self._init_mpv()
        self._load_files()
        self._init_monitors()
        self._init_tray()

        self.status.showMessage("Ready")

    def export_diagnostics(self):
        """Export logs and config files for debugging"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_path = APP_DIR / f"silence_player_diagnostics_{timestamp}.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add log file if it exists
                logs_dir = APP_DIR / 'logs'
                log_file = logs_dir / 'silence_player.log'
                if log_file.exists():
                    zf.write(log_file, 'logs/silence_player.log')
                
                # Add config files
                for cfg_file in [CFG_SETTINGS, CFG_CURRENT, CFG_POS, CFG_PLAYLISTS, CFG_STATS, CFG_COMPLETED]:
                    if cfg_file.exists():
                        zf.write(cfg_file, f'config/{cfg_file.name}')
                
                # Add environment info
                import platform
                env_info = {
                    'python_version': sys.version,
                    'platform': platform.platform(),
                    'app_dir': str(APP_DIR),
                    'log_level': self.log_level,
                    'theme': getattr(self, 'theme', 'unknown'),
                    'playback_model': getattr(self, 'playback_model', 'unknown'),
                    'timestamp': timestamp
                }
                zf.writestr('environment.json', json.dumps(env_info, indent=2))
            
            QMessageBox.information(self, "Diagnostics Exported", 
                                  f"Diagnostics exported to:\n{zip_path}")
            logger.info(f"Diagnostics exported to {zip_path}")
            
        except Exception as e:
            logger.error(f"Export diagnostics failed: {e}", exc_info=True)
            QMessageBox.warning(self, "Export Failed", f"Failed to export diagnostics:\n\n{str(e)}")

    def open_logs_folder(self):
        """Open the logs folder in file explorer"""
        try:
            import subprocess
            import platform
            logs_dir = APP_DIR / 'logs'
            logs_dir.mkdir(exist_ok=True)  # Ensure it exists
            
            if platform.system() == 'Windows':
                subprocess.run(['explorer', str(logs_dir)], check=False)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', str(logs_dir)], check=False)
            else:  # Linux
                subprocess.run(['xdg-open', str(logs_dir)], check=False)
        except Exception as e:
            logger.error(f"Open logs folder failed: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to open logs folder:\n\n{str(e)}")

    # UI
    def _build_ui(self):
        central = QWidget(); central.setObjectName('bgRoot'); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(8)
        icon_size = QSize(22, 22)

        # Top bar
        top = QHBoxLayout(); top.setSpacing(8)
        title = QLabel("Silence Suzuka Player"); title.setObjectName('titleLabel'); title.setFont(self._font_serif(20, italic=True, bold=True))
        # Scope chip (Scoped Library mode)
        self.scope_label = ClickableLabel("Scope: Library"); self.scope_label.setObjectName('scopeChip'); self.scope_label.setVisible(False); self.scope_label.setFont(QFont(self._ui_font))
        self.scope_label.clicked.connect(lambda: self._on_scope_label_clicked())
        # Left: title + scope
        top.addWidget(title); top.addWidget(self.scope_label); top.addStretch()
        # Right: Today badge • Silence • Stats • Settings • Theme
        self.today_badge = QLabel("0s"); self.today_badge.setObjectName('statsBadge'); self.today_badge.setToolTip("Total listening time today")
        top.addWidget(self.today_badge)
        self.silence_indicator = QLabel("🔇"); self.silence_indicator.setObjectName('silenceIndicator'); self.silence_indicator.setVisible(False); self.silence_indicator.setToolTip("System silence indicator — shows when no system audio is detected (configurable in Settings → Audio Monitor)")
        top.addWidget(self.silence_indicator)
        stats_btn = QPushButton("📊"); stats_btn.setObjectName('settingsBtn'); stats_btn.setToolTip("Listening Statistics"); stats_btn.clicked.connect(self.open_stats)
        top.addWidget(stats_btn)
        settings_btn = QPushButton("⚙"); settings_btn.setObjectName('settingsBtn'); settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self.open_settings_tabs)
        top.addWidget(settings_btn)
        self.theme_btn = QPushButton("🎨"); self.theme_btn.setObjectName('settingsBtn'); self.theme_btn.setToolTip(f"Toggle Theme ({self.theme.capitalize()})")
        self.theme_btn.clicked.connect(self.toggle_theme)
        top.addWidget(self.theme_btn)
        root.addLayout(top)

        # Content
        content = QHBoxLayout(); content.setSpacing(8); root.addLayout(content, 1)

        # Sidebar
        side_widget = QWidget(); side_widget.setObjectName('sidebar'); side_layout = QVBoxLayout(side_widget); side_layout.setSpacing(10)
        side_layout.setContentsMargins(8, 8, 8, 8)
        content.addWidget(side_widget, 0)

                # ---- Add Media (SVG chevron) replacement ----
        from PySide6.QtCore import QByteArray, QRectF

        _SVG_CHEVRON = """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
          <g fill="none" stroke="{stroke}" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2">
            <path d="M6 9.5 L12 15 L18 9.5"/>
          </g>
        </svg>
        """

        _svg_pixmap_cache = {}

        def make_chevron_pixmap_svg(px_size: int = 22, stroke_color: str = "#f3ead3", bg_rgba=(0, 0, 0, 18)) -> QPixmap:
            key = (px_size, stroke_color, bg_rgba)
            if key in _svg_pixmap_cache:
                return _svg_pixmap_cache[key]

            svg = _SVG_CHEVRON.format(stroke=stroke_color)
            # QSvgRenderer is available at module scope (imported near the top)
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))

            pm = QPixmap(px_size, px_size)
            pm.fill(QColor(0, 0, 0, 0))

            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing, True)

            if isinstance(bg_rgba, tuple):
                bg = QColor(*bg_rgba)
            else:
                bg = QColor(bg_rgba)
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(0, 0, px_size, px_size, px_size / 2.0, px_size / 2.0)

            renderer.render(painter, QRectF(0, 0, px_size, px_size))

            painter.end()
            _svg_pixmap_cache[key] = pm
            return pm


        # Build the Add Media widget (Variant A, SVG chevron)
        add_media_btn = QWidget(self)
        add_media_btn.setObjectName("addMediaBtn")
        add_media_btn.setCursor(Qt.PointingHandCursor)
        add_media_btn.setFixedHeight(44)

        add_media_btn.setStyleSheet("""
        #addMediaBtn {
            background-color: #e76f51;
            color: #f3ead3;
            border: none;
            border-radius: 8px;
            padding: 0 18px;
        }
        #addMediaBtn:hover { background-color: #d86a4a; }
        #addMediaBtn:pressed { background-color: #d1603f; }
        """)

        add_media_layout = QHBoxLayout(add_media_btn)
        add_media_layout.setContentsMargins(14, 0, 12, 0)
        add_media_layout.setSpacing(10)

        plus_lbl = QLabel("＋")
        plus_lbl.setStyleSheet("font-size:15px; color: #f3ead3; margin-right:8px;")
        add_media_layout.addWidget(plus_lbl)

        media_lbl = QLabel("Add Media")
        media_lbl.setStyleSheet("font-size:15px; color: #f3ead3; font-weight:700; font-family: 'Inter', 'Segoe UI', sans-serif;")
        add_media_layout.addWidget(media_lbl)

        add_media_layout.addStretch(1)

        _chev_px = make_chevron_pixmap_svg(px_size=22, stroke_color="#f3ead3", bg_rgba=(0, 0, 0, 18))
        chevron_lbl = QLabel()
        chevron_lbl.setFixedSize(22, 22)
        chevron_lbl.setPixmap(_chev_px)
        chevron_lbl.setScaledContents(False)
        add_media_layout.addWidget(chevron_lbl)

        menu = QMenu(self)
        menu.addAction("🔗 Add Link...", self.add_link_dialog)
        menu.addAction("📁 Add Files...", self.add_local_files)
        # don't call _maybe_offer_clipboard_url from aboutToShow any more
        try:
            menu.aboutToShow.connect(lambda: self._apply_menu_theme(menu))
        except Exception:
            pass

        def _add_media_show_menu(event):
            # Try clipboard offer first; if it handled (added) the URL, skip showing the menu.
            try:
                handled = False
                try:
                    handled = bool(self._maybe_offer_clipboard_url())
                except Exception:
                    handled = False
                if not handled:
                    menu.exec(add_media_btn.mapToGlobal(add_media_btn.rect().bottomRight()))
            except Exception:
                # fallback: show menu if something goes wrong
                try:
                    menu.exec(add_media_btn.mapToGlobal(add_media_btn.rect().bottomRight()))
                except Exception:
                    pass

        add_media_btn.mousePressEvent = _add_media_show_menu

        side_layout.addWidget(add_media_btn)
        # ---- end Add Media (SVG chevron) replacement ----

        opts = QHBoxLayout()
        # Front page toggles removed; configure in Settings
        side_layout.addLayout(opts)

        # Playlist controls (save/load) — Unwatched toggle with icon swap (eye / eye-off)
        controls = QHBoxLayout()
        save_btn = QPushButton("💾")
        save_btn.setObjectName('miniBtn')
        save_btn.setToolTip("Save current playlist")
        save_btn.clicked.connect(self.save_playlist)
        save_btn.setFixedSize(36, 28)
        load_btn = QPushButton("📂")
        load_btn.setObjectName('miniBtn')
        load_btn.setToolTip("Load saved playlist")
        load_btn.clicked.connect(self.load_playlist_dialog)
        load_btn.setFixedSize(36, 28)

        # New: icon-only Unwatched toggle (prefers icons/eye.svg + icons/eye-off.svg)
        self.unwatched_btn = QPushButton()
        self.unwatched_btn.setObjectName('miniBtn')
        self.unwatched_btn.setCheckable(True)
        try:
            self.unwatched_btn.setFixedSize(36, 28)
        except Exception:
            pass

        # Resolve SVG icons if present; otherwise fallback to emoji
        try:
            eye_on_path = APP_DIR / 'icons' / 'eye.svg'
            eye_off_path = APP_DIR / 'icons' / 'eye-off.svg'
            if eye_on_path.exists() and eye_off_path.exists():
                self._unwatched_icon_on = QIcon(str(eye_on_path))
                self._unwatched_icon_off = QIcon(str(eye_off_path))
                # icon-only, set icon size for alignment
                self.unwatched_btn.setIconSize(QSize(18, 18))
                self.unwatched_btn.setText("")  # icon-only
            else:
                self._unwatched_icon_on = None
                self._unwatched_icon_off = None
                # Emoji fallback: OFF shows 👁 (meaning show) and ON shows 🙈 (hidden)
                # set a compact emoji so button width matches others
                self.unwatched_btn.setText("👁" if not getattr(self, 'unwatched_only', False) else "🙈")
        except Exception:
            self._unwatched_icon_on = None
            self._unwatched_icon_off = None
            self.unwatched_btn.setText("👁" if not getattr(self, 'unwatched_only', False) else "🙈")

                # use themed tooltip instead of native QToolTip (keep accessible description)
        try:
            self.unwatched_btn.setAccessibleDescription("Show unwatched items only (toggle)")
        except Exception:
            pass
        self.unwatched_btn.setToolTip("")
        # Reuse existing logic
        self.unwatched_btn.toggled.connect(self._toggle_unwatched_only)
        # Update visuals (icon/text and styling)
        self.unwatched_btn.toggled.connect(self._update_unwatched_btn_visual)

        # initialize state from persisted flag (set in _load_files)
        try:
            self.unwatched_btn.setChecked(bool(getattr(self, 'unwatched_only', False)))
        except Exception:
            pass
        try:
            # ensure correct initial appearance
            self._update_unwatched_btn_visual(bool(getattr(self, 'unwatched_only', False)))
        except Exception:
            pass
        try:
            # Install themed tooltip (shows app-styled tooltip and is updated by _update_unwatched_btn_visual)
            initial_txt = "Unwatched only: ON (click to turn off)" if getattr(self, 'unwatched_only', False) else "Show unwatched items only (OFF)"
            self._install_themed_tooltip(self.unwatched_btn, initial_txt)
        except Exception:
            pass   
        try:
            # Convert any remaining non-empty native tooltips on child widgets to themed QLabel tooltips
            # This will: read widget.toolTip(), install themed tooltip, set accessible description, then clear native tooltip
            for child in self.findChildren(QWidget):
                try:
                    txt = child.toolTip() if hasattr(child, 'toolTip') else ""
                    if txt and isinstance(txt, str) and txt.strip():
                        # install themed QLabel tooltip
                        self._install_themed_tooltip(child, txt)
                        # preserve accessibility while hiding native QToolTip
                        try:
                            child.setAccessibleDescription(txt)
                        except Exception:
                            pass
                        child.setToolTip("")
                except Exception:
                    pass
        except Exception:
            pass            

        # Layout: Save | Load | Unwatched-icon | spacer | Group
        controls.addWidget(save_btn)
        controls.addWidget(load_btn)
        controls.addWidget(self.unwatched_btn)
        controls.addStretch()
        side_layout.addLayout(controls)

        try:
            self._update_group_toggle_visibility()
        except Exception:
            pass

        self.search_bar = QLineEdit(); self.search_bar.setPlaceholderText("Search playlist..."); self.search_bar.setObjectName('searchBar')
        self.search_bar.textChanged.connect(self.filter_playlist)
        try:
            self.search_bar.textChanged.connect(self._apply_filters_to_tree)
        except Exception:
            pass
        side_layout.addWidget(self.search_bar)

        # Create a container widget to hold either the playlist or the empty state view
        self.playlist_container = QWidget()
        self.playlist_stack = QStackedLayout(self.playlist_container)
        self.playlist_stack.setContentsMargins(0, 0, 0, 0)

        # 1. The Playlist Tree (Index 0)
        self.playlist_tree = PlaylistTree(self)
        self.playlist_tree.setHeaderHidden(True)
        self.playlist_tree.setObjectName('playlistTree')
        self.playlist_tree.setAlternatingRowColors(True)
        self.playlist_tree.setIndentation(14)
        self.playlist_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.playlist_tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)
        self.playlist_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist_tree.customContextMenuRequested.connect(self._show_playlist_context_menu)
        
        # Set text elide mode for single-line with ellipsis
        self.playlist_tree.setTextElideMode(Qt.ElideRight)

        # Set playlist font: Lora, italic, bold, size 14
        self.playlist_tree.setFont(self._font_serif(14, italic=True, bold=True))

        self.playlist_stack.addWidget(self.playlist_tree)

         # --- ADD THESE LINES FOR ICON SIZE AND ROW HEIGHT ---
        self.playlist_tree.setIconSize(QSize(28, 28))  # Make icon 28x28 (or adjust as needed)
        self.playlist_tree.setStyleSheet("#playlistTree::item { min-height: 32px; }")  # Row height for vertical alignment

        # 2. The Empty State Widget (Index 1)
        self.empty_state_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_state_widget)
        empty_layout.addStretch()
        empty_icon = QLabel()
        empty_icon.setObjectName('emptyStateIcon')
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_icon.setPixmap(load_svg_icon('icons/music-off-tabler.svg', QSize(48, 48)).pixmap(48, 48))
        empty_icon.setObjectName('emptyStateIcon')
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_heading = QLabel("Your Library is Empty")
        empty_heading.setObjectName('emptyStateHeading')
        empty_heading.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_heading)
        empty_subheading = QLabel("Click 'Add Media' to get started.")
        empty_subheading.setObjectName('emptyStateSubheading')
        empty_subheading.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_subheading)
        empty_layout.addStretch()
        self.playlist_stack.addWidget(self.empty_state_widget)

        # Add the container to the sidebar
        side_layout.addWidget(self.playlist_container, 1)

        # Main area: video frame + controls
        main_col = QVBoxLayout(); content.addLayout(main_col, 1)
        self.video_frame = QWidget(); self.video_frame.setObjectName('videoWidget')
        self.video_frame.setStyleSheet("background:#000; border-radius: 6px"); main_col.addWidget(self.video_frame, 1)

        # Now Playing and Progress Bar Layout
        now_playing_layout = QVBoxLayout()

        # Track Title Label
        self.track_label = QLabel("No track playing")
        self.track_label.setObjectName('trackLabel')
        self.track_label.setFont(self._font_serif(24, italic=True, bold=True))
        self.track_label.setWordWrap(False)  # Disable word wrap for eliding
        self.track_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.track_label.setStyleSheet("""
            color: #4a2c2a;
            background: transparent;
            margin-top: 14px;
            margin-bottom: 12px;
            letter-spacing: 0.5px;
        """)
        self._track_title_full = "No track playing"  # Store full text for eliding
        now_playing_layout.addWidget(self.track_label)

        # Progress Bar and Time Labels
        progress_layout = QHBoxLayout()
        self.time_label = QLabel("0:00")
        self.time_label.setObjectName('timeLabel')
        self.time_label.setFont(QFont(self._ui_font))
        self.progress = HoverSlider(Qt.Horizontal)
        self.progress.sliderPressed.connect(lambda: setattr(self, '_user_scrubbing', True))
        self.progress.sliderReleased.connect(self._on_slider_released)
        self.progress.sliderMoved.connect(self._on_slider_moved)
        self.dur_label = QLabel("0:00")
        self.dur_label.setObjectName('durLabel')
        self.dur_label.setFont(QFont(self._ui_font))
        
        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.progress, 1)
        progress_layout.addWidget(self.dur_label)
        now_playing_layout.addLayout(progress_layout)

        main_col.addLayout(now_playing_layout)
        # Up Next panel (toggle via Settings)
        try:
            self.up_next_container = QWidget(); up_layout = QVBoxLayout(self.up_next_container); up_layout.setContentsMargins(0,0,0,0)
            # Collapsible header as a dropdown
            self.up_next_header = QPushButton("▼ Up Next"); self.up_next_header.setCheckable(True); self.up_next_header.setChecked(True); self.up_next_header.setObjectName('upNextHeader')
            self.up_next_header.clicked.connect(lambda _=False: self._toggle_up_next_visible(self.up_next_header.isChecked()))
            # Persist collapsed state on toggle
            try:
                self.up_next_header.clicked.connect(lambda _=False: setattr(self, 'up_next_collapsed', not self.up_next_header.isChecked()))
            except Exception:
                pass
            up_layout.addWidget(self.up_next_header)
            self.up_next = QTreeWidget(); self.up_next.setHeaderHidden(True); self.up_next.setObjectName('upNext'); self.up_next.setFixedHeight(140); self.up_next.setFont(self._font_serif(14, italic=True, bold=True)); self.up_next.setAlternatingRowColors(True); self.up_next.setIndentation(12)
            self.up_next.setContextMenuPolicy(Qt.CustomContextMenu)
            self.up_next.customContextMenuRequested.connect(self._show_up_next_menu)
            self.up_next.itemDoubleClicked.connect(self._on_up_next_double_clicked)
            up_layout.addWidget(self.up_next)
            main_col.addWidget(self.up_next_container)
        except Exception:
            pass

        # Control bar

        # Shuffle
        self.shuffle_btn = QPushButton()
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setObjectName('controlBtn'); self.shuffle_btn.setToolTip("Shuffle")
        try:
            if hasattr(self, 'shuffle_icon') and not self.shuffle_icon.isNull():
                self.shuffle_btn.setIcon(self.shuffle_icon)
                self.shuffle_btn.setIconSize(icon_size)
            else:
                self.shuffle_btn.setText("🔀")
        except Exception:
            self.shuffle_btn.setText("🔀")
        self.shuffle_btn.clicked.connect(self._toggle_shuffle); 
        # Prev / Play-Pause / Next
        prev_btn = QPushButton()
        prev_btn.setIcon(self.prev_icon)
        prev_btn.setIconSize(icon_size)
        prev_btn.setObjectName('controlBtn')
        prev_btn.clicked.connect(self.previous_track)
     

        self.play_pause_btn = QPushButton()
        # initial icon will be set after we prepare tinted variants below
        self.play_pause_btn.setIconSize(QSize(30, 30))
        self.play_pause_btn.setObjectName('playPauseBtn')
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)
        
        next_btn = QPushButton()
        next_btn.setIcon(self.next_icon)
        next_btn.setIconSize(icon_size)
        next_btn.setObjectName('controlBtn')
        next_btn.clicked.connect(self.next_track)
        
        # --- Render white + brown tinted versions for play.svg and pause.svg (hover effect) ---
        try:
            svg_play = APP_DIR / 'icons' / 'play.svg'
            svg_pause = APP_DIR / 'icons' / 'pause.svg'
            icon_px = QSize(30, 30)

            if svg_play.exists():
                self._play_icon_normal = QIcon(str(svg_play))
                self._play_icon_hover = QIcon(str(svg_play))
            else:
                self._play_icon_normal = getattr(self, 'play_icon', QIcon())
                self._play_icon_hover = getattr(self, 'play_icon', QIcon())

            if svg_pause.exists():
                self._pause_icon_normal = QIcon(str(svg_pause))
                self._pause_icon_hover = QIcon(str(svg_pause))
            else:
                self._pause_icon_normal = getattr(self, 'pause_icon', QIcon())
                self._pause_icon_hover = getattr(self, 'pause_icon', QIcon())            

            # Pause icons
            if svg_pause.exists():
                pm_pause_normal = _render_svg_tinted(svg_pause, icon_px, "#FFFFFF")
                pm_pause_hover = _render_svg_tinted(svg_pause, icon_px, "#654321")
                self._pause_icon_normal = QIcon(pm_pause_normal) if (not pm_pause_normal.isNull()) else self.pause_icon
                self._pause_icon_hover = QIcon(pm_pause_hover) if (not pm_pause_hover.isNull()) else self.pause_icon
            else:
                self._pause_icon_normal = getattr(self, 'pause_icon', QIcon())
                self._pause_icon_hover = getattr(self, 'pause_icon', QIcon())

        except Exception:
            # Ensure attributes exist even on error
            self._play_icon_normal = getattr(self, 'play_icon', QIcon())
            self._play_icon_hover = getattr(self, 'play_icon', QIcon())
            self._pause_icon_normal = getattr(self, 'pause_icon', QIcon())
            self._pause_icon_hover = getattr(self, 'pause_icon', QIcon())

        # Set initial icon (show play when nothing playing)
        try:
            if self._is_playing():
                self.play_pause_btn.setIcon(self._pause_icon_normal)
                self._play_pause_shows_play = False
            else:
                self.play_pause_btn.setIcon(self._play_icon_normal)
                self._play_pause_shows_play = True
        except Exception:
            # fallback
            try:
                self.play_pause_btn.setIcon(self.play_icon)
                self._play_pause_shows_play = True
            except Exception:
                self._play_pause_shows_play = True

        # Make the play button report hover events to the main window's eventFilter
        try:
            self.play_pause_btn.installEventFilter(self)
        except Exception:
            pass
        # Repeat
        self.repeat_btn = QPushButton(); self.repeat_btn.setCheckable(True)
        self.repeat_btn.setObjectName('controlBtn'); self.repeat_btn.setToolTip("Repeat current")
        try:
            if hasattr(self, 'repeat_icon') and not self.repeat_icon.isNull():
                self.repeat_btn.setIcon(self.repeat_icon)
                self.repeat_btn.setIconSize(icon_size)
            else:
                self.repeat_btn.setText("🔁")
        except Exception:
            self.repeat_btn.setText("🔁")
        self.repeat_btn.clicked.connect(self._toggle_repeat); 
        # --- Volume icon: prefer icons/volume.svg rendered with QSvgRenderer (hi-dpi aware) ---
        try:
            from PySide6.QtCore import QRectF
            # create label
            self.volume_icon_label = QLabel()
            self.volume_icon_label.setObjectName('volumeIconLabel')
            self.volume_icon_label.setFixedSize(icon_size)  # icon_size defined earlier (QSize(22,22))
            self.volume_icon_label.setToolTip("Volume")
            try:
                self.volume_icon_label.setAccessibleDescription("Volume")
            except Exception:
                pass

            svg_path = APP_DIR / 'icons' / 'volume.svg'
            rendered = False
            try:
                # If QtSvg (QSvgRenderer) is available and the SVG exists, render it into a QPixmap
                if svg_path.exists() and ('QSvgRenderer' in globals()) and (QSvgRenderer is not None):
                    renderer = QSvgRenderer(str(svg_path))
                    # Create pixmap at requested pixel size for crisp rendering
                    pm = QPixmap(icon_size.width(), icon_size.height())
                    pm.fill(Qt.transparent)
                    painter = QPainter(pm)
                    painter.setRenderHint(QPainter.Antialiasing, True)
                    renderer.render(painter, QRectF(0, 0, icon_size.width(), icon_size.height()))
                    painter.end()
                    self.volume_icon_label.setPixmap(pm)
                    rendered = True
            except Exception:
                rendered = False

            # Fallback: use previously loaded QIcon (self.volume_icon) if available
            if not rendered:
                try:
                    if hasattr(self, 'volume_icon') and not self.volume_icon.isNull():
                        self.volume_icon_label.setPixmap(self.volume_icon.pixmap(icon_size))
                        rendered = True
                except Exception:
                    rendered = False

            # Final fallback: emoji
            if not rendered:
                self.volume_icon_label.setText("🔊")
                self.volume_icon_label.setAlignment(Qt.AlignCenter)

            # Optional: click-to-toggle-mute handler (uncomment assignment line below to enable)
            try:
                def _vol_clicked(ev):
                    try:
                        if hasattr(self, 'mpv') and (getattr(self, 'mpv', None) is not None):
                            try:
                                cur = bool(self.mpv.mute)
                                self.mpv.mute = not cur
                            except Exception:
                                pass
                    except Exception:
                        pass
                # To enable click-to-toggle behavior, uncomment the next line:
                self.volume_icon_label.mousePressEvent = _vol_clicked
            except Exception:
                pass

            
        except Exception:
            controls_bar.addWidget(QLabel("🔊"))
        # --- end volume icon block ---
        self.volume_slider = HoverSlider(Qt.Horizontal); self.volume_slider.setObjectName('volumeSlider'); self.volume_slider.setRange(0, 100); self.volume_slider.setValue(80); self.volume_slider.setFixedWidth(120); self.volume_slider.valueChanged.connect(self.set_volume)
        # --- Corrected Centered Control Bar Layout ---
        controls_row = QGridLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)

        # 1. Define the center button group
        center_controls = QHBoxLayout()
        center_controls.setSpacing(12)
        center_controls.addWidget(self.shuffle_btn)
        center_controls.addWidget(prev_btn)
        center_controls.addWidget(self.play_pause_btn)
        center_controls.addWidget(next_btn)
        center_controls.addWidget(self.repeat_btn)
        center_widget = QWidget()
        center_widget.setLayout(center_controls)

        # 2. Define the volume control group
        volume_controls = QHBoxLayout()
        volume_controls.setSpacing(6)
        volume_controls.addWidget(self.volume_icon_label)
        volume_controls.addWidget(self.volume_slider)
        volume_widget = QWidget()
        volume_widget.setLayout(volume_controls)

        # 3. Add both groups to the layout
        # The button group spans all 3 columns and is centered within them.
        controls_row.addWidget(center_widget, 0, 0, 1, 3, alignment=Qt.AlignHCenter)
        # The volume group is placed in the 3rd column (index 2) and aligned to the right.
        controls_row.addWidget(volume_widget, 0, 2, alignment=Qt.AlignRight)

        # Make the outer columns stretchable to push the volume slider to the edge.
        controls_row.setColumnStretch(0, 1)
        controls_row.setColumnStretch(2, 1)

        main_col.addLayout(controls_row)

        self.status = QStatusBar(); self.setStatusBar(self.status)

        # UI timers
        self.badge_timer = QTimer(self); self.badge_timer.timeout.connect(self.update_badge); self.badge_timer.start(5000)
        # Apply Up Next initial visibility from settings
        try:
            _show_up = bool(getattr(self, 'show_up_next', True))
            if hasattr(self, 'up_next_container'):
                self.up_next_container.setVisible(_show_up)
            if _show_up:
                try:
                    collapsed = bool(getattr(self, 'up_next_collapsed', False))
                    self.up_next_header.setChecked(not collapsed)
                    self._toggle_up_next_visible(self.up_next_header.isChecked())
                except Exception:
                    pass
        except Exception:
            pass
            
    def _update_unwatched_btn_visual(self, checked: bool):
        """Swap icon/text and styling so ON vs OFF is obvious — icon + color only, no filled pill or border.
        Also update the themed tooltip text if installed."""
        try:
            # If SVG icons available, swap them
            if getattr(self, '_unwatched_icon_on', None) and getattr(self, '_unwatched_icon_off', None):
                if checked:
                    # ON = eye (show unwatched only) — green tint
                    self.unwatched_btn.setIcon(self._unwatched_icon_on)
                else:
                    # OFF = eye-off — muted tint
                    self.unwatched_btn.setIcon(self._unwatched_icon_off)
                self.unwatched_btn.setText("")  # icon-only
                # Ensure icon is sized for alignment
                try:
                    self.unwatched_btn.setIconSize(QSize(18, 18))
                except Exception:
                    pass
            else:
                # Emoji fallback: ON = 🙈 (filter active), OFF = 👁 (show all)
                if checked:
                    self.unwatched_btn.setText("🙈")
                else:
                    self.unwatched_btn.setText("👁")

            # Simple color-only styling (transparent background, no border)
            if checked:
                # ON -> green tint on icon/text, transparent background
                self.unwatched_btn.setStyleSheet(
                    "background-color: transparent; color: #1DB954; border: none; padding: 0; margin: 0;"
                )
                native_tip = "Unwatched only: ON (click to turn off)"
            else:
                # OFF -> muted grey icon/text, transparent background
                self.unwatched_btn.setStyleSheet(
                    "background-color: transparent; color: #B3B3B3; border: none; padding: 0; margin: 0;"
                )
                native_tip = "Show unwatched items only (OFF)"

            # keep accessible description for assistive tech, hide native tooltip visually
            try:
                self.unwatched_btn.setAccessibleDescription(native_tip)
            except Exception:
                pass
            try:
                self.unwatched_btn.setToolTip("")
            except Exception:
                pass

            # If we installed a themed tooltip widget, update its text too
            try:
                if hasattr(self, '_themed_tooltips'):
                    pair = self._themed_tooltips.get(self.unwatched_btn)
                    if pair and isinstance(pair, tuple):
                        tip_label, _ = pair
                        if tip_label:
                            tip_label.setText(native_tip)
            except Exception:
                pass

        except Exception:
            pass            
    
    def _install_themed_tooltip(self, widget, text: str, duration: int = 3500):
        """Install a small themed tooltip for a single widget (shows on hover).
        Force the light (vinyl/cream) styling so all app tooltips look the same."""
        try:
            # Ensure storage exists
            if not hasattr(self, '_themed_tooltips'):
                self._themed_tooltips = {}

            # If a tooltip already exists for this widget, update and return
            existing = self._themed_tooltips.get(widget)
            if existing:
                try:
                    existing[0].setText(text)
                except Exception:
                    pass
                return

            # Create a tooltip QLabel (one per widget)
            tip = QLabel(text, self)
            tip.setObjectName('customTooltip')
            tip.setWindowFlags(Qt.ToolTip)
            tip.setAttribute(Qt.WA_TransparentForMouseEvents)
            tip.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            tip.setContentsMargins(8, 6, 8, 6)
            tip.hide()

            # FORCE light / vinyl style so all tooltips are cream + dark text (matches your preferred screenshot)
            tip_style = (
                "background-color: #fff6d9; color: #4a2c2a; "
                "border: 1px solid #c2a882; border-radius: 6px; padding: 6px;"
            )
            tip.setStyleSheet(tip_style)

            # Store widget -> (label, duration)
            self._themed_tooltips[widget] = (tip, int(duration))

            # Install event filter to show/hide on enter/leave
            widget.installEventFilter(self)

        except Exception:
            pass    


    def eventFilter(self, obj, event):
        # Handle play/pause hover tint first (swap to brown hover pixmap when mouse over)
        try:
            if hasattr(self, 'play_pause_btn') and (obj is self.play_pause_btn):
                # Only change icon on hover when the button is currently showing the "play" or "pause" glyph.
                if event.type() == QEvent.Enter:
                    try:
                        if getattr(self, '_play_pause_shows_play', False):
                            if getattr(self, '_play_icon_hover', None):
                                self.play_pause_btn.setIcon(self._play_icon_hover)
                        else:
                            if getattr(self, '_pause_icon_hover', None):
                                self.play_pause_btn.setIcon(self._pause_icon_hover)
                    except Exception:
                        pass
                    return False
                elif event.type() == QEvent.Leave:
                    try:
                        if getattr(self, '_play_pause_shows_play', False):
                            if getattr(self, '_play_icon_normal', None):
                                self.play_pause_btn.setIcon(self._play_icon_normal)
                        else:
                            if getattr(self, '_pause_icon_normal', None):
                                self.play_pause_btn.setIcon(self._pause_icon_normal)
                    except Exception:
                        pass
                    return False
        except Exception:
            pass

        # Themed tooltip handling for other widgets (unchanged)
        try:
            if hasattr(self, '_themed_tooltips') and (obj in self._themed_tooltips):
                tip, duration = self._themed_tooltips[obj]
                if event.type() == QEvent.Enter:
                    try:
                        pos = obj.mapToGlobal(obj.rect().bottomLeft())
                        pos.setY(pos.y() + 6)
                        tip.move(pos)
                        tip.show()
                        QTimer.singleShot(duration, lambda: tip.hide())
                    except Exception:
                        tip.show()
                    return False
                elif event.type() == QEvent.Leave or event.type() == QEvent.FocusOut:
                    try:
                        tip.hide()
                    except Exception:
                        pass
                    return False
        except Exception:
            pass

        return super().eventFilter(obj, event)
    
    def _set_track_title(self, text):
        """Set track title with eliding support"""
        self._track_title_full = text or ""
        self._update_track_label_elide()

    def _update_track_label_elide(self):
        """Update track label with proper eliding based on current width"""
        try:
            if not hasattr(self, '_track_title_full'):
                return
            
            metrics = QFontMetrics(self.track_label.font())
            available_width = self.track_label.width() - 20  # margin for safety
            if available_width <= 0:
                available_width = 200  # fallback width
            
            elided_text = metrics.elidedText(self._track_title_full, Qt.ElideRight, available_width)
            self.track_label.setText(elided_text)
        except Exception:
            # Fallback: just set the text directly
            if hasattr(self, '_track_title_full'):
                self.track_label.setText(self._track_title_full)

    def resizeEvent(self, event):
        """Handle window resize to update elided text"""
        super().resizeEvent(event)
        try:
            self._update_track_label_elide()
        except Exception:
            pass

    def _font_serif(self, size, italic=False, bold=False):
        """Create a serif font with proper styling and letter spacing"""
        font = QFont(self._serif_font, size)
        font.setItalic(italic)
        if bold:
            font.setWeight(QFont.Bold)
        font.setStyleStrategy(QFont.PreferAntialias)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        return font

    def _init_fonts(self):
        # Default to system fonts similar to the mock
        self._ui_font = 'Segoe UI'
        self._serif_font = 'Georgia'
        self._jp_serif_font = 'Noto Serif JP'  # Initialize Japanese serif fallback
        try:
            fonts_dir = APP_DIR / 'assets' / 'fonts'
            # print(f"Font loader scanning: {fonts_dir}")
            added_fams = []
            if fonts_dir.exists():
                # Load any TTFs and OTFs present
                for ext in ['*.ttf', '*.otf']:
                    for p in fonts_dir.glob(ext):
                        try:
                            rid = QFontDatabase.addApplicationFont(str(p))
                            if rid != -1:
                                fams_for = QFontDatabase.applicationFontFamilies(rid)
                                for fam in fams_for:
                                    added_fams.append(fam)
                        except Exception:
                            pass

                # --- Noto Sans JP font load ---
                noto_jp_path = fonts_dir / 'NotoSansJP-Regular.otf'
                if noto_jp_path.exists():
                    font_id = QFontDatabase.addApplicationFont(str(noto_jp_path))
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        self._jp_font = families[0]  # Usually "Noto Sans JP"
                    else:
                        self._jp_font = 'Noto Sans JP'
                else:
                    self._jp_font = 'Noto Sans JP'  # fallback to system font if not found

                # --- Noto Serif JP font load ---
                noto_serif_jp_path = fonts_dir / 'NotoSerifJP-Regular.otf'
                if noto_serif_jp_path.exists():
                    font_id = QFontDatabase.addApplicationFont(str(noto_serif_jp_path))
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        self._jp_serif_font = families[0]  # Usually "Noto Serif JP"
                    else:
                        self._jp_serif_font = 'Noto Serif JP'
                else:
                    self._jp_serif_font = 'Noto Serif JP'  # fallback to system font if not found

                # Set application-wide fallback font (Inter, Noto Sans JP, Segoe UI, sans-serif)
                app_font = QFont(f"{self._ui_font}, {self._jp_font}, Segoe UI, sans-serif", 14)
                QApplication.instance().setFont(app_font)

            if added_fams:
                fams = set(QFontDatabase.families())
            # Helper to pick a family by base name, favoring Regular weights and shorter names
            def _pick_family(base: str):
                # exact first
                if base in fams:
                    return base
                # prefer newly added families first
                cands = [f for f in added_fams if base.lower() in f.lower()]
                if not cands:
                    cands = [f for f in fams if base.lower() in f.lower()]
                if cands:
                    cands.sort(key=lambda s: (('regular' not in s.lower()), len(s)))
                    return cands[0]
                return None
            inter = _pick_family('Inter')
            lora = _pick_family('Lora')
            # If not found, bootstrap a verified set of fonts and retry
            if (not inter) or (not lora):
                try:
                    self._bootstrap_fonts()
                except Exception:
                    pass
                fams = set(QFontDatabase.families())
                inter = _pick_family('Inter')
                lora = _pick_family('Lora')
            if inter:
                self._ui_font = inter
            if lora:
                self._serif_font = lora

            # Set up font substitutions for Japanese text
            try:
                QFont.insertSubstitution(self._serif_font, self._jp_serif_font)
                QFont.insertSubstitution(self._ui_font, self._jp_font)
                # print(f"Font substitutions: {self._serif_font} -> {self._jp_serif_font}, {self._ui_font} -> {self._jp_font}")
            except Exception:
                pass

            # print(f"Using UI font: {self._ui_font}, Serif font: {self._serif_font}")
            # No need to set QApplication font again here; already set above!
        except Exception:
            pass

    def _bootstrap_fonts(self):
        try:
            if not HAVE_REQUESTS:
                print("Font bootstrap skipped: requests not available")
                return
            fonts_dir = APP_DIR / 'assets' / 'fonts'
            fonts_dir.mkdir(parents=True, exist_ok=True)
            targets = [
                ("Inter-VariableFont_slnt,wght.ttf", "https://github.com/google/fonts/raw/main/ofl/inter/Inter-VariableFont_slnt,wght.ttf"),
                ("Lora-VariableFont_wght.ttf", "https://github.com/google/fonts/raw/main/ofl/lora/Lora-VariableFont_wght.ttf"),
                ("Lora-Italic-VariableFont_wght.ttf", "https://github.com/google/fonts/raw/main/ofl/lora/Lora-Italic-VariableFont_wght.ttf"),
                ("NotoSerifJP-Regular.otf", "https://github.com/google/fonts/raw/main/ofl/notoserifjp/static/NotoSerifJP-Regular.otf"),
                ("NotoSansJP-Regular.otf", "https://github.com/google/fonts/raw/main/ofl/notosansjp/static/NotoSansJP-Regular.otf"),
            ]
            for fname, url in targets:
                path = fonts_dir / fname
                if not path.exists():
                    print(f"Downloading font: {fname} ...")
                    r = requests.get(url, timeout=20)
                    if r.status_code == 200 and r.content:
                        with open(path, 'wb') as f:
                            f.write(r.content)
                        rid = QFontDatabase.addApplicationFont(str(path))
                        fams_for = QFontDatabase.applicationFontFamilies(rid) if rid != -1 else []
                        print(f"✓ Installed {fname}: {list(fams_for) or 'n/a'}")
                    else:
                        print(f"✗ Failed to download {fname}: HTTP {r.status_code}")
        except Exception as e:
            print(f"Font bootstrap error: {e}")

    def _clear_background_pattern(self):
        try:
            cw = self.centralWidget()
            if cw:
                pal = cw.palette()
                pal.setBrush(cw.backgroundRole(), QBrush())
                cw.setPalette(pal)
                cw.setAutoFillBackground(False)
        except Exception:
            pass

    def _apply_vinyl_background_pattern(self):
        try:
            if 'QSvgRenderer' in globals() and QSvgRenderer is not None:
                svg_path = str(APP_DIR / 'vinyl_pattern.svg')
                renderer = QSvgRenderer(svg_path)
                tile = QPixmap(160, 160)
                tile.fill(Qt.transparent)
                p = QPainter(tile)
                renderer.render(p)
                p.end()
                pal = self.centralWidget().palette()
                pal.setBrush(self.centralWidget().backgroundRole(), QBrush(tile))
                self.centralWidget().setPalette(pal)
                self.centralWidget().setAutoFillBackground(True)
            else:
                # Fallback: clear pattern (no SVG support)
                self._clear_background_pattern()
        except Exception as e:
            print(f"Vinyl bg pattern failed: {e}")

    def _apply_dark_theme(self):
        style = """
        QMainWindow, QDialog { background-color: #121212; color: #B3B3B3; font-family: '{self._ui_font}'; }
        #titleLabel { color: #FFFFFF; font-size: 20px; font-weight: bold; font-family: '{self._serif_font}'; font-style: italic; }
        #settingsBtn { background: transparent; color: #B3B3B3; font-size: 18px; border: none; padding: 2px 6px; min-width: 32px; min-height: 28px; border-radius: 6px; }
        #settingsBtn:hover { background-color: #202020; color: #FFFFFF; }
        #settingsBtn:pressed { background-color: #181818; }
        #scopeChip { background-color: #1a1a1a; color: #B3B3B3; border: 1px solid #2e2e2e; padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-left: 8px; }
        #statsBadge { background-color: #101010; color: #B3B3B3; border: 1px solid #282828; padding: 4px 12px; margin-left: 8px; margin-right: 8px; border-radius: 10px; font-size: 12px; }
        #sidebar { background-color: rgba(24, 24, 24, 0.9); border: 1px solid #282828; border-radius: 8px; padding: 10px; }
        #addBtn { 
                background-color: #1DB954; 
                color: #FFFFFF; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 8px; 
                font-weight: bold; 
                margin-bottom: 8px;
                text-align: left;
                qproperty-text: "  + Add Media";
            }
        #addBtn::menu-indicator {
                image: url(icons/chevron-down-light.svg);
                subcontrol-position: right top;
                subcontrol-origin: padding;
                right: 10px;
                top: 2px;
            }
        #addBtn:hover { background-color: #1ED760; }
        #addBtn:pressed { background-color: #1AA24A; }
        #miniBtn { background: transparent; color: #B3B3B3; border: none; font-size: 16px; }
        #miniBtn:hover { color: #FFFFFF; }
        #miniBtn:pressed { color: #888888; }
        #playlistTree { background-color: transparent; border: none; color: #B3B3B3; font-family: '{self._serif_font}'; alternate-background-color: #181818; }
        #playlistTree::item { min-height: 24px; height: 24px; padding: 3px 8px; font-size: 13px; }
        #playlistTree::item:hover { background-color: #282828; }
        #playlistTree::item:selected { background-color: #282828; color: #1DB954; }
        #videoWidget { background-color: #000000; border-radius: 8px; border: 1px solid #202020; }
        #trackLabel { color: #FFFFFF; font-size: 16px; font-weight: bold; font-family: '{self._serif_font}'; font-style: italic; }
        #controlBtn { background: transparent; color: #B3B3B3; font-size: 20px; border: none; border-radius: 20px; width: 40px; height: 40px; padding: 0px; }
        #controlBtn:hover { background-color: #282828; }
        #controlBtn:pressed { background-color: #202020; padding-top: 1px; padding-left: 1px; }
        #playPauseBtn { background-color: #FFFFFF; color: #000000; font-size: 20px; border: none; border-radius: 25px; width: 50px; height: 50px; padding: 0px; }
        #playPauseBtn:hover { background-color: #f0f0f0; }
        #playPauseBtn:pressed { background-color: #e0e0e0; padding-top: 1px; padding-left: 1px; }
        #volumeSlider::groove:horizontal { height: 4px; background-color: #535353; border-radius: 2px; }
        #volumeSlider::handle:horizontal { width: 12px; height: 12px; background-color: #FFFFFF; border-radius: 6px; margin: -4px 0; }
        #volumeSlider::sub-page:horizontal { background-color: #1DB954; border-radius: 2px; }
        #volumeSlider::add-page:horizontal { background-color: #535353; border-radius: 2px; }
        QSlider::groove:horizontal { height: 4px; background-color: #535353; border-radius: 2px; margin: 0 1px; }
        QSlider::handle:horizontal { width: 12px; height: 12px; background-color: #FFFFFF; border-radius: 6px; margin: -4px 0; }
        QSlider::sub-page:horizontal { background-color: #1DB954; border-radius: 2px; }
        QSlider::add-page:horizontal { background-color: #535353; border-radius: 2px; }
        #silenceIndicator { color: #FF0000; font-size: 18px; margin: 0 8px; padding-bottom: 3px; }
        #upNext::item { min-height: 24px; height: 24px; padding: 3px 8px; font-size: 13px; }
        #upNext::item:hover { background-color: #282828; }
        #upNext::item:selected { background-color: #282828; color: #1DB954; }
        #upNextHeader { background-color: #1a1a1a; color: #B3B3B3; border: 1px solid #2e2e2e; border-radius: 6px; padding: 4px 8px; text-align:left; }
        #upNextHeader:hover { background-color: #202020; color: #FFFFFF; }
        #upNextHeader:pressed { background-color: #1a1a1a; }
        QProgressBar { background-color: #202020; border: 1px solid #2e2e2e; border-radius: 4px; text-align: center; color: #B3B3B3; }
        QProgressBar::chunk { background-color: #1DB954; border-radius: 4px; }
        QStatusBar { color: #B3B3B3; }
        QMenu { background-color: #282828; color: #B3B3B3; border: 1px solid #535353; font-size: 13px; }
        QMenu::item { padding: 6px 12px; }
        QMenu::item:selected { background-color: #404040; color: #1DB954; }
        QToolTip { background-color: #202020; color: #B3B3B3; border: 1px solid #2e2e2e; padding: 4px 8px; border-radius: 6px; }
        QScrollBar:vertical { background: transparent; width: 12px; margin: 0px; }
        QScrollBar::handle:vertical { background: #3a3a3a; min-height: 24px; border-radius: 6px; }
        QScrollBar::handle:vertical:hover { background: #4a4a4a; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal { background: transparent; height: 12px; margin: 0px; }
        QScrollBar::handle:horizontal { background: #3a3a3a; min-width: 24px; border-radius: 6px; }
        QScrollBar::handle:horizontal:hover { background: #4a4a4a; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        QTabWidget::pane { border: 1px solid #2e2e2e; border-radius: 6px; }
        QTabBar::tab { background-color: #1a1a1a; color: #B3B3B3; padding: 6px 10px; border: 1px solid #2e2e2e; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
        QTabBar::tab:selected { background-color: #202020; color: #FFFFFF; }
        QTabBar::tab:hover { background-color: #202020; }
        #upNext { font-family: '{self._serif_font}'; alternate-background-color: #181818; }
        #timeLabel, #durLabel { font-family: '{self._ui_font}'; font-size: 13px; color: #B3B3B3; }
        QLineEdit#searchBar { background-color: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 6px; padding: 4px 8px; margin: 8px 0; color: #e0e0e0; selection-background-color: #2e7d32; }
        #emptyStateIcon { font-size: 48px; color: #404040; padding-bottom: 10px; }
        #emptyStateHeading { font-family: '{self._serif_font}'; color: #FFFFFF; font-size: 15px; font-weight: bold; }
        #emptyStateSubheading { color: #B3B3B3; font-size: 13px; }
        /* Focus styling: replace default noisy focus rectangle with a subtle themed ring.
           Keeps the button keyboard-focusable (accessible) but removes the blue dotted box. */
        QPushButton:focus { outline: none; }
        /* Subtle, themed focus ring for the main play/pause control */
        #playPauseBtn:focus {
            border: 2px solid rgba(29,185,84,0.18); /* soft green */
            border-radius: 25px;
            padding: 0px; /* ensure size doesn't shift */
        }
        """
        style = style.replace("{self._ui_font}", self._ui_font).replace("{self._serif_font}", self._serif_font)
        self.setStyleSheet(style)
        try:
            eff = QGraphicsDropShadowEffect(self.video_frame)
            eff.setBlurRadius(20)
            eff.setOffset(0, 0)
            eff.setColor(QColor(0, 0, 0, 160))
            self.video_frame.setGraphicsEffect(eff)
        except Exception:
            pass
        self._clear_background_pattern()
        try:
            bg = self.centralWidget()
            if bg:
                bg.setStyleSheet("")
                bg.setAutoFillBackground(False)
        except Exception:
            pass

    def _apply_vinyl_theme(self):
        style = """
        QMainWindow, QDialog { background-color: #f3ead3; color: #4a2c2a; font-family: '{self._ui_font}'; }
        #titleLabel { color: #4a2c2a; font-size: 20px; font-weight: bold; font-style: italic; font-family: '{self._serif_font}'; }
        #settingsBtn { background: transparent; color: #654321; font-size: 18px; border: none; padding: 2px 6px; min-width: 32px; min-height: 28px; border-radius: 6px; }
        #settingsBtn:hover { background-color: rgba(0,0,0,0.04); color: #4a2c2a; }
        #settingsBtn:pressed { background-color: rgba(0,0,0,0.08); }
        #scopeChip { background-color: rgba(250,243,224,0.9); color: #4a2c2a; border: 1px solid #c2a882; padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-left: 8px; }
        #statsBadge { background-color: transparent; color: #654321; border: 1px solid #c2a882; padding: 4px 12px; margin-left: 8px; margin-right: 8px; border-radius: 10px; font-size: 12px; }
        #sidebar { background-color: rgba(250, 243, 224, 0.85); border: 1px solid rgba(194, 168, 130, 0.5); border-radius: 8px; padding: 12px; }
        #addBtn { 
                background-color: #e76f51; 
                color: #f3ead3; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 8px; 
                font-weight: bold; 
                margin-bottom: 8px; 
                text-align: left;
                qproperty-text: "  + Add Media";
            }
        #addBtn::menu-indicator {
                image: url(icons/chevron-down-dark.svg);
                subcontrol-position: right top;
                subcontrol-origin: padding;
                right: 10px;
                top: 2px;
            }
        #addBtn:hover { background-color: #d86a4a; }
        #addBtn:pressed { background-color: #d1603f; }
        #miniBtn { background: transparent; color: #654321; border: none; font-size: 16px; }
        #miniBtn:hover { color: #4a2c2a; }
        #miniBtn:pressed { color: #654321; }
        #playlistTree { background-color: transparent; border: none; color: #4a2c2a; font-family: '{self._serif_font}'; alternate-background-color: #f0e7cf; }
        #playlistTree::item {
            min-height: 28px;
            height: 28px;
            padding: 5px 12px;
            font-size: 14px;
            color: #3b2d1a;    /* deeper brown for better contrast */
            border-bottom: 1px solid #e5d5b8; /* subtle divider */
        }

        #playlistTree::item:selected {
            background-color: #e76f51;
            color: #fff6d9;
            font-weight: bold;
        }
        #playlistTree::item:hover { background-color: rgba(239, 227, 200, 0.7); }
        #playlistTree::item:selected { background-color: #e76f51; color: #f3ead3; }
        #videoWidget { background-color: #000; border-radius: 8px; border: 10px solid #faf3e0; }
        #trackLabel { color: #4a2c2a; font-size: 16px; font-weight: bold; font-style: italic; font-family: '{self._serif_font}'; }
        #playPauseBtn { background-color: #e76f51; color: #f3ead3; font-size: 26px; border: none; border-radius: 30px; width: 60px; height: 60px; padding: 0px; }
        #playPauseBtn:hover {
        background-color: #d86a4a;
    }
        #playPauseBtn:pressed { background-color: #d1603f; padding-top: 1px; padding-left: 1px; }
        #controlBtn { background: transparent; color: #654321; font-size: 20px; border: none; border-radius: 20px; width: 40px; height: 40px; padding: 0px; }
        #controlBtn:hover { background-color: rgba(0,0,0,0.04); color: #4a2c2a; }
        #controlBtn:pressed { background-color: rgba(0,0,0,0.08); padding-top: 1px; padding-left: 1px; }
        QSlider::groove:horizontal { height: 6px; background-color: #c2a882; border-radius: 3px; }
        QSlider::handle:horizontal { 
            width: 18px; 
            height: 18px; 
            background-color: #4a2c2a; 
            border-radius: 9px; 
            margin: -6px 0; 
        }
        QSlider::sub-page:horizontal { background-color: #e76f51; border-radius: 3px; }
        #timeLabel, #durLabel { font-family: '{self._ui_font}'; font-size: 13px; color: #654321; }
        #silenceIndicator { color: #b00000; font-size: 18px; margin: 0 8px; padding-bottom: 3px; }
        #upNext::item { min-height: 24px; height: 24px; padding: 3px 8px; font-size: 13px; }
        #upNext::item:hover { background-color: rgba(239, 227, 200, 0.7); }
        #upNext::item:selected { background-color: #e76f51; color: #f3ead3; }
        #upNextHeader { background-color: rgba(250,243,224,0.9); color: #4a2c2a; border: 1px solid #c2a882; border-radius: 6px; padding: 4px 8px; text-align:left; }
        #upNextHeader:hover { background-color: #f0e7cf; }
        #upNextHeader:pressed { background-color: #e9e0c8; }
        QProgressBar { background-color: #f0e7cf; border: 1px solid #c2a882; border-radius: 4px; text-align: center; color: #4a2c2a; }
        QProgressBar::chunk { background-color: #e76f51; border-radius: 4px; }
        QStatusBar { color: #4a2c2a; }
        QMenu { background-color: #faf3e0; color: #4a2c2a; border: 1px solid #c2a882; font-size: 13px; }
        QMenu::item { padding: 6px 12px; }
        QMenu::item:selected { background-color: #e76f51; color: #f3ead3; }
        QToolTip { background-color: #fff6d9; color: #4a2c2a; border: 1px solid #c2a882; padding: 4px 8px; border-radius: 6px; }
        QScrollBar:vertical { background: transparent; width: 12px; margin: 0px; }
        QScrollBar::handle:vertical { background: #c2a882; min-height: 24px; border-radius: 6px; }
        QScrollBar::handle:vertical:hover { background: #b6916d; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal { background: transparent; height: 12px; margin: 0px; }
        QScrollBar::handle:horizontal { background: #c2a882; min-width: 24px; border-radius: 6px; }
        QScrollBar::handle:horizontal:hover { background: #b6916d; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        QTabWidget::pane { border: 1px solid #c2a882; border-radius: 6px; }
        QTabBar::tab { background-color: rgba(250,243,224,0.9); color: #4a2c2a; padding: 6px 10px; border: 1px solid #c2a882; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
        QTabBar::tab:selected { background-color: #f0e7cf; color: #4a2c2a; }
        QTabBar::tab:hover { background-color: #f0e7cf; }
        #upNext { font-family: '{self._serif_font}'; alternate-background-color: #f0e7cf; }
        #timeLabel, #durLabel { font-family: '{self._ui_font}'; font-size: 13px; color: #654321; }
        QLineEdit#searchBar { background-color: #f0e7cf; border: 1px solid #c2a882; border-radius: 6px; padding: 4px 8px; margin: 8px 0; color: #4a2c2a; selection-background-color: #e76f51; }
        #emptyStateIcon { font-size: 48px; color: #c2a882; padding-bottom: 10px; }
        #emptyStateHeading { font-family: '{self._serif_font}'; color: #4a2c2a; font-size: 15px; font-weight: bold; }
        #emptyStateSubheading { color: #654321; font-size: 13px; }
        #addMediaBtn {
        background-color: #e76f51;
        color: #f3ead3;
        border: none;
        border-radius: 8px;
        padding: 0 18px;
        font-weight: bold;
        font-size: 1.1em;
        text-align: left;
        font-family: 'Inter', 'Segoe UI', sans-serif;
    }
    #addMediaBtn:hover {
        background-color: #d86a4a;
    }
    #addMediaBtn:pressed {
        background-color: #d1603f;
        opacity: 0.8;
    }
    #addMediaBtn::menu-indicator {
    image: none;
    width: 0;
    height: 0;
    }
    /* Focus styling: keep keyboard-accessibility but hide default outline */
    QPushButton:focus { outline: none; }
    /* Themed focus ring for play/pause in vinyl theme (soft warm accent) */
    #playPauseBtn:focus {
        border: 2px solid rgba(231,111,81,0.18); /* soft e76f51 tint */
        border-radius: 30px;
        padding: 0px;
    }    
    QHBoxLayout#top {
    border-bottom: 1.5px solid #e5d5b8;
    padding-bottom: 6px;
    margin-bottom: 8px;
    }
    #playlistTree::item:selected, #playlistTree::item:focus {
    background-color: #e76f51;
    color: #fff6d9;
    font-weight: bold;
    }
    line = QLabel()
    line.setFixedHeight(2)
    line.setStyleSheet("background-color: #e5d5b8; margin-bottom: 8px;")
    root.addWidget(line)
    #controlBtn, #playPauseBtn {
    }
    #controlBtn:hover, #playPauseBtn:hover {
    }
    """
        style = style.replace("{self._ui_font}", self._ui_font).replace("{self._serif_font}", self._serif_font)
        self.setStyleSheet(style)
        try:
            eff = QGraphicsDropShadowEffect(self.video_frame)
            eff.setBlurRadius(25)
            eff.setOffset(0, 0)
            eff.setColor(QColor(0, 0, 0, 110))
            self.video_frame.setGraphicsEffect(eff)
        except Exception:
            pass
        # Apply tiled vinyl background on central widget and hide scope chip to match iconic mock
        try:
            bg = self.centralWidget()
            if bg:
                path = str(APP_DIR / 'vinyl_pattern.svg').replace('\\','/')
                bg.setStyleSheet(f"#bgRoot {{ background-color: #f3ead3; border-image: url('{path}') 0 0 0 0 repeat repeat; }}")
                bg.setAutoFillBackground(True)
        except Exception:
            pass
        try:
            if hasattr(self, 'scope_label'):
                self.scope_label.setVisible(False)
        except Exception:
            pass

    def toggle_theme(self):
        self.theme = 'vinyl' if getattr(self, 'theme', 'dark') != 'vinyl' else 'dark'
        if self.theme == 'vinyl':
            self._apply_vinyl_theme()
        else:
            self._apply_dark_theme()
        try:
            if hasattr(self, 'theme_btn') and self.theme_btn:
                self.theme_btn.setToolTip(f"Toggle Theme ({self.theme.capitalize()})")
        except Exception:
            pass
        self._save_settings()

    # mpv
    def _init_mpv(self):
        try:
            self.mpv = MPV(
                wid=str(int(self.video_frame.winId())),
                ytdl=True,
                hwdec='no',
                osc=False
            )
            # Defaults optimized for fast start
            self.mpv['ytdl-format'] = 'best[height<=720]/bv*[height<=720]+ba/best'
            self.mpv['prefetch-playlist'] = 'yes'
            self.mpv['cache'] = 'yes'
            self.mpv['cache-secs'] = '25'
            self.mpv['demuxer-readahead-secs'] = '10'
            self.mpv['user-agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
            self.mpv['hr-seek'] = 'yes'
            self.mpv['gapless-audio'] = 'yes'

            @self.mpv.property_observer('eof-reached')
            def _eof(_name, value):
                if value:
                    if self.repeat_mode and 0 <= self.current_index < len(self.playlist):
                        self.play_current()
                    else:
                        self.next_track()

            @self.mpv.property_observer('duration')
            def _dur(_name, value):
                try:
                    dur = float(value or 0)
                    dur_ms = int(max(0, dur) * 1000)
                    if dur_ms > 0:
                        self.progress.setRange(0, dur_ms)
                        self.dur_label.setText(format_time(dur_ms))
                except Exception:
                    pass

            @self.mpv.property_observer('time-pos')
            def _time(_name, value):
                try:
                    pos = float(value or 0.0)
                    pos_ms = int(max(0.0, pos) * 1000)
                    self._last_play_pos_ms = pos_ms
                    if not self._user_scrubbing:
                        self.progress.setValue(pos_ms)
                        self.time_label.setText(format_time(pos_ms))
                except Exception:
                    pass

            @self.mpv.property_observer('file-loaded')
            def _loaded(_name, value):
                try:
                    if value:
                        self._maybe_reapply_resume('file-loaded')
                except Exception:
                    pass

            self.pos_timer = QTimer(self); self.pos_timer.timeout.connect(self._update_position_tick); self.pos_timer.start(500)
        except Exception as e:
            QMessageBox.critical(self, "mpv error", f"Failed to initialize mpv.\n{e}\n\nEnsure mpv-2.dll/libmpv is on PATH or MPV_DLL_PATH is set.")
            raise

    # Monitors
    def _init_monitors(self):
        # System-wide silence detection
        self.audio_monitor = SystemAudioMonitor(
            silence_duration_s=self.silence_duration_s,
            silence_threshold=self.silence_threshold,
            resume_threshold=getattr(self, 'resume_threshold', self.silence_threshold * 1.5),
            monitor_system_output=self.monitor_system_output,
            device_id=self.monitor_device_id
        )
        self.audio_monitor.silenceDetected.connect(self.on_silence_detected)
        self.audio_monitor.audioStateChanged.connect(self._update_silence_indicator)
        self.audio_monitor.start()
        # AFK monitor
        self.afk_monitor = AFKMonitor(self.afk_timeout_minutes)
        self.afk_monitor.userIsAFK.connect(self.on_user_afk)
        self.afk_monitor.start()

    def _update_silence_indicator(self, is_silent: bool):
        # Track the last system-wide silence state from the audio monitor
        self._last_system_is_silent = bool(is_silent)
        # Hide the icon if our own player is currently outputting audio
        self.silence_indicator.setVisible(bool(is_silent and (not self._is_playing())))

    # Tray
    def _init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("⚠ System tray not available")
            self.tray_icon = None
            return
        icon = self.play_icon
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Silence Suzuka Player")
        tray_menu = QMenu()
        self.tray_play_pause = tray_menu.addAction("Play")
        self.tray_play_pause.triggered.connect(self.toggle_play_pause)
        tray_menu.addAction("Next").triggered.connect(self.next_track)
        tray_menu.addAction("Previous").triggered.connect(self.previous_track)
        tray_menu.addSeparator()
        tray_menu.addAction("Show Player").triggered.connect(self._show_player)
        tray_menu.addAction("Quit").triggered.connect(QApplication.instance().quit)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self._show_player()

    def _show_player(self):
        self.showNormal(); self.activateWindow(); self.raise_()

    def closeEvent(self, e):
        # Gracefully stop monitors/threads and persist settings
        try:
            if getattr(self, 'audio_monitor', None):
                self.audio_monitor.stop()
                try:
                    self.audio_monitor.wait(2000)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if getattr(self, 'afk_monitor', None):
                self.afk_monitor.stop()
                try:
                    self.afk_monitor.wait(2000)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._save_settings()
        except Exception:
            pass
        super().closeEvent(e)

    def _update_tray(self):
        if not getattr(self, 'tray_icon', None):
            return
        if self._is_playing():
            self.tray_play_pause.setText("Pause"); self.tray_icon.setIcon(self.pause_icon)
        else:
            self.tray_play_pause.setText("Play"); self.tray_icon.setIcon(self.play_icon)
        if 0 <= self.current_index < len(self.playlist):
            self.tray_icon.setToolTip(f"Silence Suzuka Player\nNow Playing: {self.playlist[self.current_index].get('title','Unknown')}")
        else:
            self.tray_icon.setToolTip("Silence Suzuka Player")

    # Persistence
    def _load_files(self):
        # Settings
        if CFG_SETTINGS.exists():
            try:
                s = json.load(open(CFG_SETTINGS, 'r', encoding='utf-8'))
                self.auto_play_enabled = bool(s.get('auto_play_enabled', self.auto_play_enabled))
                self.afk_timeout_minutes = int(s.get('afk_timeout_minutes', self.afk_timeout_minutes))
                self.silence_duration_s = float(s.get('silence_duration_s', self.silence_duration_s))
                self.show_thumbnails = bool(s.get('show_thumbnails', self.show_thumbnails))
                self.volume_slider.setValue(int(s.get('volume', self.volume_slider.value())))
                self.theme = s.get('theme', self.theme)
                self.shuffle_mode = bool(s.get('shuffle_mode', self.shuffle_mode))
                self.repeat_mode = bool(s.get('repeat_mode', self.repeat_mode))
                self.grouped_view = bool(s.get('grouped_view', getattr(self, 'grouped_view', False)))
                self.monitor_system_output = bool(s.get('monitor_system_output', self.monitor_system_output))
                self.silence_threshold = float(s.get('silence_threshold', self.silence_threshold))
                self.resume_threshold = float(s.get('resume_threshold', self.resume_threshold))
                self.monitor_device_id = int(s.get('monitor_device_id', self.monitor_device_id))
                self.completed_percent = int(s.get('completed_percent', self.completed_percent))
                self.skip_completed = bool(s.get('skip_completed', self.skip_completed))
                self.unwatched_only = bool(s.get('unwatched_only', self.unwatched_only))
                self.show_up_next = bool(s.get('show_up_next', self.show_up_next))
                self.up_next_collapsed = bool(s.get('up_next_collapsed', self.up_next_collapsed))
                self.playback_model = s.get('playback_model', self.playback_model)
                self.log_level = s.get('log_level', self.log_level)
                # Update logging level immediately
                try:
                    logging.getLogger().setLevel(getattr(logging, self.log_level.upper(), logging.INFO))
                    logger.info(f"Logging level set to {self.log_level}")
                except Exception:
                    pass
                # Restore scope if available
                try:
                    sk = s.get('scope_kind'); skey = s.get('scope_key')
                    if sk and (skey is not None):
                        self.play_scope = (sk, skey)
                except Exception:
                    pass
                # Apply theme
                if self.theme == 'vinyl':
                    self._apply_vinyl_theme()
                else:
                    self._apply_dark_theme()
                # Restore window state
                try:
                    win = s.get('window') or {}
                    if isinstance(win, dict):
                        x = win.get('x'); y = win.get('y'); w = win.get('w'); h = win.get('h')
                        if all(v is not None for v in (x, y, w, h)):
                            self.setGeometry(int(x), int(y), int(w), int(h))
                        if win.get('maximized'):
                            self.showMaximized()
                except Exception:
                    pass
            except Exception as e:
                print(f"Settings load error: {e}")
    # ...rest of your function unchanged...
        # Front page auto-play checkbox removed; use Settings dialog
        # Apply persisted UI toggle states
        if hasattr(self, 'shuffle_btn'):
            self.shuffle_btn.setChecked(self.shuffle_mode)
        if hasattr(self, 'repeat_btn'):
            self.repeat_btn.setChecked(self.repeat_mode)
        # Ensure group toggle reflects current playback model visibility
        try:
            self._update_group_toggle_visibility()
        except Exception:
            pass

        # listening stats
        if CFG_STATS.exists():
            try:
                self.listening_stats = json.load(open(CFG_STATS, 'r', encoding='utf-8'))
            except Exception:
                self.listening_stats = {'daily': {}, 'overall': 0}
        else:
            self.listening_stats = {'daily': {}, 'overall': 0}

        # current playlist
        if CFG_CURRENT.exists():
            try:
                data = json.load(open(CFG_CURRENT, 'r', encoding='utf-8'))
                self.playlist = data.get('current_playlist', [])
            except Exception:
                self.playlist = []
        # positions
        if CFG_POS.exists():
            try:
                with open(CFG_POS, 'r', encoding='utf-8') as f:
                    self.playback_positions = json.load(f)
            except Exception as e:
                print(f"Resume positions load error: {e}")
                self.playback_positions = {}
        # saved playlists
        if CFG_PLAYLISTS.exists():
            try:
                self.saved_playlists = json.load(open(CFG_PLAYLISTS, 'r', encoding='utf-8'))
            except Exception:
                self.saved_playlists = {}
        # completed URLs
        if CFG_COMPLETED.exists():
            try:
                data = json.load(open(CFG_COMPLETED, 'r', encoding='utf-8'))
                if isinstance(data, list):
                    self.completed_urls = set(self._canonical_url_key(u) for u in data if u)
                elif isinstance(data, dict):
                    self.completed_urls = set(self._canonical_url_key(k) for k, v in data.items() if v and k)
            except Exception:
                self.completed_urls = set()
        self._refresh_playlist_widget()
        try:
            self._update_scope_label()
        except Exception:
            pass
        # Ensure Up Next visibility matches loaded settings on startup
        try:
            if hasattr(self, 'up_next_container'):
                self.up_next_container.setVisible(bool(getattr(self, 'show_up_next', True)))
            if hasattr(self, 'up_next_header'):
                self.up_next_header.setChecked(not bool(getattr(self, 'up_next_collapsed', False)))
                self._toggle_up_next_visible(self.up_next_header.isChecked())
        except Exception:
            pass

    def _save_settings(self):
        s = {
            'auto_play_enabled': self.auto_play_enabled,
            'afk_timeout_minutes': self.afk_timeout_minutes,
            'silence_duration_s': self.silence_duration_s,
            'show_thumbnails': self.show_thumbnails,
            'volume': self.volume_slider.value(),
            'theme': self.theme,
            'shuffle_mode': self.shuffle_mode,
            'repeat_mode': self.repeat_mode,
            'grouped_view': getattr(self, 'grouped_view', False),
            'monitor_system_output': bool(getattr(self, 'monitor_system_output', True)),
            'silence_threshold': float(getattr(self, 'silence_threshold', 0.03)),
            'resume_threshold': float(getattr(self, 'resume_threshold', max(0.03, getattr(self, 'silence_threshold', 0.03) * 1.5))),
            'monitor_device_id': int(getattr(self, 'monitor_device_id', 46)),
            'completed_percent': int(getattr(self, 'completed_percent', 95)),
            'skip_completed': bool(getattr(self, 'skip_completed', False)),
            'unwatched_only': bool(getattr(self, 'unwatched_only', False)),
            'show_up_next': bool(getattr(self, 'show_up_next', True)),
            'up_next_collapsed': bool(getattr(self, 'up_next_collapsed', False) if not hasattr(self, 'up_next_header') else (not self.up_next_header.isChecked())),
            'playback_model': getattr(self, 'playback_model', 'scoped'),
            'scope_kind': (getattr(self, 'play_scope', None)[0] if isinstance(getattr(self, 'play_scope', None), tuple) else None),
            'scope_key': (getattr(self, 'play_scope', None)[1] if isinstance(getattr(self, 'play_scope', None), tuple) else None),
            'log_level': getattr(self, 'log_level', 'INFO'),
            'window': {
                'x': int(self.geometry().x()),
                'y': int(self.geometry().y()),
                'w': int(self.geometry().width()),
                'h': int(self.geometry().height()),
                'maximized': bool(self.isMaximized())
            }
        }
        try:
            json.dump(s, open(CFG_SETTINGS, 'w', encoding='utf-8'))
        except Exception:
            pass

    def _save_current_playlist(self):
        try:
            json.dump({'current_playlist': self.playlist}, open(CFG_CURRENT, 'w', encoding='utf-8'))
        except Exception:
            pass

    def _save_positions(self):
        try:
            with open(CFG_POS, 'w', encoding='utf-8') as f:
                json.dump(self.playback_positions, f)
        except Exception as e:
            print(f"Resume positions save error: {e}")

    def _save_playlists_file(self):
        try:
            json.dump(self.saved_playlists, open(CFG_PLAYLISTS, 'w', encoding='utf-8'))
        except Exception:
            pass

    def _save_completed(self):
        try:
            json.dump(sorted(list(self.completed_urls)), open(CFG_COMPLETED, 'w', encoding='utf-8'))
        except Exception:
            pass

    # UI data binding
    def _refresh_playlist_widget(self):
        self.playlist_tree.clear()
        _hdr = "Library" if getattr(self, 'playback_model', 'scoped') == 'scoped' else "Current Playlist"
        root = QTreeWidgetItem(self.playlist_tree, [f"{_hdr} ({len(self.playlist)})"])
        root.setExpanded(True)
        # Group by playlist umbrella if any items have 'playlist'
        has_playlist_groups = any(isinstance(it, dict) and it.get('playlist') for it in self.playlist)
        if has_playlist_groups:
            group_map = {}
            for idx, it in enumerate(self.playlist):
                key = it.get('playlist_key') or it.get('playlist')
                if key:
                    g = group_map.setdefault(key, {'title': it.get('playlist') or str(key), 'items': []})
                    g['items'].append((idx, it))
                else:
                    g = group_map.setdefault('', {'title': '', 'items': []})
                    g['items'].append((idx, it))
            # Render playlist groups first (excluding empty key), then ungrouped
            for key, g in [(k, v) for k, v in group_map.items() if k]:
                ptitle = g.get('title') or str(key)
                arr = g.get('items') or []
                gnode = QTreeWidgetItem(root, [f"📃 {ptitle} ({len(arr)})"])
                try:
                    gnode.setFont(0, self._font_serif(14, italic=True, bold=True))
                except Exception:
                    pass
                norm_key = key if key else (g.get('title') or ptitle)
                gnode.setData(0, Qt.UserRole, ('group', norm_key))
                try:
                    gnode.setData(0, Qt.UserRole + 1, norm_key)
                except Exception:
                    pass
                gnode.setExpanded(False)
                for idx, it in arr:
                    icon = playlist_icon_for_type(it.get('type'))
                    node = QTreeWidgetItem([it.get('title', 'Unknown')])
                    if isinstance(icon, QIcon):
                        node.setIcon(0, icon)  # Show the SVG icon (YouTube)
                    else:
                        node.setText(0, f"{icon} {it.get('title', 'Unknown')}")  # Show emoji for other types
                    try:
                        node.setFont(0, self._font_serif(14, italic=True, bold=True))
                    except Exception:
                        pass
                    node.setData(0, Qt.UserRole, ('current', idx, it))
                    gnode.addChild(node)
            if '' in group_map:
                for idx, it in group_map['']['items']:
                    icon = playlist_icon_for_type(it.get('type'))
                    node = QTreeWidgetItem([it.get('title', 'Unknown')])
                    if isinstance(icon, QIcon):
                        node.setIcon(0, icon)  # Show the SVG icon (YouTube)
                    else:
                        node.setText(0, f"{icon} {it.get('title', 'Unknown')}")  # Show emoji for other types
                    try:
                        node.setFont(0, self._font_serif(14, italic=True, bold=True))
                    except Exception:
                        pass
                    node.setData(0, Qt.UserRole, ('current', idx, it))
                    root.addChild(node)
        else:
            # Fallback to previous grouping behavior
            if not getattr(self, 'grouped_view', False):
                for idx, it in enumerate(self.playlist):
                    icon = playlist_icon_for_type(it.get('type'))
                    node = QTreeWidgetItem([it.get('title', 'Unknown')])
                    if isinstance(icon, QIcon):
                        node.setIcon(0, icon)  # Show the SVG icon (YouTube)
                    else:
                        node.setText(0, f"{icon} {it.get('title', 'Unknown')}")  # Show emoji for other types
                    try:
                        node.setFont(0, self._font_serif(14, italic=True, bold=True))
                    except Exception:
                        pass
                    node.setData(0, Qt.UserRole, ('current', idx, it))
                    root.addChild(node)
            else:
                groups = {'youtube': [], 'bilibili': [], 'local': []}
                for idx, it in enumerate(self.playlist):
                    t = it.get('type', 'local')
                    if t not in groups: t = 'local'
                    groups[t].append((idx, it))
                names = {'youtube': '🎬 YouTube', 'bilibili': '📺 Bilibili', 'local': '📁 Local'}
                for g, arr in groups.items():
                    if not arr: continue
                    gnode = QTreeWidgetItem(root, [f"{names[g]} ({len(arr)})"])
                    try:
                        gnode.setFont(0, self._font_serif(14, italic=True, bold=True))
                    except Exception:
                        pass
                    gnode.setData(0, Qt.UserRole, ('group', g))
                    try:
                        gnode.setData(0, Qt.UserRole + 1, g)
                    except Exception:
                        pass
                    for idx, it in arr:
                        icon = playlist_icon_for_type(it.get('type'))
                        node = QTreeWidgetItem([it.get('title', 'Unknown')])
                        if isinstance(icon, QIcon):
                            node.setIcon(0, icon)  # Show the SVG icon (YouTube)
                        else:
                            node.setText(0, f"{icon} {it.get('title', 'Unknown')}")  # Show emoji for other types
                        try:
                            node.setFont(0, self._font_serif(14, italic=True, bold=True))
                        except Exception:
                            pass
                        node.setData(0, Qt.UserRole, ('current', idx, it))
                        gnode.addChild(node)
        if not self.playlist:
            self.playlist_stack.setCurrentIndex(1)  # Show empty state
        else:
            self.playlist_stack.setCurrentIndex(0)  # Show playlist  

    def _display_text(self, item):
        icon = "🔴" if item.get('type') == 'youtube' else "🐟" if item.get('type') == 'bilibili' else "🎬"
        return f"{icon} {item.get('title','Unknown')}"

    def _apply_menu_theme(self, menu: QMenu):
        try:
            try:
                menu.setFont(QFont(self._ui_font))
            except Exception:
                pass
            if getattr(self, 'theme', 'dark') == 'vinyl':
                menu.setStyleSheet(
                    "QMenu { background-color: #faf3e0; color: #4a2c2a; border: 1px solid #c2a882; } "
                    "QMenu::item { padding: 6px 12px; } "
                    "QMenu::item:selected { background-color: #e76f51; color: #f3ead3; }"
                )
            else:
                menu.setStyleSheet(
                    "QMenu { background-color: #282828; color: #B3B3B3; border: 1px solid #535353; } "
                    "QMenu::item { padding: 6px 12px; } "
                    "QMenu::item:selected { background-color: #404040; color: #1DB954; }"
                )
        except Exception:
            pass

    def _is_completed_url(self, url):
        try:
            if not url:
                return False
            key = self._canonical_url_key(url)
            return (key in self.completed_urls) or (url in self.completed_urls)
        except Exception:
            return False

    def _apply_filters_to_tree(self, *_args):
        try:
            root = self.playlist_tree.topLevelItem(0)
            if not root:
                return
            text = (self.search_bar.text() if hasattr(self, 'search_bar') else '') or ''
            text = text.strip().lower()
            uw = bool(getattr(self, 'unwatched_only', False))
            def apply(node):
                data = node.data(0, Qt.UserRole)
                if isinstance(data, tuple) and data[0] == 'current':
                    idx, it = data[1], data[2]
                    show = True
                    if text:
                        try:
                            s = (it.get('title','') + ' ' + it.get('url','')).lower()
                            show = (text in s)
                        except Exception:
                            show = False
                    if show and uw:
                        show = not self._is_completed_url(it.get('url'))
                    node.setHidden(not show)
                    return show
                # group or root
                any_visible = False
                for i in range(node.childCount()):
                    if apply(node.child(i)):
                        any_visible = True
                # hide empty groups
                if isinstance(data, tuple) and data[0] == 'group':
                    node.setHidden(not any_visible)
                return any_visible
            apply(root)
        except Exception:
            pass

    def _toggle_unwatched_only(self, checked):
        try:
            self.unwatched_only = bool(checked)
            self._save_settings()
            self._apply_filters_to_tree()
            self._update_up_next()
        except Exception:
            pass

    def _toggle_up_next_visible(self, show: bool):
        try:
            if hasattr(self, 'up_next'):
                self.up_next.setVisible(bool(show))
            # Also rotate the header caret
            if hasattr(self, 'up_next_header'):
                self.up_next_header.setText(("▼ Up Next" if show else "▶ Up Next"))
        except Exception:
            pass

    def _update_up_next(self):
        try:
            if not hasattr(self, 'up_next'):
                return
            # Respect the settings toggle
            if not bool(getattr(self, 'show_up_next', True)):
                if hasattr(self, 'up_next_container'):
                    self.up_next_container.setVisible(False)
                return
            else:
                if hasattr(self, 'up_next_container'):
                    self.up_next_container.setVisible(True)
            self.up_next.clear()
            indices = self._scope_indices()
            if not indices:
                return
            # build upcoming list after current_index within scope
            try:
                curpos = indices.index(self.current_index) if self.current_index in indices else -1
            except Exception:
                curpos = -1
            upcoming = []
            if curpos >= 0:
                upcoming = indices[curpos+1:curpos+6]
            else:
                upcoming = indices[:5]
            # Apply Unwatched-only view filter to up next if enabled
            if getattr(self, 'unwatched_only', False):
                upcoming = [i for i in upcoming if not self._is_completed_url(self.playlist[i].get('url'))]
            for i in upcoming:
                if 0 <= i < len(self.playlist):
                    it = self.playlist[i]
                    text = self._display_text(it)
                    node = QTreeWidgetItem([text])
                    node.setData(0, Qt.UserRole, ('next', i))
                    self.up_next.addTopLevelItem(node)
        except Exception:
            pass

    def _on_up_next_double_clicked(self, item, column):
        try:
            data = item.data(0, Qt.UserRole)
            if isinstance(data, tuple) and data[0] == 'next':
                idx = data[1]
                self._play_index(idx)
        except Exception:
            pass

    def _show_up_next_menu(self, pos):
        try:
            item = self.up_next.itemAt(pos)
            if not item:
                return
            data = item.data(0, Qt.UserRole)
            if not (isinstance(data, tuple) and data[0] == 'next'):
                return
            idx = data[1]
            menu = QMenu(); self._apply_menu_theme(menu)
            menu.addAction('▶ Play').triggered.connect(lambda i=idx: self._play_index(i))
            menu.addAction('🗑️ Remove').triggered.connect(lambda i=idx: self._remove_index(i))
            menu.exec(self.up_next.viewport().mapToGlobal(pos))
        except Exception:
            pass

    def _selected_current_indices(self):
        try:
            nodes = self.playlist_tree.selectedItems()
            idxs = []
            for n in nodes:
                data = n.data(0, Qt.UserRole)
                if isinstance(data, tuple) and data[0] == 'current':
                    idxs.append(int(data[1]))
            return sorted(set([i for i in idxs if 0 <= i < len(self.playlist)]))
        except Exception:
            return []

    def _bulk_remove_selected(self):
        try:
            idxs = self._selected_current_indices()
            if not idxs:
                return
            was_playing = self._is_playing()
            for i in sorted(idxs, reverse=True):
                if 0 <= i < len(self.playlist):
                    del self.playlist[i]
                    if self.current_index == i:
                        self.current_index = -1
                    elif i < self.current_index:
                        self.current_index -= 1
            self._save_current_playlist(); self._refresh_playlist_widget()
            self._recover_current_after_change(was_playing)
        except Exception:
            pass

    def _bulk_clear_resume_selected(self):
        try:
            idxs = self._selected_current_indices()
            if not idxs:
                return
            for i in idxs:
                u = self.playlist[i].get('url')
                if u and (u in self.playback_positions):
                    del self.playback_positions[u]
            self._save_positions()
            self.status.showMessage('Cleared resume for selected', 3000)
        except Exception:
            pass

    def _bulk_mark_unwatched_selected(self):
        try:
            idxs = self._selected_current_indices()
            if not idxs:
                return
            changed = 0
            for i in idxs:
                u = self.playlist[i].get('url')
                if u:
                    for k in (u, self._canonical_url_key(u)):
                        if k in self.completed_urls:
                            self.completed_urls.discard(k); changed += 1
            if changed:
                self._save_completed()
            self.status.showMessage('Marked selected as unwatched', 3000)
            self._apply_filters_to_tree()
        except Exception:
            pass

    def _highlight_current_row(self):
        try:
            root = self.playlist_tree.topLevelItem(0)
            if not root:
                return
            def apply_node(node):
                try:
                    data = node.data(0, Qt.UserRole)
                    f = node.font(0)
                    if isinstance(data, tuple) and data[0] == 'current':
                        idx = data[1]
                        f.setBold(idx == self.current_index)
                        node.setFont(0, f)
                except Exception:
                    pass
                for i in range(node.childCount()):
                    apply_node(node.child(i))
            for i in range(root.childCount()):
                apply_node(root.child(i))
        except Exception:
            pass

    def _on_title_resolved(self, url: str, title: str):
        # Update item dict and UI when a title is resolved
        try:
            self._update_item_title(url, title)
        except Exception:
            pass

    def _update_item_title(self, url: str, title: str):
        updated = False
        for it in self.playlist:
            if it.get('url') == url:
                it['title'] = title
                updated = True
                break
        if updated:
            self._save_current_playlist()
            # Update UI text in-place to avoid full refresh flicker
            root = self.playlist_tree.topLevelItem(0)
            if root:
                def update_node(node):
                    data = node.data(0, Qt.UserRole)
                    if isinstance(data, tuple) and data[0] == 'current':
                        _idx, item = data[1], data[2]
                        if isinstance(item, dict) and item.get('url') == url:
                            item['title'] = title
                            node.setText(0, self._display_text(item))
                    for i in range(node.childCount()):
                        update_node(node.child(i))
                for i in range(root.childCount()):
                    update_node(root.child(i))
            # Update now playing label if this is current
            if 0 <= self.current_index < len(self.playlist):
                if self.playlist[self.current_index].get('url') == url:
                    self._set_track_title(title)

    def _toggle_group(self, checked):
        """Toggle grouped view and refresh the playlist tree."""
        self.grouped_view = bool(checked)
        self._refresh_playlist_widget()
        self._save_settings()
        
    # URL canonicalization for consistent resume keys (instance methods)
    def _canonical_url_key(self, url: str) -> str:
        try:
            import urllib.parse as up, re
            if not url:
                return url
            lo = url.lower()
            if ('youtube.com' in lo) or ('youtu.be' in lo):
                u = up.urlsplit(url)
                vid = None
                if 'youtu.be' in lo:
                    p = u.path or ''
                    vid = p.strip('/').split('/')[0].split('?')[0]
                else:
                    qs = up.parse_qs(u.query or '')
                    vid = (qs.get('v') or [''])[0]
                if vid:
                    return f"https://www.youtube.com/watch?v={vid}"
            if 'bilibili.com' in lo:
                m = re.search(r'/video/([A-Za-z0-9]+)', url)
                if m:
                    return f"https://www.bilibili.com/video/{m.group(1)}"
            # default: strip fragment and trailing slash
            u = up.urlsplit(url)
            u2 = up.urlunsplit((u.scheme, u.netloc, (u.path or '').rstrip('/'), u.query or '', ''))
            return u2
        except Exception:
            return url

    def _is_local_file(self, url):
        """
        Returns True if the url refers to a local file path or file:// URL.
        Handles file:///C:/... (Windows), file:///home/... (Unix), and plain file paths.
        """
        import os
        from urllib.parse import urlparse, unquote

        if not url:
            return False
        if url.startswith('file://'):
            parsed = urlparse(url)
            path = unquote(parsed.path)
            # On Windows, path often starts with a slash: /C:/Users/...
            if os.name == 'nt' and path.startswith('/'):
                path = path[1:]  # Remove leading slash for Windows
            return os.path.isfile(path)
        if url.startswith('http://') or url.startswith('https://'):
            return False
        return os.path.isfile(url) or (os.path.exists(url) and not url.startswith(('http://', 'https://')))       

    def _find_resume_key_for_url(self, url: str):
        try:
            key = self._canonical_url_key(url)
            if key in self.playback_positions:
                return key
            import re
            lo = (url or '').lower()
            youid = None; bilibid = None
            # extract identifiers
            if ('youtube.com' in lo) or ('youtu.be' in lo):
                try:
                    youid = self._canonical_url_key(url).split('=')[-1]
                except Exception:
                    youid = None
            if 'bilibili.com' in lo:
                try:
                    m = re.search(r'/video/([A-Za-z0-9]+)', url)
                    bilibid = m.group(1) if m else None
                except Exception:
                    bilibid = None
            for k in list(self.playback_positions.keys()):
                kl = k.lower()
                if youid and youid in kl:
                    return k
                if bilibid and (bilibid and bilibid.lower() in kl):
                    return k
            return None
        except Exception:
            return None

    # Scoped Library helpers
    def _scope_indices(self):
        try:
            if getattr(self, 'playback_model', 'scoped') != 'scoped' or not self.playlist:
                return list(range(len(self.playlist)))
            if not getattr(self, 'play_scope', None):
                return list(range(len(self.playlist)))
            kind, key = self.play_scope
            if kind == 'group':
                # Primary: match either playlist_key OR playlist title
                has_playlist_match = any(((it.get('playlist_key') == key) or (it.get('playlist') == key)) for it in self.playlist)
                if has_playlist_match:
                    return [i for i, it in enumerate(self.playlist) if ((it.get('playlist_key') == key) or (it.get('playlist') == key))]
                # Fallback: source-type grouping (youtube/bilibili/local)
                if key in ('youtube', 'bilibili', 'local'):
                    return [i for i, it in enumerate(self.playlist) if it.get('type') == key]
                return []
            return list(range(len(self.playlist)))
        except Exception:
            return list(range(len(self.playlist)))
    
    def _get_visible_indices(self):
        indices = []
        root = self.playlist_tree.topLevelItem(0)
        def walk(node):
            for i in range(node.childCount()):
                child = node.child(i)
                data = child.data(0, Qt.UserRole)
                if isinstance(data, tuple) and data[0] == 'current':
                    indices.append(data[1])
                walk(child)
        if root:
            walk(root)
        return indices

    def _scope_title_from_key(self, key):
        try:
            for it in self.playlist:
                if (it.get('playlist_key') or it.get('playlist')) == key:
                    return it.get('playlist') or str(key)
        except Exception:
            pass
        # Fallback naming for source-type groups
        names = {'youtube': 'YouTube', 'bilibili': 'Bilibili', 'local': 'Local'}
        if key in names:
            return names[key]
        # Avoid showing 'False' or empty
        if not key or key is False:
            return 'Library'
        return str(key)

    def _update_scope_label(self):
        try:
            if getattr(self, 'playback_model', 'scoped') != 'scoped':
                self.scope_label.setVisible(False)
                return
            name = "Library"
            if getattr(self, 'play_scope', None):
                kind, key = self.play_scope
                if kind == 'group':
                    name = self._scope_title_from_key(key)
            self.scope_label.setText(f"Scope: {name}")
            self.scope_label.setVisible(True)
        except Exception:
            pass

    def _on_scope_label_clicked(self):
        # One-click clear scope back to Library
        try:
            self._set_scope_library(autoplay=False)
        except Exception:
            pass

    def _group_effective_key(self, raw_key, item=None):
        try:
            # Prefer normalized key stashed on the item
            if item is not None:
                try:
                    stored = item.data(0, Qt.UserRole + 1)
                    if stored:
                        return stored
                except Exception:
                    pass
            if raw_key in (None, False, '') and item is not None:
                txt = item.text(0) if hasattr(item, 'text') else ''
                if txt:
                    s = txt.strip()
                    if s.startswith('📃'):
                        s = s[1:].strip()
                    if s.endswith(')') and '(' in s:
                        s = s[:s.rfind('(')].strip()
                    if s:
                        return s
            return raw_key
        except Exception:
            return raw_key

    def _first_index_of_group(self, key):
        try:
            idxs = self._iter_indices_for_group(key)
            if idxs:
                return idxs[0]
        except Exception:
            pass
        return None

    def _set_scope_library(self, autoplay=False):
        self.play_scope = None
        self._update_scope_label()
        if autoplay and self.playlist:
            self.current_index = 0
            self.play_current()

    def _set_scope_group(self, key, autoplay=False):
        try:
            name = self._scope_title_from_key(key)
            # Debug: print current group map
            self._debug_print_groups()
            idxs = self._iter_indices_for_group(key)
            try:
                print(f"[PlayGroup] key={key!r} name={name!r} count={len(idxs)} model={getattr(self,'playback_model','scoped')}")
            except Exception:
                pass
            if not idxs:
                self.status.showMessage(f"No items found for group '{name}'", 4000)
                return
            self.play_scope = ('group', key)
            self._update_scope_label()
            self.status.showMessage(f"Scope set to {name} ({len(idxs)} items)", 3000)
            if autoplay:
                self.current_index = idxs[0]
                try:
                    print(f"[PlayGroup] autoplay starting idx={self.current_index}")
                except Exception:
                    pass
                self.play_current()
        except Exception as e:
            try:
                print(f"[PlayGroup] exception: {e}")
            except Exception:
                pass
            pass

    def _recover_current_after_change(self, was_playing: bool):
        try:
            if not self.playlist:
                self.current_index = -1
                if was_playing:
                    try:
                        self.mpv.pause = True
                    except Exception:
                        pass
                self._update_tray();
                return
            indices = self._scope_indices()
            if not indices:
                # Fallback to entire list
                indices = list(range(len(self.playlist)))
            if self.current_index not in indices or not (0 <= self.current_index < len(self.playlist)):
                self.current_index = indices[0]
                if was_playing:
                    self.play_current()
                else:
                    self._highlight_current_row()
            else:
                # Still valid; no action
                pass
        except Exception:
            pass

    # Watched/completion utilities
    def _iter_indices_for_group(self, key):
        try:
            # Prefer playlist umbrella match (either key or title)
            idxs = [i for i, it in enumerate(self.playlist) if ((it.get('playlist_key') == key) or (it.get('playlist') == key))]
            if idxs:
                return idxs
            # Fallback: by source type
            if key in ('youtube', 'bilibili', 'local'):
                return [i for i, it in enumerate(self.playlist) if it.get('type') == key]
        except Exception:
            pass
        return []

    def _debug_print_groups(self):
        try:
            from collections import Counter
            umb = Counter()
            types = Counter()
            for it in self.playlist:
                if not isinstance(it, dict):
                    continue
                k = it.get('playlist_key') or it.get('playlist')
                if k:
                    umb[k] += 1
                t = it.get('type')
                if t:
                    types[t] += 1
            if umb:
                print("[groups] playlist umbrellas:")
                for k, c in list(umb.items())[:10]:
                    print("   ", repr(k), c)
            else:
                print("[groups] no playlist umbrellas detected")
            if types:
                print("[groups] source types:")
                for k, c in types.items():
                    print("   ", k, c)
        except Exception as e:
            try:
                print(f"[groups] debug error: {e}")
            except Exception:
                pass

    def _clear_watched_in_library(self):
        try:
            was_playing = self._is_playing()
            before = len(self.playlist)
            self.playlist = [it for it in self.playlist if ((self._canonical_url_key(it.get('url')) not in self.completed_urls) and (it.get('url') not in self.completed_urls))]
            removed = before - len(self.playlist)
            if removed:
                self._save_current_playlist(); self._refresh_playlist_widget()
                self._recover_current_after_change(was_playing)
                self.status.showMessage(f"Removed {removed} watched items from Library", 5000)
            else:
                self.status.showMessage("No watched items to remove in Library", 3000)
        except Exception as e:
            self.status.showMessage(f"Clear watched failed: {e}", 4000)

    def _clear_watched_in_group(self, key):
        try:
            was_playing = self._is_playing()
            idxs = set(self._iter_indices_for_group(key))
            if not idxs:
                self.status.showMessage("No items found for this group", 3000); return
            before = len(self.playlist)
            self.playlist = [it for i, it in enumerate(self.playlist) if not (i in idxs and ((self._canonical_url_key(it.get('url')) in self.completed_urls) or (it.get('url') in self.completed_urls)))]
            removed = before - len(self.playlist)
            if removed:
                self._save_current_playlist(); self._refresh_playlist_widget()
                self._recover_current_after_change(was_playing)
                name = self._scope_title_from_key(key)
                self.status.showMessage(f"Removed {removed} watched items from {name}", 5000)
            else:
                self.status.showMessage("No watched items to remove in group", 3000)
        except Exception as e:
            self.status.showMessage(f"Clear watched failed: {e}", 4000)

    def _play_unwatched_in_group(self, key):
        try:
            idxs = self._iter_indices_for_group(key)
            for i in idxs:
                u = self.playlist[i].get('url')
                if (not u) or ((self._canonical_url_key(u) not in self.completed_urls) and (u not in self.completed_urls)):
                    self.play_scope = ('group', key)
                    self._update_scope_label()
                    self.current_index = i
                    self.play_current()
                    return
            name = self._scope_title_from_key(key)
            self.status.showMessage(f"No unwatched items in {name}", 4000)
        except Exception as e:
            try:
                self.status.showMessage(f"Play unwatched failed: {e}", 4000)
            except Exception:
                pass

    def _mark_group_unwatched(self, key):
        try:
            urls = []
            for i in self._iter_indices_for_group(key):
                u = self.playlist[i].get('url')
                if u:
                    urls.append(u)
            changed = 0
            for u in urls:
                if u in self.completed_urls:
                    self.completed_urls.discard(u)
                    changed += 1
            if changed:
                self._save_completed(); self.status.showMessage(f"Marked {changed} items unwatched", 4000)
            else:
                self.status.showMessage("No items needed changes", 3000)
        except Exception as e:
            self.status.showMessage(f"Mark group unwatched failed: {e}", 4000)

    def _mark_item_unwatched(self, url):
        try:
            removed = False
            keys = [url, self._canonical_url_key(url)]
            for k in keys:
                if k and k in self.completed_urls:
                    self.completed_urls.discard(k); removed = True
            # Fallback fuzzy match on video id
            if not removed:
                import re
                lo = (url or '').lower()
                vid = None
                if ('youtube.com' in lo) or ('youtu.be' in lo):
                    try:
                        vid = self._canonical_url_key(url).split('=')[-1]
                    except Exception:
                        vid = None
                elif 'bilibili.com' in lo:
                    try:
                        m = re.search(r'/video/([A-Za-z0-9]+)', url)
                        vid = m.group(1) if m else None
                    except Exception:
                        vid = None
                if vid:
                    for k in list(self.completed_urls):
                        if vid.lower() in k.lower():
                            self.completed_urls.discard(k); removed = True
            if removed:
                self._save_completed(); self.status.showMessage("Item marked unwatched", 3000)
            else:
                self.status.showMessage("Item already unwatched", 3000)
        except Exception as e:
            self.status.showMessage(f"Mark unwatched failed: {e}", 4000)

    def _play_from_beginning(self, idx: int, url: str):
        try:
            self._clear_resume_for_url(url)
        except Exception:
            pass
        # Force playing even if item is marked completed (one-off)
        self._force_play_ignore_completed = True
        self._play_index(idx)

    def _play_from_here_in_group(self, idx: int):
        try:
            if not (0 <= idx < len(self.playlist)):
                return
            it = self.playlist[idx]
            key = it.get('playlist_key') or it.get('playlist') or it.get('type')
            if not key:
                # No sensible group; just play the item
                self.current_index = idx; self.play_current(); return
            # Set scope and play this index
            self.play_scope = ('group', key)
            self._update_scope_label()
            self.current_index = idx
            self.play_current()
        except Exception:
            pass

    def _open_in_browser(self, url: str):
        try:
            import webbrowser
            if url:
                webbrowser.open(url)
        except Exception:
            pass

    def _copy_url(self, url: str):
        try:
            if url:
                QApplication.clipboard().setText(url)
                self.status.showMessage("URL copied to clipboard", 2000)
        except Exception:
            pass

    def _expand_all_groups(self, expand: bool):
        try:
            root = self.playlist_tree.topLevelItem(0)
            if not root:
                return
            def visit(node):
                data = node.data(0, Qt.UserRole)
                if isinstance(data, tuple) and data[0] == 'group':
                    node.setExpanded(bool(expand))
                for i in range(node.childCount()):
                    visit(node.child(i))
            for i in range(root.childCount()):
                visit(root.child(i))
        except Exception:
            pass

    def _export_m3u(self):
        try:
            from PySide6.QtWidgets import QFileDialog
            if not self.playlist:
                QMessageBox.information(self, "Export", "No items to export."); return
            path, _ = QFileDialog.getSaveFileName(self, "Export M3U", "playlist.m3u8", "M3U Playlists (*.m3u *.m3u8)")
            if not path:
                return
            with open(path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for it in self.playlist:
                    title = it.get('title') or it.get('url') or ''
                    url = it.get('url') or ''
                    f.write(f"#EXTINF:-1,{title}\n{url}\n")
            self.status.showMessage(f"Exported to {Path(path).name}", 4000)
        except Exception as e:
            self.status.showMessage(f"Export failed: {e}", 4000)

    def _import_m3u(self):
        try:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(self, "Import M3U", "", "M3U Playlists (*.m3u *.m3u8)")
            if not path:
                return
            added = 0
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith('#'):
                        continue
                    u = s
                    # Guess type
                    t = 'local'
                    lo = u.lower()
                    if 'youtube.com' in lo or 'youtu.be' in lo:
                        t = 'youtube'
                    elif 'bilibili.com' in lo:
                        t = 'bilibili'
                    title = Path(u).name if t == 'local' and '://' not in u else u
                    # Deduplicate by URL
                    if any(it.get('url') == u for it in self.playlist):
                        continue
                    self.playlist.append({'title': title, 'url': u, 'type': t})
                    added += 1
            if added:
                self._save_current_playlist(); self._refresh_playlist_widget()
            self.status.showMessage(f"Imported {added} items", 4000)
        except Exception as e:
            self.status.showMessage(f"Import failed: {e}", 4000)

    def _move_to_top(self, idx: int):
        try:
            if not (0 <= idx < len(self.playlist)):
                return
            it = self.playlist.pop(idx)
            self.playlist.insert(0, it)
            if self.current_index == idx:
                self.current_index = 0
            elif idx < self.current_index:
                self.current_index -= 1
            self._save_current_playlist(); self._refresh_playlist_widget()
        except Exception:
            pass

    def _move_to_bottom(self, idx: int):
        try:
            if not (0 <= idx < len(self.playlist)):
                return
            it = self.playlist.pop(idx)
            self.playlist.append(it)
            if self.current_index == idx:
                self.current_index = len(self.playlist) - 1
            elif idx < self.current_index:
                self.current_index -= 1
            self._save_current_playlist(); self._refresh_playlist_widget()
        except Exception:
            pass

    # Actions
    def _maybe_offer_clipboard_url(self):
        """
        Check clipboard for a media URL and offer to add it.
        Returns True if the clipboard URL was added (so callers can suppress other UI),
        False otherwise.
        """
        try:
            cb = QApplication.clipboard().text() or ""
            s = cb.strip()
            if not s:
                return False
            lo = s.lower()
            is_media = ('youtube.com' in lo) or ('youtu.be' in lo) or ('bilibili.com' in lo)
            if not is_media:
                return False
            # don't re-prompt for the same clipboard text
            if getattr(self, '_last_clipboard_offer', "") == s:
                return False
            # dedupe if already present
            if any(isinstance(it, dict) and it.get('url') == s for it in self.playlist):
                self._last_clipboard_offer = s
                return False

            res = QMessageBox.question(self, "Add from Clipboard", f"Detected media URL:\n\n{s}\n\nAdd to playlist?", QMessageBox.Yes | QMessageBox.No)
            if res == QMessageBox.Yes:
                t = 'youtube' if (('youtube.com' in lo) or ('youtu.be' in lo)) else ('bilibili' if ('bilibili.com' in lo) else 'local')
                will_try_playlist = (
                    t in ('youtube', 'bilibili') and (
                        ('list=' in s) or ('playlist' in lo) or ('series' in lo) or ('watchlater' in lo) or
                        ('space.bilibili.com' in lo)
                    )
                )
                if will_try_playlist:
                    self.status.showMessage("Loading playlist entries...", 5000)
                    loader = PlaylistLoaderThread(s, t)
                    self._playlist_loader = loader
                    loader.itemsReady.connect(self._on_playlist_items_ready)
                    loader.error.connect(lambda e: self.status.showMessage(e, 5000))
                    loader.finished.connect(loader.deleteLater)
                    loader.start()
                else:
                    # Single URL case: append and resolve title asynchronously
                    title = s
                    item = {'title': title, 'url': s, 'type': t}
                    self.playlist.append(item)
                    self._save_current_playlist()
                    self._refresh_playlist_widget()
                    # Try to resolve nicer title in background
                    try:
                        w = TitleResolveWorker([item], t)
                        self._title_workers.append(w)
                        w.titleResolved.connect(self._on_title_resolved)
                        w.error.connect(lambda e: self.status.showMessage(e, 5000))
                        w.finished.connect(lambda w=w: (self._title_workers.remove(w) if w in self._title_workers else None))
                        w.start()
                    except Exception:
                        pass
                self._last_clipboard_offer = s
                return True
            # user said No
            self._last_clipboard_offer = s
            return False
        except Exception as e:
            try:
                self.status.showMessage(f"Clipboard check failed: {e}", 4000)
            except Exception:
                pass
            return False

    def add_link_dialog(self):
        from PySide6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(self, "Add Media Link", "Enter YouTube or Bilibili URL or Playlist:")
        if ok and url:
            t = 'youtube' if ('youtube.com' in url or 'youtu.be' in url) else ('bilibili' if 'bilibili.com' in url else 'local')
            # Try to detect if this is a playlist and load entries in background
            will_try_playlist = (
                t in ('youtube', 'bilibili') and (
                    'list=' in url or 'playlist' in url or 'series' in url or 'watchlater' in url or
                    ('space.bilibili.com' in url)
                )
            )
            if will_try_playlist:
                self.status.showMessage("Loading playlist entries...", 5000)
                loader = PlaylistLoaderThread(url, t)
                self._playlist_loader = loader
                loader.itemsReady.connect(self._on_playlist_items_ready)
                loader.error.connect(lambda e: self.status.showMessage(e, 5000))
                loader.finished.connect(loader.deleteLater)
                loader.start()
            else:
                # Single item: append immediately but resolve title async
                title = url
                item = {'title': title, 'url': url, 'type': t}
                self.playlist.append(item)
                self._save_current_playlist()
                self._refresh_playlist_widget()
                # Spawn TitleResolveWorker for this single item
                try:
                    w = TitleResolveWorker([item], t)
                    self._title_workers.append(w)
                    w.titleResolved.connect(self._on_title_resolved)
                    w.error.connect(lambda e: self.status.showMessage(e, 5000))
                    w.finished.connect(lambda w=w: (self._title_workers.remove(w) if w in self._title_workers else None))
                    w.start()
                except Exception:
                    pass

    def add_link_dialog(self):
        from PySide6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(self, "Add Media Link", "Enter YouTube or Bilibili URL or Playlist:")
        if ok and url:
            t = 'youtube' if ('youtube.com' in url or 'youtu.be' in url) else ('bilibili' if 'bilibili.com' in url else 'local')
            # Try to detect if this is a playlist and load entries in background
            will_try_playlist = (
                t in ('youtube', 'bilibili') and (
                    'list=' in url or 'playlist' in url or 'series' in url or 'watchlater' in url or
                    ('space.bilibili.com' in url)
                )
            )
            if will_try_playlist:
                self.status.showMessage("Loading playlist entries...", 5000)
                loader = PlaylistLoaderThread(url, t)
                self._playlist_loader = loader
                loader.itemsReady.connect(self._on_playlist_items_ready)
                loader.error.connect(lambda e: self.status.showMessage(e, 5000))
                loader.finished.connect(loader.deleteLater)
                loader.start()
            else:
                # Single item: append immediately but resolve title async (so UI updates to real title)
                title = url
                item = {'title': title, 'url': url, 'type': t}
                self.playlist.append(item)
                self._save_current_playlist(); self._refresh_playlist_widget()
                # Spawn TitleResolveWorker for this single item (same pattern used for playlist items)
                try:
                    w = TitleResolveWorker([item], t)
                    self._title_workers.append(w)
                    w.titleResolved.connect(self._on_title_resolved)
                    w.error.connect(lambda e: self.status.showMessage(e, 5000))
                    w.finished.connect(lambda w=w: (self._title_workers.remove(w) if w in self._title_workers else None))
                    w.start()
                except Exception:
                    pass

    def add_local_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Media Files", "", "Media Files (*.mp4 *.avi *.mkv *.mov *.mp3 *.wav *.flac)")
        if not files:
            return
        for f in files:
            self.playlist.append({'title': Path(f).name, 'url': f, 'type': 'local'})
        self._save_current_playlist(); self._refresh_playlist_widget()

    def save_playlist(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Save Playlist", "Enter name:")
        if ok and name:
            name = self._unique_playlist_name(name)
            self.saved_playlists[name] = list(self.playlist)
            self._save_playlists_file()
            self.status.showMessage(f"Saved playlist '{name}'", 4000)

    def load_playlist_dialog(self):
        if not self.saved_playlists:
            QMessageBox.information(self, "No Playlists", "No saved playlists found.")
            return
        from PySide6.QtWidgets import QInputDialog
        names = list(self.saved_playlists.keys())
        name, ok = QInputDialog.getItem(self, "Load Playlist", "Select:", names, 0, False)
        if ok and name:
            self.playlist = list(self.saved_playlists.get(name, []))
            self.current_index = 0 if self.playlist else -1
            self._save_current_playlist(); self._refresh_playlist_widget()
            self.status.showMessage(f"Loaded playlist '{name}'", 4000)
            if self.playlist:
                self.play_current()

    def _unique_playlist_name(self, base):
        base = (base or 'Playlist').strip()
        if base not in self.saved_playlists:
            return base
        i = 2
        while f"{base} ({i})" in self.saved_playlists:
            i += 1
        return f"{base} ({i})"

    def on_tree_item_double_clicked(self, item, column):
        data = item.data(0, Qt.UserRole)
        if not isinstance(data, tuple):
            return
        kind = data[0]
        if kind == 'current':
            idx = data[1]
            # Save current track before switching by double-click
            self._save_current_position()
            self.current_index = idx
            self.play_current()
        elif kind == 'group':
            # Scoped: set scope to group and autoplay; Queue: play first child
            try:
                raw_key = data[1]
                key = self._group_effective_key(raw_key, item)
                if getattr(self, 'playback_model', 'scoped') == 'scoped':
                    self._set_scope_group(key, autoplay=True)
                else:
                    if item.childCount() > 0:
                        child = item.child(0)
                        cdata = child.data(0, Qt.UserRole)
                        if isinstance(cdata, tuple) and cdata[0] == 'current':
                            idx = cdata[1]
                            self._save_current_position()
                            self.current_index = idx
                            self.play_current()
            except Exception:
                pass

    def _show_playlist_context_menu(self, pos):
        item = self.playlist_tree.itemAt(pos)
        menu = QMenu()
        self._apply_menu_theme(menu)
        root = self.playlist_tree.topLevelItem(0)
        # Bulk actions if multiple current items are selected
        try:
            sel = [it for it in self.playlist_tree.selectedItems() if isinstance(it.data(0, Qt.UserRole), tuple) and it.data(0, Qt.UserRole)[0] == 'current']
            if len(sel) >= 2:
                menu.addAction("🗑️ Remove selected").triggered.connect(self._bulk_remove_selected)
                menu.addAction("🧹 Clear resume for selected").triggered.connect(self._bulk_clear_resume_selected)
                menu.addAction("✅ Mark selected as Unwatched").triggered.connect(self._bulk_mark_unwatched_selected)
                menu.exec(self.playlist_tree.viewport().mapToGlobal(pos)); return
        except Exception:
            pass
        if item is None:
            menu.addAction("🗑️ Clear Current").triggered.connect(self._clear_playlist)
            menu.exec(self.playlist_tree.viewport().mapToGlobal(pos)); return
        if item is root:
            if getattr(self, 'playback_model', 'scoped') == 'scoped':
                menu.addAction("▶ Play Library").triggered.connect(lambda: self._set_scope_library(True))
            else:
                menu.addAction("▶ Play Entire Library").triggered.connect(self._play_all_library)
            menu.addSeparator()
            menu.addAction("↕ Expand All Groups").triggered.connect(lambda: self._expand_all_groups(True))
            menu.addAction("↕ Collapse All Groups").triggered.connect(lambda: self._expand_all_groups(False))
            menu.addSeparator()
            menu.addAction("⬇ Import M3U...").triggered.connect(self._import_m3u)
            menu.addAction("⬆ Export M3U...").triggered.connect(self._export_m3u)
            menu.addSeparator()
            menu.addAction("🧹 Clear Current").triggered.connect(self._clear_playlist)
            menu.exec(self.playlist_tree.viewport().mapToGlobal(pos)); return
        data = item.data(0, Qt.UserRole)
        if not isinstance(data, tuple):
            if getattr(self, 'playback_model', 'scoped') == 'scoped':
                menu.addAction("▶ Play Library").triggered.connect(lambda: self._set_scope_library(True))
            else:
                menu.addAction("▶ Play Entire Library").triggered.connect(self._play_all_library)
            menu.addAction("🧹 Clear Current").triggered.connect(self._clear_playlist)
            menu.exec(self.playlist_tree.viewport().mapToGlobal(pos)); return
        kind, *rest = data
        if kind == 'current':
            idx, it = rest[0], rest[1]
            url = it.get('url')
            pkey = it.get('playlist_key') or it.get('playlist') or it.get('type')
            menu.addAction("⏮ Play From Beginning").triggered.connect(lambda i=idx, u=url: self._play_from_beginning(i, u))
            menu.addAction("▶ Play").triggered.connect(lambda: self._play_index(idx))
            # One-off bypass if completed
            if self._is_completed_url(url):
                menu.addAction("▶ Play Anyway (ignore skip once)").triggered.connect(lambda i=idx: self._force_play_anyway(i))
            if pkey:
                menu.addAction("🎯 Play From Here in Group").triggered.connect(lambda i=idx: self._play_from_here_in_group(i))
            menu.addAction("⏭️ Play Next").triggered.connect(lambda i=idx: self._queue_item_next(i))
            menu.addSeparator()
            menu.addAction("⬆ Move Up").triggered.connect(lambda: self._move_item(idx, -1))
            menu.addAction("⬇ Move Down").triggered.connect(lambda: self._move_item(idx, 1))
            menu.addAction("⤴ Move to Top").triggered.connect(lambda i=idx: self._move_to_top(i))
            menu.addAction("⤵ Move to Bottom").triggered.connect(lambda i=idx: self._move_to_bottom(i))
            menu.addSeparator()
            menu.addAction("🧹 Clear Resume").triggered.connect(lambda: self._clear_resume_for_url(url))
            menu.addAction("✅ Mark as Unwatched").triggered.connect(lambda u=url: self._mark_item_unwatched(u))
            if isinstance(url, str) and url.startswith("http"):
                menu.addAction("🌐 Open in Browser").triggered.connect(lambda u=url: self._open_in_browser(u))
            if url:
                menu.addAction("🔗 Copy URL").triggered.connect(lambda u=url: self._copy_url(u))
            menu.addSeparator()
            menu.addAction("🗑️ Remove").triggered.connect(lambda: self._remove_index(idx))
            menu.addSeparator(); menu.addAction("🗑️ Clear Current").triggered.connect(self._clear_playlist)
        elif kind == 'group':
            raw_key = rest[0]
            eff_key = self._group_effective_key(raw_key, item)
            # Fallback: if key is missing, derive from first child item
            if eff_key in (None, False, ''):
                try:
                    if item and item.childCount() > 0:
                        cdata = item.child(0).data(0, Qt.UserRole)
                        if isinstance(cdata, tuple) and cdata[0] == 'current':
                            _cidx, _cit = cdata[1], cdata[2]
                            eff_key = _cit.get('playlist_key') or _cit.get('playlist') or _cit.get('type')
                except Exception:
                    pass
            if getattr(self, 'playback_model', 'scoped') == 'scoped':
                menu.addAction("▶ Play Group").triggered.connect(lambda k=eff_key: self._set_scope_group(k, autoplay=True))
            else:
                idx = self._first_index_of_group(eff_key)
                if idx is not None:
                    menu.addAction("▶ Play Group").triggered.connect(lambda i=idx: self._play_index(i))
            menu.addSeparator()
            menu.addAction("＋ Expand Group").triggered.connect(lambda it=item: it.setExpanded(True))
            menu.addAction("－ Collapse Group").triggered.connect(lambda it=item: it.setExpanded(False))
        menu.exec(self.playlist_tree.viewport().mapToGlobal(pos))

    def _force_play_anyway(self, idx: int):
        try:
            if 0 <= idx < len(self.playlist):
                self._force_play_ignore_completed = True
                self._play_index(idx)
        except Exception:
            pass

    def _play_index(self, idx):
        if 0 <= idx < len(self.playlist):
            self.current_index = idx; self.play_current(); self._update_up_next()

    def _move_item(self, idx, delta):
        j = idx + delta
        if 0 <= idx < len(self.playlist) and 0 <= j < len(self.playlist):
            self.playlist[idx], self.playlist[j] = self.playlist[j], self.playlist[idx]
            self._save_current_playlist(); self._refresh_playlist_widget()
            self.current_index = j

    def _queue_item_next(self, idx):
        try:
            if not (0 <= idx < len(self.playlist)):
                return
            if self.current_index == -1:
                # Nothing playing: make it first
                it = self.playlist.pop(idx)
                self.playlist.insert(0, it)
                self.current_index = 0
                self._save_current_playlist(); self._refresh_playlist_widget(); self.play_current(); return
            next_pos = self.current_index + 1
            if idx == next_pos:
                return  # already next
            it = self.playlist.pop(idx)
            # Adjust current_index if the removed index was before current
            if idx < self.current_index:
                self.current_index -= 1
            next_pos = min(next_pos, len(self.playlist))
            self.playlist.insert(next_pos, it)
            self._save_current_playlist(); self._refresh_playlist_widget()
            self.status.showMessage("Queued to play next", 3000)
        except Exception:
            pass

    def _remove_index(self, idx):
        if 0 <= idx < len(self.playlist):
            del self.playlist[idx]
            self._save_current_playlist(); self._refresh_playlist_widget()
            if self.current_index >= len(self.playlist):
                self.current_index = len(self.playlist) - 1

    def _clear_resume_for_url(self, url):
        try:
            cleared = False
            # Try exact and canonical keys
            keys = [url, self._canonical_url_key(url)]
            for k in keys:
                if k and k in self.playback_positions:
                    del self.playback_positions[k]
                    cleared = True
            # Fallback: fuzzy match by video id (YouTube/Bilibili)
            if not cleared:
                alt = self._find_resume_key_for_url(url)
                if alt and alt in self.playback_positions:
                    del self.playback_positions[alt]
                    cleared = True
            self._save_positions()
            self.status.showMessage("Cleared resume point" if cleared else "No resume point found", 3000)
        except Exception as e:
            self.status.showMessage(f"Clear resume failed: {e}", 4000)

    def _clear_playlist(self):
        if QMessageBox.question(self, "Clear Playlist", "Are you sure?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.playlist.clear(); self.current_index = -1
            self._save_current_playlist(); self._refresh_playlist_widget()

    def _play_all_library(self):
        # Only use current playlist; do not include saved items
        seen = set()
        combined = []
        for it in self.playlist:
            u = it.get('url')
            if not u or u in seen:
                continue
            seen.add(u)
            combined.append({'title': it.get('title', u), 'url': u, 'type': it.get('type', 'local'), 'playlist': it.get('playlist')})
        if not combined:
            QMessageBox.information(self, "No Media", "No media found in current playlist.")
            return
        self.playlist = combined
        self.current_index = 0
        self._save_current_playlist(); self._refresh_playlist_widget()
        self.play_current()

    # Playback
    def play_current(self):
        try:
            print(f"[play_current] idx={self.current_index} len={len(self.playlist)} scope={self.play_scope}")
        except Exception:
            pass
        if not (0 <= self.current_index < len(self.playlist)):
            return
        # Skip items previously completed (>=95% watched) and move to next available
        if getattr(self, '_force_play_ignore_completed', False):
            # One-off bypass used by context action
            self._force_play_ignore_completed = False
        elif getattr(self, 'skip_completed', False):
            guard = 0
            while 0 <= self.current_index < len(self.playlist):
                url_try = self.playlist[self.current_index].get('url')
                key_try = self._canonical_url_key(url_try) if url_try else None
                if (not url_try) or ((key_try not in self.completed_urls) and (url_try not in self.completed_urls)):
                    break
                self.current_index += 1
                guard += 1
                if guard > len(self.playlist):
                    break
            if self.current_index >= len(self.playlist):
                self.status.showMessage("All items in the playlist are completed", 5000)
                return
        self._end_session()
        it = self.playlist[self.current_index]
        url = it.get('url', '')

        # Set keep-open dynamically for gapless local playback
        if self._is_local_file(url):
            self.mpv['keep-open'] = 'yes'
        else:
            self.mpv['keep-open'] = 'no'        

        # Site-specific options
        try:
            if it.get('type') == 'bilibili':
                # Bilibili often requires referer + cookies + headers
                self.mpv['referrer'] = it.get('url') or 'https://www.bilibili.com'
                self.mpv['http-header-fields'] = 'Referer: https://www.bilibili.com,Origin: https://www.bilibili.com,User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
                self.mpv['ytdl-raw-options'] = f"cookies={str(COOKIES_BILI)},add-header=Referer: https://www.bilibili.com,add-header=User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                self.mpv['ytdl-format'] = 'bv*[vcodec^=avc1][height<=720]+ba/best[height<=720]/best'
            else:
                self.mpv['referrer'] = ''
                self.mpv['http-header-fields'] = ''
                self.mpv['ytdl-raw-options'] = ''
                self.mpv['ytdl-format'] = 'best[height<=720]/bv*[height<=720]+ba/best'
        except Exception:
            pass

        self._set_track_title(it.get('title', 'Unknown'))
        self._highlight_current_row()
        # Seamless resume: load with start option to avoid 0:00 flash
        _url = it.get('url')
        _key = self._canonical_url_key(_url) if _url else None
        _resume_ms = int(self.playback_positions.get(_key, self.playback_positions.get(_url, 0))) if _url else 0
        _resume_sec = max(0.0, float(_resume_ms) / 1000.0)
        try:
            print(f"[play_current] loading title={it.get('title')} url={_url} resume_ms={_resume_ms}")
        except Exception:
            pass
        # Set enforcement window to protect target from early regressions
        self._resume_target_ms = _resume_ms
        self._resume_enforce_until = time.time() + 20.0
        try:
            if _resume_sec > 0:
                self.mpv.command('loadfile', _url, 'replace', f'start={_resume_sec}')
            else:
                self.mpv.command('loadfile', _url, 'replace')
        except Exception:
            self.mpv.play(_url)
        self.mpv.pause = False
        # In case backend ignores start, issue robust resume attempts
        if _resume_ms > 0:
            self._restore_saved_position_attempt(_url, _resume_ms, 1)
            QTimer.singleShot(350, lambda: self._maybe_reapply_resume('start'))
        # set pause icon (we are now playing)
        try:
            self.play_pause_btn.setIcon(self._pause_icon_normal)
            self._play_pause_shows_play = False
        except Exception:
            try:
                self.play_pause_btn.setIcon(self.pause_icon)
                self._play_pause_shows_play = False
            except Exception:
                pass
        self._start_session()
        self._update_tray()

        # Thumbnails (async)
        if self.show_thumbnails and HAVE_REQUESTS:
            thumb_url = self._guess_thumbnail_url(it)
            if thumb_url:
                self._thumb_thread = ThumbnailFetcher(thumb_url)
                self._thumb_thread.thumbnailReady.connect(self._set_thumbnail)
                self._thumb_thread.start()

    def _guess_thumbnail_url(self, item):
        try:
            url = item.get('url', '')
            if item.get('type') == 'youtube':
                # Try to extract video id
                import urllib.parse as up
                u = up.urlparse(url)
                if 'youtu.be' in url:
                    vid = u.path.strip('/')
                else:
                    qs = up.parse_qs(u.query)
                    vid = (qs.get('v') or [''])[0]
                if vid:
                    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            elif item.get('type') == 'bilibili':
                # As a fallback, use yt_dlp to fetch thumbnail url quickly
                try:
                    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'cookiefile': str(COOKIES_BILI)}) as ydl:
                        info = ydl.extract_info(url, download=False)
                        return info.get('thumbnail')
                except Exception:
                    return None
        except Exception:
            pass
        return None

    def _set_thumbnail(self, pm: QPixmap):
        if not pm or pm.isNull():
            return
        self.thumbnail_label.setPixmap(pm.scaled(self.thumbnail_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.thumbnail_label.show()

    def next_track(self):
        if not self.playlist:
            return
        # Save current track position before switching
        self._save_current_position()
        if getattr(self, 'playback_model', 'scoped') == 'scoped':
            indices = self._get_visible_indices()
            if indices:
                try:
                    pos = indices.index(self.current_index) if self.current_index in indices else -1
                    if self.shuffle_mode:
                        import random
                        self.current_index = random.choice(indices)
                    else:
                        self.current_index = indices[(pos + 1) % len(indices)]
                    self.play_current(); return
                except Exception:
                    pass
        if self.shuffle_mode:
            import random
            self.current_index = random.randint(0, len(self.playlist)-1)
        else:
            self.current_index = (self.current_index + 1) % len(self.playlist)
        self.play_current()

    def previous_track(self):
        if not self.playlist:
            return
        # Save current track position before switching
        self._save_current_position()
        if getattr(self, 'playback_model', 'scoped') == 'scoped':
            indices = self._get_visible_indices()
            if indices:
                try:
                    pos = indices.index(self.current_index) if self.current_index in indices else 1
                    if self.shuffle_mode:
                        import random
                        self.current_index = random.choice(indices)
                    else:
                        self.current_index = indices[(pos - 1) % len(indices)]
                    self.play_current(); return
                except Exception:
                    pass
        if self.shuffle_mode:
            import random
            self.current_index = random.randint(0, len(self.playlist)-1)
        else:
            self.current_index = (self.current_index - 1 + len(self.playlist)) % len(self.playlist)
        self.play_current()

    def toggle_play_pause(self):
        if self._is_playing():
            self.mpv.pause = True
            self._save_current_position()
            try:
                self.play_pause_btn.setIcon(self._play_icon_normal)
                self._play_pause_shows_play = True
            except Exception:
                try:
                    self.play_pause_btn.setIcon(self.play_icon)
                    self._play_pause_shows_play = True
                except Exception:
                    pass
            self._end_session()
        else:
            if self.current_index == -1 and self.playlist:
                self.current_index = 0
                self.play_current()
                return
            self.mpv.pause = False
            try:
                self.play_pause_btn.setIcon(self._pause_icon_normal)
                self._play_pause_shows_play = False
            except Exception:
                try:
                    self.play_pause_btn.setIcon(self.pause_icon)
                    self._play_pause_shows_play = False
                except Exception:
                    pass
            self._start_session()
        self._update_tray()

    def _toggle_shuffle(self):
        self.shuffle_mode = self.shuffle_btn.isChecked()
        self.status.showMessage(f"Shuffle {'on' if self.shuffle_mode else 'off'}", 3000)
        self._save_settings()

    def _toggle_repeat(self):
        self.repeat_mode = self.repeat_btn.isChecked()
        self.status.showMessage(f"Repeat {'on' if self.repeat_mode else 'off'}", 3000)
        self._save_settings()

    def set_volume(self, value):
        try:
            self.mpv.volume = int(value)
            self._save_settings()
        except Exception:
            pass

    def set_position(self, pos_ms):
        try:
            self.mpv.time_pos = max(0.0, float(pos_ms) / 1000.0)
        except Exception:
            pass

    def _on_slider_moved(self, pos_ms: int):
        # While scrubbing, update only the time label to reflect the target position
        try:
            self.time_label.setText(format_time(int(pos_ms)))
        except Exception:
            pass

    def _on_slider_released(self):
        # Apply seek when user releases the slider
        try:
            pos_ms = int(self.progress.value())
            self.set_position(pos_ms)
        except Exception:
            pass
        self._user_scrubbing = False

    def _maybe_reapply_resume(self, source: str = ''):
        try:
            tgt = int(getattr(self, '_resume_target_ms', 0) or 0)
            until = float(getattr(self, '_resume_enforce_until', 0.0) or 0.0)
            if tgt <= 0 or time.time() > until:
                return
            cur = int(self._last_play_pos_ms or 0)
            # If we're significantly before the target, re-apply seek
            if cur < tgt - 1500:
                self.mpv.time_pos = max(0.0, float(tgt) / 1000.0)
        except Exception:
            pass

    # Tick updates (position + tray + badge stats)
    def _update_position_tick(self):
        try:
            # Mark item completed when >=95% watched (does not affect current playback)
            if self._is_playing() and 0 <= self.current_index < len(self.playlist):
                dur = float(self.mpv.duration or 0)
                pos = float(self.mpv.time_pos or 0)
                if dur > 0 and pos / dur >= (float(getattr(self, 'completed_percent', 95)) / 100.0):
                    url = self.playlist[self.current_index].get('url')
                    key = self._canonical_url_key(url) if url else None
                    if key and key not in self.completed_urls and url not in self.completed_urls:
                        self.completed_urls.add(key)
                        self._save_completed()
            now = time.time()
            # Enforce resume target early after start
            self._maybe_reapply_resume('tick')
            # Periodically persist resume timestamp while playing
            if self._is_playing() and 0 <= self.current_index < len(self.playlist):
                if now - getattr(self, '_last_resume_save', 0) >= 10:
                    self._save_current_position(); self._last_resume_save = now
            if self._is_playing() and self.session_start_time and now - self.last_position_update >= 30:
                self._update_listening_stats(); self.last_position_update = now
        except Exception:
            pass
        # Update tray and silence indicator visibility based on current playback state
        self._update_tray()
        try:
            self.silence_indicator.setVisible(bool(self._last_system_is_silent and (not self._is_playing())))
        except Exception:
            pass
        self.update_badge()

    def _restore_saved_position(self):
        if not (0 <= self.current_index < len(self.playlist)):
            return
        url = self.playlist[self.current_index].get('url')
        if not url or url not in self.playback_positions:
            return
        pos_ms = int(self.playback_positions[url])
        self._restore_saved_position_attempt(url, pos_ms, 1)

    def _restore_saved_position_attempt(self, url: str, pos_ms: int, attempt: int):
        try:
            # Try to restore; if track not yet loaded, retry a few times
            if attempt > 10:
                print(f"[resume] giving up restore for {url}")
                return
            # If duration not known yet, still try to seek
            self.mpv.time_pos = max(0.0, float(pos_ms) / 1000.0)
            self.status.showMessage(f"Resuming from {format_time(pos_ms)} (attempt {attempt})", 2000)
            # Verify after a short delay
            QTimer.singleShot(400, lambda: self._verify_restore(url, pos_ms, attempt))
        except Exception as e:
            print(f"_restore_saved_position attempt error: {e}")

    def _verify_restore(self, url: str, pos_ms: int, attempt: int):
        try:
            cur = float(self.mpv.time_pos or 0.0) * 1000.0
            if abs(cur - pos_ms) < 1500:  # within 1.5s
                print(f"[resume] confirmed at {format_time(int(cur))} for {url}")
                return
        except Exception:
            pass
        # Retry
        QTimer.singleShot(600, lambda: self._restore_saved_position_attempt(url, pos_ms, attempt + 1))

    # Settings dialog
    def open_settings_tabs(self):
        dlg = QDialog(self); dlg.setWindowTitle("Settings"); dlg.resize(720, 520)
        layout = QVBoxLayout(dlg)
        tabs = QTabWidget(); layout.addWidget(tabs)

        # Playback tab
        w_play = QWidget(); f_play = QFormLayout(w_play)
        spn_completed = QSpinBox(); spn_completed.setRange(50, 100); spn_completed.setSuffix("%")
        spn_completed.setValue(int(getattr(self, 'completed_percent', 95)))
        chk_skip_completed = QCheckBox(); chk_skip_completed.setChecked(bool(getattr(self, 'skip_completed', False)))
        cmb_model = QComboBox(); cmb_model.addItems(["Scoped Library", "Queue"])
        cmb_model.setCurrentIndex(0 if getattr(self, 'playback_model', 'scoped') == 'scoped' else 1)
        f_play.addRow("Completed threshold:", spn_completed)
        f_play.addRow("Skip completed:", chk_skip_completed)
        f_play.addRow("Playback model:", cmb_model)
        s_afk = QSpinBox(); s_afk.setRange(1, 240); s_afk.setSuffix(" minutes"); s_afk.setValue(int(getattr(self, 'afk_timeout_minutes', 15)))
        f_play.addRow("Auto-pause after inactivity:", s_afk)
        tabs.addTab(w_play, "Playback")

        # Audio Monitor tab
        w_mon = QWidget(); f_mon = QFormLayout(w_mon)
        chk_monitor_system = QCheckBox(); chk_monitor_system.setChecked(bool(getattr(self, 'monitor_system_output', True)))
        chk_monitor_system.setToolTip("Monitor system audio output (speakers/headphones) instead of microphone")
        # Device picker (prioritize WASAPI loopback)
        cmb_device = QComboBox()
        try:
            sd = getattr(self.audio_monitor, '_sd', None)
            devs = sd.query_devices() if sd else []
            loopbacks = []; normals = []
            for i, d in enumerate(devs):
                try:
                    if int(d.get('max_input_channels', 0)) <= 0: continue
                    host = d.get('hostapi_name', '') or ''
                    name = d.get('name', f'Device {i}')
                    lname = name.lower()
                    if ('wasapi' in host.lower()) and ('loopback' in lname or 'stereo mix' in lname or 'what u hear' in lname):
                        loopbacks.append((i, name, host))
                    else:
                        normals.append((i, name, host))
                except Exception:
                    continue
            for i, name, host in (loopbacks + normals):
                cmb_device.addItem(f"[{i}] {name} ({host})", i)
            cur = int(getattr(self, 'monitor_device_id', -1))
            idx = cmb_device.findData(cur)
            if idx >= 0:
                cmb_device.setCurrentIndex(idx)
        except Exception:
            cmb_device.addItem("No devices available"); cmb_device.setEnabled(False)
        pb_rms = QProgressBar(); pb_rms.setRange(0, 100); pb_rms.setFormat('RMS: %p%')
        try:
            self.audio_monitor.rmsUpdated.connect(lambda v: pb_rms.setValue(int(max(0.0, min(1.0, float(v))) * 100)))
        except Exception:
            pass
        s_threshold = QDoubleSpinBox(); s_threshold.setRange(0.001, 1.0); s_threshold.setSingleStep(0.005); s_threshold.setDecimals(4)
        s_threshold.setToolTip("Lower values = more sensitive to quiet sounds")
        s_threshold.setValue(float(getattr(self, 'silence_threshold', 0.03)))
        s_resume = QDoubleSpinBox(); s_resume.setRange(0.001, 1.0); s_resume.setSingleStep(0.005); s_resume.setDecimals(4)
        s_resume.setToolTip("Threshold used to leave silence; typically ≥ silence threshold")
        s_resume.setValue(float(getattr(self, 'resume_threshold', max(0.03, getattr(self, 'silence_threshold', 0.03) * 1.5))))
        s_silence = QDoubleSpinBox(); s_silence.setRange(0.5, 60.0); s_silence.setSingleStep(0.5); s_silence.setSuffix(" minutes")
        s_silence.setValue(float(getattr(self, 'silence_duration_s', 300.0)) / 60.0)
        chk_auto = QCheckBox(); chk_auto.setChecked(bool(getattr(self, 'auto_play_enabled', True)))
        f_mon.addRow("Monitor system output:", chk_monitor_system)
        f_mon.addRow("Input device:", cmb_device)
        f_mon.addRow("Live level:", pb_rms)
        f_mon.addRow("Silence threshold:", s_threshold)
        f_mon.addRow("Resume threshold:", s_resume)
        f_mon.addRow("Auto-play after silence:", s_silence)
        f_mon.addRow("Enable auto-play on silence:", chk_auto)
        tabs.addTab(w_mon, "Audio Monitor")

        # UI & Panels tab
        w_ui = QWidget(); f_ui = QFormLayout(w_ui)
        chk_show_up_next = QCheckBox(); chk_show_up_next.setChecked(bool(getattr(self, 'show_up_next', True)))
        chk_start_collapsed = QCheckBox(); chk_start_collapsed.setChecked(bool(getattr(self, 'up_next_collapsed', False)))
        chk_thumbs = QCheckBox(); chk_thumbs.setChecked(bool(getattr(self, 'show_thumbnails', True)))
        f_ui.addRow("Show Up Next:", chk_show_up_next)
        f_ui.addRow("Start collapsed:", chk_start_collapsed)
        f_ui.addRow("Show thumbnails:", chk_thumbs)
        tabs.addTab(w_ui, "UI")
        
        # Diagnostics tab
        w_diag = QWidget()
        f_diag = QFormLayout(w_diag)
        
        # Logging section
        lbl_log = QLabel("Logging & Diagnostics")
        lbl_log.setStyleSheet("font-weight: bold; margin-top: 10px;")
        f_diag.addRow(lbl_log)
        
        log_level_combo = QComboBox()
        log_level_combo.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR'])
        log_level_combo.setCurrentText(self.log_level)
        f_diag.addRow("Log Level:", log_level_combo)
        
        logs_btn = QPushButton("Open Logs Folder")
        logs_btn.clicked.connect(self.open_logs_folder)
        f_diag.addRow("", logs_btn)
        
        export_btn = QPushButton("Export Diagnostics")
        export_btn.clicked.connect(self.export_diagnostics)
        f_diag.addRow("", export_btn)
        
        tabs.addTab(w_diag, "Diagnostics")
        
        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); layout.addWidget(btns)

        def _apply():
            # Playback
            try:
                self.completed_percent = int(spn_completed.value())
            except Exception:
                pass
            try:
                self.skip_completed = bool(chk_skip_completed.isChecked())
            except Exception:
                pass
            try:
                self.playback_model = 'scoped' if (cmb_model.currentIndex() == 0) else 'queue'
                self._update_group_toggle_visibility()
            except Exception:
                pass

            # Audio Monitor
            try:
                self.monitor_system_output = bool(chk_monitor_system.isChecked())
            except Exception:
                pass
            try:
                did = cmb_device.currentData()
                if did is not None:
                    self.monitor_device_id = int(did)
            except Exception:
                pass
            try:
                self.silence_threshold = float(s_threshold.value())
            except Exception:
                pass
            try:
                self.resume_threshold = float(s_resume.value())
            except Exception:
                self.resume_threshold = max(self.silence_threshold, self.silence_threshold * 1.5)
            try:
                self.silence_duration_s = float(s_silence.value()) * 60.0
            except Exception:
                pass
            try:
                self.auto_play_enabled = bool(chk_auto.isChecked())
            except Exception:
                pass
            # Hot-apply to running monitor
            try:
                if getattr(self, 'audio_monitor', None):
                    self.audio_monitor.update_settings(
                        silence_duration_s=self.silence_duration_s,
                        silence_threshold=self.silence_threshold,
                        resume_threshold=self.resume_threshold,
                        monitor_system_output=self.monitor_system_output,
                        device_id=self.monitor_device_id
                    )
            except Exception:
                pass

            # UI & Panels
            try:
                self.show_up_next = bool(chk_show_up_next.isChecked())
                self.up_next_collapsed = bool(chk_start_collapsed.isChecked())
                self.show_thumbnails = bool(chk_thumbs.isChecked())
                self._refresh_playlist_widget()
                # Apply Up Next visibility immediately
                if hasattr(self, 'up_next_container'):
                    self.up_next_container.setVisible(self.show_up_next)
                if hasattr(self, 'up_next_header'):
                    self.up_next_header.setChecked(not self.up_next_collapsed)
                    self._toggle_up_next_visible(self.up_next_header.isChecked())
                # Refresh filters
                self._apply_filters_to_tree()
            except Exception:
                pass

            
            # Inactivity
            try:
                self.afk_timeout_minutes = int(s_afk.value())
                if getattr(self, 'afk_monitor', None):
                    self.afk_monitor.timeout_seconds = self.afk_timeout_minutes * 60
            except Exception:
                pass

            # Persist
            try:
                self._save_settings()
            except Exception:
                pass
            dlg.accept()

        btns.accepted.connect(_apply)
        btns.rejected.connect(dlg.reject)
        dlg.exec()
    def open_settings(self):
        dlg = QDialog(self); dlg.setWindowTitle("Settings"); dlg.resize(400, 300)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        
        # Audio monitoring settings
        c_monitor_system = QCheckBox()
        c_monitor_system.setChecked(getattr(self.audio_monitor, 'monitor_system_output', True))
        c_monitor_system.setToolTip("Monitor system audio output (speakers/headphones) instead of microphone")
        form.addRow("Monitor system output:", c_monitor_system)

        # Live RMS meter (0-100%)
        pb_rms = QProgressBar(); pb_rms.setRange(0, 100); pb_rms.setFormat('RMS: %p%')
        try:
            self.audio_monitor.rmsUpdated.connect(lambda v: pb_rms.setValue(int(max(0.0, min(1.0, float(v))) * 100)))
        except Exception:
            pass
        form.addRow("Live level:", pb_rms)
        
        # Input device (prioritize WASAPI loopback-capable inputs)
        c_device = QComboBox()
        try:
            sd = getattr(self.audio_monitor, '_sd', None)
            devs = sd.query_devices() if sd else []
            loopbacks = []; normals = []
            for i, d in enumerate(devs):
                try:
                    if int(d.get('max_input_channels', 0)) <= 0:
                        continue
                    host = d.get('hostapi_name', '') or ''
                    name = d.get('name', f'Device {i}')
                    item = (i, name, host)
                    lname = name.lower()
                    if ('wasapi' in host.lower()) and ('loopback' in lname or 'stereo mix' in lname or 'what u hear' in lname):
                        loopbacks.append(item)
                    else:
                        normals.append(item)
                except Exception:
                    continue
            for i, name, host in (loopbacks + normals):
                c_device.addItem(f"[{i}] {name} ({host})", i)
            cur = int(getattr(self, 'monitor_device_id', -1))
            idx = c_device.findData(cur)
            if idx >= 0:
                c_device.setCurrentIndex(idx)
        except Exception:
            c_device.addItem("No devices available"); c_device.setEnabled(False)
        form.addRow("Input device:", c_device)
        
        s_threshold = QDoubleSpinBox()
        s_threshold.setRange(0.001, 1.0)
        s_threshold.setSingleStep(0.001)
        s_threshold.setDecimals(3)
        s_threshold.setValue(getattr(self.audio_monitor, 'threshold', 0.03))
        s_threshold.setToolTip("Lower values = more sensitive to quiet sounds")
        form.addRow("Silence threshold:", s_threshold)

        # Hysteresis resume threshold (leaving silence)
        s_resume = QDoubleSpinBox(); s_resume.setRange(0.001, 1.0); s_resume.setSingleStep(0.005); s_resume.setDecimals(4)
        s_resume.setToolTip("Threshold used to leave silence; typically ≥ silence threshold")
        try:
            s_resume.setValue(float(getattr(self, 'resume_threshold', max(0.03, getattr(self, 'silence_threshold', 0.03) * 1.5))))
        except Exception:
            s_resume.setValue(max(0.03, getattr(self, 'silence_threshold', 0.03) * 1.5))
        form.addRow("Resume threshold:", s_resume)

        # Completed threshold percent
        s_completed = QSpinBox()
        s_completed.setRange(50, 100); s_completed.setSuffix("%")
        s_completed.setValue(int(getattr(self, 'completed_percent', 95)))
        form.addRow("Completed threshold:", s_completed)

        # Skip completed toggle
        c_skip_completed = QCheckBox()
        c_skip_completed.setChecked(bool(getattr(self, 'skip_completed', False)))
        c_skip_completed.setToolTip("If enabled, items marked as completed will be auto-skipped when starting playback")
        form.addRow("Skip completed:", c_skip_completed)
        # Up Next toggle
        c_show_up_next = QCheckBox(); c_show_up_next.setChecked(bool(getattr(self, 'show_up_next', True)))
        form.addRow("Show Up Next:", c_show_up_next)
        
        s_silence = QDoubleSpinBox()
        s_silence.setRange(0.5, 60.0)
        s_silence.setSingleStep(0.5)
        s_silence.setSuffix(" minutes")
        s_silence.setValue(self.silence_duration_s/60.0)
        form.addRow("Auto-play after silence:", s_silence)
        
        s_afk = QSpinBox()
        s_afk.setRange(1, 120)
        s_afk.setValue(self.afk_timeout_minutes)
        s_afk.setSuffix(" minutes")
        form.addRow("Auto-pause after inactivity:", s_afk)
        
        c_auto = QCheckBox()
        c_auto.setChecked(self.auto_play_enabled)
        form.addRow("Enable auto-play on silence:", c_auto)
        
        c_thumb = QCheckBox()
        c_thumb.setChecked(self.show_thumbnails)
        form.addRow("Show thumbnails:", c_thumb)
        
        # Playback model selector
        m_model = QComboBox(); m_model.addItems(["Scoped Library", "Queue"]) 
        m_model.setCurrentIndex(0 if getattr(self, 'playback_model', 'scoped') == 'scoped' else 1)
        form.addRow("Playback model:", m_model)

        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(btns)
        
        def _apply():
            # Update settings
            old_monitor_system = getattr(self.audio_monitor, 'monitor_system_output', True)
            old_threshold = getattr(self.audio_monitor, 'threshold', 0.03)
            
            self.silence_duration_s = float(s_silence.value() * 60.0)
            self.afk_timeout_minutes = int(s_afk.value())
            self.auto_play_enabled = bool(c_auto.isChecked())
            self.show_thumbnails = bool(c_thumb.isChecked())
            
            new_monitor_system = bool(c_monitor_system.isChecked())
            new_threshold = float(s_threshold.value())
            new_dev_id = c_device.currentData() if 'c_device' in locals() else None
            # Persist to instance
            self.monitor_system_output = new_monitor_system
            self.silence_threshold = new_threshold
            self.monitor_device_id = new_dev_id
            self.completed_percent = int(s_completed.value())
            # Skip completed
            try:
                self.skip_completed = bool(c_skip_completed.isChecked())
                # Monitor settings and thresholds
                try:
                    self.monitor_system_output = bool(c_monitor_system.isChecked())
                except Exception:
                    pass
                try:
                    self.silence_threshold = float(s_threshold.value())
                except Exception:
                    pass
                try:
                    self.resume_threshold = float(s_resume.value())
                except Exception:
                    self.resume_threshold = max(self.silence_threshold, self.silence_threshold * 1.5)
                # Hot-apply to running monitor
                try:
                    if getattr(self, 'audio_monitor', None):
                        self.audio_monitor.update_settings(
                            silence_duration_s=self.silence_duration_s,
                            silence_threshold=self.silence_threshold,
                            resume_threshold=self.resume_threshold,
                            monitor_system_output=self.monitor_system_output,
                            device_id=self.monitor_device_id
                        )
                except Exception:
                    pass
                self.show_up_next = bool(c_show_up_next.isChecked())
                # Apply Up Next visibility immediately
                try:
                    if hasattr(self, 'up_next_container'):
                        self.up_next_container.setVisible(self.show_up_next)
                except Exception:
                    pass
            except Exception:
                pass
            
            # Update audio monitor settings
            if getattr(self, 'audio_monitor', None):
                self.audio_monitor.update_settings(
                    silence_duration_s=self.silence_duration_s,
                    silence_threshold=new_threshold,
                    monitor_system_output=new_monitor_system
                )
                
                # Restart audio monitor if monitoring mode or threshold changed significantly
                if (old_monitor_system != new_monitor_system or 
                    abs(old_threshold - new_threshold) > 0.005 or
                    int(getattr(self, 'monitor_device_id', new_dev_id)) != new_dev_id):
                    self._restart_audio_monitor()
            
            # Update AFK monitor
            if getattr(self, 'afk_monitor', None):
                self.afk_monitor.timeout_seconds = self.afk_timeout_minutes * 60

            # Apply playback model selection
            self.playback_model = 'scoped' if m_model.currentIndex() == 0 else 'queue'
            try:
                self._update_group_toggle_visibility()
            except Exception:
                pass
            try:
                self._update_scope_label()
            except Exception:
                pass
            self._refresh_playlist_widget()
            
            # Diagnostics
            try:
                old_level = self.log_level
                self.log_level = log_level_combo.currentText()
                if old_level != self.log_level:
                    # Reinitialize logging with new level
                    logging.getLogger().setLevel(getattr(logging, self.log_level.upper(), logging.INFO))
                    logger.info(f"Log level changed from {old_level} to {self.log_level}")
            except Exception as e:
                logger.error(f"Failed to apply diagnostics settings: {e}")
            
            self._save_settings()
            dlg.accept()
            self.status.showMessage("Settings saved", 4000)
        
        btns.accepted.connect(_apply)
        btns.rejected.connect(dlg.reject)
        dlg.exec()

    def _on_playlist_items_ready(self, items: list):
        if not items:
            self.status.showMessage("No entries found in playlist", 4000)
            return
        base_count = len(self.playlist)
        # Deduplicate by URL
        existing = set(it.get('url') for it in self.playlist if isinstance(it, dict))
        new_items = []
        for it in items:
            u = it.get('url')
            if not u or u in existing:
                continue
            existing.add(u)
            new_items.append(it)
        self.playlist.extend(new_items)
        self._save_current_playlist(); self._refresh_playlist_widget()
        self.status.showMessage(f"Added {len(new_items)} entries (total {len(self.playlist)})", 5000)
        # Background resolve titles for items with placeholder titles
        try:
            need = [it for it in new_items if not it.get('title') or it['title'] == it.get('url')]
            if need:
                w = TitleResolveWorker(need, items[0].get('type', 'local'))
                self._title_workers.append(w)
                w.titleResolved.connect(self._on_title_resolved)
                w.error.connect(lambda e: self.status.showMessage(e, 4000))
                w.finished.connect(lambda w=w: (self._title_workers.remove(w) if w in self._title_workers else None))
                w.start()
        except Exception:
            pass
            
    def _restart_audio_monitor(self):
        """Restart the audio monitor with new settings"""
        if hasattr(self, 'audio_monitor') and self.audio_monitor:
            # Stop current monitor
            self.audio_monitor.stop()
            self.audio_monitor.wait(2000)  # Wait up to 2 seconds
            
            # Create new monitor with current settings
            monitor_system = getattr(self.audio_monitor, 'monitor_system_output', True)
            threshold = getattr(self.audio_monitor, 'threshold', 0.03)
            
            self.audio_monitor = SystemAudioMonitor(
                silence_duration_s=self.silence_duration_s,
                silence_threshold=threshold,
                monitor_system_output=monitor_system,
                device_id=self.monitor_device_id
            )
            self.audio_monitor.silenceDetected.connect(self.on_silence_detected)
            self.audio_monitor.audioStateChanged.connect(self._update_silence_indicator)
            self.audio_monitor.start()

    def open_help(self):
        dlg = QDialog(self); dlg.setWindowTitle("Keyboard Shortcuts"); dlg.resize(420, 360)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        def add(k, desc):
            try:
                form.addRow(QLabel(k), QLabel(desc))
            except Exception:
                pass
        add("Space", "Play/Pause")
        add("N", "Next")
        add("P", "Previous")
        add("S", "Toggle Shuffle")
        add("R", "Toggle Repeat")
        add("Ctrl+L", "Add Link")
        add("Delete", "Remove selected")
        add("+ / =", "Volume up")
        add("-", "Volume down")
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Close); btns.rejected.connect(dlg.reject); layout.addWidget(btns)
        dlg.exec()

    # Stats dialog
    def open_stats(self):
        dlg = QDialog(self); dlg.setWindowTitle("Listening Statistics"); dlg.resize(780, 460)
        layout = QVBoxLayout(dlg)
        overall = QLabel(f"Total time: {human_duration(self.listening_stats.get('overall', 0))}")
        layout.addWidget(overall)

        # Heatmap
        daily = dict(self.listening_stats.get('daily', {}))
        heat = StatsHeatmapWidget(daily, theme=getattr(self, 'theme', 'dark'))
        layout.addWidget(heat)

        # Metrics under heatmap
        def _compute_metrics(dmap):
            import datetime as _dt
            if not dmap:
                return 0, 0.0
            items = []
            for k, v in dmap.items():
                try:
                    y, m, d = [int(x) for x in k.split('-')]
                    items.append((_dt.date(y, m, d), float(v or 0)))
                except Exception:
                    continue
            if not items:
                return 0, 0.0
            items.sort(key=lambda x: x[0])
            # Average over non-zero days
            nz = [v for _, v in items if v > 0]
            avg = (sum(nz) / len(nz)) if nz else 0.0
            # Longest consecutive-day streak with >0 seconds
            longest = cur = 0
            prev_date = None
            for dte, val in items:
                if val > 0:
                    if prev_date is not None and dte == prev_date + _dt.timedelta(days=1):
                        cur += 1
                    else:
                        cur = 1
                else:
                    cur = 0
                if cur > longest:
                    longest = cur
                prev_date = dte
            return int(longest), float(avg)

        _longest, _avg_sec = _compute_metrics(daily)
        metrics = QLabel(f"Longest streak: {_longest} days    •    Average daily: {human_duration(_avg_sec)}")
        layout.addWidget(metrics)

        # Table and filter controls
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Date", "Time Listened"])
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        # Make the table read-only (disable in-place editing) but keep selection/navigation
        try:
            from PySide6.QtWidgets import QAbstractItemView
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
        except Exception:
            pass
        layout.addWidget(table)

        flt = QHBoxLayout()
        selected_label = QLabel("Click a day in the heatmap to filter the table"); flt.addWidget(selected_label); flt.addStretch()
        show_all_btn = QPushButton("Show All"); show_all_btn.setVisible(False); flt.addWidget(show_all_btn)
        layout.addLayout(flt)

        def rebuild_table(filter_date=None):
            rows = sorted(daily.items(), key=lambda x: x[0], reverse=True)
            if filter_date:
                rows = [(d, s) for d, s in rows if d == filter_date]
                sel_sec = daily.get(filter_date, 0)
                selected_label.setText(f"Selected: {filter_date} — {human_duration(sel_sec)}")
                show_all_btn.setVisible(True)
            else:
                selected_label.setText("Click a day in the heatmap to filter the table")
                show_all_btn.setVisible(False)
            table.setRowCount(len(rows))
            for r, (d, sec) in enumerate(rows):
                it0 = QTableWidgetItem(d)
                try:
                    it0.setFlags(it0.flags() & ~Qt.ItemIsEditable)
                except Exception:
                    pass
                table.setItem(r, 0, it0)

                it1 = QTableWidgetItem(human_duration(sec))
                try:
                    it1.setFlags(it1.flags() & ~Qt.ItemIsEditable)
                except Exception:
                    pass
                table.setItem(r, 1, it1)
            table.resizeColumnsToContents()

        heat.daySelected.connect(lambda d: rebuild_table(d))
        show_all_btn.clicked.connect(lambda: rebuild_table(None))
        rebuild_table(None)

        btns = QDialogButtonBox(QDialogButtonBox.Close); btns.rejected.connect(dlg.reject); layout.addWidget(btns)
        layout = QVBoxLayout(dlg)
        overall = QLabel(f"Total time: {human_duration(self.listening_stats.get('overall', 0))}")
        layout.addWidget(overall)
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Date", "Time Listened"])
        # Make the table read-only
        try:
            from PySide6.QtWidgets import QAbstractItemView
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
        except Exception:
            pass

        daily = self.listening_stats.get('daily', {})
        rows = sorted(daily.items(), key=lambda x: x[0], reverse=True)
        table.setRowCount(len(rows))
        for i, (day, secs) in enumerate(rows):
            it0 = QTableWidgetItem(day)
            try:
                it0.setFlags(it0.flags() & ~Qt.ItemIsEditable)
            except Exception:
                pass
            table.setItem(i, 0, it0)

            it1 = QTableWidgetItem(human_duration(secs))
            try:
                it1.setFlags(it1.flags() & ~Qt.ItemIsEditable)
            except Exception:
                pass
            table.setItem(i, 1, it1)

        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(table)
        reset = QPushButton("Reset All Stats"); reset.clicked.connect(lambda: self._reset_stats(dlg)); layout.addWidget(reset)
        btns = QDialogButtonBox(QDialogButtonBox.Close); btns.rejected.connect(dlg.reject); layout.addWidget(btns)
        dlg.exec()

    def _reset_stats(self, dlg):
        if QMessageBox.question(self, "Reset Stats", "Are you sure?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.listening_stats = {'daily': {}, 'overall': 0}
            try:
                json.dump(self.listening_stats, open(CFG_STATS, 'w', encoding='utf-8'))
            except Exception:
                pass
            dlg.accept(); self.update_badge()

    def _toggle_auto_play(self):
        self.auto_play_enabled = self.auto_play_checkbox.isChecked()
        self._save_settings()

    # Stats/badge
    def _start_session(self):
        # Begin a listening session for stats/badge
        self.session_start_time = time.time()
        self.last_position_update = self.session_start_time

    def _end_session(self):
        if self.session_start_time:
            try:
                self._update_listening_stats()
            except Exception:
                pass
            self.session_start_time = None

    def _update_listening_stats(self):
        if not self._is_playing() or not self.session_start_time:
            return
        duration = time.time() - self.session_start_time
        today = datetime.now().strftime('%Y-%m-%d')
        self.listening_stats.setdefault('daily', {})
        self.listening_stats['daily'][today] = self.listening_stats['daily'].get(today, 0) + duration
        self.listening_stats['overall'] = self.listening_stats.get('overall', 0) + duration
        self.session_start_time = time.time()
        try:
            json.dump(self.listening_stats, open(CFG_STATS, 'w', encoding='utf-8'))
        except Exception:
            pass

    def update_badge(self):
        today = datetime.now().strftime('%Y-%m-%d')
        base = self.listening_stats.get('daily', {}).get(today, 0.0)
        if self._is_playing() and self.session_start_time:
            base += time.time() - self.session_start_time
        self.today_badge.setText(human_duration(base))

    # Resume positions
    def _save_current_position(self):
        if not (0 <= self.current_index < len(self.playlist)):
            return
        try:
            # Use last observed play position from mpv observer to avoid stale reads
            pos = int(self._last_play_pos_ms or 0)
            if pos <= 5000:
                return
            dur_sec = self.mpv.duration
            dur = int(float(dur_sec) * 1000) if dur_sec else 0
            # Do not save within last 10s when duration is known
            if dur > 0 and pos >= dur - 10000:
                return
            # During enforcement window, ignore saves that are below target by >2s
            if getattr(self, '_resume_target_ms', 0) > 0 and time.time() < getattr(self, '_resume_enforce_until', 0.0):
                tgt = int(self._resume_target_ms)
                if pos < tgt - 2000:
                    print(f"[resume] guard skip (below target) at {format_time(pos)} target {format_time(tgt)}")
                    return
            item = self.playlist[self.current_index]
            url = item.get('url')
            # Only save if advanced by >=5s since last save for this URL
            prev = self._last_saved_pos_ms.get(url, -1)
            if prev >= 0 and (pos - prev) < 5000:
                print(f"[resume] skip (no movement) at {format_time(pos)} for {url}")
                return
            self.playback_positions[url] = pos
            self._last_saved_pos_ms[url] = pos
            self._save_positions()
            print(f"[resume] saved {format_time(pos)} for {url}")
        except Exception as e:
            print(f"_save_current_position error: {e}")

    # Helpers
    def _is_playing(self):
        try:
            return not bool(self.mpv.pause) and not bool(self.mpv.idle_active)
        except Exception:
            return False

    def filter_playlist(self, text: str):
        root = self.playlist_tree.topLevelItem(0)
        if not root: return
        query = text.lower().strip()
        # If grouped, hide sub-items not matching and collapse empty groups
        if getattr(self, 'grouped_view', False) and root.childCount() > 0 and root.child(0).data(0, Qt.UserRole):
            for i in range(root.childCount()):
                g = root.child(i)
                data = g.data(0, Qt.UserRole)
                if not data or data[0] != 'group':
                    # Not a group, treat as item row
                    g.setHidden(query not in g.text(0).lower())
                    continue
                any_visible = False
                for j in range(g.childCount()):
                    c = g.child(j)
                    match = query in c.text(0).lower()
                    c.setHidden(not match)
                    any_visible = any_visible or match
                g.setHidden(not any_visible)
        else:
            for i in range(root.childCount()):
                child = root.child(i)
                child.setHidden(query not in child.text(0).lower())

    # Silence + AFK handlers
    def on_silence_detected(self):
        if self.auto_play_enabled and self.playlist and (not self._is_playing()):
            self.status.showMessage("System silence detected - Auto-playing next", 4000)
            self.next_track()

    def on_user_afk(self):
        if self._is_playing():
            self.toggle_play_pause(); self.status.showMessage("Paused due to inactivity", 4000)

    # Keyboard shortcuts
    def _setup_keyboard_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Space), self, self.toggle_play_pause)
        QShortcut(QKeySequence(Qt.Key_F1), self, self.open_help)
        QShortcut(QKeySequence(Qt.Key_N), self, self.next_track)
        QShortcut(QKeySequence(Qt.Key_P), self, self.previous_track)
        QShortcut(QKeySequence(Qt.Key_S), self, self._toggle_shuffle_shortcut)
        QShortcut(QKeySequence(Qt.Key_R), self, self._toggle_repeat_shortcut)
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_L), self, self.add_link_dialog)
        QShortcut(QKeySequence(Qt.Key_Delete), self, self._remove_selected_items)
        QShortcut(QKeySequence(Qt.Key_Plus), self, self._volume_up)
        QShortcut(QKeySequence(Qt.Key_Equal), self, self._volume_up)  # also '=' key
        QShortcut(QKeySequence(Qt.Key_Minus), self, self._volume_down)

    def _toggle_shuffle_shortcut(self):
        self.shuffle_btn.setChecked(not self.shuffle_btn.isChecked())
        self._toggle_shuffle()

    def _toggle_repeat_shortcut(self):
        self.repeat_btn.setChecked(not self.repeat_btn.isChecked())
        self._toggle_repeat()

    def _remove_selected_items(self):
        items = self.playlist_tree.selectedItems()
        if not items:
            return
        indices = []
        for it in items:
            data = it.data(0, Qt.UserRole)
            if isinstance(data, tuple) and data[0] == 'current':
                indices.append(data[1])
        for idx in sorted(indices, reverse=True):
            self._remove_index(idx)

    def _volume_up(self):
        v = min(100, self.volume_slider.value() + 5)
        self.volume_slider.setValue(v)
        self.set_volume(v)
        self.status.showMessage(f"Volume: {v}%", 1500)

    def _volume_down(self):
        v = max(0, self.volume_slider.value() - 5)
        self.volume_slider.setValue(v)
        self.set_volume(v)
        self.status.showMessage(f"Volume: {v}%", 1500)

    # Window + close
    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                QTimer.singleShot(100, self.hide); return
        super().changeEvent(event)

    def closeEvent(self, event):
        try:
            if hasattr(self, 'audio_monitor') and self.audio_monitor is not None:
                self.audio_monitor.stop()
                self.audio_monitor.wait()
            if hasattr(self, 'afk_monitor') and self.afk_monitor is not None:
                self.afk_monitor.stop()
                self.afk_monitor.wait()
        except Exception:
            pass
        # Persist window/setting state on close
        try:
            self._save_settings()
        except Exception:
            pass
        event.accept()

def main():
    app = QApplication(sys.argv)
    w = MediaPlayer()
    # Initialize typography AFTER the window builds and applies its theme so our QSS lands last
    from ui.typography import TypographyManager
    typo = TypographyManager(app, project_root=APP_DIR)
    typo.install()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
