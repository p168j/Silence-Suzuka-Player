#!/usr/bin/env python3
"""
Integrated Video Widget for Silence Suzuka Player

Implements the corner-embedded video player design from the mockups.
Provides a small video preview that integrates seamlessly with the playlist area.
"""

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QPen
from typing import Optional


class IntegratedVideoWidget(QWidget):
    """
    Small video widget that embeds in the corner of the playlist area.
    Based on Option B from the mockups - integrated corner design.
    """
    
    clicked = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(160, 120)
        self.setObjectName("integratedVideo")
        
        # Animation for hover effects
        self.hover_animation = QPropertyAnimation(self, b"geometry")
        self.hover_animation.setDuration(300)
        self.hover_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        self._setup_ui()
        self._setup_styling()
        
    def _setup_ui(self):
        """Setup the internal UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Main content area
        content_widget = QWidget()
        content_widget.setObjectName("videoContent")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setAlignment(Qt.AlignCenter)
        
        # Video icon
        self.video_icon = QLabel("▶️")
        self.video_icon.setAlignment(Qt.AlignCenter)
        self.video_icon.setStyleSheet("""
            QLabel {
                font-size: 20px;
                color: rgba(255, 255, 255, 0.7);
                margin-bottom: 6px;
            }
        """)
        
        # Video text
        self.video_text = QLabel("Video\nPreview")
        self.video_text.setAlignment(Qt.AlignCenter)
        self.video_text.setStyleSheet("""
            QLabel {
                font-size: 9px;
                color: #999999;
                text-transform: uppercase;
                letter-spacing: 1px;
                line-height: 1.2;
            }
        """)
        
        content_layout.addWidget(self.video_icon)
        content_layout.addWidget(self.video_text)
        layout.addWidget(content_widget)
        
    def _setup_styling(self):
        """Setup the widget styling"""
        self.setStyleSheet("""
            #integratedVideo {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a1a, stop:1 #0f0f0f);
                border: 1px solid #333333;
                border-radius: 8px;
            }
            #integratedVideo:hover {
                border: 1px solid #1DB954;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1e1e1e, stop:1 #121212);
            }
            #videoContent {
                background: transparent;
            }
        """)
        
    def enterEvent(self, event):
        """Handle mouse enter with subtle animation"""
        super().enterEvent(event)
        # Could add subtle scale or glow effect here
        
    def leaveEvent(self, event):
        """Handle mouse leave"""
        super().leaveEvent(event)
        
    def mousePressEvent(self, event):
        """Handle click"""
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            
    def update_video_state(self, is_playing: bool, has_video: bool):
        """Update the video widget state"""
        if has_video:
            if is_playing:
                self.video_icon.setText("⏸️")
                self.video_text.setText("Video\nPlaying")
            else:
                self.video_icon.setText("▶️")
                self.video_text.setText("Video\nPaused")
        else:
            self.video_icon.setText("🎵")
            self.video_text.setText("Audio\nOnly")


class ModernPlaylistWidget(QWidget):
    """
    Modern playlist widget that includes the integrated video corner.
    Implements the sidebar design from Option B mockup.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("modernPlaylist")
        self._setup_ui()
        self._setup_styling()
        
    def _setup_ui(self):
        """Setup the playlist UI with integrated video"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header_widget = QWidget()
        header_widget.setObjectName("playlistHeader")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(24, 24, 24, 0)
        
        title_label = QLabel("Silence Suzuka Player")
        title_label.setObjectName("playlistTitle")
        header_layout.addWidget(title_label)
        
        layout.addWidget(header_widget)
        
        # Playlist container (will contain the actual playlist and video widget)
        self.playlist_container = QWidget()
        self.playlist_container.setObjectName("playlistContainer")
        container_layout = QVBoxLayout(self.playlist_container)
        container_layout.setContentsMargins(16, 16, 16, 16)
        
        # This is where the actual playlist items would go
        # For now, we'll add a placeholder
        playlist_placeholder = QLabel("Playlist items will be added here")
        playlist_placeholder.setAlignment(Qt.AlignCenter)
        playlist_placeholder.setStyleSheet("color: #666666; padding: 40px;")
        container_layout.addWidget(playlist_placeholder)
        
        layout.addWidget(self.playlist_container)
        
        # Add integrated video widget in corner
        self.video_widget = IntegratedVideoWidget(self.playlist_container)
        self.video_widget.move(
            self.playlist_container.width() - 160 - 16,
            self.playlist_container.height() - 120 - 16
        )
        
    def _setup_styling(self):
        """Setup the modern playlist styling"""
        self.setStyleSheet("""
            #modernPlaylist {
                background-color: #000000;
                border-right: 1px solid #282828;
            }
            #playlistHeader {
                background-color: #000000;
            }
            #playlistTitle {
                font-size: 24px;
                font-weight: 900;
                color: #FFFFFF;
                margin-bottom: 16px;
            }
            #playlistContainer {
                background-color: #000000;
                position: relative;
            }
        """)
        
    def resizeEvent(self, event):
        """Handle resize to reposition video widget"""
        super().resizeEvent(event)
        if hasattr(self, 'video_widget'):
            # Position video widget in bottom-right corner
            container_rect = self.playlist_container.geometry()
            self.video_widget.move(
                container_rect.width() - 160 - 16,
                container_rect.height() - 120 - 16
            )