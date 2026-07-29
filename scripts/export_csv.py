#!/usr/bin/env python3
"""将 hr_analytics_demo.db 全表导出为 CSV，便于 Power BI 无 SQLite 连接器时导入。"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "hr_analytics_demo.db"
OUT = ROOT / "data" / "csv"


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"数据库不存在，请先运行 generate_hr_sqlite.py: {DB}")
    OUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    for t in tables:
        cur = conn.execute(f"SELECT * FROM {t}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        path = OUT / f"{t}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        print(f"{t:20s} {len(rows):7d} rows → {path.relative_to(ROOT)}")
    conn.close()
    print(f"\n完成：{OUT}")


if __name__ == "__main__":
    main()
