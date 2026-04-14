"""
export_loans.py
GitHub Actions から呼び出す専用スクリプト。
scraper.py の fetch_all_loans() を実行し、結果を loans.json に書き出す。
"""
import json
from datetime import datetime, timezone
from scraper import fetch_all_loans

def main():
    print("貸出情報を取得中...")
    loans = fetch_all_loans()

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "loans": loans,
    }

    with open("loans.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ loans.json を書き出しました（{len(loans)} 件）")

if __name__ == "__main__":
    main()
