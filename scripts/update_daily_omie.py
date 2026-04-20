import os
import json
import re
from datetime import datetime, timedelta, timezone
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "public", "omie")
INDEX_FILE = os.path.join(OUTPUT_DIR, "index.json")
DOWNLOAD_URL = "https://www.omie.es/es/file-download"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def iso_day(date_obj):
    return date_obj.strftime("%Y-%m-%d")


def load_index():
    if not os.path.exists(INDEX_FILE):
        return {"days": []}
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_index(days):
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump({"days": sorted(days)}, f, ensure_ascii=False, indent=2)


def parse_omie_text(text, date_obj):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows = []

    for line in lines:
        lower = line.lower()
        if (
            lower.startswith("*")
            or lower.startswith("#")
            or "fecha" in lower
            or "date" in lower
            or "precio" in lower
            or "price" in lower
            or "portugal" in lower
        ):
            continue

        parts = re.split(r"[;\t,]+", line)
        parts = [p.strip() for p in parts if p.strip()]

        numeric = []
        for p in parts:
            try:
                numeric.append(float(p.replace(",", ".")))
            except ValueError:
                pass

        if len(numeric) < 2:
            continue

        hour = int(numeric[0])
        price = float(numeric[-1])

        if hour < 1 or hour > 25:
            continue

        dt = datetime(date_obj.year, date_obj.month, date_obj.day, tzinfo=timezone.utc)
        dt += timedelta(hours=hour - 1)

        rows.append({
            "x": int(dt.timestamp() * 1000),
            "hour": hour,
            "price": price
        })

    return rows


def run():
    known_days = set(load_index().get("days", []))

    target = datetime.utcnow().date() + timedelta(days=1)
    date_obj = datetime(target.year, target.month, target.day)
    day_str = iso_day(date_obj)
    out_path = os.path.join(OUTPUT_DIR, f"{day_str}.json")

    if os.path.exists(out_path):
        print(f"Já existe {day_str}")
        return

    ymd = date_obj.strftime("%Y%m%d")
    filename = f"marginalpdbcpt_{ymd}.1"

    params = {
        "filename": filename,
        "parents": "marginalpdbcpt",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Connection": "keep-alive",
    }

    res = requests.get(DOWNLOAD_URL, params=params, headers=headers, timeout=60)
    res.raise_for_status()

    text = res.content.decode("latin-1", errors="ignore")
    rows = parse_omie_text(text, date_obj)

    payload = {
        "date": day_str,
        "market": "OMIE Portugal day-ahead",
        "rows": rows
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    known_days.add(day_str)
    save_index(known_days)
    print(f"OK novo dia {day_str}")


if __name__ == "__main__":
    run()
