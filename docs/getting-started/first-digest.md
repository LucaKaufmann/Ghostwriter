# First Digest Walkthrough

This walkthrough takes you from a running Ghostwriter server to a completed digest you can download or sync to a device.

## 1. Confirm You Can Sign In

Open the web UI and verify that:

- The server loads successfully
- You can log in with the admin account
- `Settings -> API Tokens` is available

If login or setup fails, start with [Sync and auth troubleshooting](../troubleshooting/sync-and-auth.md).

## 2. Add a Small Feed Set

Start with one or two feeds so your first run is easy to inspect.

Recommended first test set:

- One text-heavy article feed
- Optional: one podcast or YouTube feed if you want to test media handling later

After adding feeds, confirm they appear in the feed list and save correctly.

## 3. Review Processing Defaults

Before generating the digest, review the settings that affect first-run results:

- AI provider and credentials
- Article limits
- Schedule times
- Whether briefing-style summarization or full extraction is preferred for the feeds you added

If you are unsure, keep the defaults and test with a small input set first.

## 4. Trigger a Digest

Run a manual digest from the web UI so you can observe the result immediately.

Watch for:

- Feed fetch completion
- Article processing
- Final digest status

## 5. Open the Result

When the digest completes:

- Open it in the history view
- Download the EPUB
- Test it in your preferred reading app or device

If podcast generation is enabled in your setup, you can configure that separately after the basic EPUB flow works.

## 6. Connect a Client

After the first digest is confirmed:

- Sync it to a mobile app with [Connect mobile apps](connect-mobile-apps.md)
- Or set up [KOReader](../installation/koreader.md)

## Next Step

- Learn ongoing feed management in [Feeds](../user-guide/feeds.md)
- Learn digest management in [Digests](../user-guide/digests.md)
