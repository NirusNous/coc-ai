import asyncio
from copy import deepcopy
import json
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import LLMSettings


class LLMClientError(RuntimeError):
    pass


_LLM_SEMAPHORES: dict[int, asyncio.Semaphore] = {}


def _apply_strict_object_rules(node: Any) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object":
            node.setdefault("additionalProperties", False)

        for value in node.values():
            _apply_strict_object_rules(value)

    elif isinstance(node, list):
        for item in node:
            _apply_strict_object_rules(item)


def _build_response_format(
    schema_name: str,
    response_model: type[BaseModel],
) -> dict[str, Any]:
    schema = deepcopy(response_model.model_json_schema())
    _apply_strict_object_rules(schema)

    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": schema,
        },
    }


def _flatten_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return ""

    text_fragments: list[str] = []

    for item in content:
        if not isinstance(item, dict):
            continue

        if item.get("type") != "text":
            continue

        text = item.get("text")

        if isinstance(text, str):
            text_fragments.append(text)
        elif isinstance(text, dict):
            value = text.get("value")

            if isinstance(value, str):
                text_fragments.append(value)

    return "".join(text_fragments)


class LLMClient:
    def __init__(self, settings: LLMSettings):
        self._settings = settings

    def _get_semaphore(self) -> asyncio.Semaphore:
        limit = max(1, self._settings.max_concurrency)
        semaphore = _LLM_SEMAPHORES.get(limit)

        if semaphore is None:
            semaphore = asyncio.Semaphore(limit)
            _LLM_SEMAPHORES[limit] = semaphore

        return semaphore

    async def generate_structured_output(
        self,
        *,
        messages: list[dict[str, str]],
        schema_name: str,
        response_model: type[BaseModel],
    ) -> dict[str, Any]:
        request_payload = {
            "model": self._settings.model,
            "temperature": 0,
            "messages": messages,
            "response_format": _build_response_format(
                schema_name=schema_name,
                response_model=response_model,
            ),
        }

        if self._settings.max_output_tokens is not None:
            request_payload["max_tokens"] = self._settings.max_output_tokens

        headers = {
            "Content-Type": "application/json",
        }

        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"

        try:
            async with self._get_semaphore():
                async with httpx.AsyncClient(
                    base_url=self._settings.base_url,
                    timeout=self._settings.timeout_seconds,
                ) as client:
                    response = await client.post(
                        "/chat/completions",
                        headers=headers,
                        json=request_payload,
                    )
        except httpx.TimeoutException as error:
            raise LLMClientError("LLM request timed out.") from error
        except httpx.HTTPError as error:
            raise LLMClientError(f"LLM request failed: {error}") from error

        if response.status_code >= 400:
            detail = response.text

            try:
                error_payload = response.json()
                error_detail = error_payload.get("error", {}).get("message")

                if isinstance(error_detail, str) and error_detail.strip():
                    detail = error_detail
            except json.JSONDecodeError:
                pass

            raise LLMClientError(
                f"LLM request returned HTTP {response.status_code}: {detail}"
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as error:
            raise LLMClientError("LLM response was not valid JSON.") from error

        choices = payload.get("choices")

        if not isinstance(choices, list) or not choices:
            raise LLMClientError("LLM response did not include any choices.")

        message = choices[0].get("message")

        if not isinstance(message, dict):
            raise LLMClientError("LLM response did not include a valid message.")

        refusal = message.get("refusal")

        if isinstance(refusal, str) and refusal.strip():
            raise LLMClientError(f"LLM refused the request: {refusal}")

        content = _flatten_message_content(message.get("content"))

        if not content.strip():
            raise LLMClientError("LLM response content was empty.")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise LLMClientError("LLM response content was not valid JSON.") from error

        if not isinstance(parsed, dict):
            raise LLMClientError("LLM response JSON must be an object.")

        return parsed
