import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from notion_moon_icons import app, notifications


class DateAndImageTests(unittest.TestCase):
    def test_plain_ordinal_and_invalid_titles(self):
        for title in ("23 October 2026", "23rd October 2026", "23RD october, 2026"):
            with self.subTest(title=title):
                self.assertEqual(app.entry_date(title), "2026-10-23")
        for title in ("31 February 2026", "Journal", "123 October 2026"):
            self.assertIsNone(app.entry_date(title))

    def test_render_produces_transparent_png(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "moon.png"
            with patch.dict(os.environ, {"MOON_UTC_OFFSET": "+00:00"}):
                app.render("2026-10-23", path)
            with Image.open(path) as image:
                self.assertEqual(image.size, (320, 320))
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.getpixel((0, 0))[3], 0)
                self.assertEqual(image.getpixel((160, 160))[3], 255)


class ProcessingTests(unittest.TestCase):
    def test_pagination(self):
        with patch.object(
            app,
            "get",
            side_effect=[
                {"results": [{"id": "first"}], "has_more": True, "next_cursor": "next"},
                {"results": [{"id": "second"}], "has_more": False},
            ],
        ) as get:
            self.assertEqual(app.children("root"), [{"id": "first"}, {"id": "second"}])
            self.assertIn("start_cursor=next", get.call_args.args[0])

    def test_success_is_saved_repeat_run_is_quiet_and_failed_upload_is_not_saved(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                state = Path(directory) / "state.json"
                response = Mock()
                response.json.return_value = {
                    "id": "upload",
                    "upload_url": "https://example.invalid/upload",
                }
                if fail:
                    response.raise_for_status.side_effect = app.requests.HTTPError(
                        "Synthetic upload failure"
                    )
                with (
                    patch.dict(os.environ, {"NOTION_TOKEN": "synthetic-test-value"}),
                    patch.object(app, "ROOT", "synthetic-root"),
                    patch.object(app, "STATE", state),
                    patch.object(app, "walk", return_value=[{"id": "synthetic-entry"}]),
                    patch.object(
                        app,
                        "get",
                        return_value={
                            "properties": {
                                "title": {
                                    "title": [
                                        {"plain_text": "23 "},
                                        {"plain_text": "October 2026"},
                                    ]
                                }
                            }
                        },
                    ) as get,
                    patch.object(
                        app,
                        "render",
                        side_effect=lambda day, path: path.write_bytes(b"png"),
                    ),
                    patch.object(app.requests, "post", return_value=response),
                    patch.object(app, "patch") as update,
                    patch.object(app, "notify") as notify,
                    patch("sys.argv", ["notion-moon-icons"]),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    if fail:
                        with self.assertRaises(app.requests.HTTPError):
                            app.main()
                        self.assertFalse(state.exists())
                        update.assert_not_called()
                        notify.assert_not_called()
                    else:
                        app.main()
                        self.assertEqual(
                            json.loads(state.read_text())["processed"],
                            ["synthetic-entry"],
                        )
                        update.assert_called_once()
                        notify.assert_called_once()
                        notify.reset_mock()
                        app.main()
                        self.assertEqual(get.call_count, 1)
                        notify.assert_not_called()

    def test_missing_configuration_fails_before_network(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(app, "ROOT", ""),
            patch.object(app, "walk") as walk,
            patch("sys.argv", ["notion-moon-icons"]),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as result:
                app.main()
            self.assertEqual(result.exception.code, 2)
            walk.assert_not_called()


class NotificationTests(unittest.TestCase):
    def test_delivery_failure_is_nonfatal(self):
        with (
            patch.object(
                notifications.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("notify-send", 10),
            ),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            notifications.notify("Test", "Synthetic notification")

    def test_service_failure_notifies_and_success_is_quiet(self):
        for result in ("success", "exit-code", "timeout"):
            with (
                self.subTest(result=result),
                patch.dict(os.environ, {"SERVICE_RESULT": result}),
                patch("sys.argv", ["notifications", "--failure"]),
                patch("subprocess.run") as send,
            ):
                runpy.run_path(str(Path(notifications.__file__)), run_name="__main__")
                self.assertEqual(send.call_count, 0 if result == "success" else 1)
                if result != "success":
                    self.assertIn("--urgency=critical", send.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
