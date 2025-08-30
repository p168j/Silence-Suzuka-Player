#!/usr/bin/env python3
"""
Simple test script to check if our BounceButton classes work correctly
"""
import sys
import os

# Add the current directory to the path so we can import the application
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test basic imports"""
    try:
        from PySide6.QtWidgets import QApplication, QPushButton
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Property
        print("✓ PySide6 imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_bounce_button_creation():
    """Test creating a BounceButton"""
    try:
        # Import our custom classes from the main file
        # We need to import the specific classes, not the whole module due to the hyphen in filename
        import importlib.util
        spec = importlib.util.spec_from_file_location("suzuka_player", "silence-suzuka-player.py")
        if spec is None:
            print("✗ Could not load suzuka_player module spec")
            return False
        
        suzuka_player = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(suzuka_player)
        
        # Get the BounceButton class
        BounceButton = suzuka_player.BounceButton
        IntegratedVideoPreview = suzuka_player.IntegratedVideoPreview
        
        print("✓ Successfully imported custom classes")
        
        # Create a minimal QApplication (required for Qt widgets)
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        # Test creating a BounceButton
        btn = BounceButton("Test")
        btn.setObjectName("playPauseBtn")
        print("✓ BounceButton created successfully")
        
        # Test creating IntegratedVideoPreview
        preview = IntegratedVideoPreview()
        print("✓ IntegratedVideoPreview created successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ BounceButton creation error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing bounce button implementation...")
    
    success = True
    success &= test_imports()
    success &= test_bounce_button_creation()
    
    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)