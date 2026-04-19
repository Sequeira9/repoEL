# scripts/update_omie_pt.py
import os
import json
import re
from datetime import datetime, timedelta, timezone
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "public", "omie")
INDEX_FILE = os.path.join(OUTPUT_DIR, "index.json")

OMIE_DOWNLOAD_URL = "https://www.omie.es/es/file-download"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def format_ymd(date_obj):
    return date_obj.strftime("%Y%m%d")


def iso_day(date_obj):
    return date_obj.strftime("%Y-%m-%d")


def download_omie_text(date_obj):
    ymd = format_ymd(date_obj)
    filename = f"marginalpdbcpt_{ymd}.1"

    params = {
        "filename": filename,
        "parents": "marginalpdbcpt",
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/plain,*/*",
    }

    response = requests.get(OMIE_DOWNLOAD_URL, params=params, headers=headers, timeout=30)
    response.raise_for_status()

    text = response.text.strip()
    if not text:
        raise ValueError(f"Ficheiro OMIE vazio para {ymd}")

    return filename, text


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
            or "portugal" in lower
            or "precio" in lower
            or "price" in lower
        ):
            continue

        parts = re.split(r"[;\t,]+", line)
        parts = [p.strip() for p in parts if p.strip()]

        numeric = []
        for p in parts:
            p_norm = p.replace(",", ".")
            try:
                numeric.append(float(p_norm))
            except ValueError:
                pass

        if len(numeric) < 2:
            continue

        hour = int(numeric[0])
        price = float(numeric[-1])

        if hour < 1 or hour > 25:
            continue

        dt = datetime(date_obj.year, date_obj.month, date_obj.day, tzinfo=timezone.utc)
        dt = dt + timedelta(hours=hour - 1)

        rows.append({
            "x": int(dt.timestamp() * 1000),
            "hour": hour,
            "price": price
        })

    if not rows:
        raise ValueError(f"Não foi possível fazer parse do ficheiro para {iso_day(date_obj)}")

    return rows


def load_index():
    if not os.path.exists(INDEX_FILE):
        return {"days": []}

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_index(index_data):
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)


def save_day_json(date_obj, rows):
    day_str = iso_day(date_obj)
    out_path = os.path.join(OUTPUT_DIR, f"{day_str}.json")

    payload = {
        "date": day_str,
        "market": "OMIE Portugal day-ahead",
        "rows": rows
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return out_path


def ensure_days(days_back=120):
    index_data = load_index()
    existing_days = set(index_data.get("days", []))

    today = datetime.utcnow().date()
    updated_days = set(existing_days)

    for offset in range(days_back):
        day = today - timedelta(days=offset)
        day_dt = datetime(day.year, day.month, day.day)

        day_str = iso_day(day_dt)
        out_path = os.path.join(OUTPUT_DIR, f"{day_str}.json")

        if os.path.exists(out_path):
            updated_days.add(day_str)
            continue

        try:
            filename, text = download_omie_text(day_dt)
            rows = parse_omie_text(text, day_dt)
            save_day_json(day_dt, rows)
            updated_days.add(day_str)
            print(f"OK {filename}")
        except Exception as e:
            print(f"SKIP {day_str}: {e}")

    final_days = sorted(updated_days)
    save_index({"days": final_days})
    print(f"Index atualizado com {len(final_days)} dias")


if __name__ == "__main__":
    ensure_days(days_back=120)
