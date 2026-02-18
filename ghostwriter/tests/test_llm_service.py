"""Tests for LLM service."""

import os

import pytest

# Set test environment
os.environ["AI_PROVIDER"] = "ollama"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

from app.core.config import Settings
from app.services.llm_service import LLMService


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        ai_provider="ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.2",
        ai_timeout_seconds=30,
        ai_max_retries=1,
    )


@pytest.fixture
def llm_service(settings):
    """Create LLM service with test settings."""
    return LLMService(settings)


def test_model_string_ollama(llm_service):
    """Test model string generation for Ollama."""
    model = llm_service.settings.get_llm_model_string()
    assert model == "ollama/llama3.2"


def test_model_string_openai():
    """Test model string generation for OpenAI."""
    settings = Settings(
        ai_provider="openai",
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
    )
    model = settings.get_llm_model_string()
    assert model == "gpt-4o-mini"


def test_model_string_gemini():
    """Test model string generation for Gemini."""
    settings = Settings(
        ai_provider="gemini",
        gemini_api_key="test-key",
        gemini_model="gemini-1.5-flash",
    )
    model = settings.get_llm_model_string()
    assert model == "gemini/gemini-1.5-flash"


def test_transcript_length_guidance_short(llm_service):
    """Short transcripts should get a shorter summary target."""
    content = "word " * 1500
    guidance = llm_service._transcript_length_guidance(content)
    assert "350-500 words" in guidance


def test_transcript_length_guidance_medium(llm_service):
    """Mid-length transcripts should get a medium summary target."""
    content = "word " * 5000
    guidance = llm_service._transcript_length_guidance(content)
    assert "500-750 words" in guidance


def test_transcript_length_guidance_long(llm_service):
    """Long transcripts should get a much longer summary target."""
    content = "word " * 18000
    guidance = llm_service._transcript_length_guidance(content)
    assert "1,000-1,300 words" in guidance


@pytest.mark.asyncio
async def test_summarize_fallback(llm_service):
    """Test that summarize falls back to raw content on failure."""
    # With no actual LLM running, this should fall back
    content = "This is test content for summarization."
    result, ai_failed = await llm_service.summarize(content, retries=0)

    # Should return original content on failure
    assert ai_failed is True
    assert result == content
