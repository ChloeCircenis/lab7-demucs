FROM python:3.11-slim

WORKDIR /app

# FFmpeg is needed for audio processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "numpy==1.26.4" demucs redis minio requests

COPY worker-server.py .

CMD ["python3", "worker-server.py"]