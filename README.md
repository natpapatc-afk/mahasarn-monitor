# Monitor คิวหลุด ร้านมหาสาร

เช็กหน้าจองของ Aroided ทุก 5 นาที ถ้ามีคิวว่างโผล่ขึ้นมาใหม่ จะเด้งแจ้งเตือนเข้ามือถือ

## ติดตั้ง (ฟรี ไม่ต้องเปิดคอมทิ้งไว้)

1. **ตั้งช่องแจ้งเตือน** — เลือกอย่างใดอย่างหนึ่ง
   - **ntfy (ง่ายสุด):** ลงแอป *ntfy* บนมือถือ → Subscribe topic ชื่อสุ่มยาว ๆ เช่น `mahasarn-x7k29q` (ใครรู้ชื่อก็อ่านได้ เลยควรตั้งให้เดายาก)
   - **Telegram:** สร้างบอทกับ @BotFather เอา token มา แล้วทักบอทหนึ่งครั้งและหา chat id
2. **สร้าง GitHub repo ใหม่** แล้วอัปโหลดไฟล์ทั้งหมดในโฟลเดอร์นี้ (รวม `.github/workflows/monitor.yml`) — ตั้งเป็น Public จะได้นาที Actions ไม่จำกัด
3. **ใส่ Secrets:** Settings → Secrets and variables → Actions → New repository secret
   - `NTFY_TOPIC` = ชื่อ topic ที่ตั้งไว้ หรือ
   - `TELEGRAM_BOT_TOKEN` และ `TELEGRAM_CHAT_ID`
4. **ทดลองรัน:** แท็บ Actions → *Mahasarn queue monitor* → Run workflow (ติ๊ก `discover`)
   - รอบแรกจะเก็บ baseline ไว้เฉย ๆ ยังไม่แจ้ง
   - เปิดผลรัน → ดาวน์โหลด artifact `debug` จะได้ `page.png`, `page.txt`, `api.json`

## ปรับให้แม่นขึ้น

สคริปต์อ่านคิวจากข้อความบนหน้าเว็บที่มีเวลา/วันที่ (เช่น `18:00`, `15 ต.ค.`) ซึ่งใช้ได้กับเว็บส่วนใหญ่
ถ้าแจ้งเตือนมั่วหรือไม่แจ้ง ส่ง `page.txt` กับ `api.json` จากขั้นที่ 4 มา จะปรับให้อ่านจาก API ตรง ๆ
และกรองเฉพาะวัน/จำนวนคน/รอบเวลาที่ต้องการได้

## รันบนเครื่องตัวเอง (ทางเลือก)

```bash
pip install -r requirements.txt
python -m playwright install chromium
NTFY_TOPIC=mahasarn-x7k29q python monitor.py --loop 180
```

## หมายเหตุ
- เช็กห่างกันอย่างน้อย 2–5 นาที เพื่อไม่ยิงเว็บร้านถี่เกินไป
- GitHub Actions แบบตั้งเวลาอาจช้ากว่ากำหนดได้ 5–15 นาทีในบางช่วง ถ้าต้องการไวกว่านี้ใช้แบบรันบนเครื่องตัวเอง
- repo ที่ไม่มีความเคลื่อนไหว 60 วัน GitHub จะหยุด schedule อัตโนมัติ กด Enable กลับได้ที่แท็บ Actions
