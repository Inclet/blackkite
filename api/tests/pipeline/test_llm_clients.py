"""LLM and embedding clients, exercised without any network call."""

from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from blackkite.config import EMBEDDING_DIM, Settings
from blackkite.llm.anthropic_client import AnthropicLLM
from blackkite.llm.client import LLMError
from blackkite.llm.embeddings import VOYAGE_URL, EmbeddingError, VoyageEmbedder
from blackkite.llm.factory import embedder, extraction_llm
from blackkite.llm.prompt import load_prompt
from blackkite.pipeline.settings import PipelineSettings


class Reply(BaseModel):
    answer: str


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_client(content, stop_reason="tool_use"):
    return SimpleNamespace(
        messages=FakeMessages(SimpleNamespace(content=content, stop_reason=stop_reason))
    )


def call(llm):
    return llm.structured(
        system="sys",
        user="text",
        schema=Reply,
        tool_name="record",
        tool_description="d",
    )


def test_anthropic_forces_the_tool_and_validates_its_input():
    block = SimpleNamespace(type="tool_use", name="record", input={"answer": "42"})
    client = fake_client([SimpleNamespace(type="text", text="hi"), block])
    llm = AnthropicLLM(api_key="k", model="claude-haiku-5-5", client=client)
    assert call(llm) == Reply(answer="42")
    sent = client.messages.calls[0]
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["tool_choice"] == {"type": "tool", "name": "record"}
    assert sent["tools"][0]["input_schema"] == Reply.model_json_schema()


@pytest.mark.parametrize(
    ("content", "stop"),
    [
        ([SimpleNamespace(type="text", text="no tool")], "end_turn"),
        ([SimpleNamespace(type="tool_use", name="record", input={})], "tool_use"),
        ([SimpleNamespace(type="tool_use", name="record", input={})], "max_tokens"),
    ],
)
def test_anthropic_bad_replies_raise_llm_error(content, stop):
    llm = AnthropicLLM(api_key="k", model="m", client=fake_client(content, stop))
    with pytest.raises(LLMError):
        call(llm)


def voyage(handler, dim=EMBEDDING_DIM):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return VoyageEmbedder(api_key="vk", model="voyage-test", dim=dim, http=http)


def test_voyage_sends_dimension_and_returns_vectors_in_order():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [1.0] * 4},
                    {"index": 0, "embedding": [0.0] * 4},
                ]
            },
        )

    vecs = voyage(handler, dim=4).embed(["a", "b"])
    assert vecs == [[0.0] * 4, [1.0] * 4]
    assert seen["url"] == VOYAGE_URL
    assert seen["auth"] == "Bearer vk"
    assert b'"output_dimension":4' in seen["body"]


def test_voyage_wrong_dimension_or_http_error_raises():
    with pytest.raises(EmbeddingError):
        voyage(
            lambda r: httpx.Response(
                200, json={"data": [{"index": 0, "embedding": [1]}]}
            )
        ).embed(["a"])
    with pytest.raises(EmbeddingError):
        voyage(lambda r: httpx.Response(500)).embed(["a"])


def test_factories_return_none_without_keys():
    s = Settings(_env_file=None, anthropic_api_key=None, voyage_api_key=None)
    p = PipelineSettings(_env_file=None)
    assert extraction_llm(s, p) is None
    assert embedder(s, p) is None
    s2 = Settings(
        _env_file=None,
        anthropic_api_key=SecretStr("x"),
        voyage_api_key=SecretStr("y"),
        model_extract="claude-haiku-5-5",
    )
    assert extraction_llm(s2, p).model == "claude-haiku-5-5"
    assert embedder(s2, p).model == p.embedding_model


def test_prompt_file_is_versioned():
    p = load_prompt("extract-v1")
    assert p.version == "extract-v1"
    assert "record_opportunity" in p.text
