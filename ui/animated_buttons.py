#!/usr/bin/env python3
"""
Animated Button Components for Silence Suzuka Player

Implements bounce-back button animations and visual feedback
inspired by modern music player interfaces.
"""

from PySide6.QtWidgets import QPushButton, QWidget
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect, QTimer, Signal
from PySide6.QtGui import QPainter, QPen, QColor
from typing import Optional


class AnimatedButton(QPushButton):
    """Base class for buttons with bounce-back animation"""
    
    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(600)
        self.animation.setEasingCurve(QEasingCurve.OutElastic)
        self._original_geometry = None
        
    def mousePressEvent(self, event):
        """Handle mouse press with animation"""
        super().mousePressEvent(event)
        self._start_bounce_animation()
        
    def _start_bounce_animation(self):
        """Start the bounce-back animation"""
        if self._original_geometry is None:
            self._original_geometry = self.geometry()
            
        # Calculate shrink geometry (95% scale)
        original = self._original_geometry
        shrink_width = int(original.width() * 0.95)
        shrink_height = int(original.height() * 0.95)
        shrink_x = original.x() + (original.width() - shrink_width) // 2
        shrink_y = original.y() + (original.height() - shrink_height) // 2
        shrink_rect = QRect(shrink_x, shrink_y, shrink_width, shrink_height)
        
        # Calculate bounce geometry (115% scale)
        bounce_width = int(original.width() * 1.15)
        bounce_height = int(original.height() * 1.15)
        bounce_x = original.x() - (bounce_width - original.width()) // 2
        bounce_y = original.y() - (bounce_height - original.height()) // 2
        bounce_rect = QRect(bounce_x, bounce_y, bounce_width, bounce_height)
        
        # Set up animation sequence
        self.animation.finished.disconnect()  # Clear any existing connections
        
        # Phase 1: Shrink
        self.setGeometry(shrink_rect)
        
        # Phase 2: Bounce to larger size
        self.animation.setStartValue(shrink_rect)
        self.animation.setEndValue(bounce_rect)
        self.animation.setDuration(300)
        self.animation.finished.connect(self._finish_bounce)
        self.animation.start()
        
    def _finish_bounce(self):
        """Complete the bounce animation by returning to original size"""
        if self._original_geometry is None:
            return
            
        # Phase 3: Settle back to original
        self.animation.finished.disconnect()
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(self._original_geometry)
        self.animation.setDuration(300)
        self.animation.start()


class PlayPauseButton(AnimatedButton):
    """Primary play/pause button with state management"""
    
    play_clicked = Signal()
    pause_clicked = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("▶", parent)
        self.is_playing = False
        self.setFixedSize(60, 60)
        self.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #000000;
                border: none;
                border-radius: 30px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        """)
        
    def mousePressEvent(self, event):
        """Handle click with state toggle"""
        super().mousePressEvent(event)
        self.toggle_play_pause()
        
    def toggle_play_pause(self):
        """Toggle between play and pause states"""
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.setText("⏸")
            self.setStyleSheet("""
                QPushButton {
                    background-color: #1DB954;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 30px;
                    font-size: 24px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1ed760;
                }
                QPushButton:pressed {
                    background-color: #169c46;
                }
            """)
            self.play_clicked.emit()
        else:
            self.setText("▶")
            self.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF;
                    color: #000000;
                    border: none;
                    border-radius: 30px;
                    font-size: 24px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #f0f0f0;
                }
                QPushButton:pressed {
                    background-color: #e0e0e0;
                }
            """)
            self.pause_clicked.emit()

    def set_playing_state(self, playing: bool):
        """Set playing state without triggering signals"""
        if self.is_playing != playing:
            self.is_playing = playing
            if playing:
                self.setText("⏸")
                self.setStyleSheet("""
                    QPushButton {
                        background-color: #1DB954;
                        color: #FFFFFF;
                        border: none;
                        border-radius: 30px;
                        font-size: 24px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #1ed760;
                    }
                    QPushButton:pressed {
                        background-color: #169c46;
                    }
                """)
            else:
                self.setText("▶")
                self.setStyleSheet("""
                    QPushButton {
                        background-color: #FFFFFF;
                        color: #000000;
                        border: none;
                        border-radius: 30px;
                        font-size: 24px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #f0f0f0;
                    }
                    QPushButton:pressed {
                        background-color: #e0e0e0;
                    }
                """)


class ControlButton(AnimatedButton):
    """Control button (previous, next, shuffle, repeat) with toggle state"""
    
    def __init__(self, icon: str, parent: Optional[QWidget] = None):
        super().__init__(icon, parent)
        self.is_active = False
        self.setFixedSize(40, 40)
        self._update_style()
        
    def _update_style(self):
        """Update button style based on active state"""
        if self.is_active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: rgba(29, 185, 84, 0.2);
                    color: #1DB954;
                    border: none;
                    border-radius: 20px;
                    font-size: 18px;
                }
                QPushButton:hover {
                    background-color: rgba(29, 185, 84, 0.3);
                    color: #1ed760;
                }
                QPushButton:pressed {
                    background-color: rgba(29, 185, 84, 0.4);
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #B3B3B3;
                    border: none;
                    border-radius: 20px;
                    font-size: 18px;
                }
                QPushButton:hover {
                    background-color: #282828;
                    color: #FFFFFF;
                }
                QPushButton:pressed {
                    background-color: #383838;
                }
            """)
            
    def toggle_active(self):
        """Toggle active state"""
        self.is_active = not self.is_active
        self._update_style()
        
    def set_active(self, active: bool):
        """Set active state"""
        self.is_active = active
        self._update_style()


class AddMediaButton(AnimatedButton):
    """Add media button with distinctive styling"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("+ Add Media", parent)
        self.setFixedHeight(32)
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #1DB954;
                border: 1px solid #1DB954;
                border-radius: 16px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(29, 185, 84, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(29, 185, 84, 0.2);
            }
        """)


class VolumeButton(AnimatedButton):
    """Volume control button"""
    
    def __init__(self, icon: str, parent: Optional[QWidget] = None):
        super().__init__(icon, parent)
        self.setFixedSize(32, 32)
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #B3B3B3;
                border: none;
                border-radius: 16px;
                font-size: 16px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)