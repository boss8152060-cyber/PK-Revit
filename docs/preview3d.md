# 3D preview สำหรับฟอร์มเหล็ก (PK Revit)

สถานะ: **เอนจินพร้อม ยังไม่ต่อเข้าฟอร์มจริง และยังไม่ได้ทดสอบใน Revit** — ตรวจด้วย unit test, รัน `preview3d.py` จริงด้วย IronPython 2.7 ของ pyRevit + WPF นอก Revit แล้ว render เป็น PNG (ดูหัวข้อ "ผลที่เห็น")

## สิ่งที่เห็นในคลิป (เฟรมคลิปลำดับ 45–60, 76–95)

- **เห็นในคลิป** ฟอร์มเหล็กเดิมมีกรอบ 3D แสดงชิ้นงาน + เหล็กที่จะใส่ (คลิป 54–58 ฟอร์มพื้น/ฐานราก; 77–80 ฐานรากสามเหลี่ยมมีเสาและเหล็กเสาตั้งอยู่)
  - ชิ้นงาน (host) เป็นผิวโปร่งสีเทา/เขียวอมฟ้า มองทะลุเห็นเหล็กข้างใน เส้นขอบชิ้นงานชัด
  - เหล็กแต่ละกลุ่มคนละสี เส้นตรงล้วน (ท่อบาง) ตะแกรงพื้น/ฐานรากแสดงเป็นกริดสองทิศ (คลิป 57 สีฟ้าอมเขียว, คลิป 47 ส้ม/ขาว/เหลืองบนพื้นหลังเข้ม)
  - มุมกล้องแนว isometric จากด้านหน้าเฉียง เห็นด้านบน+สองด้านข้าง เอียงลงประมาณ 25–35°; มีข้อความใต้กรอบ "ลาก = หมุน · ล้อ = ซูม" และมีปุ่มเล็กมุมขวาล่างของกรอบ (ข้อความบนปุ่มอ่านไม่ชัด — น่าจะรีเซ็ตมุม)
  - ฟอร์มเหล็กฐานรากมีรูปแปลนแยกอีกรูป (คลิป 87/94) แสดงเส้นเหล็กแต่ละกลุ่มด้วยสี+หมายเลขวงกลม — **ยังไม่ทำ** ในเอนจินนี้ (เป็น 2D แยก)
- **อนุมาน** ว่าอัปเดตทันทีตามค่าที่กรอก (คลิปเห็นกรอบเปลี่ยนตามค่าจำนวน/ระยะ แต่ไม่ได้ยินเสียงอธิบาย)
- **ไม่แน่ใจ** รายละเอียดสีของทุกกลุ่มเหล็ก (คลิปมีหลายเวอร์ชันของฟอร์ม) — เอนจินใช้ชุดสีของตัวเอง (ด้านล่าง) ปรับได้ที่ค่าคงที่ใน `scene3d.py`
- ในคลิปธีมฟอร์มเป็นโทนเข้ม; ฟอร์มของเราเป็นขาว-ดำ จึงใช้พื้นหลัง preview สีเทาอ่อน `#F3F4F6`

## ไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| `lib/revotech/scene3d.py` | ตรรกะล้วน (ไม่พึ่ง .NET) — โครงข้อมูล Scene + ตัวสร้าง scene ต่อโมดูล + เมช (ท่อเหล็ก, ปริซึม host) |
| `lib/revotech/preview3d.py` | `Preview3D` — Viewport3D + กล้อง + เมาส์ + legend + `update/schedule` |
| `lib/revotech/ui.py` | `RevoWindow(..., preview=True)` จัดหน้าต่างซ้าย preview / ขวาฟอร์ม |
| `lib/revotech/test_scene3d.py` | unit test |
| `tools/preview_demo/` | `run_demo.ps1` + `demo_scenes.py` + `demo_window.py` (render PNG), `shims/` (os/io จิ๋วให้ IronPython เปล่า) |
| `tools/run_all_tests.py` | รัน test_*.py ทั้งหมด |

หน่วยทั้งหมด **มม.** แกน x,y แนวนอน, z ขึ้น

## API

### Scene (scene3d)
```python
Scene(title, hosts=[Host], groups=[BarGroup], notes=[ข้อความเตือน])
Host.box(x0,y0,z0,x1,y1,z1)                 # กล่อง
Host(poly2d, axis='z'|'y', lo, hi, color, alpha)   # ปริซึมรูปหลายเหลี่ยมเรียบง่าย (ear-clipping)
BarGroup(key, label, color_rgb, radius_mm, polys=[[(x,y,z),...]])
scene.bounds(), scene.legend(), scene.bar_count()
```

### ตัวสร้าง scene (รับค่าเดียวกับที่ฟอร์มส่งให้ฟังก์ชันคำนวณ)

| ฟังก์ชัน | พารามิเตอร์ | ที่มาของการคำนวณ |
|---|---|---|
| `column_scene(w,h,H,n,d_main,d_tie,cover,end_len,sp_mid,sp_end,lap_d)` | ตรงกับ `collect()` ฟอร์มเสา (เมตร→มม. เอง) | คัดลอก `main_positions` + ตรรกะโซนปลอก 3 โซนจาก `RebarColumn/script.py` |
| `beam_scene(L,b,h,spec)` | `spec` = dict เดียวกับ `beamcalc.plan_longitudinal/plan_stirrups` | **เรียก `revotech.beamcalc` ตรงๆ** (ตัวเดียวกับที่สร้างจริง) + ขางอ + ปลอก |
| `footing_scene(L,B,H,long_bar,short_bar,cover,hook,ring,column)` | `(dia,n)`; hook = `HOOK_NONE/12D/FULL`; ring=`(dia,count,spacing)` | คำนวณซ้ำกรณีสี่เหลี่ยมให้ตรง `footing_calc.plan_mat` (+ `hook_leg`, `ring_levels` ที่คัดลอกมา) |
| `footing_scene_from_bars(poly,H,bars,...)` | `bars` = ผลของ `footing_calc.plan_mat` | ฐานสามเหลี่ยม/รูปอื่น — ฟอร์มเรียก `plan_mat` เองแล้วส่งมา |
| `slab_scene(L,B,H,layers,cover)` | `layers={"TX":(dia,sp),...}` | คัดลอก `positions`/`layer_levels` ของ `slab_calc` |
| `slab_scene_from_bars(outer,holes,H,bars)` | ผลของ `slab_calc.plan_layers` | พื้นรูปอิสระ (ช่องเปิดไม่ถูกเจาะที่ host โปร่ง — เห็นจากที่ไม่มีเหล็ก) |
| `stair_scene(geo,W,sets,tw,landing=None)` | `geo`=`stair_calc.Geo`, `sets`=ผล `plan_run`/`plan_landing` | รูปตัดฟันปลา + ขยายชุด szplane/transverse |

เหตุผลที่ footing/slab/stair ไม่ import `*_calc.py` ตรงๆ: ไฟล์เหล่านั้นอยู่ในโฟลเดอร์ pushbutton ซึ่งกำลังย้ายตำแหน่ง ฟอร์มของโมดูลนั้นเรียกฟังก์ชันของตัวเองได้อยู่แล้ว จึงส่งผลมาให้ scene3d เท่านั้น
สีกลุ่ม: เสา/คาน/ฐานราก/พื้น ดู `BEAM_COLORS`, `FOOT_COLORS`, `SLAB_COLORS`; บันไดตรงกับ `stair_calc.GROUP_COLORS`.

### Preview3D (preview3d)
```python
pv = Preview3D(delay_ms=140, show_legend=True)
pv.view                     # UIElement (Border) เอาไปใส่ Child ของ container
pv.update(scene, keep_view=True)    # วาดทันที เรียกซ้ำได้ ไม่รีเซ็ตมุมถ้า keep_view
pv.schedule(lambda: scene)  # หน่วง delay_ms; เรียกซ้ำภายในเวลานั้น = เหลือครั้งสุดท้าย; build_fn โยน exception = ข้ามเงียบ
pv.reset_view(); pv.clear()
render_png(pv, path, w, h)  # สำหรับเดโม/ทดสอบ
```
เมาส์: ลากซ้ายหมุน, ล้อซูม, ลากกลางเลื่อน, ดับเบิลคลิก/ปุ่ม "รีเซ็ตมุม" รีเซ็ต
ประสิทธิภาพ: เหล็กแต่ละกลุ่ม = MeshGeometry3D เดียว; ท่อ 6 เหลี่ยม (4 เหลี่ยมถ้าเหล็ก > 1,200 เส้น); รัศมีขั้นต่ำ 0.12% ของเส้นทแยงชิ้นงานกันเส้นหาย

### RevoWindow(preview=True)
```python
ui.RevoWindow.__init__(self, body, ..., run_text, preview=True)   # preview_width=460 ค่าตั้งต้น
self.preview   # Preview3D หรือ None ถ้าสร้างไม่สำเร็จ (ฟอร์มยังเปิดได้) ; preview=False -> None
```
หน้าต่างกว้างขึ้น `preview_width` px; ฟอร์มขวาเหมือนเดิมทุกประการ (ตรวจด้วย render: `out/window_plain.png`)

## วิธีต่อเข้าฟอร์มแต่ละโมดูล (สำหรับ session ถัดไป)

แนวทางเดียวกันทุกโมดูล:
1. `ui.RevoWindow.__init__(..., preview=True)` ในคลาสฟอร์ม
2. เขียน `self._scene()` ที่อ่านค่าจากช่องกรอกด้วย `ui.num/intval` + ค่าจาก combo (ชื่อ Bar Type → เส้นผ่านศูนย์กลางผ่านฟังก์ชันที่ฟอร์มใช้อยู่) แล้วคืน Scene; **ห่อ try/except คืน None** เมื่อค่าไม่ครบ
3. ต่อ event: `TextChanged` ของ TextBox / `SelectionChanged` ของ ComboBox / `Checked` ของ CheckBox → `lambda s,a: self.preview.schedule(self._scene)` (เช็ก `self.preview is not None`) และเรียก `self.preview.update(self._scene())` หนึ่งครั้งท้าย `__init__`
4. ขนาดชิ้นงานตัวอย่าง: ถ้ามี element ที่เลือก ให้ใช้ขนาดจริงของ element แรก (เช่น `local_extents` ของเสา, ความยาว/หน้าตัดคาน) ถ้าไม่มี ใช้ค่าตัวอย่าง

| โมดูล | ใช้ | หมายเหตุ |
|---|---|---|
| เสา | `column_scene(w,h,H,n,d_main,d_tie,cover,end_len,sp_mid,sp_end,lap_d)` | ค่าจาก `cmb_n`, `cmb_main`, `cmb_tie`, `tb_*` (×1000 เป็น มม.) |
| คาน | `beam_scene(L,b,h,spec)` | สร้าง `spec` เดียวกับที่ `script.py` ส่งให้ `plan_longitudinal`; `scene.notes` จะมีข้อความเตือนของ beamcalc (เหล็กไม่พอดี ฯลฯ) แสดงสีแดงใน preview |
| ฐานราก | สี่เหลี่ยม `footing_scene`; สามเหลี่ยม/อื่น `plan_mat` แล้ว `footing_scene_from_bars` | `hook` แปลงจากตัวเลือกตะขอของฟอร์ม; ขนาดฐานจาก polygon ของ element |
| พื้น | `slab_scene` (สี่เหลี่ยม) หรือ `plan_layers` + `slab_scene_from_bars` | `layers` ใส่เฉพาะชั้นที่เลือกขนาดแล้ว |
| บันได | `stair_calc.Geo` + `plan_run` (+`plan_landing`) แล้ว `stair_scene` | ช่วงหลายช่วง: เรียกต่อ `z0`/ใช้ช่วงแรกเป็นตัวอย่างก่อน |

ข้อควรระวัง
- ฟอร์มเปิดแบบ modal ด้วย `ShowDialog()` — `DispatcherTimer` ทำงานบน dispatcher เดียวกัน ใช้ได้ปกติ
- `RevoWindow` ใช้ `SizeToContent="Height"`; พื้นที่ preview มี `MinHeight=460`
- ห้ามเรียก `update` ถี่ในลูปค่าที่กรอก ให้ใช้ `schedule`
- ชื่อ control `preview_host` ถูกใช้โดย `RevoWindow` แล้ว อย่าตั้งชื่อซ้ำใน body.xaml

## ผลที่เห็น (render ด้วย WPF จริง ไม่ใช่ Revit)

รันซ้ำได้ด้วย:
```
powershell -STA -File tools\preview_demo\run_demo.ps1                       # สร้าง out\*.png ทุกชนิด
powershell -STA -File tools\preview_demo\run_demo.ps1 -Script demo_window.py # หน้าต่าง preview=False/True
```
ผลอยู่ที่ `tools/preview_demo/out/`: `column.png` (เสา 8 เส้น ปลอก 25 ชุด 3 โซน เหล็กยืนแดงยื่นเหนือเสา), `beam.png` (บน/ล่าง 2 ชั้น/ข้าง/เสริมปลาย/ปลอก — เหล็กบนงอลง ล่างงอขึ้น), `footing.png` (ตะแกรง 2 ทิศ + ขางอ + ปลอกรัด + ตอม่อ), `footing_tri.png` (ตะแกรง 3 ทิศ 0/60/120° ใช้ผล `plan_mat` จริง), `slab.png`, `slab_L.png` (พื้นตัว L มีช่องเปิด ใช้ `plan_layers` จริง), `stair.png` (4 กลุ่มสี ใช้ `plan_run` จริง), `window_plain.png` / `window_preview.png` / `window_preview2.png` (หลัง `update()` ค่าใหม่).

เทียบกับคลิป: โครงเหมือน (host โปร่ง + เหล็กแยกสี + กล้อง isometric + legend/ข้อความวิธีใช้ + ปุ่มรีเซ็ต) ต่างที่ธีมสว่าง, legend บอกจำนวนเส้นต่อกลุ่ม, เหล็กต่อทาบของคานนับเป็นท่อน (จำนวนใน legend = จำนวน polyline)
ข้อจำกัดที่รู้: host โปร่งแสงเรียงลำดับความโปร่งใสแบบง่าย (เหล็กวาดก่อน host) มุมมองบางมุมอาจเห็นเหล็กซีดลง; ช่องเปิดของพื้นไม่เจาะที่ผิว host; ไม่มีแปลน 2D แบบคลิป 87/94; **ยังไม่เคยรันใน Revit/pyRevit จริง** (ทดสอบบน IronPython 2.7 engine ของ pyRevit นอก Revit เท่านั้น)
