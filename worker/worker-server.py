
import os
import json
import time
import tempfile
import subprocess
import logging
from pathlib import Path

import redis
import requests
from minio import Minio


# Configuration (shared with REST server)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT_NUMBER", "6379"))
REDIS_QUEUE = os.getenv("REDIS_QUEUE", "toWorker")

MINIO_HOST = os.getenv("MINIO_HOST", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "rootpass123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "demucs-bucket")

TRACKS = ("bass", "drums", "vocals", "other")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


# Connect to Redis and MinIO
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=10,
    socket_timeout=30
)

minio_client = Minio(
    MINIO_HOST,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

def log_info(message):
    logger.info(message)
    try:
        redis_client.lpush("logging", f"worker.info:{message}")
    except redis.RedisError:
        logger.exception("Failed to publish log")



def process_job(job):
    songhash = job["songhash"]
    object_name = job["object_name"]
    model = job.get("model", "htdemucs")

    log_info(f"Processing song {songhash}")

    songhash = job["songhash"]
    object_name = job["object_name"]
    model = job.get("model", "htdemucs")

    logger.info("Processing song %s", songhash)

    # Temporary directory automatically cleaned up
    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)

        input_path = work_dir / f"{songhash}.mp3"
        output_dir = work_dir / "output"

        # 1. Download original MP3
        log_info("Downloading original MP3")

        minio_client.fget_object(
            MINIO_BUCKET,
            object_name,
            str(input_path)
        )

        # 2. Run Demucs
        log_info(f"Running Demucs model {model}")

        command = [
            "python3",
            "-m",
            "demucs.separate",
            "--mp3",
            "-n",
            model,
            "--out",
            str(output_dir),
            str(input_path)
        ]

        subprocess.run(
            command,
            check=True,
            timeout=1800
        )

        # 3. Find and upload the separated tracks
        track_dir = output_dir / model / songhash

        for track in TRACKS:
            track_path = track_dir / f"{track}.mp3"

            if not track_path.is_file():
                raise FileNotFoundError(
                    f"Missing output track: {track_path}"
                )

            minio_client.fput_object(
                MINIO_BUCKET,
                f"{songhash}/{track}.mp3",
                str(track_path),
                content_type="audio/mpeg"
            )

            log_info(f"Uploaded {track}.mp3")

    log_info(f"Completed song {songhash}")

    # 4. Optional callback
    callback = job.get("callback")

    if isinstance(callback, dict) and callback.get("url"):
        try:
            requests.post(
                callback["url"],
                json=callback.get("data", {}),
                timeout=10
            )
        except requests.RequestException as exc:
            logger.warning("Callback failed: %s", exc)


def run_worker():
    """Continuously listen for Redis jobs."""

    logger.info("Worker started, listening on %s", REDIS_QUEUE)

    while True:
        try:
            # Block until a job arrives
            result = redis_client.blpop(
                REDIS_QUEUE,
                timeout=5
            )

            if result is None:
                continue

            _, message = result
            job = json.loads(message)

            try:
                process_job(job)
            except Exception:
                logger.exception(
                    "Failed processing job: %s",
                    job.get("songhash")
                )

        except redis.RedisError:
            logger.exception("Redis connection error")
            time.sleep(5)

        except (ValueError, KeyError, TypeError):
            logger.exception("Invalid job message")


if __name__ == "__main__":
    run_worker()
