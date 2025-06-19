import os
import shutil
import subprocess
import platform
import logging
import json
import re
from pathlib import Path
import platform
from config import Config


class FileProcessor:
    def __init__(self, filepath: Path, config: Config):
        self.filepath = filepath
        self.config = config
    
    def process(self):
        """Process the video file through the complete lifecycle"""
        logging.info(f"Processing {self.filepath}")
        try:
            compressed_path = self._compress_video()
            final_path = self._replace_original(compressed_path)
            return final_path
        except Exception as e:
            logging.error(f"Failed: {self.filepath} - {e}")
            raise Exception(f"Failed processing {self.filepath}: {e}")
    
    def should_skip(self):
        """Check if this file should be skipped"""
        if self.config.compressed_suffix in self.filepath.stem:
            logging.info(f"Skipping {self.filepath} because it is a temporary file")
            return True
        return False
    
    def _get_resolution(self):
        """Get video resolution"""
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json",
            str(self.filepath)
        ]
        output = subprocess.check_output(cmd).decode()
        data = json.loads(output)
        stream = data["streams"][0]
        return int(stream["width"]), int(stream["height"])
    
    def _get_crop_params(self):
        """Get crop parameters for the video"""
        crops = []
        for t in self.config.crop_timestamps:
            cmd = [
                "ffmpeg", "-ss", str(t), "-i", str(self.filepath),
                "-vframes", "10", "-vf", "cropdetect",
                "-f", "null", "-"
            ]
            try:
                result = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
                crop_matches = re.findall(r"crop=\d+:\d+:\d+:\d+", result)
                crops += crop_matches
            except subprocess.CalledProcessError:
                continue

        if not crops:
            return None

        crop_values = [list(map(int, x.split("=")[1].split(":"))) for x in crops]
        w = max(c[0] for c in crop_values)
        h = max(c[1] for c in crop_values)
        x = min(c[2] for c in crop_values)
        y = min(c[3] for c in crop_values)
        
        # Get original resolution to compare
        orig_width, orig_height = self._get_resolution()
        
        # Only return crop parameters if they actually crop something
        # (i.e., if the crop dimensions are smaller than original or offset from 0,0)
        if w < orig_width or h < orig_height or x > 0 or y > 0:
            return f"crop={w}:{h}:{x}:{y}"
        
        return None
    
    def _get_low_priority_prefix(self):
        """Return the command prefix to run a process at lowest priority based on OS"""
        system = platform.system().lower()
        if system == 'darwin':  # macOS
            return ["nice", "-n", "20"]
        elif system == 'linux':
            return ["nice", "-n", "19"]
        elif system == 'windows':
            return ["start", "/low", "/wait", "cmd", "/c"]
        return []  # Default: no prefix
    
    def _should_copy_video_stream(self):
        """Check if the video stream should be copied based on codec and filename"""
        cmd_check_codec = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
            str(self.filepath)
        ]
        try:
            codec = subprocess.check_output(cmd_check_codec).decode().strip()
            if codec == 'av1':
                return True
            return codec == "hevc" and "FuN" in self.filepath.name
        except Exception as e:
            logging.error(f"Error checking codec: {e}")
            return False
    
    def _analyze_audio_streams(self):
        """Analyze audio streams and determine what processing is needed"""
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=channels,bit_rate:format=duration", "-of", "json", str(self.filepath)
        ]
        try:
            output = subprocess.check_output(cmd).decode()
            data = json.loads(output)
            streams = data.get("streams", [])
            if not streams:
                return [], False

            # Get duration from format section
            duration = float(data.get("format", {}).get("duration", 0))
            
            stream_targets = []
            transcode_anything = False

            for i, s in enumerate(streams):
                ch = s.get("channels", 2)
                src_br = int(s.get("bit_rate", 0)) // 1000
                
                # If bitrate is unknown, get it by extracting the stream
                if src_br == 0:
                    src_br = self._get_actual_audio_bitrate(i, duration)
                
                # For stereo/mono: use target bitrate, for multi-channel: use VBR (no bitrate comparison needed)
                if ch > 2:
                    tgt_br = 0  # VBR mode, no target bitrate
                    target_codec = "libfdk_aac"
                    # Calculate threshold based on VBR level and channel count
                    vbr_level = self.config.audio_multichannel_vbr_level
                    if vbr_level == 1:
                        kbps_per_channel = 32
                    elif vbr_level == 2:
                        kbps_per_channel = 40
                    elif vbr_level == 3:
                        kbps_per_channel = 56
                    elif vbr_level == 4:
                        kbps_per_channel = 64
                    else:  # vbr_level == 5
                        kbps_per_channel = 96
                    
                    threshold_bitrate = int(kbps_per_channel * ch * self.config.audio_bitrate_threshold)
                    needs_transcode = src_br > threshold_bitrate
                else:
                    tgt_br = self.config.audio_bitrate_stereo
                    target_codec = "libopus"
                    needs_transcode = src_br > tgt_br * self.config.audio_bitrate_threshold

                stream_target = {
                    'index': i,
                    'channels': ch,
                    'source_bitrate': src_br,
                    'target_bitrate': tgt_br,
                    'target_codec': target_codec,
                    'needs_transcode': needs_transcode
                }
                
                if needs_transcode:
                    transcode_anything = True
                
                stream_targets.append(stream_target)

            return stream_targets, transcode_anything
        except Exception as e:
            logging.error(f"Error analyzing audio streams: {e}")
            raise e

    def _generate_audio_commands(self, stream_targets):
        """Generate audio encoding commands based on stream analysis"""
        cmds = []

        for target in stream_targets:
            i = target['index']
            
            if target['needs_transcode']:
                if target['target_codec'] == 'libfdk_aac':
                    cmds += [
                        f"-map", f"0:a:{i}", 
                        f"-c:a:{i}", target['target_codec'], 
                        f"-vbr", str(self.config.audio_multichannel_vbr_level)
                    ]
                else:
                    # Use bitrate for other codecs (like libopus)
                    cmds += [
                        f"-map", f"0:a:{i}", 
                        f"-c:a:{i}", target['target_codec'], 
                        f"-b:a:{i}", f"{target['target_bitrate']}k"
                    ]
            else:
                cmds += [f"-map", f"0:a:{i}", f"-c:a:{i}", "copy"]

        return cmds

    def _get_audio_bitrate_cmd(self):
        """Get audio encoding commands"""
        stream_targets, transcode_anything = self._analyze_audio_streams()
        if not stream_targets:
            return False, []
        
        cmds = self._generate_audio_commands(stream_targets)
        return transcode_anything, cmds
    
    def _get_subtitle_dispositions(self):
        """Get subtitle stream dispositions"""
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "s",
            "-show_entries", "stream=index:stream_tags=DISPOSITION_DEFAULT",
            "-of", "json", str(self.filepath)
        ]
        try:
            result = subprocess.check_output(cmd).decode()
            data = json.loads(result)
            dispositions = []

            for stream in data.get("streams", []):
                index = stream.get("index", 0)  # Get actual stream index from ffprobe
                tags = stream.get("tags", {})
                is_default = tags.get("DISPOSITION_DEFAULT", "0") == "1"
                dispositions.append((index, is_default))
            return dispositions
        except:
            return []
    
    def _compress_video(self):
        """Compress the video file"""
        # Build command components
        video_cmd = self._build_video_commands()
        audio_transcode, audio_cmd = self._get_audio_bitrate_cmd()
        
        # Check if any transcoding is needed
        video_transcode = video_cmd != ["-c:v", "copy"]
        if not audio_transcode and not video_transcode:
            logging.info("No transcoding needed, leaving file untouched: %s", str(self.filepath))
            return self.filepath
        
        # Transcoding needed, build remaining components and execute
        dst = self._get_output_path()
        map_cmd = self._build_map_commands()
        subtitle_cmd = self._build_subtitle_commands()
        metadata_cmd = self._build_metadata_commands(video_cmd, audio_cmd)
        
        return self._execute_compression(dst, map_cmd, video_cmd, audio_cmd, subtitle_cmd, metadata_cmd, audio_transcode)
    
    def _get_output_path(self):
        """Get the output file path"""
        return self.filepath.with_name(self.filepath.stem + self.config.compressed_suffix + '.mkv')
    
    def _build_map_commands(self):
        """Build ffmpeg mapping commands"""
        return [
            "-map", "0:v:0",  # Only first video stream
            "-map", "0:s?",   # All subtitle streams (optional)
            "-map_metadata", "0"
        ]
    
    def _build_video_commands(self):
        """Build video encoding commands"""
        video_transcode = not self._should_copy_video_stream()
        
        if not video_transcode:
            return ["-c:v", "copy"]
        
        width, height = self._get_resolution()
        adjusted_crf = self._calculate_adjusted_crf(width)
        scale_expr = "scale=1920:-2" if width > 1920 else ""
        
        crop_filter = self._get_crop_params()
        
        # Build filter chain only with non-empty filters
        filters = []
        if crop_filter:
            filters.append(crop_filter)
        if scale_expr:
            filters.append(scale_expr)
        
        svt_params = (
            f"enable-qm=1:qm-min=0:tune=2:"
            f"enable-variance-boost=1:keyint={self.config.keyint_seconds}"
        )
        
        video_cmd = [
            "-c:v", "libsvtav1",
            "-pix_fmt", "yuv420p10le",
            "-preset", str(self.config.cpu),
            "-crf", str(adjusted_crf),
            "-svtav1-params", svt_params,
        ]
        
        if filters:
            video_cmd.extend(["-vf", ",".join(filters)])
            
        return video_cmd
    
    def _calculate_adjusted_crf(self, width):
        """Calculate adjusted CRF based on resolution"""
        adjusted_crf = self.config.base_quality
        if width <= 720:  # DVD resolution or lower
            adjusted_crf -= 4
        elif width <= 1280:  # HD/720p
            adjusted_crf -= 2
        return adjusted_crf
    
    def _build_subtitle_commands(self):
        """Build subtitle disposition commands"""
        subtitle_dispositions = self._get_subtitle_dispositions()
        disposition_cmds = []
        for index, is_default in subtitle_dispositions:
            disposition_cmds.extend(["-disposition:s:" + str(index), "default" if is_default else "0"])
        return disposition_cmds
    
    def _build_metadata_commands(self, video_cmd, audio_cmd):
        """Build metadata commands"""
        return [
            "-metadata", f"video_settings={' '.join(video_cmd)}",
            "-metadata", f"audio_settings={' '.join(audio_cmd)}"
        ]
    
    def _execute_compression(self, dst, map_cmd, video_cmd, audio_cmd, subtitle_cmd, metadata_cmd, audio_transcode):
        """Execute the compression (only called when transcoding is needed)"""
        cmd = [
            *self._get_low_priority_prefix(),
            "ffmpeg", "-y", "-i", str(self.filepath),
            *map_cmd,
            *video_cmd,
            *audio_cmd,
            "-c:s", "copy",
            "-movflags", "use_metadata_tags",
            *subtitle_cmd,
            *metadata_cmd,
            "-nostats" if self.config.max_parallel_encodes > 1 else "-stats",
            str(dst)
        ]
        logging.info("Running ffmpeg: %s", " ".join(cmd))
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return dst
    
    def _replace_original(self, new_path: Path):
        """Replace the original file with the compressed version"""
        # If no compression occurred (new_path is same as original), just return original
        if new_path == self.filepath:
            return self.filepath
            
        # When replacing the original file, keep the .mkv extension
        final_path = self.filepath.with_suffix(".mkv")
        shutil.move(str(new_path), str(final_path))
        # Remove the original file if it has a different extension
        if self.filepath != final_path:
            self.filepath.unlink()
        return final_path
    
    def _get_actual_audio_bitrate(self, stream_index, duration):
        """Get actual audio bitrate by extracting the stream and measuring size"""
        try:            
            # Extract the audio stream to null and get the size
            extract_cmd = [
                "ffmpeg", "-i", str(self.filepath), "-map", f"0:a:{stream_index}",
                "-c", "copy", "-f", "null", "-"
            ]
            
            # Run ffmpeg and capture stderr to get the size info
            result = subprocess.run(extract_cmd, capture_output=True, text=True, check=True)
            
            # Parse the audio size from ffmpeg output (look for "audio:XXXkB" in stderr)
            size_match = re.search(r'audio:(\d+)kB', result.stderr, re.IGNORECASE)
            if size_match:
                size_kb = int(size_match.group(1))
                size_bits = size_kb * 1024 * 8
                bitrate_bps = size_bits / duration
                bitrate_kbps = int(bitrate_bps / 1000)
                
                logging.info(f"Measured audio bitrate for stream {stream_index}: {bitrate_kbps}k")
                return bitrate_kbps
            else:
                raise Exception(f"Could not parse audio stream size from ffmpeg output for stream index {stream_index} of file {self.filepath}")
                
        except Exception as e:
            logging.warning(f"Could not measure audio bitrate for stream {stream_index}: {e}")
            return 9999  # fallback: just reencode