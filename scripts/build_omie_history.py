import os
import io
import re
import json
import zipfile
from datetime import datetime, timedelta, timezone
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "public", "omie")
INDEX_FILE = os.path.join(OUTPUT_DIR, "index.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

DOWNLOAD_URL = "https://www.omie.es/es/file-download"


def iso_day(date_obj):
    return date_obj.strftime("%Y-%m-%d")


def ymd(date_obj):
    return date_obj.strftime("%Y%m%d")


def load_index():
    if not os.path.exists(INDEX_FILE):
        return {"days": []}
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_index(days):
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump({"days": sorted(days)}, f, ensure_ascii=False, indent=2)


def save_day_json(date_obj, rows):
    payload = {
        "date": iso_day(date_obj),
        "market": "OMIE Portugal day-ahead",
        "rows": rows
    }
    out_path = os.path.join(OUTPUT_DIR, f"{iso_day(date_obj)}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


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

    if not rows:
        raise ValueError(f"Sem dados válidos para {iso_day(date_obj)}")

    return rows


def download_file(filename):
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
    return res.content


def ensure_daily_file(date_obj, known_days):
    day_str = iso_day(date_obj)
    out_path = os.path.join(OUTPUT_DIR, f"{day_str}.json")

    if os.path.exists(out_path):
        known_days.add(day_str)
        return

    filename = f"marginalpdbcpt_{ymd(date_obj)}.1"
    raw = download_file(filename)
    text = raw.decode("latin-1", errors="ignore")
    rows = parse_omie_text(text, date_obj)
    save_day_json(date_obj, rows)
    known_days.add(day_str)
    print(f"OK daily {filename}")


def build_year_from_zip(year, known_days):
    zip_name = f"marginalpdbcpt_{year}.zip"
    raw = download_file(zip_name)

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".1")]

        if not members:
            raise ValueError(f"{zip_name} sem ficheiros .1")

        for member in members:
            base = os.path.basename(member)
            m = re.search(r"marginalpdbcpt_(\d{8})\.1$", base, re.IGNORECASE)
            if not m:
                continue

            date_obj = datetime.strptime(m.group(1), "%Y%m%d")
            day_str = iso_day(date_obj)
            out_path = os.path.join(OUTPUT_DIR, f"{day_str}.json")

            if os.path.exists(out_path):
                known_days.add(day_str)
                continue

            text = zf.read(member).decode("latin-1", errors="ignore")
            rows = parse_omie_text(text, date_obj)
            save_day_json(date_obj, rows)
            known_days.add(day_str)

        print(f"OK zip {zip_name}")


def build_range(start_date, end_date):
    known_days = set(load_index().get("days", []))
    current = start_date

    while current <= end_date:
        year = current.year

        if year in [2018, 2019, 2020, 2021, 2022]:
            build_year_from_zip(year, known_days)
            current = datetime(year + 1, 1, 1)
            continue

        ensure_daily_file(current, known_days)
        current += timedelta(days=1)

    save_index(known_days)
    print(f"Index atualizado com {len(known_days)} dias")


if __name__ == "__main__":
    start = os.getenv("START_DATE")
    end = os.getenv("END_DATE")

    if not start or not end:
        raise ValueError("Faltam START_DATE e END_DATE")

    start_date = datetime.fromisoformat(start)
    end_date = datetime.fromisoformat(end)
    build_range(start_date, end_date)
