#!/usr/bin/env python3
"""
Typography Management System for Silence Suzuka Player

Provides native (non-monkey-patched) typography system with:
- Font loading from assets/fonts
- App-wide QSS typography application
- Settings persistence
- Hotkey support for scaling and preferences
"""

import json
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

from PySide6.QtCore import QObject, Signal, QEvent
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication


@dataclass
class TypographySettings:
    """Typography configuration settings"""
    # Font families
    latin_family: str = "Inter"
    cjk_family: str = "Noto Sans JP"
    fallback_generic: str = "sans-serif"
    
    # Base sizes (professional baseline)
    body_size: int = 16
    list_size: int = 16
    title_size: int = 24      # used for track label (not app title)
    time_size: int = 20
    chip_size: int = 13
    badge_size: int = 12
    
    # User scale factor
    scale: float = 1.3
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TypographySettings':
        """Create from dictionary loaded from JSON"""
        # Filter to only known fields to handle forward compatibility
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered_data)


class TypographyManager(QObject):
    """
    Typography manager that loads fonts, applies QSS, and handles settings persistence.
    
    Provides hotkeys:
    - Ctrl+= / Ctrl++: scale up by 0.1
    - Ctrl+-: scale down by 0.1
    - Ctrl+0: reset scale to 1.3
    - Ctrl+,: open preferences dialog
    """
    
    settings_changed = Signal()
    
    def __init__(self, app: QApplication, project_root: Optional[Path] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.app = app
        self.project_root = project_root or Path.cwd()
        self.settings = TypographySettings()
        self._fonts_loaded = False
        self._installed = False
        
        # Load initial settings
        self._load_settings()
        
    def install(self) -> None:
        """Install the typography system (load fonts, apply QSS, install event filter)"""
        if self._installed:
            return
            
        self._load_fonts()
        self._apply_typography()
        self._install_event_filter()
        self._installed = True
        
    def _get_config_dir(self) -> Path:
        """Get platform-appropriate configuration directory"""
        try:
            import platform
            if platform.system() == 'Windows':
                import os
                return Path(os.getenv('APPDATA', Path.home())) / 'SilenceSuzukaPlayer'
            elif platform.system() == 'Darwin':
                return Path.home() / 'Library' / 'Application Support' / 'SilenceSuzukaPlayer'
            else:
                return Path.home() / '.config' / 'SilenceSuzukaPlayer'
        except Exception:
            # Fallback to project directory
            return self.project_root / 'config'
            
    def _get_config_file(self) -> Path:
        """Get typography configuration file path"""
        config_dir = self._get_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / 'typography.json'
        
    def _load_settings(self) -> None:
        """Load settings from configuration file"""
        try:
            config_file = self._get_config_file()
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.settings = TypographySettings.from_dict(data)
        except Exception as e:
            print(f"Failed to load typography settings: {e}")
            # Use defaults
            self.settings = TypographySettings()
            
    def _save_settings(self) -> None:
        """Save current settings to configuration file"""
        try:
            config_file = self._get_config_file()
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save typography settings: {e}")
            
    def _load_fonts(self) -> None:
        """Load fonts from assets/fonts directory"""
        if self._fonts_loaded:
            return
            
        try:
            fonts_dir = self.project_root / 'assets' / 'fonts'
            if not fonts_dir.exists():
                print("Typography: assets/fonts directory not found, using system fonts")
                self._fonts_loaded = True
                return
                
            loaded_families = []
            for ext in ['*.ttf', '*.otf']:
                for font_path in fonts_dir.glob(ext):
                    try:
                        font_id = QFontDatabase.addApplicationFont(str(font_path))
                        if font_id != -1:
                            families = QFontDatabase.applicationFontFamilies(font_id)
                            loaded_families.extend(families)
                    except Exception as e:
                        print(f"Failed to load font {font_path}: {e}")
                        
            if loaded_families:
                print(f"Typography: Loaded fonts: {', '.join(set(loaded_families))}")
            else:
                print("Typography: No fonts loaded, using system fonts")
                
            self._fonts_loaded = True
            
        except Exception as e:
            print(f"Typography: Font loading error: {e}")
            self._fonts_loaded = True
            
    def _build_font_family_stack(self) -> str:
        """Build CSS font-family stack with fallbacks"""
        return f'"{self.settings.latin_family}", "{self.settings.cjk_family}", {self.settings.fallback_generic}'
        
    def _get_scaled_size(self, base_size: int) -> int:
        """Get scaled font size"""
        return max(8, int(base_size * self.settings.scale))
        
    def _build_typography_qss(self) -> str:
        """Build QSS stylesheet for typography"""
        font_family = self._build_font_family_stack()
        
        # Scale base sizes
        body_size = self._get_scaled_size(self.settings.body_size)
        list_size = self._get_scaled_size(self.settings.list_size)
        title_size = self._get_scaled_size(self.settings.title_size)  # used for track label
        time_size = self._get_scaled_size(self.settings.time_size)
        chip_size = self._get_scaled_size(self.settings.chip_size)
        badge_size = self._get_scaled_size(self.settings.badge_size)

        # Scale row heights so items don't get cramped as font size grows
        row_height_playlist = max(22, int(32 * self.settings.scale))  # base ~32px
        row_height_upnext = max(20, int(28 * self.settings.scale))    # base ~28px
        
        return f"""
/* Typography Manager - FAMILY Block */
QLabel, QAbstractItemView {{
    font-family: {font_family};
}}

/* Typography Manager - SIZE Block */
QLabel {{
    font-size: {body_size}px;
}}

QAbstractItemView {{
    font-size: {list_size}px;
}}

/* Specific component sizes */
/* Keep app title fixed by NOT setting #titleLabel here */

#trackLabel {{
    font-size: {title_size}px;
}}

#timeLabel, #durLabel, #elapsedLabel, #remainingLabel, #currentTimeLabel, #totalTimeLabel {{
    font-size: {time_size}px;
}}

#scopeChip {{
    font-size: {chip_size}px;
}}

#statsBadge {{
    font-size: {badge_size}px;
}}

/* Row heights to match scaled text */
#playlistTree::item {{
    min-height: {row_height_playlist}px;
}}

#upNext::item {{
    min-height: {row_height_upnext}px;
}}
"""
        
    def _apply_typography(self) -> None:
        """Apply typography QSS to the application"""
        try:
            # Get current application stylesheet
            current_stylesheet = self.app.styleSheet()
            
            # Build our typography QSS
            typography_qss = self._build_typography_qss()
            
            # Append our typography rules (they will take precedence due to CSS cascade)
            combined_stylesheet = current_stylesheet + "\n" + typography_qss
            
            # Apply to application
            self.app.setStyleSheet(combined_stylesheet)
            
        except Exception as e:
            print(f"Typography: Failed to apply QSS: {e}")
            
    def _install_event_filter(self) -> None:
        """Install global event filter for hotkey handling"""
        self.app.installEventFilter(self)
        
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Handle global hotkey events"""
        if event.type() == QEvent.KeyPress:
            try:
                from PySide6.QtCore import Qt
                key = event.key()
                modifiers = event.modifiers()
                
                if modifiers & Qt.ControlModifier:
                    if key in (Qt.Key_Plus, Qt.Key_Equal):  # Ctrl+= or Ctrl++
                        self._scale_up()
                        return True
                    elif key == Qt.Key_Minus:  # Ctrl+-
                        self._scale_down()
                        return True
                    elif key == Qt.Key_0:  # Ctrl+0
                        self._reset_scale()
                        return True
                    elif key == Qt.Key_Comma:  # Ctrl+,
                        self._open_preferences()
                        return True
                        
            except Exception as e:
                print(f"Typography: Hotkey handling error: {e}")
                
        return False  # Don't call super() on QObject
        
    def _scale_up(self) -> None:
        """Increase scale by 0.1"""
        self.settings.scale = min(3.0, self.settings.scale + 0.1)
        self._update_typography()
        
    def _scale_down(self) -> None:
        """Decrease scale by 0.1"""
        self.settings.scale = max(0.5, self.settings.scale - 0.1)
        self._update_typography()
        
    def _reset_scale(self) -> None:
        """Reset scale to default (1.3)"""
        self.settings.scale = 1.3
        self._update_typography()
        
    def _update_typography(self) -> None:
        """Update typography and save settings"""
        self._apply_typography()
        self._save_settings()
        self.settings_changed.emit()
        
    def _open_preferences(self) -> None:
        """Open typography preferences dialog"""
        try:
            from .preferences_typography import TypographyPreferencesDialog
            main_window = None
            for widget in self.app.topLevelWidgets():
                if widget.isVisible() and hasattr(widget, 'setWindowTitle'):
                    main_window = widget
                    break
            dialog = TypographyPreferencesDialog(self, main_window)
            dialog.exec()
        except Exception as e:
            print(f"Typography: Failed to open preferences: {e}")
            
    def update_settings(self, new_settings: TypographySettings) -> None:
        """Update settings and apply changes"""
        self.settings = new_settings
        self._update_typography()
        
    def get_available_fonts(self) -> list:
        """Get list of available font families"""
        system_fonts = QFontDatabase.families()
        common_fonts = [
            "Inter", "Roboto", "Open Sans", "Lato", "Source Sans Pro",
            "Segoe UI", "Arial", "Helvetica", "Verdana", "Tahoma",
            "Noto Sans", "Noto Sans JP", "Noto Sans CJK JP", 
            "Yu Gothic UI", "Meiryo UI", "MS Gothic", "SimSun"
        ]
        available_fonts = []
        for font in common_fonts:
            if font in system_fonts:
                available_fonts.append(font)
        for font in sorted(system_fonts):
            if font not in available_fonts:
                available_fonts.append(font)
        return available_fonts
