# CHANGELOG

รูปแบบเวอร์ชัน `PK-Revit X.Y.Z` (ดูกฎใน [CLAUDE.md](CLAUDE.md)) สถานะการทดสอบ: **ยังไม่มีเวอร์ชันไหนทดสอบใน Revit** ทุกรายการตรวจแค่ syntax + unit test ของฟังก์ชันคำนวณ

| เวอร์ชัน | สิ่งที่เปลี่ยน | ทดสอบ |
|---|---|---|
| 0.7.2 | โมดูลเหล็กทั้ง 5: dropdown ดึง Rebar Bar Type ทุกชนิดจากโปรเจกต์ เรียงตามขนาด | syntax + unit test |
| 0.7.1 | Roof Master: dropdown ดึง "Family : Type" จริง จำค่าที่เลือกล่าสุด (`%LOCALAPPDATA%\REVOTECH\roofmaster_last.json`) | syntax |
| 0.7.0 | Dang Gen (ขั้นที่ 5 ของ Roof Master), QTO Tables, License + i18n (TH/EN/LO) เบื้องต้น | syntax + unit test |
| 0.6.0 | บาร์คัท/BBS: ตารางตัด, แผนตัดท่อน 10/12 ม., ส่งออก Excel/CSV, ชีต Revit | syntax + unit test |
| 0.5.0 | Rebar พื้น (เหล็กเส้น/ไวร์เมช), Rebar บันได | syntax + unit test |
| 0.4.0 | Rebar คาน, Rebar ฐานราก, Roof Cover | syntax + unit test |
| 0.3.0 | lib กลาง `revotech` (units, rvt, ui, rebar, theme) + Rebar เสา | syntax + unit test |
| 0.2.1 | roadmap | — |
| 0.2.0 | สำเนา Roof Master v2, dropdown เลือก type, ติ๊กทั้งหมด, popup สรุป, เอกสารวิเคราะห์คลิป | syntax |

## เรื่องที่ค้าง
- ทดสอบทุกโมดูลใน Revit 2026 (ดู [docs/test-guide.md](docs/test-guide.md))
- ค่ามาตรฐานวิศวกรรมที่รอยืนยัน: ดูหัวข้อ "ค่าที่รอยืนยัน" ในแต่ละ `docs/accept-*.md`
- engine เดิม 4 ตัวของ Roof Master ยังก๊อป helper ซ้ำ (ยังไม่ย้ายเข้า lib)
- ขั้น 0 ใน Roof Master (จากคลิป) ยังไม่ทราบความหมาย
