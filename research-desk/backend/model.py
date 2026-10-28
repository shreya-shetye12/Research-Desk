"""Local Ollama HTTP client; no framework, cloud key, or weight updates."""

import json
import os
import urllib.request
from urllib.parse import urlparse
from pydantic import ValidationError

MODEL = os.environ.get("SHIFT_MODEL", "qwen3:8b")
EMBED_MODEL = "nomic-embed-text"
URL = os.environ.get("SHIFT_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
if urlparse(URL).scheme != "http" or urlparse(URL).hostname not in {
    "localhost",
    "127.0.0.1",
}:
    raise ValueError("This edition requires a loopback Ollama endpoint")
OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 1500}


def request(endpoint, payload=None, timeout=180):
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        URL + endpoint, body, {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def health():
    try:
        tags = request("/api/tags", timeout=2)["models"]
        found = next((t for t in tags if t["name"] in {MODEL, MODEL + ":latest"}), None)
        return {
            "connected": True,
            "ready": found is not None,
            "name": MODEL,
            "digest": found["digest"] if found else None,
            "embedding_ready": any(
                t["name"] in {EMBED_MODEL, EMBED_MODEL + ":latest"} for t in tags
            ),
            "embedding_digest": next(
                (
                    t["digest"]
                    for t in tags
                    if t["name"] in {EMBED_MODEL, EMBED_MODEL + ":latest"}
                ),
                None,
            ),
        }
    except (OSError, ValueError):
        return {"connected": False, "ready": False, "name": MODEL, "digest": None}


def chat(system, payload, schema):
    from .observability import span

    with span(
        "role." + schema.__name__, {"system": system, "input": payload}
    ) as active:
        output = _chat(system, payload, schema)
        if active:
            active.set_outputs(output)
        return output


def embed(texts):
    return request(
        "/api/embed", {"model": EMBED_MODEL, "input": texts, "truncate": False}
    )["embeddings"]


def _chat(system, payload, schema):
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload)},
    ]
    for attempt in range(2):
        if len(json.dumps(messages).encode()) > 22000:
            raise ValueError(
                "Evidence and memory exceed the conservative context budget."
            )
        response = request(
            "/api/chat",
            {
                "model": MODEL,
                "stream": False,
                "think": False,
                "format": schema.model_json_schema(),
                "messages": messages,
                "options": OPTIONS,
            },
        )
        content = response["message"]["content"]
        try:
            return schema.model_validate_json(content).model_dump()
        except ValidationError as error:
            if attempt:
                raise ValueError(
                    "The local model did not return a valid structured response."
                ) from error
            messages += [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": "Repair the JSON format. Validation errors: "
                    + str(error),
                },
            ]
    raise ValueError("No structured output returned")
