"""
Monitor คิวหลุด ร้านมหาสาร (Aroided)
- เปิดหน้า available-bookings ด้วย headless Chromium (หน้าเว็บโหลดคิวด้วย JS)
- ดึงรายการคิวที่แสดงอยู่ + JSON ที่หน้าเว็บโหลดมา
- เทียบกับรอบก่อน ถ้ามีคิวใหม่โผล่ → แจ้งเตือน (ntfy / Telegram)

ใช้งาน:
  python monitor.py            # เช็ก 1 รอบ (ใช้กับ GitHub Actions / cron)
  python monitor.py --loop 180 # เช็กวนทุก 180 วินาที (รันบนเครื่องตัวเอง)
  python monitor.py --discover # บันทึก API ที่หน้าเว็บเรียก + screenshot ไว้ดูโครงสร้าง
"""
import argparse, hashlib, json, os, re, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = os.getenv(
    "BOOKING_URL",
    "https://aroided.aroided.com/available-bookings?res=2c1290e0-748b-41b0-9a24-a1018c178060",
)
STATE = Path(os.getenv("STATE_FILE", "state/snapshot.json"))
DEBUG_DIR = Path("debug")
BKK = timezone(timedelta(hours=7))

# บรรทัดที่ดูเหมือน "คิว" — มีเวลา (18:00 / 18.00) หรือวันที่
TIME_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b")
DATE_RE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b|"
    r"(ม\.ค\.|ก\.พ\.|มี\.ค\.|เม\.ย\.|พ\.ค\.|มิ\.ย\.|ก\.ค\.|ส\.ค\.|ก\.ย\.|ต\.ค\.|พ\.ย\.|ธ\.ค\.|"
    r"มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม|"
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
)
# ข้อความที่บอกว่า "ไม่มีคิว" — ถ้าเจอบรรทัดนี้จะไม่นับเป็นคิว
EMPTY_HINTS = ("ไม่มี", "เต็ม", "no available", "sold out", "fully booked")


SESSION = STATE.parent / "session.json"  # เก็บ cookie ล็อกอินไว้ใช้รอบถัดไป


class LoginError(Exception):
    pass


def needs_login(page):
    return page.locator("input[type=password]:visible").count() > 0


def do_login(page):
    email, password = os.getenv("AROIDED_EMAIL"), os.getenv("AROIDED_PASSWORD")
    if not (email and password):
        raise LoginError("หน้าเว็บต้องล็อกอิน แต่ยังไม่ได้ใส่ AROIDED_EMAIL / AROIDED_PASSWORD ใน Secrets")

    email_box = page.locator(
        "input[type=email]:visible, input[name*=mail i]:visible, input[id*=mail i]:visible, "
        "input[name*=user i]:visible, input[type=text]:visible"
    ).first
    email_box.fill(email)
    page.locator("input[type=password]:visible").first.fill(password)

    submit = page.locator(
        "button[type=submit]:visible, input[type=submit]:visible, "
        "button:visible:has-text('เข้าสู่ระบบ'), button:visible:has-text('Login'), "
        "button:visible:has-text('Log in'), button:visible:has-text('Sign in')"
    ).first
    if submit.count():
        submit.click()
    else:
        page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle", timeout=60_000)
    page.wait_for_timeout(3000)


def scrape(discover=False):
    json_payloads = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            locale="th-TH", viewport={"width": 430, "height": 2000},
            storage_state=str(SESSION) if SESSION.exists() else None,
        )
        page = ctx.new_page()

        def on_response(resp):
            try:
                if "json" in (resp.headers.get("content-type") or ""):
                    json_payloads.append({"url": resp.url, "status": resp.status, "body": resp.json()})
            except Exception:
                pass

        page.on("response", on_response)

        def snap(name):
            if discover:
                DEBUG_DIR.mkdir(exist_ok=True)
                page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)

        try:
            page.goto(URL, wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(3000)
            if needs_login(page):
                snap("login-page")
                do_login(page)
                json_payloads.clear()
                page.goto(URL, wait_until="networkidle", timeout=60_000)
                page.wait_for_timeout(3000)
                if needs_login(page):
                    snap("login-failed")
                    raise LoginError("ล็อกอินไม่ผ่าน — เช็กอีเมล/รหัสผ่านใน Secrets")
                SESSION.parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=str(SESSION))

            page.wait_for_timeout(2000)  # เผื่อ render ช้า
            text = page.inner_text("body")
            snap("page")
            if discover:
                (DEBUG_DIR / "page.txt").write_text(text, encoding="utf-8")
                (DEBUG_DIR / "api.json").write_text(
                    json.dumps(json_payloads, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        finally:
            browser.close()
    return text, json_payloads


def extract_slots(text):
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    slots = []
    for l in lines:
        if not l or len(l) > 120:
            continue
        if any(h in l.lower() for h in EMPTY_HINTS):
            continue
        if TIME_RE.search(l) or DATE_RE.search(l):
            slots.append(l)
    return sorted(set(slots))


def notify(title, body):
    sent = False
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={"Title": title.encode("utf-8"), "Priority": "high",
                     "Tags": "rotating_light", "Click": URL},
            timeout=15,
        )
        sent = True
    tg_token, tg_chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            json={"chat_id": tg_chat, "text": f"{title}\n\n{body}\n\n{URL}"},
            timeout=15,
        )
        sent = True
    if not sent:
        print("[no notifier configured]", title, body, sep="\n")


def check_once(discover=False):
    now = datetime.now(BKK).strftime("%Y-%m-%d %H:%M:%S")
    try:
        text, payloads = scrape(discover)
    except LoginError as e:
        # แจ้งแค่ครั้งเดียวจนกว่าจะล็อกอินผ่าน จะได้ไม่เด้งรัวทุก 5 นาที
        flag = STATE.parent / "login_failed"
        if not flag.exists():
            notify("⚠️ มหาสาร monitor: ล็อกอินไม่ได้", str(e))
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text(now)
        SESSION.unlink(missing_ok=True)
        print("LOGIN ERROR:", e)
        sys.exit(1)
    (STATE.parent / "login_failed").unlink(missing_ok=True)
    slots = extract_slots(text)
    api_hash = hashlib.sha256(
        json.dumps([p["body"] for p in payloads], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()

    prev = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else None
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"checked_at": now, "slots": slots, "api_hash": api_hash},
                                ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[{now}] พบ {len(slots)} รายการที่ดูเหมือนคิว, JSON {len(payloads)} ชุด")
    if prev is None:
        print("รอบแรก: บันทึก baseline ไว้ ยังไม่แจ้งเตือน")
        return

    added = [s for s in slots if s not in set(prev["slots"])]
    if added:
        notify("🔔 มหาสาร: มีคิวว่างโผล่!", "\n".join(f"• {s}" for s in added[:20]))
        print("NEW:", *added, sep="\n  ")
    elif api_hash != prev.get("api_hash") and not slots and not prev["slots"]:
        # อ่านคิวจากหน้าเว็บไม่ออก แต่ข้อมูลเบื้องหลังเปลี่ยน → แจ้งแบบกว้าง ๆ
        notify("🔔 มหาสาร: ข้อมูลคิวเปลี่ยน", "ข้อมูลการจองบนหน้าเว็บเปลี่ยนไป ลองเปิดเช็กดู")
    else:
        print("ไม่มีคิวใหม่")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, help="เช็กวนทุก N วินาที (แนะนำ ≥ 120)")
    ap.add_argument("--discover", action="store_true")
    a = ap.parse_args()
    if a.loop:
        while True:
            try:
                check_once(a.discover)
            except Exception as e:
                print("error:", e, file=sys.stderr)
            time.sleep(max(a.loop, 60))
    else:
        check_once(a.discover)
