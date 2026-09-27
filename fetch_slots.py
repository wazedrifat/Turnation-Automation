"""
Fetch available Turf Nation football slots for the next N weeks and export to CSV.

GET https://turfnationbd.com/api/turfnation/slots?fieldId=<id>&date=YYYY-MM-DD
Times from the API are treated as Asia/Dhaka (BDT). Only available slots are stored.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

SLOTS_URL = "https://turfnationbd.com/api/turfnation/slots"
BDT = ZoneInfo("Asia/Dhaka")

FIELDS = {
    "187fe9ea-426a-49b4-a44b-d7e65d25b44e": "Turfnation A (5-a side)",
    "3a42c6bf-e3d2-4dab-93d7-d7f7ad8c6566": "Turfnation B (6-a side)",
}

CSV_FIELDS = ["date", "weekday", "time", "arena", "price"]

# Match slot start times (BDT). Empty list = keep every available slot.
# Examples: ["8:30 PM"], ["8.30 PM", "10:00 PM"], ["20:30"]
FILTERS: dict[str, list[str]] = {
    "start_times": ["8.30 PM"],
}

HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://turfnationbd.com",
    "referer": "https://turfnationbd.com/booking",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
    ),
}


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute), tzinfo=BDT)


def parse_filter_time(value: str) -> time:
    """Parse '8:30 PM', '8.30 PM', or '20:30' into a BDT clock time."""
    raw = value.strip().upper().replace(".", ":")
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt).time()
            return time(parsed.hour, parsed.minute, tzinfo=BDT)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized filter time: {value!r}")


def allowed_start_times() -> set[time] | None:
    values = FILTERS.get("start_times") or []
    if not values:
        return None
    return {parse_filter_time(item) for item in values}


def format_time_ampm(t: time) -> str:
    # %#I is Windows-only; strip leading zero manually for cross-platform.
    return t.strftime("%I:%M %p").lstrip("0")


def fetch_slots(session: requests.Session, field_id: str, day: date) -> list[dict]:
    response = session.get(
        SLOTS_URL,
        headers=HEADERS,
        params={"fieldId": field_id, "date": day.isoformat()},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or "data" not in payload:
        raise ValueError(f"Unexpected slots response for {field_id} on {day}: {payload!r}")
    data = payload["data"]
    if not isinstance(data, list):
        raise ValueError(f"Unexpected slots data for {field_id} on {day}: {data!r}")
    return data


def daterange(start: date, days: int):
    for offset in range(days):
        yield start + timedelta(days=offset)


def print_progress(current: int, total: int, day: date, width: int = 32) -> None:
    filled = int(width * current / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    pct = int(100 * current / total) if total else 100
    label = f"{day.isoformat()} {day.strftime('%a')}"
    print(f"\r{label}  [{bar}] {current}/{total} ({pct}%)", end="", flush=True)


def export_slots(
    weeks: int = 12,
    output: Path | None = None,
    start: date | None = None,
) -> Path:
    start_day = start or datetime.now(BDT).date()
    total_days = weeks * 7
    out_path = output or Path(f"available_slots_{weeks}w.csv")
    wanted_times = allowed_start_times()

    rows: list[dict[str, str]] = []
    errors: list[str] = []

    with requests.Session() as session:
        for index, day in enumerate(daterange(start_day, total_days), start=1):
            print_progress(index, total_days, day)
            weekday = day.strftime("%a")
            for field_id, field_name in FIELDS.items():
                try:
                    slots = fetch_slots(session, field_id, day)
                except (requests.RequestException, ValueError) as exc:
                    errors.append(f"{day} | {field_name} | slots: {exc}")
                    continue

                for slot in slots:
                    if not slot.get("available"):
                        continue

                    start_local = parse_hhmm(slot["startTime"])
                    if wanted_times is not None and start_local not in wanted_times:
                        continue
                    rows.append(
                        {
                            "date": day.isoformat(),
                            "weekday": weekday,
                            "time": format_time_ampm(start_local),
                            "arena": field_name,
                            "price": str(slot.get("price", "")),
                            "_sort_time": start_local.strftime("%H:%M"),
                        }
                    )

    print()

    rows.sort(key=lambda r: (r["date"], r["_sort_time"], r["arena"]))
    for row in rows:
        row.pop("_sort_time", None)

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} slots -> {out_path.resolve()}")
    if errors:
        print(f"\n{len(errors)} request(s) failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)

    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Turf Nation available slots to CSV")
    parser.add_argument(
        "-w",
        "--weeks",
        type=int,
        default=12,
        help="How many next weeks to check (default: 12)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    export_slots(weeks=args.weeks)
