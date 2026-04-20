import os
import json
from datetime import datetime, timedelta
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


# PARSER
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
            dt = datetime(year, month, day)
            dt += timedelta(hours=index - 1)

        # FORMATO NOVO (15 min)
        else:
            dt = datetime(year, month, day)
            dt += timedelta(minutes=(index - 1) * 15)

        rows.append({
            "x": int(dt.timestamp() * 1000),
            "price": price
        })

    if not rows:
        print(f"SKIP (sem dados): {date_obj}")
        return []

    return rows


def run():
    known_days = set(load_index().get("days", []))

    # dia seguinte (day-ahead)
    target = datetime.utcnow().date() + timedelta(days=1)
    date_obj = datetime(target.year, target.month, target.day)
    day_str = iso_day(date_obj)
    out_path = os.path.join(OUTPUT_DIR, f"{day_str}.json")

    # já existe → não faz nada
    if os.path.exists(out_path):
        print(f"Já existe {day_str}")
        return

    filename = f"marginalpdbcpt_{date_obj.strftime('%Y%m%d')}.1"

    params = {
        "filename": filename,
        "parents": "marginalpdbcpt",
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
    }

    try:
        res = requests.get(DOWNLOAD_URL, params=params, headers=headers, timeout=60)
        res.raise_for_status()
    except Exception as e:
        print(f"ERRO download {filename}: {e}")
        return

    text = res.content.decode("latin-1", errors="ignore")
    rows = parse_omie_text(text, date_obj)

    # NÃO guardar ficheiros vazios
    if not rows:
        print(f"SKIP guardar {day_str}")
        return

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
