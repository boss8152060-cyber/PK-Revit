# CHANGELOG

รูปแบบเวอร์ชัน `PK-Revit X.Y.Z` (ดูกฎใน [CLAUDE.md](CLAUDE.md)) สถานะการทดสอบ: **ยังไม่มีเวอร์ชันไหนทดสอบใน Revit** ทุกรายการตรวจแค่ syntax + unit test ของฟังก์ชันคำนวณ

| เวอร์ชัน | สิ่งที่เปลี่ยน | ทดสอบ |
|---|---|---|
| 0.10.0 | แผง Manage ตาม PK Tool แต่ดีกว่า: Select Rebar, Select Host, Delete Rebar (ยืนยันก่อนลบ, ลบเฉพาะของ PK Revit ได้), Show/Hide Obscured, Rebar Collision (bbox แล้วตรวจ solid จริง + clearance + CSV), Color by Parameter (หลาย view, Reset เฉพาะที่ระบาย), Propagate Rebar, Preset (Local/Project), จำค่าต่อ element (ExtensibleStorage) | syntax + unit test + โหลด XAML ใน WPF |
| 0.9.0 | lib `reinforcement` (หาเหล็กบน host รวม Area/Path/Fabric) และ `hostpick` (เลือกทีละตัว/ตาม Mark) | syntax |
| 0.8.1 | เพิ่มไฟล์ family ใบมีด miter ที่ engine Roof Master ใช้ | — |
| 0.8.0 | เปลี่ยนชื่อเป็น **PK Revit** (แท็บ/แผง/ชื่อหน้าต่าง/โฟลเดอร์ `src/PKRevit.extension`), ธีมใหม่ขาว-ดำแบบ PK (ไม่มีส้ม) พร้อมโลโก้ PK, ไอคอนปุ่มทุกตัว (ปกติ+dark), ตัวมาร์ก Comments เปลี่ยนเป็น `PKRevit:` และโฟลเดอร์ log เป็น `%LOCALAPPDATA%\PKRevit` | syntax + unit test + render XAML ด้วย WPF จริง |
| 0.7.2 | โมดูลเหล็กทั้ง 5: dropdown ดึง Rebar Bar Type ทุกชนิดจากโปรเจกต์ เรียงตามขนาด | syntax + unit test |
| 0.7.1 | Roof Master: dropdown ดึง "Family : Type" จริง จำค่าที่เลือกล่าสุด (`%LOCALAPPDATA%\PKRevit\roofmaster_last.json`) | syntax |
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
