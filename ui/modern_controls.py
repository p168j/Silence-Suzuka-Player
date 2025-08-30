#!/usr/bin/env python3
"""
Modern Control Panel for Silence Suzuka Player

Implements the bottom control area design with progress bar,
time labels, and animated buttons from the mockups.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
    QSlider, QProgressBar, QFrame
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QLinearGradient, QColor
from typing import Optional

from .animated_buttons import PlayPauseButton, ControlButton, AddMediaButton, VolumeButton


class ModernProgressBar(QSlider):
    """Custom progress bar with Spotify-style appearance"""
    
    position_changed = Signal(int)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(Qt.Horizontal, parent)
        self.setFixedHeight(20)
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: #535353;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #1DB954;
                border: none;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #1ed760;
            }
            QSlider::sub-page:horizontal {
                background: #1DB954;
                border-radius: 2px;
            }
        """)
        
        self.valueChanged.connect(self.position_changed.emit)


class TimeLabel(QLabel):
    """Styled time label for current/total time display"""
    
    def __init__(self, text: str = "0:00", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setFixedWidth(40)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #B3B3B3;
                font-weight: 500;
            }
        """)
        
    def set_time(self, seconds: int):
        """Set time from seconds"""
        minutes = seconds // 60
        secs = seconds % 60
        self.setText(f"{minutes}:{secs:02d}")


class ModernControlPanel(QWidget):
    """
    Modern control panel implementing the bottom controls design.
    Includes now playing info, progress bar, and control buttons.
    """
    
    # Signals
    play_pause_clicked = Signal()
    previous_clicked = Signal()
    next_clicked = Signal()
    shuffle_toggled = Signal(bool)
    repeat_toggled = Signal(bool)
    volume_changed = Signal(int)
    position_changed = Signal(int)
    add_media_clicked = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("modernControls")
        self._setup_ui()
        self._setup_styling()
        self._connect_signals()
        
    def _setup_ui(self):
        """Setup the control panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Now playing section
        self.now_playing_widget = QWidget()
        now_playing_layout = QVBoxLayout(self.now_playing_widget)
        now_playing_layout.setAlignment(Qt.AlignCenter)
        now_playing_layout.setSpacing(8)
        
        self.track_title = QLabel("No track selected")
        self.track_title.setObjectName("trackLabel")
        self.track_title.setAlignment(Qt.AlignCenter)
        now_playing_layout.addWidget(self.track_title)
        
        layout.addWidget(self.now_playing_widget)
        
        # Progress section
        progress_widget = QWidget()
        progress_layout = QHBoxLayout(progress_widget)
        progress_layout.setSpacing(12)
        
        self.current_time_label = TimeLabel("0:00")
        self.current_time_label.setObjectName("currentTimeLabel")
        
        self.progress_bar = ModernProgressBar()
        
        self.total_time_label = TimeLabel("0:00")
        self.total_time_label.setObjectName("totalTimeLabel")
        
        progress_layout.addWidget(self.current_time_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.total_time_label)
        
        layout.addWidget(progress_widget)
        
        # Control buttons section
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setAlignment(Qt.AlignCenter)
        controls_layout.setSpacing(20)
        
        # Left side controls
        self.shuffle_btn = ControlButton("🔀")
        self.previous_btn = ControlButton("⏮")
        
        # Center play/pause
        self.play_pause_btn = PlayPauseButton()
        
        # Right side controls
        self.next_btn = ControlButton("⏭")
        self.repeat_btn = ControlButton("🔁")
        
        controls_layout.addWidget(self.shuffle_btn)
        controls_layout.addWidget(self.previous_btn)
        controls_layout.addWidget(self.play_pause_btn)
        controls_layout.addWidget(self.next_btn)
        controls_layout.addWidget(self.repeat_btn)
        
        layout.addWidget(controls_widget)
        
        # Bottom section with add media and volume
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setSpacing(20)
        
        # Add media button (left)
        self.add_media_btn = AddMediaButton()
        bottom_layout.addWidget(self.add_media_btn)
        
        bottom_layout.addStretch()
        
        # Volume controls (right)
        volume_widget = QWidget()
        volume_layout = QHBoxLayout(volume_widget)
        volume_layout.setSpacing(10)
        
        self.volume_down_btn = VolumeButton("🔉")
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: #535353;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #1DB954;
                border: none;
                width: 8px;
                height: 8px;
                margin: -2px 0;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #1DB954;
                border-radius: 2px;
            }
        """)
        
        self.volume_up_btn = VolumeButton("🔊")
        
        volume_layout.addWidget(self.volume_down_btn)
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_up_btn)
        
        bottom_layout.addWidget(volume_widget)
        
        layout.addWidget(bottom_widget)
        
    def _setup_styling(self):
        """Setup the control panel styling"""
        self.setStyleSheet("""
            #modernControls {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a1a, stop:1 #111111);
                border-top: 1px solid #282828;
                border-radius: 12px;
            }
            #trackLabel {
                font-size: 24px;
                font-weight: bold;
                color: #FFFFFF;
            }
            #currentTimeLabel, #totalTimeLabel {
                font-size: 12px;
                color: #B3B3B3;
                font-weight: 500;
            }
        """)
        
    def _connect_signals(self):
        """Connect internal signals"""
        self.play_pause_btn.play_clicked.connect(self.play_pause_clicked.emit)
        self.play_pause_btn.pause_clicked.connect(self.play_pause_clicked.emit)
        
        self.previous_btn.clicked.connect(self.previous_clicked.emit)
        self.next_btn.clicked.connect(self.next_clicked.emit)
        
        self.shuffle_btn.clicked.connect(self._on_shuffle_clicked)
        self.repeat_btn.clicked.connect(self._on_repeat_clicked)
        
        self.add_media_btn.clicked.connect(self.add_media_clicked.emit)
        
        self.volume_down_btn.clicked.connect(self._on_volume_down)
        self.volume_up_btn.clicked.connect(self._on_volume_up)
        self.volume_slider.valueChanged.connect(self.volume_changed.emit)
        
        self.progress_bar.position_changed.connect(self.position_changed.emit)
        
    def _on_shuffle_clicked(self):
        """Handle shuffle button click"""
        self.shuffle_btn.toggle_active()
        self.shuffle_toggled.emit(self.shuffle_btn.is_active)
        
    def _on_repeat_clicked(self):
        """Handle repeat button click"""
        self.repeat_btn.toggle_active()
        self.repeat_toggled.emit(self.repeat_btn.is_active)
        
    def _on_volume_down(self):
        """Handle volume down"""
        current = self.volume_slider.value()
        self.volume_slider.setValue(max(0, current - 10))
        
    def _on_volume_up(self):
        """Handle volume up"""
        current = self.volume_slider.value()
        self.volume_slider.setValue(min(100, current + 10))
        
    def update_track_info(self, title: str, artist: str = ""):
        """Update the currently playing track information"""
        display_text = title
        if artist:
            display_text = f"{title} - {artist}"
        self.track_title.setText(display_text)
        
    def update_progress(self, current_seconds: int, total_seconds: int):
        """Update progress bar and time labels"""
        self.current_time_label.set_time(current_seconds)
        self.total_time_label.set_time(total_seconds)
        
        if total_seconds > 0:
            progress_percent = int((current_seconds / total_seconds) * 100)
            self.progress_bar.setValue(progress_percent)
            
    def update_playback_state(self, is_playing: bool):
        """Update the playback state"""
        self.play_pause_btn.set_playing_state(is_playing)
        
    def update_volume(self, volume: int):
        """Update volume slider"""
        self.volume_slider.setValue(volume)
        
    def set_shuffle_active(self, active: bool):
        """Set shuffle button state"""
        self.shuffle_btn.set_active(active)
        
    def set_repeat_active(self, active: bool):
        """Set repeat button state"""
        self.repeat_btn.set_active(active)