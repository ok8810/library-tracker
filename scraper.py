import json
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, NavigableString

BASE_URL  = "https://webopac.city.minoh.osaka.jp/opw/OPW"
LOGIN_URL = f"{BASE_URL}/OPWUSERCONF.CSP?DB=LIB&MODE=1&PREPID=OPWMAIN&NEXTPID=OPWMAIN&HEADFLG=1"

def _login(member: dict, page):
    """ログイン処理"""
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.locator("input[name='usercardno']").fill(member["user_id"])
    page.locator("input[name='userpasswd']").fill(member["password"])
    page.locator("input[type='submit'], button[type='submit']").first.click()
    page.wait_for_load_state("networkidle")

def get_loans(member: dict, page) -> list[dict]:
    """1人分の貸出情報を取得する"""
    loans = []
    current_page = 1
    max_pages = 2

    while current_page <= max_pages:
        url = (f"{BASE_URL}/OPWUSERINFO.CSP?DB=LIB&MODE=1"
               f"&active=lend&SORTTYPE=1&LENDSORTTYPE=2&PAGE={current_page}")
        page.goto(url)
        page.wait_for_load_state("networkidle")

        soup = BeautifulSoup(page.content(), "html.parser")
        rows = soup.find_all("tr", class_=["lightcolor", "basecolor"])
        if not rows:
            break

        found = 0
        seen = set()
        for row in rows:
            tds = row.find_all("td")
            if len(tds) != 7:
                continue
            title_tag = tds[1].find("a")
            if not title_tag:
                continue

            # セル内の全テキストノードを結合してタイトルを取得する
            # （<a>の外にサブタイトルが複数ノードで分散していても全量取得できる）
            title = " ".join(tds[1].get_text(" ", strip=True).split())

            due_text = tds[4].get_text(strip=True)
            try:
                due_date = datetime.strptime(due_text, "%Y/%m/%d")
            except ValueError:
                continue

            key = f"{title}_{due_text}"
            if key in seen:
                continue
            seen.add(key)

            loans.append({
                "member":       member["name"],
                "title":        title,
                "due_date":     due_text,
                "due_date_obj": due_date,
            })
            found += 1

        print(f"  [貸出] {member['name']} {current_page}ページ目: {found}件")

        next_link = soup.find("a", href=lambda h: h and f"PAGE={current_page + 1}" in h)
        if not next_link:
            break
        current_page += 1

    return loans


def get_reservations(member: dict, page) -> list[dict]:
    """1人分の予約情報を取得する（予約は常に1ページに収まるためページ遷移なし）"""
    reservations = []

    url = f"{BASE_URL}/OPWUSERINFO.CSP?DB=LIB&MODE=1&active=rsv&PAGE=1"
    page.goto(url)
    page.wait_for_load_state("networkidle")

    soup = BeautifulSoup(page.content(), "html.parser")
    rows = soup.find_all("tr", class_=["lightcolor", "basecolor"])

    for row in rows:
        tds = row.find_all("td")
        if len(tds) != 10:
            continue

        status    = tds[1].get_text(strip=True)
        queue_rank      = tds[2].get_text(strip=True)   # 順位（例："5 / 7"、空欄あり）
        title_tag = tds[3].find("a")
        title     = title_tag.get_text(strip=True) if title_tag else tds[3].get_text(strip=True)

        # タイトル後のサブタイトル補完
        if title_tag:
            next_text = title_tag.next_sibling
            if next_text and isinstance(next_text, str):
                extra = next_text.strip().split('[')[0].strip()
                if extra:
                    title = f"{title} {extra}"

        pickup_deadline = tds[6].get_text(strip=True)  # 取り置き期限（空欄あり）

        # td[0] が数字（予約番号）の行だけを対象にする
        if not tds[0].get_text(strip=True).isdigit():
            continue

        if not title or not status:
            continue

        reservations.append({
            "member":          member["name"],
            "title":           title,
            "status":          status,
            "queue_rank":      queue_rank,
            "pickup_deadline": pickup_deadline,
            "sort_order":      {"準備できました": 0, "移送中": 1}.get(status, 99),
        })

    print(f"  [予約] {member['name']}: {len(reservations)}件")
    return reservations


def fetch_all(config_path: str = "config.json") -> dict:
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    all_loans        = []
    all_reservations = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for member in config["members"]:
            page = browser.new_page()
            try:
                _login(member, page)
                loans = get_loans(member, page)
                all_loans.extend(loans)

                reservations = get_reservations(member, page)
                all_reservations.extend(reservations)

                print(f"✅ {member['name']}: 貸出{len(loans)}件 / 予約{len(reservations)}件")
            except Exception as e:
                print(f"❌ {member['name']}: エラー - {e}")
            finally:
                page.close()
        browser.close()
        
    # 貸出：重複除去（member + title + due_date が同じものを除外）→ 返却期限順
    seen_loans = set()
    unique_loans = []
    for loan in all_loans:
        key = (loan["member"], loan["title"], loan["due_date"])
        if key not in seen_loans:
            seen_loans.add(key)
            unique_loans.append(loan)
    unique_loans.sort(key=lambda x: x["due_date_obj"])
    for loan in unique_loans:
        del loan["due_date_obj"]
    all_loans = unique_loans

    # 予約：重複除去（member + title + status が同じものを除外）→ ステータス優先度順
    seen_rsvs = set()
    unique_rsvs = []
    for rsv in all_reservations:
        key = (rsv["member"], rsv["title"], rsv["status"])
        if key not in seen_rsvs:
            seen_rsvs.add(key)
            unique_rsvs.append(rsv)
    unique_rsvs.sort(key=lambda x: (
        x["sort_order"],
        x["pickup_deadline"] if x["pickup_deadline"] else "9999"
    ))
    for rsv in unique_rsvs:
        del rsv["sort_order"]
    all_reservations = unique_rsvs

    return {
        "loans":        all_loans,
        "reservations": all_reservations,
    }


# 後方互換：scraper単体実行・旧export_loans.pyからの呼び出し用
def fetch_all_loans(config_path: str = "config.json") -> list[dict]:
    return fetch_all(config_path)["loans"]


if __name__ == "__main__":
    result = fetch_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))
