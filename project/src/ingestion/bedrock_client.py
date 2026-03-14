"""Bedrock LLM client for structured extraction and adjudication."""
import json
import os
from typing import Optional

import boto3
from botocore import UNSIGNED
from botocore.config import Config

from ..core.logging import get_logger
from ..core import paths
from ..core.utils import cache_key, load_json_cache, save_json_cache

log = get_logger(__name__)

CACHE_DIR = paths.CACHE / "bedrock"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class BedrockClient:
    """AWS Bedrock client for LLM calls with caching."""

    def __init__(self):
        api_key = os.environ.get("BEDROCK_API_KEY", "")
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            config=Config(signature_version=UNSIGNED),
        )
        # Inject bearer token
        def inject_bearer(request, **kwargs):
            request.headers["Authorization"] = f"Bearer {api_key}"
        self._client.meta.events.register("before-send.bedrock-runtime.*", inject_bearer)

        self.model_reasoning = "us.anthropic.claude-sonnet-4-6"
        self.model_fast = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    def converse(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: str = "",
        use_cache: bool = True,
    ) -> str:
        """Send a message to Bedrock and get text response."""
        model = model or self.model_fast
        ck = cache_key("bedrock", model, prompt[:300])
        if use_cache:
            cached = load_json_cache(CACHE_DIR / f"{ck}.json")
            if cached:
                return cached.get("response", "")

        messages = [{"role": "user", "content": [{"text": prompt}]}]
        kwargs = {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
        }
        if system:
            kwargs["system"] = [{"text": system}]

        try:
            resp = self._client.converse(**kwargs)
            text = resp["output"]["message"]["content"][0]["text"]
            if use_cache:
                save_json_cache(CACHE_DIR / f"{ck}.json", {"response": text})
            return text
        except Exception as e:
            log.error(f"Bedrock call failed: {e}")
            return ""

    def extract_json(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> Optional[dict]:
        """Call Bedrock and parse JSON from response."""
        text = self.converse(prompt, model=model, max_tokens=max_tokens)
        if not text:
            return None
        # Try to find JSON in response
        try:
            # Direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find JSON block in markdown
        import re
        match = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # Try to find any JSON-like structure
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        log.warning("Could not parse JSON from Bedrock response")
        return None
