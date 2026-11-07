# ระบบ i18n (TH/EN/LO) และ license เบื้องต้น

สถานะ: โครงสร้างพร้อม unit test (18 เทสต์ผ่านนอก Revit) — **ยังไม่ได้ทดสอบใน Revit** (ปุ่ม License และฟอร์ม WPF ยังไม่เคยรันจริง)
ยังไม่เชื่อมกับโมดูลเดิมใดๆ → ไม่มีโมดูลถูกบล็อก

ไฟล์: `lib/revotech/i18n.py`, `lib/revotech/license.py`, `REVOTECH.panel/License.pushbutton/` (มี `test_license_i18n.py`)
รันเทสต์: `python REVOTECH.panel/License.pushbutton/test_license_i18n.py`

## 1) i18n

- `from revotech.i18n import t` → `t("ui.close")`, `t("ui.select_first", what=u"เสา", hint=u"")`
- พจนานุกรม `STRINGS = {key: {"th":..., "en":..., "lo":...}}` ในไฟล์เดียว; ไทยเป็นต้นฉบับ
- fallback: ภาษาปัจจุบัน → อังกฤษ → ไทย → ตัวคีย์ (ไม่ error)
- ภาษาที่เลือกเก็บที่ `%LOCALAPPDATA%\REVOTECH\settings.json` คีย์ `language` (ค่าเริ่มต้น `th`; env `REVOTECH_HOME` ใช้ย้ายโฟลเดอร์ ไว้เทสต์)
- ตัวอย่างข้อความของ `ui.py` ใส่ไว้แล้ว (`ui.close`, `ui.details`, `ui.select_first`, `ui.summary.*` ฯลฯ) แต่ **ยังไม่ได้แก้ `ui.py` ให้เรียก `t()`** ตามข้อกำหนดห้ามแก้ไฟล์เดิม
- ฟอร์ม XAML ของโมดูลเดิมมีข้อความไทยฝังใน `body.xaml` — ต้องย้ายเป็น `x:Name` + กำหนด `.Text = t(...)` จากโค้ด (ตามแบบ License.pushbutton) ทีละโมดูล
- ภาษาเปลี่ยนแล้วมีผลเต็มที่เมื่อเปิดหน้าต่างถัดไป (ปุ่ม/tooltip ใน ribbon อ่านจาก `bundle.yaml` ซึ่ง pyRevit โหลดตอนเริ่ม ไม่สลับตามภาษา — ต้องตัดสินใจ ดูคำถามข้อ 6)

### ภาษาลาว — **ต้องให้เจ้าของภาษาตรวจ**
ใส่เฉพาะคำสั้นที่มั่นใจ: ปิด, รายละเอียด, กรุณาเลือก…ก่อน, เสา, สถานะ, ภาษา — คำอื่นไม่มี `lo` จึงขึ้นเป็นอังกฤษ ศัพท์วิศวกรรมลาว (คาน, ฐานราก, เหล็กปลอก ฯลฯ) ยังไม่ได้ใส่ ควรให้ผู้พูดลาวที่รู้ศัพท์ก่อสร้างทำทั้งตาราง

## 2) license

### การออกแบบ
```
ผู้ใช้ป้อนรหัส ─▶ activate(key) ─▶ validator.validate(key, machine_id) ─▶ Result(ok, reason, detail)
                                       │ ok → บันทึก %LOCALAPPDATA%\REVOTECH\license.json
```
- `machine_id()` = SHA-256 ของ (ชื่อเครื่อง, MAC ถ้าไม่สุ่ม, CPU id, domain) ตัดเหลือ 20 ตัว — ไม่เก็บค่าดิบ
- รูปแบบรหัส `XXXXX-XXXXX-XXXXX-XXXXX` (ตรวจรูปแบบเท่านั้น ไม่ได้ตรวจความถูกต้อง)
- จำกัด 2 เครื่อง: ฟังก์ชันล้วน `check_activation(machines, mid, limit=2)` (ย้ายไปใช้ฝั่ง server ได้)
- Validators: `DevValidator` (เปิดทุกอย่าง), `NoServerValidator` (ค่าเริ่มต้น → ตอบไม่ผ่านเหตุผล `no_server`), `InMemoryValidator` (ต้นแบบ/เทสต์)
- **โหมด dev**: ตั้ง env `REVOTECH_LICENSE_MODE=dev` → `is_licensed()` เป็นจริงเสมอ
- ไม่มีคีย์/ความลับ/URL ฝังในโค้ด

### ข้อจำกัดที่ต้องรู้
- `license.json` ฝั่งเครื่องผู้ใช้แก้เองได้ และ Python ของ pyRevit เป็นโค้ดเปิด → **การบังคับจริงต้องมี server** ฝั่งไคลเอนต์ทำได้แค่ "ขัดขวางคนทั่วไป"
- เงื่อนไข "2 เครื่องแต่ไม่พร้อมกัน" ต้องมี session/heartbeat ที่ server (ยังไม่ทำ; reason `in_use_elsewhere` เตรียมข้อความไว้แล้ว)
- ยังไม่มีการ deactivate / ย้ายเครื่อง / หมดอายุ / offline grace period

### วิธีเชื่อมกับโมดูลอื่น (ยังไม่ทำ)
1. เขียน `RemoteValidator(BaseValidator)` ใน license.py: `validate(key, mid)` ยิง HTTPS ไป server แล้วแปลง response เป็น `Result`; แก้ `default_validator()` ให้ใช้เมื่อมี URL ใน settings (ไม่ฝังในโค้ด)
2. ใน script.py ของโมดูล (หลัง import):
   ```python
   from revotech import license as lic
   if not lic.is_licensed():
       from pyrevit import forms
       forms.alert(u"ยังไม่ได้เปิดสิทธิ์ — กดปุ่ม สิทธิ์การใช้งาน", exitscript=True)
   ```
   หรือใส่ที่เดียวใน `ui.RevoWindow.__init__`/`need_*` เพื่อไม่ต้องแก้ทุกโมดูล (ต้องแก้ `ui.py` — ต้องได้รับอนุญาต)
3. ระหว่างพัฒนาใช้ `REVOTECH_LICENSE_MODE=dev` (ตั้งเป็น user env var แล้วรีสตาร์ท Revit)
4. เพิ่มเทสต์ว่าโมดูลที่ถูกเชื่อมยังรันได้ในโหมด dev

## 3) คำถามที่ต้องให้ boss ตัดสินใจ
1. **ใครออกคีย์และเก็บฐานข้อมูล?** (ทำ server เอง / ใช้บริการสำเร็จรูปเช่น Keygen, LemonSqueezy / ออกมือด้วยสเปรดชีตช่วงแรก)
2. **โมเดลธุรกิจ**: ซื้อขาด 1 สิทธิ์/2 เครื่อง ตามคลิปจริงหรือไม่? อัปเดตฟรีตลอด? (ไม่แน่ใจ — เป็นคำอ้างของผู้พูดในคลิป) มีสิทธิ์ทดลอง (trial) ไหม
3. **offline**: ต้องใช้ได้โดยไม่มีเน็ตไหม? ถ้าใช่ ต้องมี token ลงลายเซ็น (public key ฝังได้ ไม่ใช่ความลับ) + อายุ/grace period
4. **"ไม่พร้อมกัน"**: บังคับจริงไหม (ต้อง heartbeat) หรือแค่ไม่เกิน 2 เครื่อง
5. **ย้ายเครื่อง/เครื่องเสีย**: ใครรีเซ็ตเครื่อง ผ่านช่องทางไหน จำกัดจำนวนครั้งไหม
6. **ไม่มีสิทธิ์แล้วให้เกิดอะไร**: บล็อกทั้งหมด หรือเปิดโหมดจำกัด (เช่น ดูได้ สร้างไม่ได้)? ปุ่ม ribbon ต้องสลับภาษาด้วยไหม (ต้องสร้าง bundle.yaml หลายชุด/รีโหลด)
7. **ความเป็นส่วนตัว**: fingerprint ส่งขึ้น server ได้ไหม ต้องแจ้งผู้ใช้/นโยบายอย่างไร
8. **ลาว**: ใครตรวจคำแปล และใส่ศัพท์วิศวกรรมครบเมื่อไร
9. ย้ายข้อความไทยในโมดูลเดิมมาใช้ `t()` ทีละโมดูลเมื่อไร (ต้องแก้ `ui.py` และ `body.xaml` เดิม)
