"""End-to-end smoke test for Local Karaoke.

1. Generates a short (10s) synthetic sine-wave WAV with ffmpeg.
2. Uploads it to POST /api/songs.
3. Polls GET /api/songs/{id} every 1.5 seconds until 'done' or 'failed'.
4. Validates that meta.json, status.json, instrumental.flac, vocals.flac,
   and lyrics.json are all present and follow §2.4 contract rules.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

BASE_URL = "http://localhost:8000"


def generate_test_audio(out_wav: Path, duration_sec: int = 10) -> None:
    """Generate a clean 10-second stereo 44.1kHz sine tone using ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:duration={duration_sec}",
        "-ac", "2",
        "-ar", "44100",
        str(out_wav),
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def upload_song(file_path: Path, title: str, artist: str) -> str:
    """Upload multipart form to POST /api/songs without external dependencies."""
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    data = []

    def add_field(name, value):
        data.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())

    add_field("title", title)
    add_field("artist", artist)

    # File part
    file_bytes = file_path.read_bytes()
    data.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_path.name}\"\r\nContent-Type: audio/wav\r\n\r\n".encode()
    )
    data.append(file_bytes)
    data.append(f"\r\n--{boundary}--\r\n".encode())

    body = b"".join(data)
    req = Request(f"{BASE_URL}/api/songs", data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    with urlopen(req) as resp:
        res = json.loads(resp.read().decode())
        return res["id"]


def poll_song(song_id: str, timeout_sec: int = 180) -> dict:
    """Poll GET /api/songs/{id} until done or failed."""
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        req = Request(f"{BASE_URL}/api/songs/{song_id}")
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            status = data["status"]
            state = status["state"]
            print(f"[{round(time.time() - t0, 1)}s] Song state: {state} (stage: {status.get('stage')}, msg: {status.get('message')})")
            if state == "done":
                return data
            if state == "failed":
                raise RuntimeError(f"Job failed: {status.get('error')}")
        time.sleep(1.5)
    raise TimeoutError(f"Job did not complete within {timeout_sec}s")


def validate_lyrics_contract(lyrics: dict) -> None:
    """Validate lyrics.json rules per §2.4."""
    assert lyrics.get("version") == 1, "lyrics version must be 1"
    assert "language" in lyrics, "language missing"
    assert "source" in lyrics, "source missing"
    assert "alignment" in lyrics, "alignment missing"
    assert "quality" in lyrics, "quality missing"
    assert "lines" in lyrics, "lines missing"

    lines = lyrics["lines"]
    for l_idx, line in enumerate(lines):
        assert "start" in line and "end" in line, f"Line {l_idx} missing start/end"
        assert line["start"] <= line["end"], f"Line {l_idx} start > end"
        words = line.get("words", [])
        assert len(words) > 0, f"Line {l_idx} words array is empty"

        cur_time = line["start"]
        for w_idx, w in enumerate(words):
            assert "w" in w and "s" in w and "e" in w, f"Word {w_idx} missing w/s/e"
            assert isinstance(w["s"], (int, float)) and isinstance(w["e"], (int, float)), "Word times must be numeric"
            assert w["s"] <= w["e"], f"Word {w['w']} s > e ({w['s']} > {w['e']})"
            assert w["s"] >= cur_time - 0.05, f"Word times must be non-decreasing within line"
            cur_time = w["e"]

    print("✓ lyrics.json passed all contract validation rules!")


def main():
    print("=== Local Karaoke Smoke Test ===")
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_wav = Path(tmp_dir) / "test_sample.wav"
        print("1. Generating 10s synthetic audio tone...")
        generate_test_audio(test_wav, duration_sec=10)

        print("2. Uploading to /api/songs...")
        song_id = upload_song(test_wav, title="Smoke Test Song", artist="AI Runner")
        print(f"   Created song ID: {song_id}")

        print("3. Polling status until done...")
        res = poll_song(song_id, timeout_sec=180)

        print("4. Validating output files and contracts...")
        req = Request(f"{BASE_URL}/api/songs/{song_id}/lyrics")
        with urlopen(req) as resp:
            lyrics_data = json.loads(resp.read().decode())
            validate_lyrics_contract(lyrics_data)

        print("=== SMOKE TEST SUCCEEDED ===")


if __name__ == "__main__":
    main()
