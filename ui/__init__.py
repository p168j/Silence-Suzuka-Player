"""
UI Module for Silence Suzuka Player

Contains typography management, preferences dialogs, and modern UI components.
"""

from .typography import TypographyManager, TypographySettings
from .preferences_typography import TypographyPreferencesDialog
from .animated_buttons import AnimatedButton, PlayPauseButton, ControlButton, AddMediaButton, VolumeButton
from .integrated_video_widget import IntegratedVideoWidget, ModernPlaylistWidget
from .modern_controls import ModernControlPanel, ModernProgressBar, TimeLabel
from .playlist_items import PlaylistItemWidget, ModernPlaylistView
from .main_window import ModernMediaPlayerWindow, MainVideoArea

__all__ = [
    'TypographyManager', 'TypographySettings', 'TypographyPreferencesDialog',
    'AnimatedButton', 'PlayPauseButton', 'ControlButton', 'AddMediaButton', 'VolumeButton',
    'IntegratedVideoWidget', 'ModernPlaylistWidget',
    'ModernControlPanel', 'ModernProgressBar', 'TimeLabel',
    'PlaylistItemWidget', 'ModernPlaylistView',
    'ModernMediaPlayerWindow', 'MainVideoArea'
]