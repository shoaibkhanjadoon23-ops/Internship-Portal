# ============================================================
# SadTalker Batch Render Worker
# ------------------------------------------------------------
# Paste this into a Colab or Kaggle notebook (split into cells
# where marked "# --- CELL ---"). Run top to bottom manually,
# once per batch (e.g. weekly), whenever there are queued lessons.
#
# What it does each run:
#   1. Loop: ask the backend for the next queued video job
#   2. Generate speech audio from the lesson script (Piper TTS, free/offline)
#   3. Feed the audio + presenter photo into SadTalker
#   4. Upload the rendered .mp4 to Supabase Storage
#   5. Tell the backend the job is done (or failed)
#   6. Repeat until the queue is empty
# ============================================================

# --- CELL 1: Setup (run once per session) ---
"""
!git clone https://github.com/OpenTalker/SadTalker.git
%cd SadTalker
!pip install -q -r requirements.txt
!bash scripts/download_models.sh          # downloads SadTalker's pretrained checkpoints
!pip install -q piper-tts requests supabase
"""

# --- CELL 2: Config ---
import os

API_BASE_URL = "https://YOUR-BACKEND-URL.example.com"   # your deployed FastAPI backend
WORKER_API_KEY = "PASTE_THE_SAME_WORKER_API_KEY_FROM_.env"

SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "PASTE_YOUR_SERVICE_ROLE_KEY"   # same one the backend uses
VIDEO_BUCKET = "lesson-videos"

DEFAULT_PRESENTER_PHOTO = "/content/presenter.jpg"  # upload your one avatar photo here in Colab's file panel

WORK_DIR = "/content/render_tmp"
os.makedirs(WORK_DIR, exist_ok=True)

# --- CELL 3: Imports + clients ---
import requests
import uuid
import subprocess
from supabase import create_client

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
HEADERS = {"X-Worker-Key": WORKER_API_KEY}


# --- CELL 4: Helper functions ---
def get_next_job():
    r = requests.get(f"{API_BASE_URL}/jobs/next", headers=HEADERS, params={"worker_id": "colab-worker-1"})
    r.raise_for_status()
    return r.json().get("job")


def mark_job_done(job_id: str, video_url: str):
    r = requests.post(f"{API_BASE_URL}/jobs/{job_id}/complete", headers=HEADERS, json={"result_video_url": video_url})
    r.raise_for_status()


def mark_job_failed(job_id: str, error_message: str):
    requests.post(f"{API_BASE_URL}/jobs/{job_id}/fail", headers=HEADERS, json={"error_message": error_message[:500]})


def script_to_audio(script_text: str, out_wav_path: str):
    """
    Text -> speech using Piper (fully offline, free, no API key needed).
    Requires a Piper voice model downloaded once, e.g.:
      !wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
      !wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
    """
    voice_model = "/content/en_US-lessac-medium.onnx"
    with open(f"{WORK_DIR}/script.txt", "w") as f:
        f.write(script_text)
    subprocess.run(
        f"cat {WORK_DIR}/script.txt | piper --model {voice_model} --output_file {out_wav_path}",
        shell=True, check=True,
    )


def render_with_sadtalker(photo_path: str, audio_path: str, out_dir: str) -> str:
    """
    Runs SadTalker's inference script. Returns the path to the rendered mp4.
    Assumes SadTalker was cloned + set up in Cell 1 and we're running from /content/SadTalker.
    """
    subprocess.run(
        f"python inference.py --driven_audio {audio_path} --source_image {photo_path} "
        f"--result_dir {out_dir} --still --preprocess full --enhancer gfpgan",
        shell=True, check=True, cwd="/content/SadTalker",
    )
    # SadTalker writes a timestamped subfolder; grab the newest .mp4 in out_dir
    mp4s = sorted(
        [os.path.join(root, f) for root, _, files in os.walk(out_dir) for f in files if f.endswith(".mp4")],
        key=os.path.getmtime,
    )
    if not mp4s:
        raise RuntimeError("SadTalker did not produce an output video")
    return mp4s[-1]


def upload_video(local_path: str) -> str:
    dest_name = f"{uuid.uuid4()}.mp4"
    with open(local_path, "rb") as f:
        sb.storage.from_(VIDEO_BUCKET).upload(dest_name, f, {"content-type": "video/mp4"})
    return sb.storage.from_(VIDEO_BUCKET).get_public_url(dest_name)


# --- CELL 5: Main batch loop — run this to process the whole queue ---
def run_batch():
    processed, failed = 0, 0
    while True:
        job = get_next_job()
        if not job:
            print("Queue empty — nothing left to render.")
            break

        job_id = job["id"]
        print(f"\n=== Rendering job {job_id} (lesson {job['lesson_id']}) ===")
        try:
            photo = job.get("avatar_photo_url") or DEFAULT_PRESENTER_PHOTO
            audio_path = f"{WORK_DIR}/{job_id}.wav"
            out_dir = f"{WORK_DIR}/{job_id}_out"
            os.makedirs(out_dir, exist_ok=True)

            script_to_audio(job["script_text"], audio_path)
            mp4_path = render_with_sadtalker(photo, audio_path, out_dir)
            public_url = upload_video(mp4_path)

            mark_job_done(job_id, public_url)
            print(f"Done -> {public_url}")
            processed += 1

        except Exception as e:
            print(f"FAILED: {e}")
            mark_job_failed(job_id, str(e))
            failed += 1

    print(f"\nBatch complete. Rendered: {processed}, Failed: {failed}")


# Run the whole queue:
run_batch()
