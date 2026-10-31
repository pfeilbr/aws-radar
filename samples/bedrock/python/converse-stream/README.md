# bedrock: Converse streaming with Claude

**Relates to:** [Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
**Last run:** not run yet

## What it shows

`ConverseStream` against a cross-region inference profile: prints text as it arrives, then
the stop reason, input/output token counts and server-side latency from the `metadata`
event. Useful as a baseline when comparing models or regions.

## Run

```bash
uv run main.py "Summarize what changed in S3 this year in three bullets"
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-5-5 uv run main.py "hello"
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `AWS_REGION` | `us-east-1` | Region to call |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-5-5` | Model or inference profile id (`aws bedrock list-inference-profiles`) |
| `MAX_TOKENS` | `1024` | Output token cap |

Needs model access for the chosen model in the Bedrock console.

## AWS resources and cost

None created. Each run is one model invocation, billed per input and output token at the
model's on-demand price (a short prompt costs a fraction of a cent).

## Clean up

Nothing to clean up.
