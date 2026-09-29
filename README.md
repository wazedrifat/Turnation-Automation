# Turfnation slots

Available football slots in Dhaka, refreshed every night at **00:00 BDT**.

## Live CSV

[available_slots_12w.csv](https://raw.githubusercontent.com/wazedrifat/Turnation-Automation/master/available_slots_12w.csv)

```
https://raw.githubusercontent.com/wazedrifat/Turnation-Automation/master/available_slots_12w.csv
```

## Drop it into Google Sheets

Paste this in `A1`:

```excel
=IMPORTDATA("https://raw.githubusercontent.com/wazedrifat/Turnation-Automation/master/available_slots_12w.csv")
```

Sheets may cache the file for up to about an hour. Use a Filter view (or a second sheet) if you want to sort — don’t edit the `IMPORTDATA` cells.

## Filters

Only **available** slots are stored. Narrow them further with `FILTERS` in `fetch_slots.py`. An empty `start_times` list keeps every available slot.

```python
# Match slot start times (BDT). Empty list = keep every available slot.
# Examples: ["8:30 PM"], ["8.30 PM", "10:00 PM"], ["20:30"]
FILTERS: dict[str, list[str]] = {
    "start_times": ["8.30 PM"],
}
```

The nightly CSV uses that default: **8:30 PM** kickoff only.

## Run it yourself

```bash
pip install -r requirements.txt
python fetch_slots.py          # 12 weeks
python fetch_slots.py -w 4     # fewer weeks
```
