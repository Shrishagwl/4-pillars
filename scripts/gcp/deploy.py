"""Deploy immutable backend images. Never reads secret payloads or changes IAM."""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SERVICES = ("telstra-fake", "telstra-gateway", "engine", "ingest-api", "twin")
DEPENDENCIES = {
    "telstra-fake": {},
    "telstra-gateway": {"TELSTRA_BASE_URL": "telstra-fake"},
    "engine": {"GATEWAY_URL": "telstra-gateway", "INGEST_URL": "ingest-api"},
    "ingest-api": {"ENGINE_URL": "engine"},
    "twin": {"TELSTRA_FAKE_URL": "telstra-fake", "INGEST_URL": "ingest-api"},
}
SECRETS = {
    "ingest-api": {"DATABASE_URL": "ingest-database-url", "ADMIN_API_KEY": "ingest-admin-key"},
    "engine": {"DATABASE_URL": "engine-database-url"},
    "twin": {"INGEST_API_KEY": "ingest-admin-key"},
    "telstra-gateway": {
        "TELSTRA_CLIENT_ID": "telstra-client-id",
        "TELSTRA_CLIENT_SECRET": "telstra-client-secret",
    },
}


@dataclass(frozen=True)
class Settings:
    project: str
    region: str
    repository: str = "four-pillars"
    service_prefix: str = "four-pillars"
    runtime_sa_prefix: str = "fp"
    secret_prefix: str = "four-pillars"
    secret_version: str = "1"
    max_instances: int = 2
    cloud_sql_instance: str = ""
    log_level: str = "info"
    use_application_secrets: bool = False
    # Short topic name ingest-api publishes to; empty keeps the HTTP hand-off.
    pubsub_topic: str = ""
    # Which secrets have a version yet. Empty with use_application_secrets = all of them.
    enabled_secrets: tuple = ()

    def __post_init__(self):
        for value in (self.project, self.region, self.repository, self.service_prefix,
                      self.runtime_sa_prefix, self.secret_prefix):
            if not re.fullmatch(r"[a-z][a-z0-9-]*", value):
                raise ValueError("Deployment identifiers must use lowercase letters, digits and hyphens")
        if len(self.runtime_sa_prefix) > 14 or len(self.service_prefix) > 33:
            raise ValueError("Prefixes exceed service account or Cloud Run name limits")
        if not 1 <= self.max_instances <= 100:
            raise ValueError("max_instances must be between 1 and 100")
        if not re.fullmatch(r"[1-9][0-9]*", self.secret_version):
            raise ValueError("Pin secrets to a positive numeric version, never latest")
        if self.cloud_sql_instance and not re.fullmatch(
            re.escape(self.project) + r":[a-z0-9-]+:[a-z0-9-]+", self.cloud_sql_instance
        ):
            raise ValueError("Cloud SQL instance must belong to the deployment project")
        if self.log_level not in {"debug", "info", "warn", "error"}:
            raise ValueError("Unsupported log level")
        if self.pubsub_topic and not re.fullmatch(r"[a-z][a-z0-9-]*", self.pubsub_topic):
            raise ValueError("Pub/Sub topic must be a short lowercase name")
        known = {secret for names in SECRETS.values() for secret in names.values()}
        if set(self.enabled_secrets) - known:
            raise ValueError(f"Unknown secrets: {sorted(set(self.enabled_secrets) - known)}")

    @classmethod
    def from_env(cls):
        secret_opt_in = os.getenv("GCP_USE_APPLICATION_SECRETS") or "false"
        if secret_opt_in not in {"true", "false"}:
            raise ValueError("GCP_USE_APPLICATION_SECRETS must be true or false")
        return cls(
            project=os.environ["GCP_PROJECT_ID"],
            region=os.environ["GCP_REGION"],
            repository=os.getenv("GCP_ARTIFACT_REPOSITORY") or "four-pillars",
            service_prefix=os.getenv("GCP_SERVICE_PREFIX") or "four-pillars",
            runtime_sa_prefix=os.getenv("GCP_RUNTIME_SA_PREFIX") or "fp",
            secret_prefix=os.getenv("GCP_SECRET_PREFIX") or "four-pillars",
            secret_version=os.getenv("GCP_SECRET_VERSION") or "1",
            max_instances=int(os.getenv("GCP_MAX_INSTANCES") or "2"),
            cloud_sql_instance=os.getenv("GCP_CLOUD_SQL_INSTANCE", ""),
            log_level=os.getenv("GCP_LOG_LEVEL") or "info",
            use_application_secrets=secret_opt_in == "true",
            pubsub_topic=os.getenv("GCP_PUBSUB_TOPIC") or "",
            enabled_secrets=tuple(
                name.strip() for name in (os.getenv("GCP_ENABLED_SECRETS") or "").split(",")
                if name.strip()
            ),
        )

    def service_name(self, service):
        return f"{self.service_prefix}-{service}"


def validate_images(settings, images):
    if set(images) != set(SERVICES):
        raise ValueError("An immutable image is required for each of the five backend services")
    registry = f"{settings.region}-docker.pkg.dev/{settings.project}/{settings.repository}"
    for service, image in images.items():
        if not re.fullmatch(re.escape(f"{registry}/{service}@sha256:") + r"[a-f0-9]{64}", image):
            raise ValueError(f"Invalid image digest or registry for {service}")


def render_service(settings, service, image, urls):
    env = [{"name": "LOG_LEVEL", "value": settings.log_level}]
    for key, target in DEPENDENCIES[service].items():
        url = urls[target]
        if not re.fullmatch(r"https://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app", url):
            raise ValueError(f"Expected a private Cloud Run HTTPS URL for {target}")
        env.append({"name": key, "value": url})
    # Implemented scaffold routes need no credentials. Do not invent payloads just
    # to satisfy secret mounts; opt in only after valid versions have been added.
    secrets = SECRETS.get(service, {}) if settings.use_application_secrets else {}
    if settings.enabled_secrets:
        secrets = {k: v for k, v in secrets.items() if v in settings.enabled_secrets}
    if service == "ingest-api" and settings.pubsub_topic:
        env.append({"name": "PUBSUB_TOPIC",
                    "value": f"projects/{settings.project}/topics/{settings.pubsub_topic}"})
    for key, secret in secrets.items():
        env.append({"name": key, "valueFrom": {"secretKeyRef": {
            "name": f"{settings.secret_prefix}-{secret}", "key": settings.secret_version,
        }}})
    annotations = {
        "autoscaling.knative.dev/minScale": "0",
        "autoscaling.knative.dev/maxScale": str(settings.max_instances),
        "run.googleapis.com/cpu-throttling": "true",
        "run.googleapis.com/startup-cpu-boost": "false",
        "run.googleapis.com/execution-environment": "gen2",
    }
    if settings.cloud_sql_instance and service in {"ingest-api", "engine"}:
        annotations["run.googleapis.com/cloudsql-instances"] = settings.cloud_sql_instance
    return {
        "apiVersion": "serving.knative.dev/v1",
        "kind": "Service",
        "metadata": {
            "name": settings.service_name(service),
            "annotations": {"run.googleapis.com/ingress": "all"},
        },
        "spec": {
            "template": {
                "metadata": {"annotations": annotations},
                "spec": {
                    "serviceAccountName": f"{settings.runtime_sa_prefix}-{service}@{settings.project}.iam.gserviceaccount.com",
                    "containerConcurrency": 20,
                    "timeoutSeconds": 60,
                    "containers": [{
                        "image": image,
                        "ports": [{"containerPort": 8080}],
                        "env": env,
                        "resources": {"limits": {"cpu": "1", "memory": "512Mi"}},
                        "startupProbe": {
                            "httpGet": {"path": "/health", "port": 8080},
                            "periodSeconds": 5, "timeoutSeconds": 3, "failureThreshold": 24,
                        },
                        "livenessProbe": {
                            "httpGet": {"path": "/health", "port": 8080},
                            "periodSeconds": 30, "timeoutSeconds": 3, "failureThreshold": 3,
                        },
                    }],
                },
            },
            "traffic": [{"latestRevision": True, "percent": 100}],
        },
    }


def gcloud(settings, *args):
    executable = shutil.which("gcloud.cmd") or shutil.which("gcloud") or "gcloud"
    result = subprocess.run(
        [executable, *args, "--project", settings.project, "--region", settings.region, "--quiet"],
        check=True, text=True, stdout=subprocess.PIPE,
    )
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True, help="JSON mapping services to image digests")
    parser.add_argument("--dry-run", action="store_true", help="Read service URLs and render without deploying")
    parser.add_argument("--output-dir", type=Path, default=Path("deployment-manifests"))
    args = parser.parse_args()
    settings = Settings.from_env()
    images = json.loads(args.images.read_text())
    validate_images(settings, images)
    # Resolve and render everything before any mutation. Missing bootstrap fails safely.
    urls = {service: gcloud(settings, "run", "services", "describe", settings.service_name(service),
                            "--format=value(status.url)") for service in SERVICES}
    manifests = {service: render_service(settings, service, images[service], urls) for service in SERVICES}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "service-urls.json").write_text(json.dumps(urls, indent=2) + "\n")
    for service, manifest in manifests.items():
        (args.output_dir / f"{service}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if args.dry_run:
        return
    # gcloud waits for readiness; /health startup failures stop the rollout.
    # Replacements preserve IAM, which is managed separately by Terraform.
    with tempfile.TemporaryDirectory() as directory:
        for service in SERVICES:
            path = Path(directory) / f"{service}.json"
            path.write_text(json.dumps(manifests[service]))
            gcloud(settings, "run", "services", "replace", str(path))
            print(f"Ready: {settings.service_name(service)}")


if __name__ == "__main__":
    main()
