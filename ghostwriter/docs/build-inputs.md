# Ghostwriter container build inputs

The Docker image builds its frontend with **Node 24** and its backend/runtime
with **Python 3.12**. These are the versions used by the existing Ghostwriter PR
checks (`.github/workflows/ghostwriter-pr-check.yml`). Node 24 is an upstream
LTS line through April 2028; Python 3.12 receives upstream security support
through October 2028. Those major/minor lines are the supported container and
CI matrix. Patch versions still follow the base image tags.

The local transcription binary is built from whisper.cpp release `v1.8.7`,
commit `48f628a84833905ee4a0658ee6d4a5c915ce1997`. The Dockerfile fetches
that commit directly and checks `HEAD` before building. The release source has
the `whisper-cli` CMake target and the shared `libwhisper`/`libggml` targets
copied into the runtime image. The YouTube audio fallback installs the
`yt-dlp==2026.8.19` wheel with its published SHA-256 from
`build-constraints.txt`; the runtime install uses `--require-hashes` and
`--no-deps`. The app's ordinary Python requirements are still resolved from
`requirements.txt`, and the frontend uses `npm ci` with `package-lock.json`.
`GGML_NATIVE=OFF` keeps whisper.cpp from generating instructions for only the
builder CPU; the arm64 build targets the armv8-a baseline.

References: [whisper.cpp v1.8.7](https://github.com/ggml-org/whisper.cpp/releases/tag/v1.8.7),
[yt-dlp 2026.8.19 on PyPI](https://pypi.org/project/yt-dlp/2026.8.19/),
[Node release schedule](https://nodejs.org/en/about/previous-releases), and
[Python support status](https://devguide.python.org/versions/).

## Updating inputs

1. Select an upstream whisper.cpp release. Resolve its **full** commit with
   `git ls-remote https://github.com/ggml-org/whisper.cpp.git refs/tags/<tag>`;
   if the tag is annotated, resolve `refs/tags/<tag>^{}` as well. Change
   `WHISPER_CPP_COMMIT` in the Dockerfile. Inspect its CMake output locations,
   build both supported architectures, and run `whisper-cli --help` in the image.
2. Select a yt-dlp release from PyPI. Read the `bdist_wheel` entry in its
   version JSON (`https://pypi.org/pypi/yt-dlp/<version>/json`) and update both
   the version and that wheel's `digests.sha256` in `build-constraints.txt`.
   Confirm `yt-dlp --version` inside the image. This intentionally installs the
   base wheel without optional extras. Review upstream optional runtime needs
   before changing that choice, especially the JavaScript runtime and
   `yt-dlp-ejs` used for full YouTube support.
3. Change Node/Python major or minor lines only with a corresponding CI update
   and a passing backend/frontend check on that line. Review the base image
   release notes, rebuild, and run the synthetic startup/migration smoke below.

## Verification

With a local Docker daemon and a builder that lists `linux/amd64` and
`linux/arm64`, build a unique local tag per platform. Do not push these tags.

```sh
cd ghostwriter
docker buildx ls
docker buildx build --platform linux/amd64 --load -t ghostwriter-runtime-check:amd64 .
docker buildx build --platform linux/arm64 --load -t ghostwriter-runtime-check:arm64 .
```

For a native image, start with **new empty temporary directories** for
`/app/data`, `/app/output`, and `/app/logs`; set only synthetic local settings.
Wait for `/health`, check that startup logs show `alembic upgrade head`, and
stop the container. Do not use a production `.env`, existing data directories,
provider credentials, or model downloads for this smoke. Run backend tests
under Python 3.12 and `npm ci`, `npm run check`, `npm run build` under Node 24.

The commit and wheel hash control those two inputs; they do **not** make the
whole image bit-for-bit reproducible. `node:24-alpine` and `python:3.12-slim`
tags, Debian `apt` packages, nonlocked Python requirements, and their
transitive dependencies can still change. Architecture-specific compiler
output also differs. Docker build and runtime behavior must be reverified
after base or dependency updates.
