# PK-Revit

Plugin Revit 2026 (pyRevit) สำหรับโครงหลังคาและเหล็กเสริม ตามคลิปสาธิต REVOTECH

สถานะ: เขียนครบทุกโมดูลตามคลิปแล้ว (เวอร์ชัน 0.7.x) แต่**ยังไม่ผ่านการทดสอบใน Revit** ดู [CHANGELOG.md](CHANGELOG.md)

## โมดูล (แท็บ REVOTECH)
Roof Master (5 ขั้น), Roof Cover, Rebar เสา/คาน/ฐานราก/พื้น/บันได, บาร์คัท/BBS, QTO Tables, License/ภาษา

## เอกสาร
- [CLAUDE.md](CLAUDE.md) — เป้าหมาย กฎการทำงาน
- [docs/features.md](docs/features.md) — ฟีเจอร์ที่เห็นในคลิป
- [docs/gap-analysis.md](docs/gap-analysis.md) — เทียบกับโค้ด v2
- [docs/roadmap.md](docs/roadmap.md) — แผนโมดูล
- [docs/test-guide.md](docs/test-guide.md) — วิธีทดสอบใน Revit
- `docs/accept-*.md` — เกณฑ์ตรวจรับรายโมดูล

## ติดตั้ง
คัดลอกโฟลเดอร์ `RoofMaster/REVOTECH.extension` ไปไว้ใน `%APPDATA%\pyRevit\Extensions\` แล้ว pyRevit > Reload
