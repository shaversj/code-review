from __future__ import annotations

import json
import time

from code_review_app.config import get_settings
from code_review_app.queue.sqs import SqsQueue


def main() -> None:
    settings = get_settings()
    queue = SqsQueue.from_region(settings.aws_region, settings.sqs_queue_url)
    while True:
        for message in queue.receive_messages(max_messages=1, wait_time_seconds=20):
            body = json.loads(message["Body"])
            print(f"received review job {body['review_run_id']}")
            queue.delete_message(message["ReceiptHandle"])
        time.sleep(1)
