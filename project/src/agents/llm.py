"""LangChain LLM wrapper for AWS Bedrock via HyperAPI proxy."""
import os
from typing import Optional

from langchain_aws.chat_models.bedrock_converse import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage

from ..core.logging import get_logger

log = get_logger(__name__)


def get_bedrock_llm(
    model_id: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> ChatBedrockConverse:
    """Create a LangChain ChatBedrockConverse instance pointing at our Bedrock proxy.

    Uses BEDROCK_API_KEY for bearer-token auth via botocore event injection.
    """
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    api_key = os.environ.get("BEDROCK_API_KEY", "")
    model_id = model_id or "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    # Build a raw boto3 client with bearer-token injection (same as BedrockClient)
    client = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        config=Config(signature_version=UNSIGNED),
    )

    def _inject_bearer(request, **kwargs):
        request.headers["Authorization"] = f"Bearer {api_key}"

    client.meta.events.register("before-send.bedrock-runtime.*", _inject_bearer)

    llm = ChatBedrockConverse(
        client=client,
        model=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    log.info(f"Initialized LangChain ChatBedrockConverse with model={model_id}")
    return llm


# Convenience singletons for the two model tiers
_llm_fast: Optional[ChatBedrockConverse] = None
_llm_reasoning: Optional[ChatBedrockConverse] = None


def get_fast_llm() -> ChatBedrockConverse:
    """Return (cached) Haiku 4.5 instance for fast classification / tool calls."""
    global _llm_fast
    if _llm_fast is None:
        _llm_fast = get_bedrock_llm("us.anthropic.claude-haiku-4-5-20251001-v1:0")
    return _llm_fast


def get_reasoning_llm() -> ChatBedrockConverse:
    """Return (cached) Sonnet 4.6 instance for complex reasoning."""
    global _llm_reasoning
    if _llm_reasoning is None:
        _llm_reasoning = get_bedrock_llm("us.anthropic.claude-sonnet-4-6")
    return _llm_reasoning
