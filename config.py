from pathlib import Path


class Config:
    def __init__(self):
        self.source_dir = Path("C:/Users/Markus/source")
        self.base_quality = 26
        self.cpu = 2
        # Audio encoding: stereo/mono uses libopus with bitrate, multi-channel uses libfdk_aac with VBR
        self.audio_bitrate_stereo = 160
        self.audio_bitrate_threshold = 1.25
        self.audio_multichannel_vbr_level = 2  # used for streams witht more than 2 channels. VBR level for libfdk_aac multi-channel (1-5, where 1=highest quality, 5=lowest)
        self.audio_multichannel_aac_at_quality = 10  # VBR quality level for aac_at multi-channel (0-14, where 0=highest quality, 14=lowest)
        self.keyint_seconds = "-2"
        self.max_parallel_encodes = 2
        self.video_exts = {".mp4", ".mkv", ".mov", ".webm", ".avi"}
        self.compressed_suffix = "_compressed"
        self.crop_timestamps = [90, 180, 300]