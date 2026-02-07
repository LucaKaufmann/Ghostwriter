"""Summarize.sh CLI integration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.whisper_models import resolve_whisper_model_path

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_RELATIVE = Path("app/resources/summarize_config.default.json")


@dataclass
class SummarizeResult:
    """Result of a Summarize.sh invocation."""

    summary: str
    ai_failed: bool
    original_word_count: int | None = None
    error: str | None = None


class SummarizeShService:
    """Wrapper around the Summarize.sh CLI."""

    @staticmethod
    def _sanitize_error(message: str, max_len: int = 300) -> str:
        cleaned = " ".join(message.split())
        if len(cleaned) <= max_len:
            return cleaned
        return f"{cleaned[: max_len - 3]}..."

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

    def _summarize_config_details(self) -> dict[str, str | None]:
        raw, source = self.get_config()
        model = "auto"
        language = None
        error = None
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                value = payload.get("model")
                if isinstance(value, str) and value.strip():
                    model = value.strip()
                output = payload.get("output")
                if isinstance(output, dict):
                    lang_value = output.get("language")
                    if isinstance(lang_value, str) and lang_value.strip():
                        language = lang_value.strip()
        except json.JSONDecodeError as exc:
            error = f"invalid_json: {exc.msg}"
            model = "invalid"
        return {
            "path": str(self._resolve_config_path()),
            "source": source,
            "model": model,
            "language": language,
            "error": error,
        }

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

    def _resolve_cli_home(self) -> Path:
        return Path(os.path.expanduser(self.settings.data_dir))

    def _resolve_cli_config_path(self) -> Path:
        return self._resolve_cli_home() / ".summarize" / "config.json"

    def _prepare_cli_config(self) -> tuple[Path, Path, str]:
        """
        Ensure summarize CLI can read the UI-managed config from the data volume.

        summarize currently reads ~/.summarize/config.json; we force HOME=/app/data
        and link that expected location to the configured path.
        """
        source = self._resolve_config_path()
        cli_home = self._resolve_cli_home()
        target = self._resolve_cli_config_path()

        target.parent.mkdir(parents=True, exist_ok=True)

        if source.resolve() == target.resolve():
            return cli_home, target, "direct"

        if target.exists() or target.is_symlink():
            same_file = False
            try:
                same_file = target.resolve() == source.resolve()
            except OSError:
                same_file = False
            if same_file:
                return cli_home, target, "existing_link"
            target.unlink()

        try:
            target.symlink_to(source)
            sync_mode = "symlink"
        except OSError:
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            sync_mode = "copy"

        return cli_home, target, sync_mode

    @staticmethod
    def _extract_summary(payload: object) -> str | None:
        if isinstance(payload, dict):
            for key in ("summary", "output", "text", "content", "result"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _extract_model_info(payload: object) -> tuple[str | None, list[str]]:
        input_model = None
        provider_models: list[str] = []
        if isinstance(payload, dict):
            input_block = payload.get("input")
            if isinstance(input_block, dict):
                model_value = input_block.get("model")
                if isinstance(model_value, str) and model_value.strip():
                    input_model = model_value.strip()
            metrics = payload.get("metrics")
            if isinstance(metrics, dict):
                providers = metrics.get("providers")
                if isinstance(providers, list):
                    for provider in providers:
                        if not isinstance(provider, dict):
                            continue
                        model_value = provider.get("model")
                        if isinstance(model_value, str) and model_value.strip():
                            provider_models.append(model_value.strip())
        return input_model, provider_models

    @staticmethod
    def _extract_model_from_metrics(stderr_text: str) -> str | None:
        for line in stderr_text.splitlines():
            if "·" not in line:
                continue
            parts = [part.strip() for part in line.split("·")]
            if len(parts) >= 3 and parts[2]:
                return parts[2]
        match = re.search(r"\b(?:openai|google|anthropic|xai|zai|openrouter|cli)/\S+", stderr_text)
        if match:
            return match.group(0)
        return None

    @staticmethod
    def _looks_like_unsummarized_output(text: str, is_media: bool) -> bool:
        stripped = text.lstrip().lower()
        if stripped.startswith("transcript:") or stripped.startswith("transkript:"):
            return True
        if not is_media:
            return False
        # Media summaries should not return near full transcripts.
        return len(text.split()) >= 2500

    def _build_env(self, whisper_model: str | None, cli_home: Path | None) -> dict[str, str]:
        env = os.environ.copy()

        if cli_home is not None:
            home_value = str(cli_home)
            env["HOME"] = home_value
            env["USERPROFILE"] = home_value

        override_path = (
            Path(os.path.expanduser(self.settings.data_dir)) / "bin" / "whisper-cli"
        )
        configured_binary = (self.settings.summarize_sh_whisper_cpp_binary or "").strip()
        configured_path = (
            Path(os.path.expanduser(configured_binary)) if configured_binary else None
        )

        resolved_binary_path: Path | None = None
        resolved_binary_source: str | None = None
        if override_path.is_file():
            if os.access(override_path, os.X_OK):
                resolved_binary_path = override_path
                resolved_binary_source = "user override"
            else:
                logger.warning(
                    "Whisper override binary exists but is not executable: %s",
                    override_path,
                )

        if (
            resolved_binary_path is None
            and configured_path is not None
            and configured_path.is_file()
            and os.access(configured_path, os.X_OK)
        ):
            resolved_binary_path = configured_path
            resolved_binary_source = (
                "bundled"
                if str(configured_path) == "/usr/local/bin/whisper-cli"
                else "configured"
            )

        if resolved_binary_path is not None:
            env["SUMMARIZE_WHISPER_CPP_BINARY"] = str(resolved_binary_path)
            logger.info(
                "Whisper binary resolved: %s (%s)",
                resolved_binary_path,
                resolved_binary_source,
            )
        else:
            env.pop("SUMMARIZE_WHISPER_CPP_BINARY", None)

        models_dir = Path(
            os.path.expanduser(self.settings.summarize_sh_whisper_models_dir)
        )
        model_path = resolve_whisper_model_path(models_dir, whisper_model)
        if model_path:
            env["SUMMARIZE_WHISPER_CPP_MODEL_PATH"] = str(model_path)
        else:
            env.pop("SUMMARIZE_WHISPER_CPP_MODEL_PATH", None)

        return env

    async def summarize_url(
        self,
        url: str,
        whisper_model: str | None = None,
        is_media: bool = False,
    ) -> SummarizeResult:
        """
        Summarize a URL using Summarize.sh.

        Returns:
            SummarizeResult with summary and ai_failed flag.
        """
        self._ensure_config_exists()
        cli_home = self._resolve_cli_home()
        cli_config_path = self._resolve_cli_config_path()
        cli_config_mode = "none"
        try:
            cli_home, cli_config_path, cli_config_mode = self._prepare_cli_config()
        except OSError as exc:
            logger.warning("Failed to prepare summarize CLI config: %s", exc)
        config_details = self._summarize_config_details()
        logger.info(
            "Summarize.sh config in use",
            extra={
                "config_path": config_details["path"],
                "config_source": config_details["source"],
                "config_model": config_details["model"],
                "config_language": config_details["language"],
                "config_error": config_details["error"],
                "cli_home": str(cli_home),
                "cli_config_path": str(cli_config_path),
                "cli_config_mode": cli_config_mode,
                "whisper_model": whisper_model,
            },
        )

        cmd = ["summarize", url, "--plain"]
        logger.debug("Running Summarize.sh: %s", " ".join(cmd))
        env = self._build_env(whisper_model, cli_home=cli_home)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            logger.error("Summarize.sh CLI not found: %s", exc)
            return SummarizeResult(
                summary="",
                ai_failed=True,
                error="summarize CLI not found in PATH",
            )

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
            return SummarizeResult(
                summary="",
                ai_failed=True,
                error=f"timed out after {self.settings.summarize_sh_timeout_seconds}s",
            )

        if process.returncode != 0:
            err_text = stderr.decode("utf-8", errors="ignore").strip()
            logger.error("Summarize.sh failed: %s", err_text)
            if err_text:
                error = f"exit {process.returncode}: {self._sanitize_error(err_text)}"
            else:
                error = f"exit {process.returncode} with empty stderr"
            return SummarizeResult(summary="", ai_failed=True, error=error)

        output = stdout.decode("utf-8", errors="ignore").strip()
        if not output:
            logger.warning("Summarize.sh returned empty output for %s", url)
            return SummarizeResult(summary="", ai_failed=True, error="empty output")

        stderr_text = stderr.decode("utf-8", errors="ignore")
        observed_model = self._extract_model_from_metrics(stderr_text)
        logger.info(
            "Summarize.sh model selection: config=%s observed=%s",
            config_details["model"],
            observed_model,
            extra={
                "url": url,
                "config_model": config_details["model"],
                "observed_model": observed_model,
            },
        )
        if self._looks_like_unsummarized_output(output, is_media=is_media):
            logger.warning(
                "Summarize.sh returned transcript-like output; treating as failure",
                extra={
                    "url": url,
                    "is_media": is_media,
                    "word_count": len(output.split()),
                },
            )
            return SummarizeResult(
                summary=output,
                ai_failed=True,
                error="output looked like unsummarized transcript",
            )
        logger.info("Summarize.sh returned summary", extra={"url": url})
        return SummarizeResult(summary=output, ai_failed=False)
