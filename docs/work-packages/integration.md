# Integration, runtime, and dependent implementation packages

All packages inherit the [master backlog](backlog.md) and [worker prompt](worker-prompt.md). Prepared at `cdb776d` on 2026-09-27; no implementation or new runtime evidence is claimed.

## RETENTION-02

**P2 — Apply the accepted digest deletion contract.** Depends on RETENTION-01's recorded ownership/deletion decision and ENV-01 verification setup. If a material destructive policy remains unresolved, remain gated and report the precise choice to root.

Own `ghostwriter/app/worker/cleanup.py`, `ghostwriter/app/api/digests.py`, a new focused deletion service, `ghostwriter/tests/test_digest_retention.py`, and related assertions in `test_digest_download_formats.py`. Model/Alembic paths require root's allocation after RETENTION-01. Do not add broader transcript/debug retention, change retention periods, remove independent episodes/covers, sweep historical unknown files, or enable all foreign keys as a shortcut.

Outcome: manual deletion and scheduled retention use the same implementation and remove exactly the rows/artifacts owned by the digest according to the accepted policy. Article/PDF orphans stop accumulating. Source references, one-off privacy, and independently retained audio obey the recorded contract.

Acceptance: manual/scheduled parity; unrelated files/content survive; missing files, permission failure, interrupted DB/filesystem sequence, concurrent download/generation, repeated retry, and referenced episodes are exercised. Do not silently report complete deletion after required cleanup fails. Migration/backfill only if approved in the contract; fresh/previous-head tests required if schema changes. Checks: B with retention, download formats, podcast privacy/API and migration tests as applicable. Independent data-integrity review; one focused fix PR and result file.

## RUNTIME-01

**P2 — Control container build inputs and verify supported runtimes.** Depends on ENV-01; must precede CI-01's final runtime matrix. Own `ghostwriter/Dockerfile`, a new `ghostwriter/build-constraints.txt` if needed, and `ghostwriter/docs/build-inputs.md`. No ownership of `requirements.txt`, `pyproject.toml`, existing CI workflows, package lockfiles, or app behavior; request a narrow handoff from ENV-01 if a manifest change is essential.

Outcome: container build no longer clones arbitrary whisper.cpp HEAD or separately installs an unconstrained yt-dlp; supported Python/Node versions are explicit and tested. Select compatible versions from current working evidence and official upstream documentation during implementation; do not invent version pins in the plan. Avoid unrelated major upgrades. Preserve declared self-hosted/private-host functionality and target architecture compatibility.

Acceptance: exact validated whisper.cpp revision and controlled yt-dlp input; the actual Docker install consumes those inputs; an explicit update procedure; fresh local container startup/migration smoke with synthetic mounts and relevant backend tests under supported runtime(s). Verify amd64 and arm64 build feasibility or report unavailable architecture as unverified. Resolve Node 22/container versus 24/CI and Python 3.11/container versus 3.12/CI by a documented supported matrix or evidence-based alignment; CI-01 consumes that choice. Record residual mutable base/apt/transitive dependencies honestly rather than claiming bit-for-bit reproducibility. No registry push, release tag, production mounts, or paid transcription. Commands: inspect builder/daemon/platform availability; `docker build`/synthetic smoke with unique tags/volumes plus B/W checks for the chosen runtime matrix. A missing Docker daemon is blocked, not failed application behavior.

## CI-01

**P2 — Run meaningful backend, helper, and plugin regressions on PRs.** Depends on ENV-01, RUNTIME-01's runtime decision, AUTH-01, HELPER-01, and KO-01 harnesses; other ready backend regressions are included as they integrate. Own `.github/workflows/ghostwriter-pr-check.yml` and a narrowly named test runner only if existing commands cannot be invoked directly. No ownership of browser/native workflows: WEB-01 owns `ghostwriter-browser.yml`, BUILD-NATIVE owns `native-checks.yml`.

Outcome: recent podcast/privacy and data-integrity behavior is checked by CI, and changes under the helper/plugin paths actually trigger their tests. Prefer the isolated full backend suite if runtime supports it; do not retain an arbitrary smoke subset that omits implemented podcast behavior. Install declared dependencies and necessary native PDF libraries; use the runtime matrix fixed by RUNTIME-01. CI scripts must not load real `.env` or receive provider secrets.

Acceptance: workflow path filters include affected app/tests/declared dependencies/helper/plugin changes; relevant commands execute instead of only importing/collecting; failures fail jobs; no silent skipped required suites; timeouts bound execution; sanitized logs/fixtures. Browser/native checks are separate and neither duplicated nor omitted. Verify YAML/runner commands locally where possible and inspect actual GitHub check results after the PR exists. Before remote runs, static/local validation is only that evidence; draft the PR if required CI execution remains unavailable. No weakening tests to force green. Conventional Commit test/ci PR with real run links once available.

## JOURNEY-01

**P2 — Prove the integrated reading/listening journey with fixtures.** Depends on ENV-01, AUTH-01, INGEST-01, RETENTION-02, WEB-01/02 and relevant runtime changes; root supplies a local integration/stacked base containing exact verified commits. Own a new `ghostwriter/tests/test_reading_listening_journey.py`, a separate `ghostwriter/frontend/tests/e2e/reading-listening.spec.ts`, task-specific fixtures, and `ghostwriter/docs/fixture-journey.md`. Shared fixtures/playwright configuration need a narrow handoff after WEB-01. No broad product code changes; return discovered defects as bounded assignments to root.

Outcome: exercise a real local FastAPI instance and browser through synthetic sources → persisted digest → EPUB/PDF/web reading → mocked-provider generated episode → private feed. Use real local storage/rendering/transformation where practical, replacing external extraction/LLM/TTS/transcription and source accounts with deterministic fixtures. A browser fed entirely canned API responses is not this integration check.

Acceptance: successful output can be opened/read; episode/feed privacy is enforced; generation progress reaches an accurate terminal state; one controlled generation failure is visible and retry recovers without source loss; repeated polling is bounded; deletion follows accepted retention policy; offline/native behavior is not inferred from this server/web check. Inspect rendered views and save sanitized screenshots/trace. Document which external boundaries are mocked. Run B/W relevant integration commands against unique temporary ports/storage; no real source content or provider charges. Independent review of the harness to ensure mocks do not bypass the behavior it claims to test. A test PR is the deliverable; real audio quality and device scheduling remain explicitly unverified.

## Coverage and deferred investigation outcomes

RECOVERY-01 is deliberately an evidence/design PR. If fault injection establishes additional defects, root creates the smallest implementation follow-up from its exact reproduction and accepted recovery contract; do not authorize a speculative pipeline rewrite now. MEDIA-01 can include its bounded single-process concurrency fix after a deterministic reproduction. Neither may claim distributed job guarantees.

General documentation positioning, broad dependency lock-manager migration, performance redesign, Swift 6 migration, generated-podcast native controls, and feature-flag rollout remain outside this reliability plan. RELEASE-01 records real release-readiness gaps without deploying. The ignored personal deploy script remains held as DEPLOY-01.
