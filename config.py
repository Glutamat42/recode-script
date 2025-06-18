from pathlib import Path


class Config:
    def __init__(self):
        self.source_dir = Path("C:/Users/Markus/source")
        self.base_quality = 26
        self.cpu = 2
        self.audio_bitrate_stereo = 160
        self.audio_bitrate_multi = 256
        self.audio_bitrate_threshold = 1.25
        self.keyint_seconds = "-2"
        self.max_parallel_encodes = 1
        self.video_exts = {".mp4", ".mkv", ".mov", ".webm", ".avi"}
        self.compressed_suffix = "_compressed"
        self.crop_timestamps = [90, 180, 300]