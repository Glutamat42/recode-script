import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import subprocess
import json
import main


class TestVideoCompressor(unittest.TestCase):

    def setUp(self):
        # Create test paths
        self.test_source = Path("test_source")
        self.test_old = Path("test_old")
        main.SOURCE_DIR = self.test_source
        main.OLD_DIR = self.test_old

    @patch('pathlib.Path.rglob')
    def test_find_video_files(self, mock_rglob):
        # Setup
        mock_files = [
            Path('video1.mp4'),
            Path('video2.mkv'),
            Path('text.txt')
        ]
        mock_rglob.return_value = mock_files

        # Execute
        result = main.find_video_files(self.test_source)

        # Assert
        self.assertEqual(len(result), 2)
        self.assertIn(Path('video1.mp4'), result)
        self.assertIn(Path('video2.mkv'), result)

    @patch('subprocess.check_output')
    def test_is_av1_true(self, mock_check_output):
        # Setup
        mock_check_output.return_value = b'av1\n'

        # Execute
        result = main.is_av1(Path('video.mp4'))

        # Assert
        self.assertTrue(result)

    @patch('subprocess.check_output')
    def test_is_av1_false(self, mock_check_output):
        # Setup
        mock_check_output.return_value = b'h264\n'

        # Execute
        result = main.is_av1(Path('video.mp4'))

        # Assert
        self.assertFalse(result)

    @patch('subprocess.check_output')
    def test_get_resolution(self, mock_check_output):
        # Setup
        mock_response = json.dumps({
            "streams": [{"width": 1920, "height": 1080}]
        })
        mock_check_output.return_value = mock_response.encode()

        # Execute
        width, height = main.get_resolution(Path('video.mp4'))

        # Assert
        self.assertEqual(width, 1920)
        self.assertEqual(height, 1080)

    @patch('subprocess.check_output')
    def test_get_crop_params(self, mock_check_output):
        # Setup
        mock_output = b'crop=1920:1080:0:0'
        mock_check_output.return_value = mock_output

        # Execute
        crop = main.get_crop_params(Path('video.mp4'))

        # Assert
        self.assertEqual(crop, 'crop=1920:1080:0:0')

    def test_should_skip_compressed_file(self):
        # Test files with _compressed in name
        self.assertTrue(main.should_skip(Path('video_compressed.mp4')))

    @patch('main.is_av1')
    def test_should_skip_av1_file(self, mock_is_av1):
        # Setup
        mock_is_av1.return_value = True

        # Execute & Assert
        self.assertTrue(main.should_skip(Path('video.mp4')))

    @patch('subprocess.check_output')
    def test_get_audio_bitrate_cmd_stereo(self, mock_check_output):
        # Setup
        mock_response = json.dumps({
            "streams": [{"channels": 2, "bit_rate": "320000"}]
        })
        mock_check_output.return_value = mock_response.encode()

        # Execute
        result = main.get_audio_bitrate_cmd(Path('video.mp4'))

        # Assert
        self.assertEqual(result, ['-b:a:0', '128k'])

    @patch('subprocess.check_output')
    def test_get_audio_bitrate_cmd_multichannel(self, mock_check_output):
        # Setup
        mock_response = json.dumps({
            "streams": [{"channels": 6, "bit_rate": "384000"}]
        })
        mock_check_output.return_value = mock_response.encode()

        # Execute
        result = main.get_audio_bitrate_cmd(Path('video.mp4'))

        # Assert
        self.assertEqual(result, ['-b:a:0', '192k'])

    @patch('subprocess.check_output')
    def test_get_subtitle_dispositions(self, mock_check_output):
        # Setup
        mock_response = json.dumps({
            "streams": [
                {"index": 0, "tags": {"DISPOSITION_DEFAULT": "1"}},
                {"index": 1, "tags": {"DISPOSITION_DEFAULT": "0"}}
            ]
        })
        mock_check_output.return_value = mock_response.encode()

        # Execute
        result = main.get_subtitle_dispositions(Path('video.mp4'))

        # Assert
        self.assertEqual(result, [(0, True), (1, False)])

    @patch('shutil.move')
    @patch('pathlib.Path.mkdir')
    def test_move_to_old(self, mock_mkdir, mock_move):
        # Setup
        source_file = self.test_source / "test.mp4"

        # Execute
        main.move_to_old(source_file)

        # Assert
        mock_mkdir.assert_called_once()
        mock_move.assert_called_once()

    @patch('subprocess.run')
    @patch('main.get_resolution')
    @patch('main.get_subtitle_dispositions')
    @patch('main.get_audio_bitrate_cmd')
    @patch('main.get_crop_params')
    def test_compress_video(self, mock_crop, mock_audio, mock_subs, mock_res, mock_run):
        # Setup
        mock_res.return_value = (1920, 1080)
        mock_subs.return_value = [(0, True)]
        mock_audio.return_value = ['-b:a:0', '128k']
        mock_crop.return_value = None

        # Execute
        result = main.compress_video(Path('test.mp4'))

        # Assert
        mock_run.assert_called_once()
        self.assertEqual(result, Path('test_compressed.mp4'))


if __name__ == '__main__':
    unittest.main()