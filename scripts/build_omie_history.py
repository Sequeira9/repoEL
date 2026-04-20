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


# 🔥 PARSER FINAL (SUPORTA 24h + 15min)
def parse_omie_text(text, date_obj):
    rows = []

    for line in text.splitlines():
        line = line.strip()

        if not line or line.startswith("*") or line.startswith("MARGINAL"):
            continue

        parts = line.split(";")

        if len(parts) < 6:
            continue

        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
            index = int(parts[3])
            price = float(parts[-2].replace(",", "."))
        except:
            continue

        # FORMATO ANTIGO (horas)
        if index <= 25:
            dt = datetime(year, month, day, tzinfo=timezone.utc)
            dt += timedelta(hours=index - 1)

        # FORMATO NOVO (15 min)
        else:
            dt = datetime(year, month, day, tzinfo=timezone.utc)
            dt += timedelta(minutes=(index - 1) * 15)

        rows.append({
            "x": int(dt.timestamp() * 1000),
            "price": price
        })

    if not rows:
        print(f"SKIP (sem dados): {iso_day(date_obj)}")
        return []

    return rows


def download_file(filename):
    params = {
        "filename": filename,
        "parents": "marginalpdbcpt",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
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

    try:
        raw = download_file(filename)
        text = raw.decode("latin-1", errors="ignore")
        rows = parse_omie_text(text, date_obj)

        if rows:
            save_day_json(date_obj, rows)
            known_days.add(day_str)
            print(f"OK daily {filename}")
        else:
            print(f"SKIP daily {filename}")

    except Exception as e:
        print(f"ERRO daily {filename}: {e}")


def build_year_from_zip(year, known_days):
    zip_name = f"marginalpdbcpt_{year}.zip"

    try:
        raw = download_file(zip_name)
    except:
        print(f"SKIP zip {zip_name}")
        return

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".1")]

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

            try:
                text = zf.read(member).decode("latin-1", errors="ignore")
                rows = parse_omie_text(text, date_obj)

                if rows:
                    save_day_json(date_obj, rows)
                    known_days.add(day_str)
                else:
                    print(f"SKIP zip day {day_str}")

            except Exception as e:
                print(f"ERRO zip {day_str}: {e}")

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
