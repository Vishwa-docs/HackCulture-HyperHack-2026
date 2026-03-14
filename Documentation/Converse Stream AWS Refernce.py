# Same as Converse but streams tokens as they are generated. Use for chatbots or real-time UIs where you want instant feedback.


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

# Available models:
#   us.anthropic.claude-sonnet-4-6
#   us.anthropic.claude-haiku-4-5-20251001-v1:0

response = client.converse_stream(
    modelId="us.anthropic.claude-sonnet-4-6",
    messages=[
        {
            "role": "user",
            "content": [{"text": "Write a haiku about coding"}],
        }
    ],
    inferenceConfig={"maxTokens": 512},
)

for event in response["stream"]:
    if "contentBlockDelta" in event:
        print(event["contentBlockDelta"]["delta"]["text"], end="")
print()