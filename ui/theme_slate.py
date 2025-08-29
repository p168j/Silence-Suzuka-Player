"""
Slate theme for Silence Suzuka Player.
Implements a modern dark theme using slate color palette.
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect


def apply_slate_theme(window):
    """
    Apply slate theme to the MediaPlayer window.
    
    Color palette:
    - bg: #1A202C (slate 900)
    - surface: #2D3748 (slate 800)
    - text: #E2E8F0 (slate 200)
    - muted: #A0AEC0 (slate 400)
    - accent: #4FD1C5 (teal 300)
    - border: #4A5568 (slate 600)
    """
    style = """
        QMainWindow, QDialog { background-color: #1A202C; color: #E2E8F0; font-family: '{self._ui_font}'; }
        #titleLabel { color: #E2E8F0; font-size: 20px; font-weight: bold; font-family: '{self._serif_font}'; font-style: italic; }
        #settingsBtn { background: transparent; color: #A0AEC0; font-size: 18px; border: none; padding: 2px 6px; min-width: 32px; min-height: 28px; border-radius: 6px; }
        #settingsBtn:hover { background-color: #2D3748; color: #E2E8F0; }
        #settingsBtn:pressed { background-color: #4A5568; }
        #scopeChip { background-color: #2D3748; color: #A0AEC0; border: 1px solid #4A5568; padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-left: 8px; }
        #statsBadge { background-color: #2D3748; color: #A0AEC0; border: 1px solid #4A5568; padding: 4px 12px; margin-left: 8px; margin-right: 8px; border-radius: 10px; font-size: 12px; }
        #sidebar { background-color: rgba(45, 55, 72, 0.9); border: 1px solid #4A5568; border-radius: 8px; padding: 10px; }
        #addBtn { 
                background-color: #4FD1C5; 
                color: #1A202C; 
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
        #addBtn:hover { background-color: #38B2AC; }
        #addBtn:pressed { background-color: #319795; }
        #miniBtn { background: transparent; color: #A0AEC0; border: none; font-size: 16px; }
        #miniBtn:hover { color: #E2E8F0; }
        #miniBtn:pressed { color: #4A5568; }
        #playlistTree { background-color: transparent; border: none; color: #E2E8F0; font-family: '{self._serif_font}'; alternate-background-color: #2D3748; }
        #playlistTree::item { min-height: 24px; height: 24px; padding: 3px 8px; }
        #playlistTree::item:hover { background-color: #4A5568; }
        #playlistTree::item:selected { background-color: #4A5568; color: #4FD1C5; }
        #videoWidget { background-color: #000000; border-radius: 8px; border: 1px solid #4A5568; }
        #trackLabel { color: #E2E8F0; font-weight: bold; font-family: '{self._serif_font}'; font-style: italic; }
        #controlBtn { background: transparent; color: #A0AEC0; font-size: 20px; border: none; border-radius: 20px; width: 40px; height: 40px; padding: 0px; }
        #controlBtn:hover { background-color: #2D3748; }
        #controlBtn:pressed { background-color: #4A5568; padding-top: 1px; padding-left: 1px; }
        #playPauseBtn { background-color: #E2E8F0; color: #1A202C; font-size: 20px; border: none; border-radius: 25px; width: 50px; height: 50px; padding: 0px; }
        #playPauseBtn:hover { background-color: #CBD5E0; }
        #playPauseBtn:pressed { background-color: #A0AEC0; padding-top: 1px; padding-left: 1px; }
        #volumeSlider::groove:horizontal { height: 4px; background-color: #4A5568; border-radius: 2px; }
        #volumeSlider::handle:horizontal { width: 12px; height: 12px; background-color: #E2E8F0; border-radius: 6px; margin: -4px 0; }
        #volumeSlider::sub-page:horizontal { background-color: #4FD1C5; border-radius: 2px; }
        #volumeSlider::add-page:horizontal { background-color: #4A5568; border-radius: 2px; }
        QSlider::groove:horizontal { height: 4px; background-color: #4A5568; border-radius: 2px; margin: 0 1px; }
        QSlider::handle:horizontal { width: 12px; height: 12px; background-color: #E2E8F0; border-radius: 6px; margin: -4px 0; }
        QSlider::sub-page:horizontal { background-color: #4FD1C5; border-radius: 2px; }
        QSlider::add-page:horizontal { background-color: #4A5568; border-radius: 2px; }
        #silenceIndicator { color: #FF0000; font-size: 18px; margin: 0 8px; padding-bottom: 3px; }
        #upNext::item { min-height: 24px; height: 24px; padding: 3px 8px; }
        #upNext::item:hover { background-color: #2D3748; }
        #upNext::item:selected { background-color: #2D3748; color: #4FD1C5; }
        #upNextHeader { background-color: #2D3748; color: #A0AEC0; border: 1px solid #4A5568; border-radius: 6px; padding: 4px 8px; text-align:left; }
        #upNextHeader:hover { background-color: #4A5568; color: #E2E8F0; }
        #upNextHeader:pressed { background-color: #2D3748; }
        QProgressBar { background-color: #2D3748; border: 1px solid #4A5568; border-radius: 4px; text-align: center; color: #A0AEC0; }
        QProgressBar::chunk { background-color: #4FD1C5; border-radius: 4px; }
        QStatusBar { color: #A0AEC0; }
        QMenu { background-color: #2D3748; color: #E2E8F0; border: 1px solid #4A5568; font-size: 13px; }
        QMenu::item { padding: 6px 12px; }
        QMenu::item:selected { background-color: #4A5568; color: #4FD1C5; }
        QToolTip { background-color: #2D3748; color: #E2E8F0; border: 1px solid #4A5568; padding: 4px 8px; border-radius: 6px; }
        QScrollBar:vertical { background: transparent; width: 12px; margin: 0px; }
        QScrollBar::handle:vertical { background: #4A5568; min-height: 24px; border-radius: 6px; }
        QScrollBar::handle:vertical:hover { background: #718096; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal { background: transparent; height: 12px; margin: 0px; }
        QScrollBar::handle:horizontal { background: #4A5568; min-width: 24px; border-radius: 6px; }
        QScrollBar::handle:horizontal:hover { background: #718096; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        QTabWidget::pane { border: 1px solid #4A5568; border-radius: 6px; }
        QTabBar::tab { background-color: #2D3748; color: #A0AEC0; padding: 6px 10px; border: 1px solid #4A5568; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
        QTabBar::tab:selected { background-color: #4A5568; color: #E2E8F0; }
        QTabBar::tab:hover { background-color: #4A5568; }
        #upNext { font-family: '{self._serif_font}'; alternate-background-color: #2D3748; }
        #timeLabel, #durLabel { font-family: '{self._ui_font}'; font-size: 13px; color: #A0AEC0; }
        QLineEdit#searchBar { background-color: #2D3748; border: 1px solid #4A5568; border-radius: 6px; padding: 4px 8px; margin: 8px 0; color: #E2E8F0; selection-background-color: #4FD1C5; }
        #emptyStateIcon { font-size: 48px; color: #4A5568; padding-bottom: 10px; }
        #emptyStateHeading { font-family: '{self._serif_font}'; color: #E2E8F0; font-size: 15px; font-weight: bold; }
        #emptyStateSubheading { color: #A0AEC0; font-size: 13px; }
        /* Focus styling: replace default noisy focus rectangle with a subtle themed ring.
           Keeps the button keyboard-focusable (accessible) but removes the blue dotted box. */
        QPushButton:focus { outline: none; }
        /* Subtle, themed focus ring for the main play/pause control */
        #playPauseBtn:focus {
            border: 2px solid rgba(79,209,197,0.18); /* soft teal */
            border-radius: 25px;
            padding: 0px; /* ensure size doesn't shift */
        }
        """
    
    # Replace font placeholders
    style = style.replace("{self._ui_font}", window._ui_font).replace("{self._serif_font}", window._serif_font)
    window.setStyleSheet(style)
    
    # Add subtle drop shadow to video frame (similar intensity to dark theme, a bit lighter than vinyl)
    try:
        eff = QGraphicsDropShadowEffect(window.video_frame)
        eff.setBlurRadius(18)  # Between dark (20) and vinyl (25), slightly lighter
        eff.setOffset(0, 0)
        eff.setColor(QColor(0, 0, 0, 140))  # Between dark (160) and vinyl (110)
        window.video_frame.setGraphicsEffect(eff)
    except Exception:
        pass
    
    # Clear any tiled vinyl background/pattern
    try:
        bg = window.centralWidget()
        if bg:
            bg.setStyleSheet("")
            bg.setAutoFillBackground(False)
    except Exception:
        pass
    
    # Set handle color for HoverSlider if the method exists
    _set_slider_handle_colors(window, QColor(226, 232, 240))  # #E2E8F0


def _set_slider_handle_colors(window, color):
    """Set handle colors for progress and volume sliders if setHandleColor method exists."""
    try:
        if hasattr(window, 'progress_slider') and hasattr(window.progress_slider, 'setHandleColor'):
            window.progress_slider.setHandleColor(color)
    except Exception:
        pass
    
    try:
        if hasattr(window, 'volume_slider') and hasattr(window.volume_slider, 'setHandleColor'):
            window.volume_slider.setHandleColor(color)
    except Exception:
        pass