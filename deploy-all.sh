#!/bin/sh
set -eu

# Deploy Redis
kubectl apply -f redis/redis-deployment.yaml
kubectl apply -f redis/redis-service.yaml

# Deploy MinIO
kubectl apply -f minio/minio-deployment.yaml
kubectl apply -f minio/minio-service.yaml

# Deploy REST API
kubectl apply -f rest/rest-deployment.yaml
kubectl apply -f rest/rest-service.yaml

# Deploy logging service
kubectl apply -f logs/logs-deployment.yaml

# Deploy Demucs worker
kubectl apply -f worker/worker-deployment.yaml

# Expose REST API
kubectl apply -f rest/rest-ingress.yaml

echo "Kubernetes resources submitted successfully."
