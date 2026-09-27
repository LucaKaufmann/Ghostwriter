# REVIEW-WEB-CONFLICTS

PR96 comments4115286307/4115286315: edit/toggle conflicts against a tombstone now offer an explicit guarded POST restore with captured complete proposed fields. Active-feed conflicts keep guarded PUT. Add/edit dialogs close before exposing the page action, preserving the captured proposal and removing the modal overlay/focus trap. No write occurs before the user chooses retry/restore.

`npm run check`: zero errors/warnings. `npm run test:e2e -- --project=behavior`:22 passed, including add-dialog restore, edit-dialog retry, deleted-feed restore, existing bulk CAS and session expiry/retry cases. Production build runs as browser setup and passed. Initial new test assumed the fixture's mode incorrectly; assertion corrected to compare the captured proposal with the submitted one, then all22 passed. Fixture providers only.

Root inspected [deleted-feed restore](assets/web-deleted-feed-restore.png). No backend/shared/native contract change.

Independent review identified two proposal-loss paths: failed restore POST and unrelated toggle success. Correction uses a per-conflict token so only the successful explicit resolving action clears that proposal; transient failures preserve retry. Expanded browser behavior suite23/23 and typecheck pass after correction.
