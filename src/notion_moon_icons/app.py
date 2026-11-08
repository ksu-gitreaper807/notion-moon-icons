"""Standalone Notion moon-icon updater. Requires NOTION_TOKEN and PIL."""

import os, json, math, datetime, pathlib, requests, re
from PIL import Image
from .notifications import notify

ROOT = os.environ.get("MOON_ROOT_PAGE_ID", "")
STATE = pathlib.Path(
    os.environ.get("MOON_STATE", "~/.local/share/moon-icons/state.json")
).expanduser()
API = "https://api.notion.com/v1"
H = {
    "Authorization": "Bearer " + os.environ.get("NOTION_TOKEN", ""),
    "Notion-Version": "2022-06-28",
}


def get(u):
    r = requests.get(API + u, headers=H, timeout=(10, 30))
    r.raise_for_status()
    return r.json()


def patch(u, b):
    r = requests.patch(
        API + u,
        headers={**H, "Content-Type": "application/json"},
        json=b,
        timeout=(10, 30),
    )
    r.raise_for_status()
    return r.json()


def children(i):
    out = []
    cur = None
    while True:
        u = f"/blocks/{i}/children?page_size=100" + (
            f"&start_cursor={cur}" if cur else ""
        )
        d = get(u)
        out += d["results"]
        if not d.get("has_more"):
            return out
        cur = d["next_cursor"]


def walk():
    q = [ROOT]
    out = []
    while q:
        bid = q.pop()
        for b in children(bid):
            if b.get("archived") or b.get("in_trash"):
                continue
            if b["type"] == "child_page":
                out.append(b)
                q.append(b["id"])
            elif b.get("has_children") and b["type"] not in (
                "synced_block",
                "child_database",
                "link_to_page",
            ):
                q.append(b["id"])
    return out


def phase(ts):
    d = ts / 86400000 - 0.5 + 2440588 - 2451545
    R = math.pi / 180
    O = R * 23.4397

    def c(l, b):
        return (
            math.atan2(
                math.sin(l) * math.cos(O) - math.tan(b) * math.sin(O), math.cos(l)
            ),
            math.asin(
                math.sin(b) * math.cos(O) + math.cos(b) * math.sin(O) * math.sin(l)
            ),
        )

    M = R * (357.5291 + 0.98560028 * d)
    sl = (
        M
        + R * (1.9148 * math.sin(M) + 0.02 * math.sin(2 * M) + 0.0003 * math.sin(3 * M))
        + R * 102.9372
        + math.pi
    )
    s = c(sl, 0)
    mm = R * (134.963 + 13.064993 * d)
    F = R * (93.272 + 13.22935 * d)
    m = c(
        R * (218.316 + 13.176396 * d) + R * 6.289 * math.sin(mm),
        R * 5.128 * math.sin(F),
    )
    a = math.acos(
        max(
            -1,
            min(
                1,
                math.sin(s[1]) * math.sin(m[1])
                + math.cos(s[1]) * math.cos(m[1]) * math.cos(s[0] - m[0]),
            ),
        )
    )
    inc = math.atan2(
        149598000 * math.sin(a), 385001 - 20905 * math.cos(mm) - 149598000 * math.cos(a)
    )
    ang = math.atan2(
        math.cos(s[1]) * math.sin(s[0] - m[0]),
        math.sin(s[1]) * math.cos(m[1])
        - math.cos(s[1]) * math.sin(m[1]) * math.cos(s[0] - m[0]),
    )
    return (0.5 + 0.5 * inc * (-1 if ang < 0 else 1) / math.pi, (1 + math.cos(inc)) / 2)


def render(day, path):
    ph, il = phase(
        datetime.datetime.fromisoformat(
            day + "T12:00:00" + os.environ.get("MOON_UTC_OFFSET", "+00:00")
        ).timestamp()
        * 1000
    )
    s = 320
    r = s * 0.47
    lz = 2 * il - 1
    lx = (1 if ph < 0.5 else -1) * math.sqrt(max(0, 1 - lz * lz))
    im = Image.new("RGBA", (s, s))
    px = im.load()
    for y in range(s):
        for x in range(s):
            nx = (x + 0.5 - s / 2) / r
            ny = (y + 0.5 - s / 2) / r
            q = nx * nx + ny * ny
            if q >= 1:
                continue
            z = math.sqrt(1 - q)
            dot = nx * lx + z * lz
            lit = max(0, min(1, dot / 0.015 + 0.5))
            v = round(
                24 + 8 * z + (195 + 32 * math.sqrt(max(0, dot)) - 24 - 8 * z) * lit
            )
            px[x, y] = (
                v,
                v,
                max(0, v - 3),
                round(255 * min(1, (1 - math.sqrt(q)) * r)),
            )
    im.save(path)


def entry_date(title):
    m = re.search(
        "\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+([A-Za-z]+)\\s+(\\d{4})\\b",
        title.replace(",", ""),
        re.IGNORECASE,
    )
    if not m:
        return None
    try:
        return (
            datetime.datetime.strptime(" ".join(m.groups()), "%d %B %Y")
            .date()
            .isoformat()
        )
    except ValueError:
        return None


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Assign dated moon icons to nested Notion journal pages."
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    parser.parse_args()
    if not ROOT or not os.environ.get("NOTION_TOKEN"):
        parser.error("Set NOTION_TOKEN and MOON_ROOT_PAGE_ID in the environment.")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {"processed": []}
    done = set(state["processed"])
    updated = 0
    skipped = 0
    for b in walk():
        if b["id"] in done:
            continue
        p = get("/pages/" + b["id"])
        title_items = p["properties"].get("title", {}).get("title", [])
        title = "".join((item.get("plain_text", "") for item in title_items))
        day = entry_date(title)
        if not day:
            skipped += 1
            continue
        fn = STATE.parent / f"moon-{day}-{b['id']}.png"
        render(day, fn)
        u = requests.post(
            API + "/file_uploads",
            headers={**H, "Content-Type": "application/json"},
            json={
                "mode": "single_part",
                "filename": fn.name,
                "content_type": "image/png",
            },
            timeout=(10, 30),
        )
        u.raise_for_status()
        up = u.json()
        send_headers = {
            k: v
            for k, v in up.get("upload_headers", {}).items()
            if k.lower() not in ("content-type", "content-length")
        }
        send_headers.update(
            {"Authorization": H["Authorization"], "Notion-Version": H["Notion-Version"]}
        )
        with fn.open("rb") as image_file:
            requests.post(
                up["upload_url"],
                headers=send_headers,
                files={"file": (fn.name, image_file, "image/png")},
                timeout=(10, 30),
            ).raise_for_status()
        patch(
            "/pages/" + b["id"],
            {"icon": {"type": "file_upload", "file_upload": {"id": up["id"]}}},
        )
        done.add(b["id"])
        state["processed"] = sorted(done)
        STATE.write_text(json.dumps(state, indent=2))
        fn.unlink(missing_ok=True)
        updated += 1
        print(f"Updated moon icon: {b['id']} ({day})", flush=True)
    print(
        f"Moon icons: {updated} updated; {skipped} unprocessed pages without a recognized date; {len(done)} processed total.",
        flush=True,
    )
    if updated:
        notify(
            "Notion moon icons updated",
            f"Updated {updated} journal {('entry' if updated == 1 else 'entries')} with moon icons.",
        )


if __name__ == "__main__":
    main()
