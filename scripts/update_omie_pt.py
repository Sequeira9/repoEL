import os
import json
import re
import time
from datetime import datetime, timedelta, timezone
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "public", "omie")
INDEX_FILE = os.path.join(OUTPUT_DIR, "index.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def iso_day(date_obj):
    return date_obj.strftime("%Y-%m-%d")


def load_index():
    if not os.path.exists(INDEX_FILE):
        return {"days": []}
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_index(index_data):
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)


def download_omie_text(date_obj):
    ymd = date_obj.strftime("%Y%m%d")
    filename = f"marginalpdbcpt_{ymd}.1"
    url = f"https://www.omie.es/es/file-download?filename={filename}&parents=marginalpdbcpt"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Connection": "keep-alive",
    }

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise Exception(f"HTTP {response.status_code}")

    text = response.text.strip()

    if not text or len(text) < 50:
        raise Exception("Conteúdo OMIE vazio ou inválido")

    return text


def parse_omie(text, date_obj):
    rows = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        lower = line.lower()
        if (
            lower.startswith("*")
            or lower.startswith("#")
            or "date" in lower
            or "fecha" in lower
            or "precio" in lower
            or "price" in lower
            or "portugal" in lower
        ):
            continue

        parts = re.split(r"[;\t,]+", line)
        nums = []

        for p in parts:
            try:
                nums.append(float(p.replace(",", ".")))
            except Exception:
                pass

        if len(nums) < 2:
            continue

        hour = int(nums[0])
        price = nums[-1]

        if hour < 1 or hour > 25:
            continue

        dt = datetime(date_obj.year, date_obj.month, date_obj.day, tzinfo=timezone.utc)
        dt += timedelta(hours=hour - 1)

        rows.append({
            "x": int(dt.timestamp() * 1000),
            "price": price
        })

    if not rows:
        raise Exception("Sem linhas válidas após parse")

    return rows


def ensure_range(start_date, end_date):
    index = load_index()
    existing = set(index.get("days", []))
    updated = set(existing)

    current = start_date

    while current <= end_date:
        day_str = iso_day(current)
        out_path = os.path.join(OUTPUT_DIR, f"{day_str}.json")

        if os.path.exists(out_path):
            updated.add(day_str)
            current += timedelta(days=1)
            continue

        try:
            text = download_omie_text(current)
            rows = parse_omie(text, current)

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "date": day_str,
                        "market": "OMIE Portugal day-ahead",
                        "rows": rows
                    },
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            updated.add(day_str)
            print(f"OK {day_str}")
            time.sleep(0.5)

        except Exception as e:
            print(f"SKIP {day_str}: {e}")

        current += timedelta(days=1)

    save_index({"days": sorted(updated)})


if __name__ == "__main__":
    start = os.getenv("START_DATE")
    end = os.getenv("END_DATE")

    if start and end:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
        ensure_range(start_date, end_date)
    else:
        today = datetime.utcnow().date()
        start_date = today - timedelta(days=7)
        ensure_range(
            datetime(start_date.year, start_date.month, start_date.day),
            datetime(today.year, today.month, today.day),
        )
