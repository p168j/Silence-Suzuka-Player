"""
UI Module for Silence Suzuka Player

Contains typography management, preferences dialogs, and themes.
"""

from .typography import TypographyManager, TypographySettings
from .preferences_typography import TypographyPreferencesDialog
from .theme_slate import apply_slate_theme

__all__ = ['TypographyManager', 'TypographySettings', 'TypographyPreferencesDialog', 'apply_slate_theme']