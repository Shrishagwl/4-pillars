import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.gcp.deploy import SERVICES, Settings, main, render_service, validate_images


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(project="demo-project", region="australia-southeast1",
                                 use_application_secrets=True)
        self.urls = {name: f"https://{name}-example.run.app" for name in SERVICES}
        self.images = {
            name: f"australia-southeast1-docker.pkg.dev/demo-project/four-pillars/{name}@sha256:"
            + "a" * 64
            for name in SERVICES
        }

    def test_every_service_has_health_probe_and_bounded_resources(self):
        for name in SERVICES:
            manifest = render_service(self.settings, name, self.images[name], self.urls)
            template = manifest["spec"]["template"]
            spec = template["spec"]
            container = spec["containers"][0]
            self.assertEqual(container["startupProbe"]["httpGet"]["path"], "/health")
            self.assertEqual(container["ports"], [{"containerPort": 8080}])
            self.assertEqual(container["image"], self.images[name])
            self.assertEqual(template["metadata"]["annotations"]["autoscaling.knative.dev/minScale"], "0")
            self.assertEqual(template["metadata"]["annotations"]["autoscaling.knative.dev/maxScale"], "2")
            self.assertEqual(spec["serviceAccountName"], f"fp-{name}@demo-project.iam.gserviceaccount.com")

    def test_dependency_urls_and_secret_isolation(self):
        expected = {
            "ingest-api": ({"ENGINE_URL": "engine"}, {"DATABASE_URL": "ingest-database-url",
                                                     "ADMIN_API_KEY": "ingest-admin-key"}),
            "engine": ({"GATEWAY_URL": "telstra-gateway", "INGEST_URL": "ingest-api"},
                       {"DATABASE_URL": "engine-database-url"}),
            "twin": ({"INGEST_URL": "ingest-api", "TELSTRA_FAKE_URL": "telstra-fake"},
                     {"INGEST_API_KEY": "ingest-admin-key"}),
            "telstra-gateway": ({"TELSTRA_BASE_URL": "telstra-fake"}, {
                "TELSTRA_CLIENT_ID": "telstra-client-id", "TELSTRA_CLIENT_SECRET": "telstra-client-secret"
            }),
            "telstra-fake": ({}, {}),
        }
        for name, (urls, secrets) in expected.items():
            manifest = render_service(self.settings, name, self.images[name], self.urls)
            env = {v["name"]: v for v in manifest["spec"]["template"]["spec"]["containers"][0]["env"]}
            for key, target in urls.items():
                self.assertEqual(env[key]["value"], self.urls[target])
            actual = {key: value["valueFrom"]["secretKeyRef"] for key, value in env.items() if "valueFrom" in value}
            self.assertEqual(actual, {
                key: {"name": f"four-pillars-{secret}", "key": "1"} for key, secret in secrets.items()
            })

    def test_cloudsql_only_attached_to_database_services(self):
        settings = Settings(project="demo-project", region="australia-southeast1",
                            cloud_sql_instance="demo-project:australia-southeast1:pillars")
        for name in SERVICES:
            manifest = render_service(settings, name, self.images[name], self.urls)
            annotations = manifest["spec"]["template"]["metadata"]["annotations"]
            self.assertEqual("run.googleapis.com/cloudsql-instances" in annotations, name in {"engine", "ingest-api"})

    def test_scaffolds_do_not_require_nonexistent_secret_versions(self):
        settings = Settings(project="demo-project", region="australia-southeast1")
        for name in SERVICES:
            manifest = render_service(settings, name, self.images[name], self.urls)
            env = manifest["spec"]["template"]["spec"]["containers"][0]["env"]
            self.assertFalse(any("valueFrom" in value for value in env))
        with patch.dict("os.environ", {"GCP_PROJECT_ID": "demo-project",
                                      "GCP_REGION": "australia-southeast1"}, clear=True):
            self.assertFalse(Settings.from_env().use_application_secrets)
        with patch.dict("os.environ", {"GCP_PROJECT_ID": "demo-project",
                                      "GCP_REGION": "australia-southeast1",
                                      "GCP_USE_APPLICATION_SECRETS": "true"}, clear=True):
            self.assertTrue(Settings.from_env().use_application_secrets)

    def test_only_secrets_with_versions_are_mounted(self):
        settings = Settings(project="demo-project", region="australia-southeast1",
                            use_application_secrets=True,
                            enabled_secrets=("ingest-database-url", "engine-database-url"))
        gateway = render_service(settings, "telstra-gateway", self.images["telstra-gateway"], self.urls)
        ingest = render_service(settings, "ingest-api", self.images["ingest-api"], self.urls)
        secret_env = lambda m: {v["name"] for v in m["spec"]["template"]["spec"]["containers"][0]["env"]
                                if "valueFrom" in v}
        self.assertEqual(secret_env(gateway), set())
        self.assertEqual(secret_env(ingest), {"DATABASE_URL"})
        with self.assertRaises(ValueError):
            Settings(project="demo-project", region="australia-southeast1", enabled_secrets=("nope",))

    def test_only_twin_and_engine_keep_cpu_between_requests(self):
        for name in SERVICES:
            annotations = render_service(self.settings, name, self.images[name], self.urls)[
                "spec"]["template"]["metadata"]["annotations"]
            expected = "false" if name in {"twin", "engine"} else "true"
            self.assertEqual(annotations["run.googleapis.com/cpu-throttling"], expected)
            self.assertEqual(annotations["autoscaling.knative.dev/minScale"], "0")

    def test_pubsub_topic_goes_to_ingest_only(self):
        settings = Settings(project="demo-project", region="australia-southeast1",
                            pubsub_topic="meter-silent")
        for name in SERVICES:
            env = {v["name"]: v.get("value") for v in render_service(
                settings, name, self.images[name], self.urls)["spec"]["template"]["spec"]["containers"][0]["env"]}
            if name == "ingest-api":
                self.assertEqual(env["PUBSUB_TOPIC"], "projects/demo-project/topics/meter-silent")
            else:
                self.assertNotIn("PUBSUB_TOPIC", env)
        with self.assertRaises(ValueError):
            Settings(project="demo-project", region="australia-southeast1", pubsub_topic="Bad Topic")

    def test_invalid_secret_opt_in_fails_closed(self):
        with patch.dict("os.environ", {"GCP_PROJECT_ID": "demo-project",
                                      "GCP_REGION": "australia-southeast1",
                                      "GCP_USE_APPLICATION_SECRETS": "yes"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_rejects_missing_images_mutable_tags_and_foreign_registry(self):
        validate_images(self.settings, self.images)
        for bad in ({}, {**self.images, "engine": "image:latest"},
                    {**self.images, "engine": self.images["engine"].replace("demo-project", "other-project")}):
            with self.assertRaises(ValueError):
                validate_images(self.settings, bad)

    def test_rejects_insecure_dependency_url(self):
        for url in ("http://localhost:8082", "https://x.evilrun.app"):
            with self.assertRaises(ValueError):
                render_service(self.settings, "engine", self.images["engine"],
                               {**self.urls, "telstra-gateway": url})

    def test_rejects_unbounded_scaling_and_latest_secret(self):
        for kwargs in ({"max_instances": 0}, {"max_instances": 101}, {"secret_version": "latest"}):
            with self.assertRaises(ValueError):
                Settings(project="demo-project", region="australia-southeast1", **kwargs)

    def run_deployment(self, directory, cloud, dry_run=False):
        images = Path(directory) / "images.json"
        images.write_text(json.dumps(self.images))
        arguments = ["deploy.py", "--images", str(images), "--output-dir", directory]
        if dry_run:
            arguments.append("--dry-run")
        with patch("sys.argv", arguments), patch(
            "scripts.gcp.deploy.Settings.from_env", return_value=self.settings
        ), patch("scripts.gcp.deploy.gcloud", side_effect=cloud):
            main()

    def test_resolves_all_dependencies_before_mutation_and_keeps_rollback_manifests(self):
        calls = []

        def cloud(settings, *args):
            calls.append(args)
            if args[2] == "describe":
                return self.urls[args[3].removeprefix("four-pillars-")]
            manifest = json.loads(Path(args[3]).read_text())
            self.assertEqual(manifest["spec"]["traffic"], [{"latestRevision": True, "percent": 100}])
            return ""

        with tempfile.TemporaryDirectory() as directory:
            self.run_deployment(directory, cloud)
            self.assertEqual([call[2] for call in calls], ["describe"] * 5 + ["replace"] * 5)
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 7)
            self.assertEqual(json.loads((Path(directory) / "service-urls.json").read_text()), self.urls)

    def test_dry_run_only_reads_cloud(self):
        calls = []

        def cloud(settings, *args):
            calls.append(args)
            return self.urls[args[3].removeprefix("four-pillars-")]

        with tempfile.TemporaryDirectory() as directory:
            self.run_deployment(directory, cloud, dry_run=True)
        self.assertEqual([call[2] for call in calls], ["describe"] * 5)

    def test_missing_bootstrap_never_mutates_and_failed_rollout_stops(self):
        for fail_on in ("describe", "replace"):
            with self.subTest(fail_on=fail_on), tempfile.TemporaryDirectory() as directory:
                calls = []

                def cloud(settings, *args):
                    calls.append(args)
                    if args[2] == fail_on:
                        raise subprocess.CalledProcessError(1, ["gcloud"])
                    return self.urls[args[3].removeprefix("four-pillars-")]

                with self.assertRaises(subprocess.CalledProcessError):
                    self.run_deployment(directory, cloud)
                expected = ["describe"] if fail_on == "describe" else ["describe"] * 5 + ["replace"]
                self.assertEqual([call[2] for call in calls], expected)


if __name__ == "__main__":
    unittest.main()
