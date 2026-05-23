import json

from code_review_app.queue.sqs import SqsQueue


class FakeSqsClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.deleted: list[dict] = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "msg-1"}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)
        return {}


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
