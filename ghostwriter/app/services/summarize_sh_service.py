"""Summarize.sh CLI integration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_RELATIVE = Path("app/resources/summarize_config.default.json")


@dataclass
class SummarizeResult:
    """Result of a Summarize.sh invocation."""

    summary: str
    ai_failed: bool
    original_word_count: int | None = None


class SummarizeShService:
    """Wrapper around the Summarize.sh CLI."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _resolve_config_path(self) -> Path:
        return Path(os.path.expanduser(self.settings.summarize_sh_config_path))

    def _default_config_path(self) -> Path:
        # Resolve relative to repo root if possible, else fall back to app/ resources.
        repo_root = Path(__file__).resolve().parents[2]
        return repo_root / _DEFAULT_CONFIG_RELATIVE

    def _read_default_config(self) -> str:
        path = self._default_config_path()
        if not path.exists():
            logger.warning("Default Summarize.sh config missing at %s", path)
            return "{}"
        return path.read_text(encoding="utf-8")

    def get_config(self) -> tuple[str, str]:
        """
        Return config JSON and source indicator.

        Returns:
            Tuple of (config_json, source) where source is "user" or "default".
        """
        path = self._resolve_config_path()
        if path.exists():
            return path.read_text(encoding="utf-8"), "user"
        return self._read_default_config(), "default"

    def validate_config_json(self, raw_json: str) -> None:
        """
        Validate that config JSON parses correctly.

        Raises:
            ValueError if JSON parsing fails.
        """
        try:
            json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc.msg} (line {exc.lineno})") from exc

    def save_config(self, raw_json: str) -> None:
        """
        Persist config JSON to the Summarize.sh config path.
        """
        self.validate_config_json(raw_json)
        path = self._resolve_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        content = raw_json.strip()
        if not content.endswith("\n"):
            content += "\n"
        path.write_text(content, encoding="utf-8")

    def _ensure_config_exists(self) -> None:
        path = self._resolve_config_path()
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        default_json = self._read_default_config().strip()
        if default_json:
            if not default_json.endswith("\n"):
                default_json += "\n"
            path.write_text(default_json, encoding="utf-8")

    @staticmethod
    def _extract_summary(payload: object) -> str | None:
        if isinstance(payload, dict):
            for key in ("summary", "output", "text", "content", "result"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    async def summarize_url(self, url: str) -> SummarizeResult:
        """
        Summarize a URL using Summarize.sh.

        Returns:
            SummarizeResult with summary and ai_failed flag.
        """
        self._ensure_config_exists()

        cmd = ["summarize", url, "--json"]
        logger.debug("Running Summarize.sh: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            logger.error("Summarize.sh CLI not found: %s", exc)
            return SummarizeResult(summary="", ai_failed=True)

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.settings.summarize_sh_timeout_seconds,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            logger.error(
                "Summarize.sh timed out after %ss",
                self.settings.summarize_sh_timeout_seconds,
            )
            return SummarizeResult(summary="", ai_failed=True)

        if process.returncode != 0:
            err_text = stderr.decode("utf-8", errors="ignore").strip()
            logger.error("Summarize.sh failed: %s", err_text)
            return SummarizeResult(summary="", ai_failed=True)

        output = stdout.decode("utf-8", errors="ignore").strip()
        if not output:
            logger.warning("Summarize.sh returned empty output for %s", url)
            return SummarizeResult(summary="", ai_failed=True)

        try:
            payload = json.loads(output)
            summary = self._extract_summary(payload)
            if summary:
                logger.info("Summarize.sh returned summary", extra={"url": url})
                return SummarizeResult(summary=summary, ai_failed=False)
            logger.warning("Summarize.sh JSON output missing summary field")
        except json.JSONDecodeError:
            logger.warning("Summarize.sh output was not JSON; using raw output")

        return SummarizeResult(summary=output, ai_failed=False)
