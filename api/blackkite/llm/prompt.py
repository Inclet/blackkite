"""Versioned prompt files under llm/prompts/. The version is the file stem."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import resources


@dataclass(frozen=True, slots=True)
class Prompt:
    version: str
    text: str


@cache
def load_prompt(version: str) -> Prompt:
    path = resources.files("blackkite.llm").joinpath("prompts", f"{version}.md")
    return Prompt(version=version, text=path.read_text(encoding="utf-8").strip())
