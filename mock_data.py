#!/usr/bin/env python3
"""
Mock Data for Silence Suzuka Player

Provides sample playlist items, media metadata, and test content
for development and demonstration purposes.
"""

from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path


@dataclass
class MockMediaItem:
    """Mock media item with metadata"""
    title: str
    artist: str = ""
    duration: int = 0  # seconds
    file_path: Optional[str] = None
    url: Optional[str] = None
    media_type: str = "audio"  # "audio" or "video"
    thumbnail: Optional[str] = None
    description: str = ""
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def get_duration_string(self) -> str:
        """Get formatted duration string (MM:SS)"""
        minutes = self.duration // 60
        seconds = self.duration % 60
        return f"{minutes}:{seconds:02d}"

    def get_icon(self) -> str:
        """Get appropriate icon for media type"""
        return "🎬" if self.media_type == "video" else "🎵"


class MockDataProvider:
    """Provides mock data for testing and demonstration"""
    
    @staticmethod
    def get_sample_playlist() -> List[MockMediaItem]:
        """Get a sample playlist with diverse content"""
        return [
            MockMediaItem(
                title="Horse Racing Highlights 2023",
                artist="Racing Channel",
                duration=492,  # 8:12
                media_type="video",
                description="Best moments from the 2023 racing season",
                tags=["racing", "highlights", "2023"]
            ),
            MockMediaItem(
                title="Training Music Mix",
                artist="Workout Beats",
                duration=1800,  # 30:00
                media_type="audio",
                description="High-energy training soundtrack",
                tags=["training", "music", "workout"]
            ),
            MockMediaItem(
                title="Derby Championship Final",
                artist="Sports Network",
                duration=3600,  # 60:00
                media_type="video",
                description="Complete coverage of the championship race",
                tags=["derby", "championship", "final"]
            ),
            MockMediaItem(
                title="Victory Celebration Songs",
                artist="Victory Records",
                duration=2400,  # 40:00
                media_type="audio",
                description="Triumphant celebration music collection",
                tags=["victory", "celebration", "music"]
            ),
            MockMediaItem(
                title="Behind the Scenes",
                artist="Documentary Team",
                duration=1320,  # 22:00
                media_type="video",
                description="Exclusive behind-the-scenes footage",
                tags=["documentary", "behind-scenes"]
            ),
            MockMediaItem(
                title="Warm-up Routine",
                artist="Training Academy",
                duration=900,  # 15:00
                media_type="audio",
                description="Pre-race warm-up music and guidance",
                tags=["warm-up", "routine", "training"]
            ),
            MockMediaItem(
                title="Race Analysis Commentary",
                artist="Expert Panel",
                duration=2700,  # 45:00
                media_type="audio",
                description="In-depth race analysis and commentary",
                tags=["analysis", "commentary", "expert"]
            ),
            MockMediaItem(
                title="Jockey Interviews",
                artist="Sports Media",
                duration=1080,  # 18:00
                media_type="video",
                description="Exclusive interviews with top jockeys",
                tags=["interviews", "jockey", "exclusive"]
            )
        ]

    @staticmethod
    def get_current_playing() -> MockMediaItem:
        """Get the currently playing item"""
        return MockDataProvider.get_sample_playlist()[0]

    @staticmethod
    def get_playback_state() -> dict:
        """Get mock playback state"""
        return {
            "is_playing": False,
            "current_time": 165,  # 2:45
            "total_time": 492,    # 8:12
            "volume": 70,
            "is_shuffled": False,
            "repeat_mode": "none"  # "none", "one", "all"
        }