#!/usr/bin/env bash
set -euo pipefail

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

awslocal sqs create-queue \
  --queue-name code-review-jobs \
  --attributes VisibilityTimeout=900,ReceiveMessageWaitTimeSeconds=20
