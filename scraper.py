import json
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import NavigableString

BASE_URL = "https://webopac.city.minoh.osaka.jp/opw/OPW"
LOGIN_URL = f"{BASE_URL}/OPWUSERCONF.CSP?DB=LIB&MODE=1&PREPID=OPWMAIN&NEXTPID=OPWMAIN&HEADFLG=1"
LEND_URL  = f"{BASE_URL}/OPWUSERINFO.CSP?DB=LIB&PID=OPWUSERINFO&MODE=1&active=lend&SORTTYPE=1&LENDSORTTYPE=2"

def login_and_get_loans(member: dict, page) -> list[dict]:
    """1人分のアカウントでログインして貸出情報を取得する"""
    from bs4 import BeautifulSoup

    # ログインページを開く
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")

    # 利用者番号と暗証番号を入力
    page.locator("input[name='usercardno']").fill(member["user_id"])
    page.locator("input[name='userpasswd']").fill(member["password"])

    # ログインボタンをクリック
    page.locator("input[type='submit'], button[type='submit']").first.click()
    page.wait_for_load_state("networkidle")

    loans = []
    current_page = 1
    max_pages = 2  # 無限ループ防止

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
        seen_titles = set()  # このページ内の重複タイトルを除外
        for row in rows:
            tds = row.find_all("td")
            if len(tds) != 7:
                continue
            title_tag = tds[1].find("a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            next_text = title_tag.next_sibling
            if next_text and isinstance(next_text, str):
                extra = next_text.strip().split('[')[0].strip()
                if extra:
                    title = f"{title} {extra}"

            due_text = tds[4].get_text(strip=True)
            try:
                due_date = datetime.strptime(due_text, "%Y/%m/%d")
            except ValueError:
                continue

            # タイトル＋期限の組み合わせで重複チェック
            key = f"{title}_{due_text}"
            if key in seen_titles:
                continue
            seen_titles.add(key)

            loans.append({
                "member": member["name"],
                "title": title,
                "due_date": due_text,
                "due_date_obj": due_date,
            })
            found += 1

        print(f"  {member['name']} {current_page}ページ目: {found}件")

        # 次ページリンク確認
        next_link = soup.find("a", href=lambda h: h and f"PAGE={current_page + 1}" in h)
        if not next_link:
            break

        current_page += 1

    return loans

def fetch_all_loans(config_path: str = "config.json") -> list[dict]:
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    all_loans = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        for member in config["members"]:
            page = browser.new_page()
            try:
                loans = login_and_get_loans(member, page)
                all_loans.extend(loans)
                print(f"✅ {member['name']}: {len(loans)}件取得")
            except Exception as e:
                print(f"❌ {member['name']}: エラー - {e}")
            finally:
                page.close()
        browser.close()

    all_loans.sort(key=lambda x: x["due_date_obj"])
    for loan in all_loans:
        del loan["due_date_obj"]

    return all_loans


if __name__ == "__main__":
    loans = fetch_all_loans()
    print(json.dumps(loans, ensure_ascii=False, indent=2))
