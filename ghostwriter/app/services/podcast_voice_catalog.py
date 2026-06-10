"""Curated podcast voice metadata shared by API clients and agent skills."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


PodcastVoiceProvider = Literal["openai", "elevenlabs"]


@dataclass(frozen=True)
class PodcastVoiceCatalogEntry:
    provider: PodcastVoiceProvider
    name: str
    id: str
    vibe: str
    best_suited_for: str
    pairing_notes: str


@dataclass(frozen=True)
class PodcastVoicePairPreset:
    provider: PodcastVoiceProvider
    label: str
    host_a_voice: str
    host_b_voice: str
    best_suited_for: str


VOICE_CATALOG: tuple[PodcastVoiceCatalogEntry, ...] = (
    PodcastVoiceCatalogEntry(
        provider="openai",
        name="Alloy",
        id="alloy",
        vibe="Balanced, neutral, clear",
        best_suited_for="General research briefings and mixed-source summaries",
        pairing_notes="Works well as the analytical host opposite Echo or Shimmer",
    ),
    PodcastVoiceCatalogEntry(
        provider="openai",
        name="Echo",
        id="echo",
        vibe="Warm, conversational, steady",
        best_suited_for="Context-setting, explanatory turns, and recaps",
        pairing_notes="Pairs naturally with Alloy for a classic two-host format",
    ),
    PodcastVoiceCatalogEntry(
        provider="openai",
        name="Fable",
        id="fable",
        vibe="Expressive, story-forward, lighter",
        best_suited_for="Narrative explainers and approachable solo summaries",
        pairing_notes="Pairs with Nova when you want a more energetic show",
    ),
    PodcastVoiceCatalogEntry(
        provider="openai",
        name="Onyx",
        id="onyx",
        vibe="Deep, calm, authoritative",
        best_suited_for="Serious analysis, longer-form synthesis, and solo narration",
        pairing_notes="Use with Shimmer or Echo for contrast",
    ),
    PodcastVoiceCatalogEntry(
        provider="openai",
        name="Nova",
        id="nova",
        vibe="Bright, quick, energetic",
        best_suited_for="Hooks, momentum, and lively research updates",
        pairing_notes="Pairs with Fable or Onyx depending on desired contrast",
    ),
    PodcastVoiceCatalogEntry(
        provider="openai",
        name="Shimmer",
        id="shimmer",
        vibe="Polished, friendly, precise",
        best_suited_for="Executive-style briefings and concise summaries",
        pairing_notes="Pairs well with Onyx for serious but accessible episodes",
    ),
    PodcastVoiceCatalogEntry(
        provider="elevenlabs",
        name="Chris",
        id="iP95p4xoKVk53GoZ742B",
        vibe="Natural, confident, presenter-like",
        best_suited_for="Host A in research briefings and decision summaries",
        pairing_notes="Default ElevenLabs Host A with Matilda",
    ),
    PodcastVoiceCatalogEntry(
        provider="elevenlabs",
        name="Matilda",
        id="XrExE9yKIg1WjnnlVkGX",
        vibe="Warm, clear, explanatory",
        best_suited_for="Host B context, definitions, and clarifying questions",
        pairing_notes="Default ElevenLabs Host B with Chris",
    ),
    PodcastVoiceCatalogEntry(
        provider="elevenlabs",
        name="George",
        id="JBFqnCBsd6RMkjVDRZzb",
        vibe="Measured, grounded, direct",
        best_suited_for="Formal analysis and slower-paced synthesis",
        pairing_notes="Alternative Host A with Bella",
    ),
    PodcastVoiceCatalogEntry(
        provider="elevenlabs",
        name="Bella",
        id="hpp4J3VqNfWAUOO0d1Us",
        vibe="Friendly, responsive, conversational",
        best_suited_for="Accessible companion host and lighter recap segments",
        pairing_notes="Alternative Host B with George",
    ),
)


VOICE_PAIR_PRESETS: tuple[PodcastVoicePairPreset, ...] = (
    PodcastVoicePairPreset(
        provider="openai",
        label="Alloy + Echo",
        host_a_voice="alloy",
        host_b_voice="echo",
        best_suited_for="Default balanced research briefing",
    ),
    PodcastVoicePairPreset(
        provider="openai",
        label="Nova + Fable",
        host_a_voice="nova",
        host_b_voice="fable",
        best_suited_for="More energetic narrative episodes",
    ),
    PodcastVoicePairPreset(
        provider="elevenlabs",
        label="Chris + Matilda",
        host_a_voice="iP95p4xoKVk53GoZ742B",
        host_b_voice="XrExE9yKIg1WjnnlVkGX",
        best_suited_for="Default ElevenLabs research briefing",
    ),
    PodcastVoicePairPreset(
        provider="elevenlabs",
        label="George + Bella",
        host_a_voice="JBFqnCBsd6RMkjVDRZzb",
        host_b_voice="hpp4J3VqNfWAUOO0d1Us",
        best_suited_for="Formal analysis with a warmer companion voice",
    ),
)


def podcast_voice_catalog_payload() -> dict[str, object]:
    """Return the serializable podcast voice catalog payload."""
    return {
        "voices": [asdict(entry) for entry in VOICE_CATALOG],
        "pair_presets": [asdict(entry) for entry in VOICE_PAIR_PRESETS],
    }
