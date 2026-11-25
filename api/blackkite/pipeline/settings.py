"""Pipeline settings (prefix BK_), kept apart from the app Settings.

Model names and API keys stay in ``blackkite.config.Settings`` (BK_MODEL_EXTRACT,
ANTHROPIC_API_KEY, VOYAGE_API_KEY).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BK_", env_file=".env", extra="ignore")

    # Where downloaded documents are kept (for extraction and the owner's reference
    # only; never served to members, spec 10).
    data_dir: Path = Path("data")
    # Largest detail page or attachment the enrich stage keeps, in bytes.
    document_max_bytes: int = 10_000_000
    # Attachments (PDFs) followed per item.
    documents_per_item: int = 3
    # Characters of source text sent to the extraction model.
    extract_max_chars: int = 40_000
    # Voyage AI model (decision 12); output dimension is EMBEDDING_DIM.
    embedding_model: str = "voyage-3.5"
    llm_timeout_seconds: float = 60.0


@lru_cache
def get_pipeline_settings() -> PipelineSettings:
    return PipelineSettings()
