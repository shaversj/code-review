import json

import boto3

from code_review_app.queue.sqs import SqsQueue


class FakeSqsClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.deleted: list[dict] = []
        self.received: list[dict] = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "msg-1"}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)
        return {}

    def receive_message(self, **kwargs):
        self.received.append(kwargs)
        return {
            "Messages": [
                {
                    "MessageId": "msg-1",
                    "ReceiptHandle": "receipt",
                    "Body": "{}",
                    "Attributes": {"ApproximateReceiveCount": "3"},
                }
            ]
        }


def test_enqueue_review_job_sends_json_body() -> None:
    client = FakeSqsClient()
    queue = SqsQueue(client=client, queue_url="https://queue")

    message_id = queue.enqueue_review_job({"review_run_id": 1, "head_sha": "abc"})

    assert message_id == "msg-1"
    assert json.loads(client.sent[0]["MessageBody"]) == {"review_run_id": 1, "head_sha": "abc"}


def test_delete_message_uses_receipt_handle() -> None:
    client = FakeSqsClient()
    queue = SqsQueue(client=client, queue_url="https://queue")

    queue.delete_message("receipt")

    assert client.deleted == [{"QueueUrl": "https://queue", "ReceiptHandle": "receipt"}]


def test_receive_messages_requests_system_attributes() -> None:
    client = FakeSqsClient()
    queue = SqsQueue(client=client, queue_url="https://queue")

    messages = queue.receive_messages()

    assert messages[0]["MessageId"] == "msg-1"
    assert client.received[0]["MessageSystemAttributeNames"] == ["All"]
    assert SqsQueue.receive_count(messages[0]) == 3


def test_from_region_uses_endpoint_url_for_lazy_client(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_client(service_name: str, **kwargs):
        calls.append({"service_name": service_name, **kwargs})
        return FakeSqsClient()

    monkeypatch.setattr(boto3, "client", fake_client)
    queue = SqsQueue.from_region(
        "us-east-1",
        "http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/code-review-jobs",
        endpoint_url="http://localhost.localstack.cloud:4566",
    )

    queue.enqueue_review_job({"review_run_id": 1})

    assert calls == [
        {
            "service_name": "sqs",
            "region_name": "us-east-1",
            "endpoint_url": "http://localhost.localstack.cloud:4566",
        }
    ]
