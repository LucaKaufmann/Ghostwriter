"""Synthetic HTTP responses exercise the helper's installed urllib opener."""

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/create_one_off_podcast.py"
spec = importlib.util.spec_from_file_location("podcast_helper_transport", SCRIPT)
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)
TOKEN = "synthetic-secret-token"
BASE = "https://example.test/api"
EPISODE_ID = "12345678-1234-1234-1234-123456789abc"
DOWNLOAD = BASE + f"/podcast/episodes/{EPISODE_ID}/download"


class FakeHTTP(urllib.request.BaseHandler):
    handler_order = 100

    def __init__(self, routes):
        self.routes = routes
        self.seen = []

    def http_open(self, request):
        return self.respond(request)

    https_open = http_open

    def respond(self, request):
        self.seen.append(request)
        status, headers, body = self.routes[request.full_url]
        message = Message()
        for key, value in headers.items():
            message[key] = value
        response = urllib.response.addinfourl(io.BytesIO(body), message, request.full_url, status)
        response.msg = "synthetic"
        return response


class TransportTests(unittest.TestCase):
    def use_routes(self, routes):
        fake = FakeHTTP(routes)
        build = urllib.request.build_opener
        patched = patch.object(
            helper.urllib.request,
            "build_opener",
            side_effect=lambda *handlers: build(fake, *handlers),
        )
        return fake, patched

    def assert_exit(self, code, call):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            call()
        self.assertEqual(raised.exception.code, code)
        self.assertNotIn(TOKEN, stderr.getvalue())
        return stderr.getvalue()

    def test_same_origin_multi_hop_and_default_port(self):
        first = BASE + "/podcast/episodes/one-off"
        routes = {
            first: (302, {"Location": "/next"}, b""),
            "https://example.test/next": (302, {"Location": "https://EXAMPLE.test:443/final"}, b""),
            "https://EXAMPLE.test:443/final": (200, {"Content-Type": "application/json"}, b'{"ok": true}'),
        }
        fake, patched = self.use_routes(routes)
        with patched:
            self.assertEqual(
                helper.request_json(method="GET", api_base=BASE, path="/podcast/episodes/one-off", token=TOKEN),
                {"ok": True},
            )
        self.assertEqual(len(fake.seen), 3)
        self.assertTrue(all(req.get_header("Authorization") == "Bearer " + TOKEN for req in fake.seen))

    def test_cross_origin_after_valid_hop_never_opens(self):
        first = BASE + "/poll"
        fake, patched = self.use_routes({
            first: (302, {"Location": "/safe"}, b""),
            "https://example.test/safe": (302, {"Location": "//other.test/steal"}, b""),
        })
        with patched:
            self.assert_exit(helper.EXIT_API, lambda: helper.request_json(
                method="GET", api_base=BASE, path="/poll", token=TOKEN
            ))
        self.assertEqual([req.full_url for req in fake.seen], [first, "https://example.test/safe"])

    def test_initial_url_and_downgrade_are_rejected(self):
        fake, patched = self.use_routes({BASE + "/poll": (302, {"Location": "http://example.test/poll"}, b"")})
        with patched:
            self.assert_exit(helper.EXIT_DOWNLOAD, lambda: helper.request_bytes(
                url="https://other.test/audio", api_base=BASE, token=TOKEN, allow_insecure_http=True
            ))
            self.assert_exit(helper.EXIT_API, lambda: helper.request_json(
                method="GET", api_base=BASE, path="/poll", token=TOKEN,
                allow_insecure_http=True,
            ))
        self.assertEqual(len(fake.seen), 1)

    def test_port_change_and_audio_redirect_are_rejected(self):
        fake, patched = self.use_routes({
            "https://example.test/audio": (302, {"Location": "https://example.test:444/audio"}, b""),
        })
        with patched:
            self.assert_exit(helper.EXIT_DOWNLOAD, lambda: helper.request_bytes(
                url="https://example.test/audio", api_base=BASE,
                token=TOKEN, allow_insecure_http=False,
            ))
        self.assertEqual(len(fake.seen), 1)

    def test_trailing_dot_host_is_a_different_http_origin(self):
        fake, patched = self.use_routes({
            BASE + "/poll": (302, {"Location": "https://example.test./poll"}, b""),
        })
        with patched:
            self.assert_exit(helper.EXIT_API, lambda: helper.request_json(
                method="GET", api_base=BASE, path="/poll", token=TOKEN,
            ))
        self.assertEqual(len(fake.seen), 1)

    def test_loopback_http_works_without_opt_in(self):
        base = "http://localhost:8080/api"
        url = base + "/poll"
        fake, patched = self.use_routes({
            url: (200, {"Content-Type": "application/json"}, b"{}"),
        })
        with patched:
            self.assertEqual(helper.request_json(
                method="GET", api_base=base, path="/poll", token=TOKEN,
            ), {})
        self.assertEqual(len(fake.seen), 1)

    def test_remote_http_requires_opt_in(self):
        base = "http://example.test/api"
        url = base + "/poll"
        fake, patched = self.use_routes({
            url: (200, {"Content-Type": "application/json"}, b"{}"),
        })
        with patched:
            self.assert_exit(helper.EXIT_API, lambda: helper.request_json(
                method="GET", api_base=base, path="/poll", token=TOKEN,
            ))
            self.assertEqual(helper.request_json(
                method="GET", api_base=base, path="/poll", token=TOKEN,
                allow_insecure_http=True,
            ), {})
        self.assertEqual(len(fake.seen), 1)

    def test_reject_userinfo_bad_port_and_scheme_before_open(self):
        fake, patched = self.use_routes({})
        with patched:
            for url in ("https://person:pass@example.test/audio", "https://example.test:bad/audio",
                        "https://example.test:0/audio", "https://example.test:/audio",
                        "https://example.test:65536/audio", "ftp://example.test/audio"):
                with self.subTest(url=url):
                    self.assert_exit(helper.EXIT_DOWNLOAD, lambda: helper.request_bytes(
                        url=url, api_base=BASE, token=TOKEN, allow_insecure_http=False
                    ))
        self.assertEqual(fake.seen, [])

    def test_redirect_loop_is_bounded(self):
        first = BASE + "/loop"
        fake, patched = self.use_routes({first: (302, {"Location": "/api/loop"}, b"")})
        with patched:
            self.assert_exit(helper.EXIT_API, lambda: helper.request_json(
                method="GET", api_base=BASE, path="/loop", token=TOKEN
            ))
        self.assertLessEqual(len(fake.seen), 12)

    def test_unique_redirect_chain_is_bounded(self):
        routes = {
            BASE + f"/hop/{index}": (
                302, {"Location": f"/api/hop/{index + 1}"}, b""
            )
            for index in range(15)
        }
        fake, patched = self.use_routes(routes)
        with patched:
            self.assert_exit(helper.EXIT_API, lambda: helper.request_json(
                method="GET", api_base=BASE, path="/hop/0", token=TOKEN,
            ))
        self.assertLessEqual(len(fake.seen), 11)

    def test_post_302_becomes_get_without_source_body(self):
        first = BASE + "/submit"
        second = BASE + "/next"
        fake, patched = self.use_routes({
            first: (302, {"Location": second}, b""),
            second: (200, {"Content-Type": "application/json"}, b"{}"),
        })
        with patched:
            helper.request_json(method="POST", api_base=BASE, path="/submit",
                                token=TOKEN, payload={"sources": ["private source"]})
        self.assertEqual([req.get_method() for req in fake.seen], ["POST", "GET"])
        self.assertIsNotNone(fake.seen[0].data)
        self.assertIsNone(fake.seen[1].data)

    def test_post_307_does_not_resend_source_body(self):
        first = BASE + "/submit"
        fake, patched = self.use_routes({first: (307, {"Location": BASE + "/next"}, b"redirect")})
        with patched:
            self.assert_exit(helper.EXIT_API, lambda: helper.request_json(
                method="POST", api_base=BASE, path="/submit", token=TOKEN,
                payload={"sources": ["private source"]},
            ))
        self.assertEqual(len(fake.seen), 1)

    def test_download_uses_configured_api_for_public_and_same_origin_urls(self):
        fake, patched = self.use_routes({
            DOWNLOAD: (200, {"Content-Type": "audio/mpeg"}, b"audio bytes"),
        })
        with tempfile.TemporaryDirectory() as directory, patched:
            for advertised_url in (
                f"https://public.test/api/podcast/episodes/{EPISODE_ID}/download",
                f"https://example.test/api/podcast/episodes/{EPISODE_ID}/download",
                f"/api/podcast/episodes/{EPISODE_ID}/download",
            ):
                with self.subTest(advertised_url=advertised_url):
                    path = helper.download_episode(
                        api_base=BASE, token=TOKEN,
                        detail={"id": EPISODE_ID, "download_url": advertised_url},
                        output=str(Path(directory) / "episode.mp3"),
                        allow_insecure_http=False,
                    )
                    self.assertEqual(path.read_bytes(), b"audio bytes")
        self.assertEqual([req.full_url for req in fake.seen], [DOWNLOAD] * 3)
        self.assertTrue(all(req.get_header("Authorization") == "Bearer " + TOKEN for req in fake.seen))

    def test_download_rejects_malformed_id_and_advertised_url_before_open(self):
        fake, patched = self.use_routes({})
        with tempfile.TemporaryDirectory() as directory, patched:
            for episode_id in ("../secret", "123", EPISODE_ID + "/extra", "{" + EPISODE_ID + "}"):
                with self.subTest(episode_id=episode_id):
                    self.assert_exit(helper.EXIT_DOWNLOAD, lambda: helper.download_episode(
                        api_base=BASE, token=TOKEN,
                        detail={"id": episode_id, "download_url": "https://public.test/audio"},
                        output=None, allow_insecure_http=False,
                    ))
            for advertised_url in ("ftp://public.test/audio", "https://public.test:bad/audio",
                                   "https://person:pass@public.test/audio"):
                with self.subTest(advertised_url=advertised_url):
                    self.assert_exit(helper.EXIT_DOWNLOAD, lambda: helper.download_episode(
                        api_base=BASE, token=TOKEN,
                        detail={"id": EPISODE_ID, "download_url": advertised_url},
                        output=str(Path(directory) / "rejected.mp3"),
                        allow_insecure_http=False,
                    ))
            self.assertFalse((Path(directory) / "rejected.mp3").exists())
        self.assertEqual(fake.seen, [])

    def test_download_canonicalizes_hex_id_in_route_and_default_filename(self):
        fake, patched = self.use_routes({
            DOWNLOAD: (200, {"Content-Type": "audio/mpeg"}, b"audio bytes"),
        })
        with tempfile.TemporaryDirectory() as directory, patched, patch.object(helper.Path, "cwd", return_value=Path(directory)):
            path = helper.download_episode(
                api_base=BASE, token=TOKEN,
                detail={"episode_id": EPISODE_ID.replace("-", "").upper(), "stream_url": "https://public.test/audio"},
                output=None, allow_insecure_http=False,
            )
            self.assertEqual(path.name, f"ghostwriter-podcast-{EPISODE_ID}.mp3")
            self.assertEqual(path.read_bytes(), b"audio bytes")
        self.assertEqual([req.full_url for req in fake.seen], [DOWNLOAD])

    def test_download_redirect_to_public_origin_never_sends_credentials(self):
        fake, patched = self.use_routes({
            DOWNLOAD: (302, {"Location": "https://public.test/audio"}, b""),
        })
        with tempfile.TemporaryDirectory() as directory, patched:
            self.assert_exit(helper.EXIT_DOWNLOAD, lambda: helper.download_episode(
                api_base=BASE, token=TOKEN,
                detail={"id": EPISODE_ID, "download_url": "https://public.test/audio"},
                output=str(Path(directory) / "rejected.mp3"), allow_insecure_http=False,
            ))
            self.assertFalse((Path(directory) / "rejected.mp3").exists())
        self.assertEqual([req.full_url for req in fake.seen], [DOWNLOAD])

    def test_remote_http_download_still_requires_explicit_opt_in(self):
        base = "http://internal.test/api"
        url = base + f"/podcast/episodes/{EPISODE_ID}/download"
        fake, patched = self.use_routes({
            url: (200, {"Content-Type": "audio/mpeg"}, b"audio bytes"),
        })
        detail = {"id": EPISODE_ID, "download_url": "https://public.test/audio"}
        with tempfile.TemporaryDirectory() as directory, patched:
            output = str(Path(directory) / "episode.mp3")
            self.assert_exit(helper.EXIT_DOWNLOAD, lambda: helper.download_episode(
                api_base=base, token=TOKEN, detail=detail,
                output=output, allow_insecure_http=False,
            ))
            self.assertFalse(Path(output).exists())
            path = helper.download_episode(
                api_base=base, token=TOKEN, detail=detail,
                output=output, allow_insecure_http=True,
            )
            self.assertEqual(path.read_bytes(), b"audio bytes")
        self.assertEqual([req.full_url for req in fake.seen], [url])

    def test_poll_rejects_untrusted_episode_id_before_open(self):
        fake, patched = self.use_routes({})
        with patched:
            self.assert_exit(helper.EXIT_API, lambda: helper.poll_episode(
                api_base=BASE, token=TOKEN, episode_id="../other",
                interval_seconds=0, timeout_seconds=1,
            ))
        self.assertEqual(fake.seen, [])

    def test_error_body_does_not_print_token(self):
        first = BASE + "/fail"
        fake, patched = self.use_routes({first: (401, {}, ("bad " + TOKEN).encode())})
        with patched:
            self.assert_exit(helper.EXIT_API, lambda: helper.request_json(
                method="GET", api_base=BASE, path="/fail", token=TOKEN
            ))
        self.assertEqual(len(fake.seen), 1)

    def test_non_json_error_redacts_before_truncation(self):
        first = BASE + "/invalid-json"
        fake, patched = self.use_routes({
            first: (200, {}, ("x" * 499 + TOKEN + " trailing").encode()),
        })
        with patched:
            error = self.assert_exit(helper.EXIT_API, lambda: helper.request_json(
                method="GET", api_base=BASE, path="/invalid-json", token=TOKEN,
            ))
        self.assertNotIn("x" * 499 + TOKEN[:1], error)
        self.assertEqual(len(fake.seen), 1)


if __name__ == "__main__":
    unittest.main()
