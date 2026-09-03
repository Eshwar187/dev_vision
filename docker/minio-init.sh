#!/bin/sh
# Wait for MinIO service to become ready
echo "Waiting for MinIO server to be available..."
until /usr/bin/mc alias set devvision_minio http://minio:9000 minioadmin minioadmin; do
    echo "MinIO not ready yet, sleeping 2 seconds..."
    sleep 2
done

echo "MinIO is ready. Creating default private bucket: devvision-local"
/usr/bin/mc mb --ignore-existing devvision_minio/devvision-local
/usr/bin/mc anonymous set none devvision_minio/devvision-local
echo "MinIO default bucket configuration complete."
