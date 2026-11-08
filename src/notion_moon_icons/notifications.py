"""Best-effort KDE notifications for the moon icon service."""

import os
import subprocess
import sys


def notify(title, body, urgency="normal"):
    try:
        subprocess.run(
            [
                "/usr/bin/notify-send",
                "--app-name=Notion Moon Icons",
                "--icon=weather-clear-night",
                f"--urgency={urgency}",
                title,
                body,
            ],
            check=True,
            timeout=10,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(
            f"Desktop notification could not be delivered ({type(error).__name__}).",
            file=sys.stderr,
            flush=True,
        )


if __name__ == "__main__":
    result = os.environ.get("SERVICE_RESULT", "success")
    if "--failure" in sys.argv and result != "success":
        notify(
            "Moon icon update failed",
            f"Service result: {result}. Check journalctl --user -u moon-icons.service for details.",
            urgency="critical",
        )
