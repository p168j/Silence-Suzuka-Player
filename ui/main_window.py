#!/usr/bin/env python3
"""
Main Window Integration for Silence Suzuka Player

Combines all the modern UI components into a cohesive main window
that implements the design from the mockups.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QLabel, QSplitter, QFrame
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from typing import Optional

from .modern_controls import ModernControlPanel
from .playlist_items import ModernPlaylistView
from .integrated_video_widget import IntegratedVideoWidget
from mock_data import MockDataProvider, MockMediaItem


class MainVideoArea(QWidget):
    """
    Main content area for visualizations, large video, or audio content.
    Based on the main-content area from the mockups.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("mainVideoArea")
        self._setup_ui()
        self._setup_styling()
        
    def _setup_ui(self):
        """Setup the main video area UI"""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        # Placeholder content
        self.placeholder_icon = QLabel("🎵")
        self.placeholder_icon.setAlignment(Qt.AlignCenter)
        self.placeholder_icon.setStyleSheet("""
            QLabel {
                font-size: 48px;
                color: rgba(255, 255, 255, 0.3);
                margin-bottom: 16px;
            }
        """)
        
        self.placeholder_text = QLabel("Audio Visualizer Space")
        self.placeholder_text.setAlignment(Qt.AlignCenter)
        self.placeholder_text.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: 500;
                color: #535353;
            }
        """)
        
        layout.addWidget(self.placeholder_icon)
        layout.addWidget(self.placeholder_text)
        
    def _setup_styling(self):
        """Setup the main area styling"""
        self.setStyleSheet("""
            #mainVideoArea {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a1a, stop:1 #0d0d0d);
            }
        """)
        
    def update_content_type(self, media_type: str):
        """Update the placeholder based on content type"""
        if media_type == "video":
            self.placeholder_icon.setText("🎬")
            self.placeholder_text.setText("Video Player Area")
        else:
            self.placeholder_icon.setText("🎵")
            self.placeholder_text.setText("Audio Visualizer Space")


class ModernMediaPlayerWindow(QMainWindow):
    """
    Main window that combines all modern UI components.
    Implements the complete design from the mockups.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Silence Suzuka Player")
        self.setMinimumSize(800, 600)
        
        # Mock data
        self.mock_provider = MockDataProvider()
        self.current_media = None
        self.playback_state = self.mock_provider.get_playback_state()
        
        # Setup UI
        self._setup_ui()
        self._setup_styling()
        self._connect_signals()
        self._load_mock_data()
        
        # Setup update timer for demo
        self._setup_demo_timer()
        
    def _setup_ui(self):
        """Setup the main window UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout - horizontal split
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Left side - Playlist with integrated video
        self.playlist_view = ModernPlaylistView()
        self.playlist_view.setFixedWidth(320)
        
        # Right side - Main content and controls
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # Main video/content area
        self.main_video_area = MainVideoArea()
        
        # Control panel
        self.control_panel = ModernControlPanel()
        
        right_layout.addWidget(self.main_video_area)
        right_layout.addWidget(self.control_panel)
        
        # Add integrated video widget to playlist
        self.integrated_video = IntegratedVideoWidget(self.playlist_view.playlist_container)
        
        main_layout.addWidget(self.playlist_view)
        main_layout.addWidget(right_widget)
        
    def _setup_styling(self):
        """Setup the main window styling"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
                color: #FFFFFF;
            }
        """)
        
    def _connect_signals(self):
        """Connect UI signals"""
        # Playlist signals
        self.playlist_view.item_selected.connect(self._on_item_selected)
        
        # Control panel signals
        self.control_panel.play_pause_clicked.connect(self._on_play_pause)
        self.control_panel.previous_clicked.connect(self._on_previous)
        self.control_panel.next_clicked.connect(self._on_next)
        self.control_panel.shuffle_toggled.connect(self._on_shuffle_toggled)
        self.control_panel.repeat_toggled.connect(self._on_repeat_toggled)
        self.control_panel.volume_changed.connect(self._on_volume_changed)
        self.control_panel.position_changed.connect(self._on_position_changed)
        self.control_panel.add_media_clicked.connect(self._on_add_media)
        
        # Integrated video signals
        self.integrated_video.clicked.connect(self._on_video_clicked)
        
    def _load_mock_data(self):
        """Load mock playlist data"""
        playlist = self.mock_provider.get_sample_playlist()
        self.playlist_view.load_playlist(playlist)
        
        # Set first item as current
        if playlist:
            self.current_media = playlist[0]
            self.playlist_view.set_current_item(self.current_media)
            self._update_ui_for_current_media()
            
    def _setup_demo_timer(self):
        """Setup timer for demo progress updates"""
        self.demo_timer = QTimer()
        self.demo_timer.timeout.connect(self._update_demo_progress)
        self.demo_timer.start(1000)  # Update every second
        
    def _update_demo_progress(self):
        """Update demo progress (simulated playback)"""
        if self.playback_state["is_playing"] and self.current_media:
            current = self.playback_state["current_time"]
            total = self.current_media.duration
            
            if current < total:
                self.playback_state["current_time"] += 1
                self.control_panel.update_progress(current + 1, total)
            else:
                # Auto-advance to next track
                self._on_next()
                
    def _update_ui_for_current_media(self):
        """Update UI elements for the current media"""
        if not self.current_media:
            return
            
        # Update control panel
        self.control_panel.update_track_info(
            self.current_media.title, 
            self.current_media.artist
        )
        self.control_panel.update_progress(
            self.playback_state["current_time"],
            self.current_media.duration
        )
        
        # Update main video area
        self.main_video_area.update_content_type(self.current_media.media_type)
        
        # Update integrated video
        self.integrated_video.update_video_state(
            self.playback_state["is_playing"],
            self.current_media.media_type == "video"
        )
        
    def _on_item_selected(self, media_item: MockMediaItem):
        """Handle playlist item selection"""
        self.current_media = media_item
        self.playback_state["current_time"] = 0
        self._update_ui_for_current_media()
        
    def _on_play_pause(self):
        """Handle play/pause button"""
        self.playback_state["is_playing"] = not self.playback_state["is_playing"]
        self.control_panel.update_playback_state(self.playback_state["is_playing"])
        
        if self.current_media:
            self.integrated_video.update_video_state(
                self.playback_state["is_playing"],
                self.current_media.media_type == "video"
            )
        
    def _on_previous(self):
        """Handle previous button"""
        if not self.playlist_view.playlist_items:
            return
            
        current_index = self._get_current_item_index()
        if current_index > 0:
            prev_item = self.playlist_view.playlist_items[current_index - 1].media_item
            self._select_item(prev_item)
            
    def _on_next(self):
        """Handle next button"""
        if not self.playlist_view.playlist_items:
            return
            
        current_index = self._get_current_item_index()
        if current_index < len(self.playlist_view.playlist_items) - 1:
            next_item = self.playlist_view.playlist_items[current_index + 1].media_item
            self._select_item(next_item)
        else:
            # Loop back to first item
            first_item = self.playlist_view.playlist_items[0].media_item
            self._select_item(first_item)
            
    def _get_current_item_index(self) -> int:
        """Get index of current item"""
        if not self.current_media:
            return -1
            
        for i, item_widget in enumerate(self.playlist_view.playlist_items):
            if item_widget.media_item == self.current_media:
                return i
        return -1
        
    def _select_item(self, media_item: MockMediaItem):
        """Select and play a specific item"""
        self.current_media = media_item
        self.playlist_view.set_current_item(media_item)
        self.playback_state["current_time"] = 0
        self.playback_state["is_playing"] = True
        self.control_panel.update_playback_state(True)
        self._update_ui_for_current_media()
        
    def _on_shuffle_toggled(self, enabled: bool):
        """Handle shuffle toggle"""
        self.playback_state["is_shuffled"] = enabled
        
    def _on_repeat_toggled(self, enabled: bool):
        """Handle repeat toggle"""
        self.playback_state["repeat_mode"] = "all" if enabled else "none"
        
    def _on_volume_changed(self, volume: int):
        """Handle volume change"""
        self.playback_state["volume"] = volume
        
    def _on_position_changed(self, position: int):
        """Handle position change"""
        if self.current_media:
            new_time = int((position / 100) * self.current_media.duration)
            self.playback_state["current_time"] = new_time
            self.control_panel.update_progress(new_time, self.current_media.duration)
            
    def _on_add_media(self):
        """Handle add media button"""
        print("Add media clicked - would open file dialog")
        
    def _on_video_clicked(self):
        """Handle integrated video click"""
        print("Video widget clicked - would toggle video size or open in main area")
        
    def resizeEvent(self, event):
        """Handle window resize"""
        super().resizeEvent(event)
        
        # Reposition integrated video widget
        if hasattr(self, 'integrated_video'):
            container = self.playlist_view.playlist_container
            self.integrated_video.move(
                container.width() - 160 - 16,
                container.height() - 120 - 16
            )