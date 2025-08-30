#!/usr/bin/env python3
"""
Demo script for the modern UI components

Run this to see the integrated mockup designs in action
with the Python/Qt implementation.
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Add project root to path for imports
APP_DIR = Path(__file__).parent
sys.path.insert(0, str(APP_DIR))

from ui.main_window import ModernMediaPlayerWindow
from ui.typography import TypographyManager


def main():
    """Main demo function"""
    app = QApplication(sys.argv)
    app.setApplicationName("Silence Suzuka Player - Modern UI Demo")
    
    # Create main window
    window = ModernMediaPlayerWindow()
    
    # Initialize typography system
    typo = TypographyManager(app, project_root=APP_DIR)
    typo.install()
    
    # Apply dark theme
    app.setStyleSheet("""
        QApplication {
            background-color: #121212;
            color: #FFFFFF;
        }
    """)
    
    # Show window
    window.show()
    window.resize(1000, 700)
    
    print("Modern UI Demo started!")
    print("Features:")
    print("- Integrated corner video widget")
    print("- Bounce-back button animations")
    print("- Modern playlist design")
    print("- Spotify-inspired controls")
    print("- Typography hotkeys (Ctrl+=/-, Ctrl+0, Ctrl+,)")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()