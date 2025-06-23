#!/usr/bin/env python3
"""Test script to verify AAC encoder detection works correctly"""

from pathlib import Path
from config import Config
from file_processor import FileProcessor
import tempfile

def test_encoder_detection():
    """Test the encoder detection functionality"""
    config = Config()
    
    # Create a dummy file path for testing
    dummy_file = Path(tempfile.gettempdir()) / "test.mp4"
    
    # Create FileProcessor instance
    processor = FileProcessor(dummy_file, config)
    
    # Test encoder detection
    try:
        encoder_name, quality_param, quality_value = processor._get_available_aac_encoder()
        print(f"Detected encoder: {encoder_name}")
        print(f"Quality parameter: {quality_param}")
        print(f"Quality value: {quality_value}")
        
        # Test caching
        encoder_name2, quality_param2, quality_value2 = processor._get_available_aac_encoder()
        print(f"\nSecond call (should be cached):")
        print(f"Detected encoder: {encoder_name2}")
        print(f"Quality parameter: {quality_param2}")
        print(f"Quality value: {quality_value2}")
        
        # Verify caching works
        assert encoder_name == encoder_name2
        assert quality_param == quality_param2
        assert quality_value == quality_value2
        print("\n✓ Caching works correctly")
        
    except Exception as e:
        print(f"Error during encoder detection: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("Testing AAC encoder detection...")
    if test_encoder_detection():
        print("\n✓ All tests passed!")
    else:
        print("\n✗ Tests failed!")
