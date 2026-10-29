"""
Step 1a: download the PriceCatcher sample for the feasibility check.

What it downloads (into data/raw/):
  - lookup_item.parquet     item code -> name, unit, group, category
  - lookup_premise.parquet  premise code -> name, type, state, district
  - pricecatcher_YYYY-MM.parquet for April to September 2025
    (3 months before and 3 months after the 1 July 2025 SST change)

Source: OpenDOSM / data.gov.my, PriceCatcher (KPDN and DOSM), CC BY 4.0.
Run from the project root:  python scripts/download_data.py
Re-running is safe: files that already exist are skipped.
"""

from pathlib import Path

import requests

BASE_URL = "https://storage.data.gov.my/pricecatcher"
RAW_DIR = Path("data/raw")

# Months to download for the feasibility sample.
MONTHS = ["2025-04", "2025-05", "2025-06", "2025-07", "2025-08", "2025-09"]

FILES = ["lookup_item.parquet", "lookup_premise.parquet"] + [
    f"pricecatcher_{m}.parquet" for m in MONTHS
]


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
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {len(FILES)} files into {RAW_DIR.resolve()}")
    for name in FILES:
        download(name)
    print("Done.")


if __name__ == "__main__":
    main()
