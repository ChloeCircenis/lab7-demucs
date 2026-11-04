#Identify your Google Cloud project.
# Enable the necessary APIs.
# Check whether the Artifact Registry repository exists.
# Create the repository if necessary.
# Build and upload the REST Docker image.
# Build and upload the Demucs worker Docker image.
import argparse
import subprocess
from pathlib import Path

# Project configuration
CLUSTER = "demucs-lab7"
ZONE = "us-central1-b"
MACHINE_TYPE = "e2-standard-4"
REGION = "us-central1"
REPOSITORY = "demucs-images"
# VERSION = "v5"
REST_VERSION = "v4"
WORKER_VERSION = "v5"

ROOT = Path(__file__).resolve().parent


def run(command):
    """Execute a command and stop if it fails."""
    print(f"\nRunning: {' '.join(command)}", flush=True)
    subprocess.run(command, check=True, cwd=ROOT)


def get_project_id():
    """Read the currently configured Google Cloud project."""
    result = subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()


def setup_registry():
    """Enable APIs and create the image repository if needed."""
    run([
        "gcloud", "services", "enable",
        "cloudbuild.googleapis.com",
        "artifactregistry.googleapis.com",
        "container.googleapis.com"
    ])

    check = subprocess.run(
        [
            "gcloud", "artifacts", "repositories", "describe",
            REPOSITORY, "--location", REGION
        ],
        capture_output=True
    )

    if check.returncode != 0:
        run([
            "gcloud", "artifacts", "repositories", "create",
            REPOSITORY,
            "--repository-format=docker",
            "--location", REGION
        ])


def build_images(project_id):
    """Build and upload REST and worker images."""
    registry = (
        f"{REGION}-docker.pkg.dev/"
        f"{project_id}/{REPOSITORY}"
    )

    images = [
        ("demucs-rest", "rest", REST_VERSION),
        ("demucs-worker", "worker", WORKER_VERSION)
    ]

    for service, directory, version in images:
        image = f"{registry}/{service}:{version}"

        # REST uses a custom Dockerfile name
        if directory == "rest":
            dockerfile = ROOT / "rest" / "Dockerfile-rest"
            default = ROOT / "rest" / "Dockerfile"
            default.write_bytes(dockerfile.read_bytes())

        run([
            "gcloud", "builds", "submit",
            str(ROOT / directory),
            "--tag", image
        ])

        print(f"Built image: {image}")


def deploy_application():
    """Deploy resources and verify Kubernetes rollouts."""
    run(["sh", "deploy-all.sh"])

    for deployment in [
        "redis",
        "minio",
        "rest-server",
        "demucs-worker",
        "logs"
    ]:
        run([
            "kubectl", "rollout", "status",
            f"deployment/{deployment}",
            "--timeout=300s"
        ])

    print("All Kubernetes deployments are ready.")


def create_cluster():
    """Create a GKE cluster if it doesn't exist."""
    check = subprocess.run(
        [
            "gcloud", "container", "clusters", "describe",
            CLUSTER, "--zone", ZONE
        ],
        capture_output=True
    )

    if check.returncode != 0:
        run([
            "gcloud", "container", "clusters", "create",
            CLUSTER,
            "--zone", ZONE,
            "--num-nodes", "2",
            "--machine-type", MACHINE_TYPE,
            "--disk-size", "50"
        ])

    run([
        "gcloud", "container", "clusters", "get-credentials",
        CLUSTER, "--zone", ZONE
    ])


def create_minio_secret():
    """Create credentials used by MinIO and application pods."""
    import secrets

    # Preserve credentials if the secret already exists
    check = subprocess.run(
        ["kubectl", "get", "secret", "minio-credentials"],
        capture_output=True
    )

    if check.returncode == 0:
        return

    password = secrets.token_urlsafe(24)

    run([
        "kubectl", "create", "secret", "generic",
        "minio-credentials",
        "--from-literal=access-key=rootuser",
        f"--from-literal=secret-key={password}"
    ])

def delete_cluster():
    """Delete the GKE cluster to stop compute charges."""
    run([
        "gcloud", "container", "clusters", "delete",
        CLUSTER, "--zone", ZONE, "--quiet"
    ])


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--build", action="store_true")
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--cleanup", action="store_true")

    args = parser.parse_args()

    if args.cleanup:
        delete_cluster()
        return

    if args.build:
        project_id = get_project_id()
        setup_registry()
        build_images(project_id)

    if args.deploy:
        setup_registry()
        create_cluster()
        create_minio_secret()
        deploy_application()

    if not any([args.build, args.deploy, args.cleanup]):
        parser.print_help()



if __name__ == "__main__":
    main()
