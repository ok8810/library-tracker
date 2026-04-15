"""
export_loans.py
GitHub Actions から呼び出す専用スクリプト。
scraper.py の fetch_all() を実行し、結果を loans.json に書き出す。
"""
import json
from datetime import datetime, timezone
from scraper import fetch_all

def main():
    print("貸出・予約情報を取得中...")
    data = fetch_all()

    payload = {
        "updated_at":   datetime.now(timezone.utc).isoformat(),
        "loans":        data["loans"],
        "reservations": data["reservations"],
    }

    with open("loans.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ loans.json を書き出しました（貸出{len(data['loans'])}件 / 予約{len(data['reservations'])}件）")

if __name__ == "__main__":
    main()
