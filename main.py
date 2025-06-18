import os
import logging
import concurrent.futures
from pathlib import Path
from tqdm import tqdm
from datetime import datetime
from config import Config
from file_processor import FileProcessor

# === LOGGING SETUP ===
config = Config()
log_file = config.source_dir / f"video_compression_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers = [
        logging.FileHandler(log_file),
    ]
)

# Try to disable copyfile (._ files) on macOS
os.environ['COPYFILE_DISABLE'] = '1'


def main():
    video_files = find_video_files(config.source_dir)
    total_files = len(video_files)

    logging.info(f"Found {total_files} video files to process")

    # Setup progress bar
    with tqdm(total=total_files, desc="Compressing videos", unit="file") as progress_bar:
        # Process videos in parallel using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=config.max_parallel_encodes) as executor:
            futures = {}
            for filepath in video_files:
                processor = FileProcessor(filepath, config)
                if processor.should_skip():
                    logging.info(f"Skipping {filepath}")
                    progress_bar.update(1)  # Update progress for skipped files
                    continue
                future = executor.submit(processor.process)
                futures[future] = filepath

            # Wait for all tasks to complete and log results
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    logging.info(f"Done: {result}")
                except Exception as e:
                    filepath = futures[future]
                    logging.error(f"Failed task: {filepath} - {e}")
                finally:
                    progress_bar.update(1)  # Update progress bar

def find_video_files(root: Path):
    return [p for p in root.rglob("*") if p.suffix.lower() in config.video_exts and not p.name.startswith("._")]

if __name__ == "__main__":
    main()
