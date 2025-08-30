#!/usr/bin/env python3
"""
Modern Playlist Item Components

Implements the playlist item design from the mockups with
proper styling, hover effects, and state management.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont
from typing import Optional, List

from mock_data import MockMediaItem


class PlaylistItemWidget(QWidget):
    """Individual playlist item widget with modern styling"""
    
    clicked = Signal(MockMediaItem)
    
    def __init__(self, media_item: MockMediaItem, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.media_item = media_item
        self.is_active = False
        self._setup_ui()
        self._setup_styling()
        
    def _setup_ui(self):
        """Setup the playlist item UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        
        # Media type icon
        self.icon_label = QLabel(self.media_item.get_icon())
        self.icon_label.setFixedSize(28, 28)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("""
            QLabel {
                background-color: #535353;
                border-radius: 4px;
                font-size: 14px;
            }
        """)
        
        # Text content
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        
        self.title_label = QLabel(self.media_item.title)
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #B3B3B3;
                font-weight: 500;
            }
        """)
        
        # Artist and duration info
        info_text = ""
        if self.media_item.artist:
            info_text = self.media_item.artist
        if self.media_item.duration > 0:
            duration_str = self.media_item.get_duration_string()
            info_text += f" • {duration_str}" if info_text else duration_str
            
        if info_text:
            self.info_label = QLabel(info_text)
            self.info_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #666666;
                }
            """)
            text_layout.addWidget(self.info_label)
        else:
            self.info_label = None
            
        text_layout.addWidget(self.title_label)
        
        layout.addWidget(self.icon_label)
        layout.addWidget(text_widget)
        layout.addStretch()
        
    def _setup_styling(self):
        """Setup the item styling"""
        self.setStyleSheet("""
            PlaylistItemWidget {
                background-color: transparent;
                border-radius: 4px;
            }
            PlaylistItemWidget:hover {
                background-color: #282828;
            }
        """)
        
    def mousePressEvent(self, event):
        """Handle item click"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.media_item)
            
    def set_active(self, active: bool):
        """Set the active state of this item"""
        self.is_active = active
        if active:
            self.setStyleSheet("""
                PlaylistItemWidget {
                    background-color: #282828;
                    border-radius: 4px;
                }
            """)
            self.title_label.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    color: #1DB954;
                    font-weight: 600;
                }
            """)
            self.icon_label.setStyleSheet("""
                QLabel {
                    background-color: #1DB954;
                    color: #FFFFFF;
                    border-radius: 4px;
                    font-size: 14px;
                }
            """)
        else:
            self.setStyleSheet("""
                PlaylistItemWidget {
                    background-color: transparent;
                    border-radius: 4px;
                }
                PlaylistItemWidget:hover {
                    background-color: #282828;
                }
            """)
            self.title_label.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    color: #B3B3B3;
                    font-weight: 500;
                }
            """)
            self.icon_label.setStyleSheet("""
                QLabel {
                    background-color: #535353;
                    border-radius: 4px;
                    font-size: 14px;
                }
            """)


class ModernPlaylistView(QWidget):
    """
    Modern playlist view that displays playlist items with the integrated
    corner video widget from the mockups.
    """
    
    item_selected = Signal(MockMediaItem)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("playlistView")
        self.playlist_items = []
        self.current_item_widget = None
        self._setup_ui()
        self._setup_styling()
        
    def _setup_ui(self):
        """Setup the playlist view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header_widget = QWidget()
        header_widget.setObjectName("playlistHeader")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(24, 24, 24, 16)
        
        title_label = QLabel("Silence Suzuka Player")
        title_label.setObjectName("playlistTitle")
        header_layout.addWidget(title_label)
        
        layout.addWidget(header_widget)
        
        # Playlist container
        self.playlist_container = QWidget()
        self.playlist_container.setObjectName("playlistContainer")
        self.playlist_layout = QVBoxLayout(self.playlist_container)
        self.playlist_layout.setContentsMargins(16, 0, 16, 16)
        self.playlist_layout.setSpacing(4)
        self.playlist_layout.setAlignment(Qt.AlignTop)
        
        layout.addWidget(self.playlist_container)
        
    def _setup_styling(self):
        """Setup the playlist styling"""
        self.setStyleSheet("""
            #playlistView {
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
            }
            #playlistContainer {
                background-color: #000000;
            }
        """)
        
    def load_playlist(self, items: List[MockMediaItem]):
        """Load playlist items"""
        # Clear existing items
        self.clear_playlist()
        
        # Add new items
        for item in items:
            item_widget = PlaylistItemWidget(item)
            item_widget.clicked.connect(self._on_item_clicked)
            self.playlist_layout.addWidget(item_widget)
            self.playlist_items.append(item_widget)
            
        # Add stretch to push items to top
        self.playlist_layout.addStretch()
        
    def clear_playlist(self):
        """Clear all playlist items"""
        for item_widget in self.playlist_items:
            item_widget.deleteLater()
        self.playlist_items.clear()
        self.current_item_widget = None
        
    def _on_item_clicked(self, media_item: MockMediaItem):
        """Handle playlist item click"""
        # Update active states
        for item_widget in self.playlist_items:
            item_widget.set_active(item_widget.media_item == media_item)
            if item_widget.media_item == media_item:
                self.current_item_widget = item_widget
                
        self.item_selected.emit(media_item)
        
    def set_current_item(self, media_item: MockMediaItem):
        """Set the current playing item"""
        for item_widget in self.playlist_items:
            item_widget.set_active(item_widget.media_item == media_item)
            if item_widget.media_item == media_item:
                self.current_item_widget = item_widget