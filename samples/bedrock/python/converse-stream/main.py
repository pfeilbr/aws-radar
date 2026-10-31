# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.40"]
# ///
"""Stream a reply from a Claude model on Amazon Bedrock with the Converse API."""

import os
import sys

import boto3

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-5-5")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))


def main() -> int:
    prompt = " ".join(sys.argv[1:]) or "In one paragraph, what is the Bedrock Converse API for?"
    client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    response = client.converse_stream(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": MAX_TOKENS},
    )
    for event in response["stream"]:
        if "contentBlockDelta" in event:
            print(event["contentBlockDelta"]["delta"].get("text", ""), end="", flush=True)
        elif "messageStop" in event:
            print(f"\n\n[stop: {event['messageStop']['stopReason']}]")
        elif "metadata" in event:
            usage, metrics = event["metadata"]["usage"], event["metadata"]["metrics"]
            print(f"[{MODEL_ID}: {usage['inputTokens']} in / {usage['outputTokens']} out, "
                  f"{metrics['latencyMs']} ms]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
