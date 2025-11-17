import subprocess
import threading
from pathlib import Path

def download(url: str, download_dir: str, callback=None):
    download_path = Path(download_dir)
    download_path.mkdir(parents=True, exist_ok=True)

    before = {f for f in download_path.glob("*")}

    def worker():
        try:
            process = subprocess.run(
                ["spotdl", url, "--output", str(download_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if process.returncode != 0:
                print("STDERR:", process.stderr)
                print("Error Spotdl")
                if callback:
                    callback(None, None)
                return

            after = {f for f in download_path.glob("*")}
            new_files = sorted(after - before)

            if not new_files:
                print("No new files were downloaded.")
                if callback:
                    callback(None, None)
                return
            
            if callback:
                callback(
                    [f.name for f in new_files],
                    [str(f) for f in new_files]
                )

        except Exception as e:
            print(f"Exception during download: {e}")
            if callback:
                callback(None, None)

    thread = threading.Thread(target=worker)
    thread.start()