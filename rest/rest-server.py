# accepts MP3 requests
# communicate with Redis
# retrieve processed audio from MinIO

import os
import io
import json
import base64
import binascii
import hashlib

import redis
from minio import Minio
from minio.error import S3Error
from flask import Flask, jsonify, request, send_file

app = Flask(__name__)

# Environment configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT_NUMBER", "6379"))
REDIS_QUEUE = os.getenv("REDIS_QUEUE", "toWorker")

MINIO_HOST = os.getenv("MINIO_HOST", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "rootpass123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "demucs-bucket")

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)

minio_client = Minio(
    MINIO_HOST,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

TRACKS = {"bass.mp3", "drums.mp3", "vocals.mp3", "other.mp3"}


def ensure_bucket():
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Music Separation Server",
        "status": "running"
    })


@app.route("/apiv1/separate", methods=["POST"])
def separate():
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or "mp3" not in data:
        return jsonify({"error": "Missing MP3 data"}), 400

    model = data.get("model", "htdemucs")
    callback = data.get("callback")

    try:
        audio = base64.b64decode(data["mp3"], validate=True)
    except (TypeError, ValueError, binascii.Error):
        return jsonify({"error": "Invalid Base64 audio"}), 400

    if not audio:
        return jsonify({"error": "Empty audio file"}), 400

    # Generate a unique song identifier
    songhash = hashlib.sha256(audio).hexdigest()

    # Store original MP3 in MinIO
    object_name = f"{songhash}/original.mp3"

    try:
        ensure_bucket()

        minio_client.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(audio),
            length=len(audio),
            content_type="audio/mpeg"
        )

        # Send lightweight job to Redis
        job = {
            "songhash": songhash,
            "object_name": object_name,
            "model": model,
            "callback": callback
        }

        redis_client.rpush(
            REDIS_QUEUE,
            json.dumps(job)
        )

    except Exception:
        app.logger.exception("Failed to enqueue song")
        return jsonify({"error": "Storage or queue unavailable"}), 503

    return jsonify({
        "hash": songhash,
        "reason": "Song enqueued for separation"
    }), 200


@app.route("/apiv1/queue", methods=["GET"])
@app.route("/apiv1/queue/", methods=["GET"])
def queue():
    try:
        jobs = redis_client.lrange(REDIS_QUEUE, 0, -1)
        hashes = [json.loads(job)["songhash"] for job in jobs]

        return jsonify({"queue": hashes})
    except Exception:
        app.logger.exception("Failed to read queue")
        return jsonify({"error": "Queue unavailable"}), 503


@app.route("/apiv1/track/<songhash>/<track>", methods=["GET"])
def get_track(songhash, track):
    if track not in TRACKS:
        return jsonify({"error": "Invalid track"}), 400

    object_name = f"{songhash}/{track}"

    try:
        response = minio_client.get_object(
            MINIO_BUCKET, object_name
        )

        try:
            audio = response.read()
        finally:
            response.close()
            response.release_conn()

        return send_file(
            io.BytesIO(audio),
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name=track
        )

    except S3Error as exc:
        if exc.code in ("NoSuchKey", "NoSuchBucket"):
            return jsonify({"error": "Track not found"}), 404
        app.logger.exception("MinIO error")
        return jsonify({"error": "Storage error"}), 503


@app.route("/apiv1/remove/<songhash>/<track>", methods=["GET", "DELETE"])
def remove_track(songhash, track):
    if track not in TRACKS:
        return jsonify({"error": "Invalid track"}), 400

    try:
        minio_client.remove_object(
            MINIO_BUCKET,
            f"{songhash}/{track}"
        )

        return jsonify({
            "hash": songhash,
            "track": track,
            "reason": "Track removed"
        })

    except Exception:
        app.logger.exception("Failed to remove track")
        return jsonify({"error": "Storage error"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)