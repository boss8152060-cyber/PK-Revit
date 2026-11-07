# โครง ribbon ของ PK Revit (จัดกลุ่มใหม่)

เดิมมี 17 ปุ่มกระจายใน panel เดียว ตอนนี้รวมเป็น 4 panel (พฤติกรรมของฟอร์มเดิมทุกตัวไม่เปลี่ยน — ปุ่มรวมแค่ "เลือกทาง" แล้วเรียกสคริปต์เดิม)

| Panel | ปุ่ม | ทำอะไร |
|---|---|---|
| **เหล็ก** | **Rebar** | ดูว่าเลือกอะไรอยู่ → เปิดฟอร์มของชนิดนั้น (เสา/คาน/ฐานราก/พื้น/บันได) |
| | pulldown **จัดการเหล็ก** | Select Rebar, Select Host, Delete Rebar, Show/Hide Obscured, Rebar Collision, Color by Parameter, Propagate Rebar |
| **หลังคา** | **Roof** | หน้าต่างเลือก 2 ปุ่ม: โครงหลังคา (Roof Master) / วัสดุมุง (Roof Cover) |
| **ผลลัพธ์** | pulldown **บาร์คัท & QTO** | บาร์คัท, QTO Tables |
| **ตั้งค่า** | **License** | รหัสสิทธิ์ + เลือกภาษา |

Dang Gen ไม่มีปุ่มของตัวเอง (เดิมก็เป็นขั้นที่ 5 ของ Roof Master ใน `engines/`) จึงไม่แยกออกมา

## โครงโฟลเดอร์

```
PK Revit.tab/
  bundle.yaml                  (layout: เหล็ก, หลังคา, ผลลัพธ์, ตั้งค่า)
  เหล็ก.panel/
    Rebar.pushbutton/
      script.py                dispatcher
      body.xaml                หน้าต่างเลือก 5 ปุ่ม
      modules/                 (git mv จากปุ่มเดิม — รักษาประวัติ)
        RebarColumn.pushbutton/  RebarBeam.pushbutton/  RebarFooting.pushbutton/
        RebarSlab.pushbutton/    RebarStair.pushbutton/
      test_dispatch.py
    จัดการเหล็ก.pulldown/
      SelectRebar / SelectHost / DeleteRebar / ObscuredRebar /
      RebarCollision / ColorByParameter / PropagateRebar  (.pushbutton)
  หลังคา.panel/
    Roof.pushbutton/
      script.py   body.xaml
      modules/RoofMaster.pushbutton/ (มี engines/ เหมือนเดิม)   modules/RoofCover.pushbutton/
  ผลลัพธ์.panel/ถอดปริมาณ.pulldown/  BarCut.pushbutton  QtoTables.pushbutton
  ตั้งค่า.panel/License.pushbutton
lib/revotech/dispatch.py       ตรรกะจัดชนิด/หาสคริปต์/execfile (ไฟล์ใหม่)
lib/revotech/hubwindow.py      หน้าต่างปุ่มใหญ่บน RevoWindow (ไฟล์ใหม่)
```

ชื่อโฟลเดอร์ของแต่ละโมดูลยังเป็น `RebarColumn.pushbutton` ฯลฯ เหมือนเดิม เพราะ `revotech.ui.RevoWindow` ใช้ชื่อโฟลเดอร์เป็นชื่อกลุ่ม Preset และ `hostconfig.KINDS` ชี้ชื่อนี้

## Rebar ทำงานอย่างไร (dispatch)

1. อ่าน selection แล้วจัดชนิดทีละ element ด้วย `dispatch.kind_of`:
   OST_StructuralColumns → เสา, OST_StructuralFraming ที่ `StructuralType == Beam` → คาน, OST_StructuralFoundation → ฐานราก, OST_Floors → พื้น, OST_Stairs → บันได (อย่างอื่น เช่น Brace/กำแพง ข้ามไป)
2. มีชนิดเดียว → รันโมดูลนั้นเลย
3. ไม่มีชนิดที่รองรับ (ไม่ได้เลือกอะไร หรือเลือกแต่ของที่ไม่รองรับ) → หน้าต่าง 5 ปุ่มใหญ่ → `hostpick.resolve` ให้คลิกเลือกชิ้นงานของชนิดนั้น → รันโมดูล
4. หลายชนิด → ถามทีเดียวว่าจะทำทีละชนิดตามลำดับ เสา → คาน → ฐานราก → พื้น → บันได; ก่อนชนิดถัดไปถามอีกครั้ง (กันกรณียกเลิกฟอร์มก่อนหน้า)
5. ก่อนรันแต่ละโมดูล ตั้ง selection เป็นเฉพาะชิ้นงานของชนิดนั้น แล้ว `execfile` โดยไม่ส่ง `CONFIG_OVERRIDE` (= ฟอร์มปกติ ไม่ใช่โหมด Propagate)

`dispatch.run_script` แก้ปัญหาการรันผ่าน execfile:
- ตั้ง `__file__`/`__name__` เป็นของโมดูล → `body.xaml` และ `ui.xaml` หาเจอจากโฟลเดอร์โมดูล (Roof Master เดิมใช้ `script.get_bundle_file` ซึ่งจะชี้ไปปุ่ม Roof จึงแก้ให้ใช้ `__file__`)
- ใส่โฟลเดอร์โมดูลใน `sys.path` → `import footing_calc / slab_calc / stair_calc` ได้
- `script.exit()` ในโมดูลคือ `SystemExit` → dispatcher จับแล้วถือว่าจบขั้นนั้น (แยก "เสร็จ" กับ "ยกเลิก" ไม่ได้ เพราะโมดูลจบด้วย exit ทั้งคู่)

หาไฟล์สคริปต์ได้ทั้ง `script.py` และ `<ชื่อโมดูล>.py` (เช่น `RebarColumn.py`) — ใช้กฎเดียวกันใน Rebar, Roof, และ Propagate Rebar; Roof Master หา engine เองด้วยกฎเดิม (`engines/<ปุ่ม>/script.py` หรือ `<ปุ่ม>.py`)

### path ที่ตรวจแล้วว่าไม่พัง
- Roof Master `step_path`: ตัวแรก (ปุ่มพี่น้องใน panel) ไม่มีแล้วแต่ตกมาที่ `engines/` ในโมดูลเอง ซึ่งย้ายไปพร้อมกัน; ไฟล์ `.rfa` ของ HipRidge/Purlin/Valley อ้างจากโฟลเดอร์ engine ด้วยกันเอง
- Propagate Rebar `_module_path`: เดิมหาโฟลเดอร์พี่น้อง ตอนนี้หาที่ `เหล็ก.panel/Rebar.pushbutton/modules/` (มีทางสำรองแบบเดิม)
- Preset: ชื่อกลุ่มมาจากชื่อโฟลเดอร์โมดูล (ไม่เปลี่ยน) → preset ที่บันทึกไว้ยังใช้ได้
- `test_*.py` ที่ย้ายแก้ path ไป `lib` ให้ตรงความลึกใหม่ (ไม่ได้แก้ตรรกะ)

## Roof

หน้าต่างเลือก 2 ปุ่มใหญ่ (เลือกวิธีนี้แทนฟอร์มแท็บรวม เพราะ Roof Master กับ Roof Cover เป็นฟอร์มต่างโครงกัน ถ้ารวมต้องเขียนฟอร์มใหม่และเสี่ยงเปลี่ยนพฤติกรรม) บอกจำนวนหลังคาที่เลือกอยู่ด้วย แล้ว `execfile` สคริปต์เดิม

## วิธีทดสอบ

นอก Revit (ทำได้เลย):
```bash
# รันทุก test ในส่วนขยาย (แต่ละไฟล์รันจากโฟลเดอร์ของมันเอง)
cd src/PKRevit.extension
find . -name "test_*.py" | while read f; do (cd "$(dirname "$f")" && python "$(basename "$f")"); done
```
`test_dispatch.py` ตรวจ: การจัดชนิด/จัดกลุ่ม, หาสคริปต์ทั้งสองชื่อ, `run_script` (import ไฟล์ข้างๆ, `__file__`, SystemExit, ไม่ส่ง CONFIG_OVERRIDE), ทุกโมดูลมีอยู่ในที่ที่ dispatcher/Propagate/Roof Master หา, โครง ribbon, ไอคอน 96x96 และไม่มีคำเก่าใน UI ใหม่

ใน Revit 2026 (ยังไม่เคยลอง — ดูเคส 3, 7a, 7b, 7c ใน `docs/test-guide.md`): หลัง Reload ดูว่า 4 panel ขึ้นครบ → ทดสอบ Rebar 3 กรณี (เลือกชนิดเดียว / ไม่เลือก / เลือกปน) → Roof ทั้ง 2 ทาง → Propagate Rebar

## จุดเสี่ยงที่ยังไม่ได้ลองจริง
1. ชื่อ panel/pulldown เป็นภาษาไทย และ `layout` ใน `bundle.yaml` ของ tab/panel — ถ้า pyRevit ไม่รองรับ panel จะเรียงตามตัวอักษร หรือไม่ขึ้น
2. `modules/X.pushbutton` ซ้อนใน `Rebar.pushbutton` (แบบเดียวกับ `engines/` ของ Roof Master) — ถ้า pyRevit เห็นเป็นปุ่มเพิ่มจะมีปุ่มซ้ำ
3. `execfile` ซ้อนในสคริปต์ pyRevit: ตัวแปร global ที่ pyRevit ฉีดให้สคริปต์หลัก (เช่น `__revit__`) ไม่มีใน namespace ของโมดูล — โมดูลเดิมใช้ `from pyrevit import ...` ทั้งหมดและ Propagate/Roof Master ใช้วิธีเดียวกันอยู่แล้ว แต่ยังไม่เคยเรียกโมดูลเหล็กผ่าน Rebar
4. การ `SetElementIds` ก่อนรันโมดูล แล้วโมดูลอ่านด้วย `selected()` — ยังไม่เห็นกับตาว่า selection เปลี่ยนจริงก่อนฟอร์มเปิด
5. ตรวจคานด้วย `StructuralType == Beam`; คานบางตัวที่ผู้ใช้สร้างจาก family อื่นอาจถูกจัดเป็น Brace/Other แล้วถูกข้าม — ไม่ได้ตรวจกับโมเดลจริง (ตรงกับที่ Propagate Rebar และโมดูลคานเดิมทำ)
6. หน้าต่างเลือกซ่อนปุ่มรันและแถบ Preset ของ `RevoWindow` ด้วยการไล่หา StackPanel แม่ของ `pk_preset_cmb` — ตรวจ render XAML แล้วแต่ยังไม่ได้เปิดผ่าน pyRevit จริง
7. กด ✕ หรือยกเลิกฟอร์มโมดูล แล้วโมดูลที่ 2+ ยังถูกถามต่อ (โมดูลจบด้วย exit ทั้งสองกรณี)
8. ตัวติดตั้งในเครื่องผู้ใช้ที่เปลี่ยนชื่อสคริปต์เป็น `<ชื่อ>.py`: รองรับทั้ง modules และ engines แต่ถ้าเปลี่ยนชื่อ `body.xaml`/`ui.xaml` ด้วยจะหาไม่เจอ (ไม่ได้รองรับ)
