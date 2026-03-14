# Best for most use cases. Unified API across all models — handles message formatting for you. Use this by default.


import boto3, json
from botocore import UNSIGNED
from botocore.config import Config

API_KEY = "YOUR_API_KEY_HERE"

client = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1",
    config=Config(signature_version=UNSIGNED),
)

# Inject bearer token (no AWS creds needed)
def inject_bearer(request, **kwargs):
    request.headers["Authorization"] = f"Bearer {API_KEY}"
client.meta.events.register("before-send.bedrock-runtime.*", inject_bearer)

# Available models:
#   us.anthropic.claude-sonnet-4-6
#   us.anthropic.claude-haiku-4-5-20251001-v1:0

response = client.converse(
    modelId="us.anthropic.claude-sonnet-4-6",
    messages=[
        {
            "role": "user",
            "content": [{"text": "Hello, what can you do?"}],
        }
    ],
    inferenceConfig={"maxTokens": 512, "temperature": 0.7},
)

print(response["output"]["message"]["content"][0]["text"])