import os
import shutil
import subprocess
import logging
import json
import re
from pathlib import Path

# === CONFIGURATION ===
SOURCE_DIR = Path("/Volumes/Ohne Titel/source")
OLD_DIR = Path("/Volumes/Ohne Titel/old")
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi"}
BASE_QUALITY = 60
#BASE_QUALITY = 38
CPU = 7
#CPU = 2
AUDIO_BITRATE_STEREO = 128
AUDIO_BITRATE_MULTI = 192
AUDIO_BITRATE_THRESHOLD = 1.25  # wont convert if source bitrate is less than this times target bitrate
OPUS_DELAY_MS = 60
COMPRESSED_SUFFIX = "_compressed"
KEYINT_SECONDS = "20s"
CROP_TIMESTAMPS = [90, 180, 300]

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Try to disable copyfile (._ files) on macOS
os.environ['COPYFILE_DISABLE'] = '1'

def main():
    video_files = find_video_files(SOURCE_DIR)
    for filepath in video_files:
        if should_skip(filepath):
            logging.info(f"Skipping {filepath}")
            continue
        logging.info(f"Processing {filepath}")
        try:
            compressed_path = compress_video(filepath)
            move_to_old(filepath)
            replace_original(filepath, compressed_path)
            logging.info(f"Done: {filepath}")
        except Exception as e:
            logging.error(f"Failed: {filepath} - {e}")

def find_video_files(root: Path):
    return [p for p in root.rglob("*") if p.suffix.lower() in VIDEO_EXTS and not p.name.startswith("._")]

def should_skip(path: Path):
    if COMPRESSED_SUFFIX in path.stem:
        return True
    return is_av1(path)

def is_av1(path: Path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
        str(path)
    ]
    try:
        output = subprocess.check_output(cmd).decode().strip()
        return output == "av1"
    except:
        return False

def get_resolution(path: Path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json",
        str(path)
    ]
    output = subprocess.check_output(cmd).decode()
    data = json.loads(output)
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"])

def get_crop_params(path: Path):
    crops = []
    for t in CROP_TIMESTAMPS:
        cmd = [
            "ffmpeg", "-ss", str(t), "-i", str(path),
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
    return f"crop={w}:{h}:{x}:{y}"

def compress_video(src: Path):
    dst = src.with_name(src.stem + COMPRESSED_SUFFIX + src.suffix)
    subtitle_dispositions = get_subtitle_dispositions(src)
    map_cmd = [
        "-map", "0:v",
        "-map", "0:a?",
        "-map", "0:s?",
        "-map_metadata", "0"
    ]
    audio_bitrate_cmd = get_audio_bitrate_cmd(src)
    disposition_cmds = []
    for index, is_default in subtitle_dispositions:
        disposition_cmds.extend(["-disposition:s:" + str(index), "default" if is_default else "0"])

    width, height = get_resolution(src)
    scale_expr = ""
    adjusted_crf = BASE_QUALITY
    if width <= 720:  # DVD resolution or lower
        adjusted_crf -= 4
    elif width <= 1280:  # HD/720p
        adjusted_crf -= 2
    elif width > 1920:
        scale_expr = "scale=1920:-2"

    crop_filter = get_crop_params(src)
    vf_chain = ",".join(filter(None, [crop_filter, scale_expr]))

    svt_params = (
        f"aq-mode=2:enable-qm=1:qm-min=0:tune=2:"
        f"enable-variance-boost=1:keyint={KEYINT_SECONDS}"
    )

    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        *map_cmd,
        "-c:v", "libsvtav1",
        "-pix_fmt", "yuv420p10le",
        "-preset", str(CPU),
        "-crf", str(adjusted_crf),
        "-svtav1-params", svt_params,
        *(["-vf", vf_chain] if vf_chain else []),
        "-application", "audio",
        "-opus_delay", str(OPUS_DELAY_MS),
        *audio_bitrate_cmd,
        "-c:s", "copy",
        "-movflags", "use_metadata_tags",
        *disposition_cmds,
        str(dst)
    ]
    logging.info("Running ffmpeg: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    return dst

def get_audio_bitrate_cmd(path: Path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=channels,bit_rate,channel_layout", "-of", "json", str(path)
    ]
    try:
        output = subprocess.check_output(cmd).decode()
        data = json.loads(output)
        streams = data.get("streams", [])
        if not streams:
            return []
        cmds = []
        for i, s in enumerate(streams):
            ch = s.get("channels", 2)
            src_br = int(s.get("bit_rate", 0)) // 1000
            layout = s.get("channel_layout", "")
            tgt_br = AUDIO_BITRATE_MULTI if ch > 2 else AUDIO_BITRATE_STEREO

            if src_br >= tgt_br * AUDIO_BITRATE_THRESHOLD:
                cmds += [f"-c:a:{i}", "libopus", f"-b:a:{i}", f"{tgt_br}k"]
                # Use channel mapping filter for 5.1 audio
                if ch > 2 and "5.1" in layout and "side" in layout:
                    cmds += [f"-af:a:{i}", "channelmap=channel_layout=5.1"]
            else:
                cmds += [f"-c:a:{i}", "copy"]
        return cmds
    except Exception as e:
        logging.error(f"Error in get_audio_bitrate_cmd: {e}")
        return []

def get_subtitle_dispositions(path: Path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "s",
        "-show_entries", "stream=index:stream_tags=DISPOSITION_DEFAULT",
        "-of", "json", str(path)
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

def move_to_old(path: Path):
    rel_path = path.relative_to(SOURCE_DIR)
    target_path = OLD_DIR / rel_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target_path))

def replace_original(orig: Path, new: Path):
    shutil.move(str(new), str(orig))

if __name__ == "__main__":
    main()
