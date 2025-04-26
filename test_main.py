import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import main

class TestVideoCompression(unittest.TestCase):

    @patch("main.subprocess.check_output")
    def test_is_av1_true(self, mock_subproc):
        mock_subproc.return_value = b"av1"
        result = main.is_av1(Path("dummy.mkv"))
        self.assertTrue(result)

    @patch("main.subprocess.check_output")
    def test_is_av1_false(self, mock_subproc):
        mock_subproc.return_value = b"h264"
        result = main.is_av1(Path("dummy.mkv"))
        self.assertFalse(result)

    @patch("main.subprocess.check_output")
    def test_get_resolution(self, mock_subproc):
        mock_subproc.return_value = b'{"streams": [{"width": 1920, "height": 800}]}'
        w, h = main.get_resolution(Path("video.mp4"))
        self.assertEqual((w, h), (1920, 800))

    @patch("main.subprocess.check_output")
    def test_get_crop_params(self, mock_subproc):
        mock_subproc.return_value = (
            b"[Parsed_cropdetect_0 @ x] crop=1280:720:0:0\n"
            b"[Parsed_cropdetect_0 @ x] crop=1280:700:0:10\n"
        )
        with patch("main.CROP_TIMESTAMPS", [1]):
            result = main.get_crop_params(Path("video.mp4"))
        self.assertEqual(result, "crop=1280:720:0:0")

    @patch("main.subprocess.check_output")
    def test_get_audio_bitrate_cmd_convert(self, mock_subproc):
        mock_subproc.return_value = b'{"streams": [{"channels": 2, "bit_rate": "300000"}]}'
        result = main.get_audio_bitrate_cmd(Path("vid.mp4"))
        self.assertIn("-b:a:0", result)

    @patch("main.subprocess.check_output")
    def test_get_audio_bitrate_cmd_copy(self, mock_subproc):
        mock_subproc.return_value = b'{"streams": [{"channels": 2, "bit_rate": "100000"}]}'
        result = main.get_audio_bitrate_cmd(Path("vid.mp4"))
        self.assertIn("-c:a:0", result)

    def test_should_skip_compressed_suffix(self):
        path = Path("some/thing_compressed.mp4")
        self.assertTrue(main.should_skip(path))

    @patch("main.is_av1", return_value=True)
    def test_should_skip_av1(self, mock_av1):
        path = Path("vid.mkv")
        self.assertTrue(main.should_skip(path))

    def test_find_video_files_filters_exts(self):
        files = [
            Path("a.mp4"), Path("b.txt"), Path("c.mkv"),
            Path("d.MOV"), Path("e.jpg")
        ]
        with patch("main.Path.rglob", return_value=files):
            result = main.find_video_files(Path("test"))
        self.assertEqual(len(result), 3)

if __name__ == '__main__':
    unittest.main()
