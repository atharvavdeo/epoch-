"""Server-side Cerebras adapter (OpenAI-compatible HTTPS via httpx; D15).

- One capability probe selects an account-accessible model from a fixed
  preference list and verifies strict json_schema output; the choice is
  recorded in provenance. No guessed model substitutions.
- Retries (COLAB_RUNBOOK §6): 429/5xx/network -> at most 2 retries after the
  first attempt inside a 45 s total deadline, honouring Retry-After;
  401/403 -> no retry. Keys are never logged or exported.
- Transcript/OCR/observations are quoted data inside user messages; the
  system prompt says so (A05 prompt-injection).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx

from pipeline.orchestration.settings import setting

PREFERENCE = ["gpt-oss-120b", "qwen-3.8-27b"]
DEADLINE_S = 45.0
MAX_RETRIES = 2


class LLMError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.retryable = code, retryable


@dataclass
class LLMCall:
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    attempts: int


@dataclass
class CerebrasClient:
    api_key: str
    base_url: str
    model: str = ""
    calls: list[LLMCall] = field(default_factory=list)
    transport: httpx.BaseTransport | None = None  # tests inject a MockTransport

    @classmethod
    def from_env(cls, transport=None) -> "CerebrasClient":
        key = setting("CEREBRAS_API_KEY")
        if not key:
            raise LLMError("no_api_key", "CEREBRAS_API_KEY is not configured (.env)")
        return cls(api_key=key, base_url=setting("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1").rstrip("/"),
                   model=setting("CEREBRAS_MODEL", ""), transport=transport)

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(timeout=timeout, transport=self.transport,
                            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})

    # ----------------------------------------------------------------- probe
    def probe(self) -> dict:
        with self._client(20) as c:
            r = c.get(f"{self.base_url}/models")
        if r.status_code in (401, 403):
            raise LLMError("auth_failed", "Cerebras rejected the API key")
        if r.status_code != 200:
            raise LLMError("probe_failed", f"model list returned HTTP {r.status_code}", retryable=True)
        available = [m["id"] for m in r.json().get("data", [])]
        wanted = [self.model] if self.model else PREFERENCE
        chosen = next((m for m in wanted if m in available), None)
        if not chosen:
            raise LLMError("no_model_access", f"none of {wanted} is available to this account ({available})")
        self.model = chosen
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
        out = self.json_call("Return JSON only.", 'Reply with {"ok": true}.', "probe", schema, max_tokens=200)
        if out.get("ok") is not True:
            raise LLMError("structured_output_unsupported", f"{chosen} did not honour the strict schema")
        return {"model": chosen, "available": available, "structured_outputs": "json_schema strict"}

    # ------------------------------------------------------------------ call
    def json_call(self, system: str, user: str, name: str, schema: dict, *, max_tokens: int = 2048,
                  temperature: float = 0.0) -> dict:
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": temperature, "max_completion_tokens": max_tokens,
                "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}}
        if self.model.startswith("gpt-oss"):
            body["reasoning_effort"] = "medium"
        start = time.time()
        attempt, last = 0, None
        while True:
            attempt += 1
            remaining = DEADLINE_S - (time.time() - start)
            if remaining <= 1:
                raise LLMError("deadline_exceeded", f"no answer within {DEADLINE_S:.0f}s ({last})", retryable=False)
            try:
                with self._client(remaining) as c:
                    r = c.post(f"{self.base_url}/chat/completions", json=body)
            except httpx.HTTPError as exc:
                last = f"network: {type(exc).__name__}"
                if attempt > MAX_RETRIES:
                    raise LLMError("network_error", last, retryable=True) from exc
                time.sleep(min(2 * attempt, max(0.0, DEADLINE_S - (time.time() - start) - 1)))
                continue
            if r.status_code in (401, 403):
                raise LLMError("auth_failed", f"HTTP {r.status_code} from Cerebras (no retry)")
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                if attempt > MAX_RETRIES:
                    raise LLMError("rate_limited" if r.status_code == 429 else "provider_error", last, retryable=True)
                wait = float(r.headers.get("retry-after", 2 * attempt) or 2 * attempt)
                if time.time() - start + wait > DEADLINE_S - 1:
                    raise LLMError("rate_limited", f"{last}; Retry-After {wait}s exceeds deadline", retryable=True)
                time.sleep(wait)
                continue
            if r.status_code != 200:
                raise LLMError("bad_request", f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            u = data.get("usage") or {}
            self.calls.append(LLMCall(self.model, int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0)),
                                      round(time.time() - start, 2), attempt))
            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            try:
                return json.loads(content)
            except json.JSONDecodeError as exc:
                raise LLMError("invalid_json", f"model returned non-JSON content: {content[:200]}") from exc

    def usage(self) -> dict:
        return {"model": self.model, "calls": len(self.calls),
                "prompt_tokens": sum(c.prompt_tokens for c in self.calls),
                "completion_tokens": sum(c.completion_tokens for c in self.calls),
                "latency_s": round(sum(c.latency_s for c in self.calls), 1)}
