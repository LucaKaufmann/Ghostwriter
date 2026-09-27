"""Synthetic HTTP responses exercise the helper's installed urllib opener."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/create_one_off_podcast.py"
spec = importlib.util.spec_from_file_location("podcast_helper_transport", SCRIPT)
helper = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)
TOKEN = "synthetic-secret-token"
BASE = "https://example.test/api"


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

    def test_same_origin_download_and_cross_origin_audio_rejection(self):
        fake, patched = self.use_routes({
            "https://example.test/audio": (200, {"Content-Type": "audio/mpeg"}, b"audio bytes"),
        })
        with tempfile.TemporaryDirectory() as directory, patched:
            path = helper.download_episode(
                api_base=BASE, token=TOKEN,
                detail={"id": "123", "download_url": "/audio"},
                output=str(Path(directory) / "episode.mp3"), allow_insecure_http=False,
            )
            self.assertEqual(path.read_bytes(), b"audio bytes")
            self.assert_exit(helper.EXIT_DOWNLOAD, lambda: helper.download_episode(
                api_base=BASE, token=TOKEN,
                detail={"id": "123", "download_url": "//other.test/audio"},
                output=str(Path(directory) / "rejected.mp3"), allow_insecure_http=False,
            ))
            self.assertFalse((Path(directory) / "rejected.mp3").exists())
        self.assertEqual(len(fake.seen), 1)

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
