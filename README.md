# Notion Moon Icons

Generate moon-phase PNG icons for dated Notion journal pages. Run manually or every five hours with a Linux user systemd timer, with desktop notifications when icons change or a run fails.

## What it does

- Recursively discovers ordinary child pages beneath a configured Notion page, including pages inside columns and other block containers.
- Reads dates such as `23 October 2026` or `23rd October 2026` from page titles.
- Renders a transparent 320 × 320 moon icon for noon on that date and uploads it to Notion.
- Records successfully processed page IDs locally so subsequent runs leave those pages alone.
- Sends Linux desktop notifications for completed updates and, under systemd, failed runs. Runs without changes stay quiet.

The moon image is a smooth, approximate phase illustration, not a photograph or a scientific ephemeris. The calculation uses noon UTC by default; configure `MOON_UTC_OFFSET` to choose a different offset.

## Requirements

- Python 3.10 or newer.
- A Notion internal integration with access to the parent journal page, read/update content permissions, and permission to upload files.
- For scheduling: Linux with user systemd. For notifications: `notify-send` (typically provided by `libnotify` or `libnotify-bin`) and a running desktop notification service. Tested originally with KDE Plasma.

See Notion's guides to [creating an integration](https://www.notion.com/help/create-integrations-with-the-notion-api) and [connecting it to a page](https://www.notion.com/help/add-and-manage-connections-with-the-api). Each user supplies their own integration and credentials.

## Install and configure

The example systemd units expect the following checkout location:

```bash
mkdir -p ~/.local/share
git clone https://github.com/ksu-gitreaper807/notion-moon-icons.git ~/.local/share/notion-moon-icons
cd ~/.local/share/notion-moon-icons
python3 -m venv .venv
.venv/bin/python -m pip install .
cp .env.example .env
chmod 600 .env
```

Edit `.env` with your own token and root page ID. The ID is the 32 hexadecimal characters at the end of the root page's URL, with or without UUID hyphens; exclude any query string. Set `MOON_UTC_OFFSET` to a numeric offset such as `+00:00` or `-04:00`. This is a fixed offset and does not automatically follow daylight-saving changes.

To run once in Bash:

```bash
set -a
source .env
set +a
.venv/bin/notion-moon-icons
```

The program reads environment variables; it does not automatically load `.env`. systemd loads it through `EnvironmentFile` in the next step.

| Variable | Required | Default |
| --- | --- | --- |
| `NOTION_TOKEN` | Yes | None |
| `MOON_ROOT_PAGE_ID` | Yes | None |
| `MOON_UTC_OFFSET` | No | `+00:00` |
| `MOON_STATE` | No | `~/.local/share/moon-icons/state.json` |

**First run:** all dated pages beneath the root that are absent from the state file are eligible, including older pages and pages with existing icons. Their icons will be replaced. Choose a dedicated root or test page before enabling it on an existing journal. This version has no creation-date cutoff, date-title autofill, or icon backup/restore feature.

Successfully processed pages are skipped even if their titles or icons later change. Keep the state file when upgrading. Resetting or deleting it makes those pages eligible again. Avoid overlapping manual runs; systemd serializes its own service invocations.

## Check every five hours

After the first manual run succeeds:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/notion-moon-icons.service systemd/notion-moon-icons.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now notion-moon-icons.timer
```

The timer checks shortly after the user manager starts (normally at login), then five hours after the previous service start, with up to one minute of timer coalescing. Its interval pauses during suspend, and it does not wake the laptop. It needs internet access and runs independently of Notion and the browser. If you use another checkout location, adjust all paths in the service file before installing it.

```bash
# Check status and schedule
systemctl --user list-timers notion-moon-icons.timer

# Trigger a check manually
systemctl --user start notion-moon-icons.service

# Read results and errors
journalctl --user -u notion-moon-icons.service -n 30

# Disable scheduling
systemctl --user disable --now notion-moon-icons.timer
```

Notifications report the number of updated entries. A failed systemd run sends a critical notification with a pointer to its logs. HTTP requests have bounded connection/read timeouts; the service also has a ten-minute overall startup timeout. Notification delivery failures are logged without failing the updater. Desktop Do Not Disturb settings still apply, and a graphical session is needed for visible desktop notifications.

## Troubleshooting

- **Unauthorized or forbidden:** verify the token, integration capabilities, and connection to the root page. A token alone does not grant access to every page.
- **No matching dates:** use an English full month name with a day and four-digit year, optionally including an ordinal suffix. Titles are interpreted using Python's default English date locale.
- **No pages discovered:** this version walks ordinary child pages. It intentionally skips child databases, synced blocks, and page links.
- **Timeout or rate limit:** inspect the service log and retry when connectivity or API capacity recovers. Requests are not automatically retried. Successful icon updates are saved after each page, so the next run resumes from the state file.
- **No notification:** check that `notify-send` is installed, a desktop notification service is running, and Do Not Disturb is off. Direct command-line failures appear in the terminal; failure notifications are provided by the supplied systemd service.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

Tests use synthetic pages and temporary state. They do not use a real Notion token, contact Notion, or send desktop notifications. An example GitHub Actions workflow in `examples/github-actions-tests.yml` runs the same tests on Python 3.10 and 3.14. To enable it, copy it to `.github/workflows/tests.yml` and push with GitHub credentials that allow workflow changes. Passing these tests validates local behavior against controlled responses, not current Notion availability.

## Privacy and license

Your integration token is sent only to Notion's API and its file-upload endpoint. Journal page titles are read to select dates; page IDs and dates appear in local logs, and processed IDs are stored in the local state file. There is no application telemetry. `.env`, runtime state, logs, generated images, and virtual environments are excluded from Git.

MIT licensed; see [LICENSE](LICENSE).
