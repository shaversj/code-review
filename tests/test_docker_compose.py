from pathlib import Path

import yaml


def test_compose_defines_local_runtime_services() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    assert set(compose["services"]) == {"api", "worker", "localstack"}
    assert compose["services"]["api"]["build"]["context"] == "."
    assert compose["services"]["worker"]["build"]["context"] == "."
    assert compose["services"]["localstack"]["image"].startswith("localstack/localstack")
    assert compose["services"]["api"]["depends_on"]["localstack"]["condition"] == "service_healthy"
    assert compose["services"]["worker"]["depends_on"]["localstack"]["condition"] == "service_healthy"


def test_compose_points_app_services_at_localstack_sqs() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    for service_name in ("api", "worker"):
        environment = compose["services"][service_name]["environment"]
        assert environment["AWS_ENDPOINT_URL"] == "http://localstack:4566"
        assert environment["AWS_ACCESS_KEY_ID"] == "test"
        assert environment["AWS_SECRET_ACCESS_KEY"] == "test"
        assert environment["SQS_QUEUE_URL"] == "http://localstack:4566/000000000000/code-review-jobs"


def test_localstack_init_script_creates_review_queue() -> None:
    script = Path("localstack/init/ready.d/create-sqs.sh").read_text(encoding="utf-8")

    assert "awslocal sqs create-queue" in script
    assert "--queue-name code-review-jobs" in script
    assert "VisibilityTimeout=900" in script
    assert "ReceiveMessageWaitTimeSeconds=20" in script
