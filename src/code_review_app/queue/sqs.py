from __future__ import annotations

import json
from typing import Any

import boto3


class SqsQueue:
    def __init__(self, client: Any, queue_url: str) -> None:
        self.client = client
        self.queue_url = queue_url

    @classmethod
    def from_region(cls, region_name: str, queue_url: str) -> SqsQueue:
        return cls(client=boto3.client("sqs", region_name=region_name), queue_url=queue_url)

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
