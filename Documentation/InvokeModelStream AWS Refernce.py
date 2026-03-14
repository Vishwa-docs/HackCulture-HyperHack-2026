# Low-level streaming. Same as InvokeModel but streams the response. Use for streaming + model-specific parameters.


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
        {"role": "user", "content": "List 3 AWS services"}
    ],
})

# Available models:
#   us.anthropic.claude-sonnet-4-6
#   us.anthropic.claude-haiku-4-5-20251001-v1:0

response = client.invoke_model_with_response_stream(
    modelId="us.anthropic.claude-sonnet-4-6",
    contentType="application/json",
    accept="application/json",
    body=body,
)

for event in response["body"]:
    chunk = json.loads(event["chunk"]["bytes"])
    if chunk["type"] == "content_block_delta":
        print(chunk["delta"]["text"], end="")
print()