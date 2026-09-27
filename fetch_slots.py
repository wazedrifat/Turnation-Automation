"""
Fetch available Turf Nation football slots for the next N weeks and export to CSV.

API quirk:
  - Request `date` must be midnight BDT expressed as UTC (e.g. 2026-08-12 00:00 BDT
    -> 2026-08-11T18:00:00.000Z).
  - Response times use a dummy date (1970-01-01); only the clock portion is meaningful.
    Those UTC clock values are converted to BDT for the CSV.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

SLOTS_URL = "https://admin.turfnationbd.com/api/appointments/available-slots"
PRICING_URL = "https://admin.turfnationbd.com/api/arenas/{arena_id}/pricing"
BDT = ZoneInfo("Asia/Dhaka")
UTC = timezone.utc

ARENAS = {
    "67619460992c39b4c6675735": "Turf A (5-A side)",
    "6761946a992c39b4c667573a": "Turf B (6-A side)",
}

CSV_FIELDS = ["date", "weekday", "time", "arena", "price"]

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://www.turfnationbd.com",
    "referer": "https://www.turfnationbd.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
    ),
}


def bdt_midnight_as_utc_iso(day: date) -> str:
    """Midnight BDT for `day`, serialized as UTC ISO (…T18:00:00.000Z previous calendar day)."""
    midnight_bdt = datetime.combine(day, time.min, tzinfo=BDT)
    return midnight_bdt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def slot_utc_to_bdt_time(slot_iso: str) -> time:
    """Take time-of-day from API (dummy 1970-01-01 UTC) and return BDT clock time."""
    slot_utc = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
    return slot_utc.astimezone(BDT).time()


def format_time_ampm(t: time) -> str:
    # %#I is Windows-only; strip leading zero manually for cross-platform.
    return t.strftime("%I:%M %p").lstrip("0")


def fetch_slots(session: requests.Session, arena_id: str, day: date, duration: int) -> list[str]:
    payload = {
        "arenaId": arena_id,
        "date": bdt_midnight_as_utc_iso(day),
        "duration": duration,
    }
    response = session.post(SLOTS_URL, headers=HEADERS, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError(f"Unexpected slots response for {arena_id} on {day}: {data!r}")
    return data


def fetch_price(
    session: requests.Session,
    arena_id: str,
    day: date,
    start_time_iso: str,
    duration: int,
) -> int | str:
    payload = {
        "duration": duration,
        "date": bdt_midnight_as_utc_iso(day),
        "startTime": start_time_iso,
    }
    url = PRICING_URL.format(arena_id=arena_id)
    response = session.post(url, headers=HEADERS, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or "price" not in data:
        raise ValueError(f"Unexpected pricing response for {arena_id} on {day}: {data!r}")
    return data["price"]


def daterange(start: date, days: int):
    for offset in range(days):
        yield start + timedelta(days=offset)


def export_slots(
    weeks: int = 3,
    duration: int = 90,
    output: Path | None = None,
    start: date | None = None,
) -> Path:
    start_day = start or datetime.now(BDT).date()
    total_days = weeks * 7
    out_path = output or Path(f"available_slots_{start_day.isoformat()}_{weeks}w.csv")

    rows: list[dict[str, str]] = []
    errors: list[str] = []

    with requests.Session() as session:
        for day in daterange(start_day, total_days):
            weekday = day.strftime("%a")  # Mon, Tue, Sat, ...
            for arena_id, arena_name in ARENAS.items():
                try:
                    slots = fetch_slots(session, arena_id, day, duration)
                except (requests.RequestException, ValueError) as exc:
                    errors.append(f"{day} | {arena_name} | slots: {exc}")
                    continue

                for slot_iso in slots:
                    local_time = slot_utc_to_bdt_time(slot_iso)
                    try:
                        price = fetch_price(session, arena_id, day, slot_iso, duration)
                    except (requests.RequestException, ValueError) as exc:
                        errors.append(f"{day} {format_time_ampm(local_time)} | {arena_name} | price: {exc}")
                        price = ""

                    rows.append(
                        {
                            "date": day.isoformat(),
                            "weekday": weekday,
                            "time": format_time_ampm(local_time),
                            "arena": arena_name,
                            "price": str(price),
                            "_sort_time": local_time.strftime("%H:%M"),
                        }
                    )

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
        default=3,
        help="How many next weeks to check (default: 3)",
    )
    parser.add_argument("--duration", type=int, default=90, help="Slot duration minutes (default: 90)")
    parser.add_argument(
        "--start",
        type=date.fromisoformat,
        default=None,
        help="Start date YYYY-MM-DD in BDT (default: today in BDT)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: available_slots_<start>_<weeks>w.csv)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    export_slots(weeks=args.weeks, duration=args.duration, output=args.output, start=args.start)
