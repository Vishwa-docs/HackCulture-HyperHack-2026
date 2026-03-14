# Low-level API — you build the model-specific request body yourself. Use when you need model-specific params not exposed by Converse.


import boto3, json
from botocore import UNSIGNED
from botocore.config import Config

API_KEY = "YOUR_API_KEY_HERE"

client = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1",
    config=Config(signature_version=UNSIGNED),
)

def inject_bearer(request, **kwargs):
    request.headers["Authorization"] = f"Bearer {API_KEY}"
client.meta.events.register("before-send.bedrock-runtime.*", inject_bearer)

body = json.dumps({
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 512,
    "messages": [
        {"role": "user", "content": "Explain Lambda in one sentence"}
    ],
})

# Available models:
#   us.anthropic.claude-sonnet-4-6
#   us.anthropic.claude-haiku-4-5-20251001-v1:0

response = client.invoke_model(
    modelId="us.anthropic.claude-sonnet-4-6",
    contentType="application/json",
    accept="application/json",
    body=body,
)

result = json.loads(response["body"].read())
print(result["content"][0]["text"])