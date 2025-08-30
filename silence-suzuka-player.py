#!/usr/bin/env python3
"""
Silence Auto-Player (mpv edition)
- mpv backend for fast streaming and near-instant next/prev
- System-wide silence monitor (auto-play on silence)
- AFK monitor (auto-pause on inactivity)
- Tray icon + tooltip reflecting playback state
- Saved playlist management (save/load)
- Theme styling (Dark) and optional thumbnails
"""

import sys
import os
import json
import time
import logging
import zipfile
import qtawesome as qta
from PySide6.QtGui import QIcon, QPainter, QPixmap
from pathlib import Path
from datetime import datetime

from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QSize, QRectF, Qt, QTimer
from PySide6.QtWidgets import QLabel

def load_svg_icon(path, size=QSize(18, 18)):
    renderer = QSvgRenderer(path)
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
    painter.end()
    return QIcon(pixmap)

class MarqueeLabel(QLabel):
    """
    Custom QLabel with marquee scrolling effect for long text.
    """
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll_text)
        self._scroll_speed = 30  # Milliseconds between updates
        self._scroll_active = False
        self.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.setStyleSheet("background: transparent;")

    def setText(self, text):
        super().setText(text)
        self._offset = 0
        self._update_scroll_state()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scroll_state()

    def _update_scroll_state(self):
        """
        Start or stop scrolling based on text width compared to label width.
        """
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        if text_width > self.width():
            if not self._scroll_active:
                self._timer.start(self._scroll_speed)
                self._scroll_active = True
        else:
            if self._scroll_active:
                self._timer.stop()
                self._scroll_active = False
                self._offset = 0
                self.update()

    def _scroll_text(self):
        """
        Update the scrolling position of the text.
        """
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        self._offset -= 1
        if abs(self._offset) > text_width:
            self._offset = self.width()
        self.update()

    def paintEvent(self, event):
        """
        Custom paint event to draw scrolling text.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        x = self._offset
        y = self.height() / 2 + self.fontMetrics().ascent() / 2
        painter.drawText(x, y, self.text())
        painter.end()

# Example integration into MediaPlayer class or equivalent UI class
class MediaPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Silence Suzuka Player")
        self.setGeometry(100, 100, 800, 600)

        self.track_label = MarqueeLabel("No track playing", self)
        self.track_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.track_label.setFixedHeight(40)

        self.volume_slider = QSlider(Qt.Horizontal, self)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)

        layout = QVBoxLayout()
        layout.addWidget(self.track_label)
        layout.addWidget(self.volume_slider)

        container = QWidget(self)
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Example to test marquee
        QTimer.singleShot(1000, lambda: self.update_track_title("This is an example of a very long track title that will scroll if it doesn't fit."))

    def update_track_title(self, title):
        self.track_label.setText(title)

def main():
    app = QApplication(sys.argv)
    player = MediaPlayer()
    player.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()