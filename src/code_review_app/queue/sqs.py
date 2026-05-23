from __future__ import annotations

import json
from typing import Any

import boto3


class SqsQueue:
    def __init__(self, client: Any | None, queue_url: str, region_name: str | None = None) -> None:
        self._client = client
        self.queue_url = queue_url
        self.region_name = region_name

    @classmethod
    def from_region(cls, region_name: str, queue_url: str) -> SqsQueue:
        return cls(client=None, queue_url=queue_url, region_name=region_name)

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = boto3.client("sqs", region_name=self.region_name)
        return self._client

    def enqueue_review_job(self, payload: dict[str, Any]) -> str:
        response = self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(payload, separators=(",", ":")),
        )
        return str(response["MessageId"])

    def receive_messages(self, max_messages: int = 1, wait_time_seconds: int = 20) -> list[dict[str, Any]]:
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_time_seconds,
            MessageAttributeNames=["All"],
        )
        return list(response.get("Messages", []))

    def delete_message(self, receipt_handle: str) -> None:
        self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)

    def extend_visibility(self, receipt_handle: str, timeout_seconds: int) -> None:
        self.client.change_message_visibility(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=timeout_seconds,
        )
