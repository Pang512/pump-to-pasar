"""
Download PriceCatcher monthly files plus the item and premise lookups.

Usage (run from the project root):
  python scripts/download_data.py 2024-01 2024-12   # a range of months, inclusive
  python scripts/download_data.py 2025-07           # a single month

What it downloads (into data/raw/):
  - lookup_item.parquet     item code -> name, unit, group, category
  - lookup_premise.parquet  premise code -> name, type, state, district
  - pricecatcher_YYYY-MM.parquet for each month requested

Source: OpenDOSM / data.gov.my, PriceCatcher (KPDN and DOSM), CC BY 4.0.
Re-running is safe: files that already exist are skipped.
"""

import sys
from pathlib import Path

import requests

BASE_URL = "https://storage.data.gov.my/pricecatcher"
RAW_DIR = Path("data/raw")


def month_range(start: str, end: str) -> list[str]:
    """'2024-01', '2024-03' -> ['2024-01', '2024-02', '2024-03']"""
    y, m = map(int, start.split("-"))
    end_y, end_m = map(int, end.split("-"))
    months = []
    while (y, m) <= (end_y, end_m):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def is_parquet(path: Path) -> bool:
    """A real Parquet file starts and ends with the 4 bytes 'PAR1'.
    Servers sometimes return an HTML error page instead, so we check."""
    with open(path, "rb") as f:
        head = f.read(4)
        f.seek(-4, 2)
        tail = f.read(4)
    return head == b"PAR1" and tail == b"PAR1"


def download(name: str) -> None:
    target = RAW_DIR / name
    if target.exists() and is_parquet(target):
        print(f"  skip     {name} (already downloaded)")
        return

    url = f"{BASE_URL}/{name}"
    tmp = target.with_suffix(".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MB at a time
                f.write(chunk)

    if not is_parquet(tmp):
        tmp.unlink()
        raise RuntimeError(f"{name}: downloaded file is not a valid Parquet file")

    tmp.replace(target)
    size_mb = target.stat().st_size / 1e6
    print(f"  ok       {name} ({size_mb:.1f} MB)")


def main() -> None:
    args = sys.argv[1:]
    if len(args) not in (1, 2):
        sys.exit("Usage: python scripts/download_data.py START_MONTH [END_MONTH]   e.g. 2024-01 2024-12")
    months = month_range(args[0], args[-1])

    files = ["lookup_item.parquet", "lookup_premise.parquet"] + [
        f"pricecatcher_{m}.parquet" for m in months
    ]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {len(files)} files into {RAW_DIR.resolve()}")
    for name in files:
        download(name)
    print("Done.")


if __name__ == "__main__":
    main()
