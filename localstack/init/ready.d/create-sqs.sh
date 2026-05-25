#!/usr/bin/env bash
set -euo pipefail

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

awslocal sqs create-queue \
  --queue-name code-review-jobs-dlq \
  --attributes MessageRetentionPeriod=1209600

DLQ_ARN="$(awslocal sqs get-queue-attributes \
  --queue-url "$(awslocal sqs get-queue-url --queue-name code-review-jobs-dlq --query QueueUrl --output text)" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)"

awslocal sqs create-queue \
  --queue-name code-review-jobs \
  --attributes VisibilityTimeout=900,ReceiveMessageWaitTimeSeconds=20

QUEUE_URL="$(awslocal sqs get-queue-url \
  --queue-name code-review-jobs \
  --query QueueUrl \
  --output text)"

awslocal sqs set-queue-attributes \
  --queue-url "${QUEUE_URL}" \
  --attributes "RedrivePolicy={\"deadLetterTargetArn\":\"${DLQ_ARN}\",\"maxReceiveCount\":\"5\"}"
