# REVIEW-VERIFICATION

Review comments75/4114827157,101/4115437083 and98/4115324868 addressed. The nested pytest subprocess explicitly adds the repository source path before importing app, independent of editable-install hooks. Wrong-instance live pull and write assertions require HTTP409 in addition to server_changed. Backup instructions stop optional Ollama before copying its volume and keep restored writers stopped until restoration/migration is complete.

Metadata tests passed5/5 on Python3.11 and requirements-only Python3.12 (pip reports no installed ghostwriter package). The nested process runs from a temporary directory and restores environment/socket state. `scripts/verify-feed-sync-contract.py --python /private/tmp/epilogue-runtime-312/bin/python` passed1 live FastAPI/Ktor fixture test with zero skips/failures, using task AndroidSDK/JDK17. No provider calls. Backup change is documentation checked against Compose with-ollama service/profile; no real backup/deployment was performed. `git diff --check` passed.

Review correction: removed an unsupported instruction to wait for Compose Ollama health status; the existing optional service declares no healthcheck. Restore keeps both volume writers stopped and starts the sidecar before Ghostwriter, retaining the existing application health/reader checks.
