# -*- coding: utf-8 -*-
"""QTO Tables — สรุปปริมาณวัสดุโครงหลังคา + วัสดุมุง

อ่านจากโมเดล (ไม่แก้โมเดล ยกเว้นตอนสร้าง Schedule ถ้าติ๊ก):
- โครง: Structural Framing จัดกลุ่มตามคำในชื่อ type (แป จันทัน ตะเฆ่สัน อกไก่ รางน้ำ ตะเฆ่ราง ดั้ง)
  นับท่อน/ความยาวรวม (ม.)/น้ำหนักรวม — กก./ม. อ่านจากพารามิเตอร์ type ถ้ามี ไม่มีเว้นว่าง
- วัสดุมุง: DirectShape ที่ Comments ขึ้นต้น "REVOTECH:roofcover:" (จาก Roof Cover)
  แยกชนิดจากชื่อ material ที่ทาไว้ — แผ่นมุงใช้ครึ่งหนึ่งของพื้นที่ผิวรวม (≈ผิวบน)
ผล: ตารางในฟอร์ม + Schedule (Transaction เดียว Ctrl+Z ย้อนได้) + CSV UTF-8 BOM + log
คำนวณอยู่ใน qto_calc.py (ทดสอบนอก Revit) — ยังไม่เคยรันใน Revit ดู docs/accept-qto-tables.md
"""

import os
import sys
import traceback
from pyrevit import revit, DB, script

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qto_calc as qc  # noqa: E402

from revotech import ui  # noqa: E402
from revotech.rvt import ename, id_value  # noqa: E402
from revotech.units import ft_to_m  # noqa: E402

doc = revit.doc
MARK = u"REVOTECH:roofcover:"
COMMENTS = DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS
SCHED_FRAME = u"REVOTECH QTO โครงหลังคา"
SCHED_COVER = u"REVOTECH QTO วัสดุมุง"
LOG = "Qto_tables.txt"
FT2_PER_M2 = 1.0 / (ft_to_m(1.0) ** 2)   # ตร.ฟุต ต่อ ตร.ม. (ใช้หารกลับ)


# ------------------------------------------------------------ อ่านโมเดล
def _kg_per_m(sym, cache):
    """กก./ม. จากพารามิเตอร์ type — None ถ้าไม่มี (ห้ามเดา)"""
    key = id_value(sym.Id)
    if key in cache:
        return cache[key]
    val = None
    for p in sym.Parameters:
        try:
            if not qc.is_weight_param(p.Definition.Name):
                continue
            if p.StorageType != DB.StorageType.Double or not p.HasValue:
                continue
            v = p.AsDouble()
            try:  # ค่า internal ของ "มวลต่อความยาว" ต้องแปลงเป็น กก./ม.
                if p.Definition.GetDataType() == DB.SpecTypeId.MassPerUnitLength:
                    v = DB.UnitUtils.ConvertFromInternalUnits(
                        v, DB.UnitTypeId.KilogramsPerMeter)
            except Exception:
                pass
            if v > 0:
                val = v
                break
        except Exception:
            continue
    cache[key] = val
    return val


def _length_m(e):
    p = e.get_Parameter(DB.BuiltInParameter.STRUCTURAL_FRAME_CUT_LENGTH)
    if p is not None and p.HasValue and p.AsDouble() > 0:
        return ft_to_m(p.AsDouble())
    try:
        return ft_to_m(e.Location.Curve.Length)
    except Exception:
        return 0.0


def read_framing():
    items, cache = [], {}
    for e in DB.FilteredElementCollector(doc).OfCategory(
            DB.BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType():
        try:
            sym = doc.GetElement(e.GetTypeId())
            if sym is None:
                continue
            items.append({"type": ename(sym), "length_m": _length_m(e),
                          "kg_per_m": _kg_per_m(sym, cache)})
        except Exception:
            continue
    return items


def _material_name(ds, solid):
    try:
        for f in solid.Faces:
            mid = doc.GetPaintedMaterial(ds.Id, f)
            if mid is None or mid == DB.ElementId.InvalidElementId:
                mid = f.MaterialElementId
            m = doc.GetElement(mid) if mid is not None else None
            if m is not None:
                return ename(m)
    except Exception:
        pass
    return u""


def read_cover():
    items = []
    for ds in DB.FilteredElementCollector(doc).OfClass(DB.DirectShape):
        try:
            p = ds.get_Parameter(COMMENTS)
            if p is None or not (p.AsString() or u"").startswith(MARK):
                continue
            area_ft2, mat = 0.0, u""
            for g in ds.get_Geometry(DB.Options()):
                if isinstance(g, DB.Solid) and g.Volume > 0:
                    area_ft2 += g.SurfaceArea
                    mat = mat or _material_name(ds, g)
            if qc.classify_cover(mat) == "sheet":
                area_ft2 /= 2.0           # แผ่นบาง: ผิวบน ≈ ครึ่งของผิวทั้งหมด
            items.append({"material": mat, "area_m2": area_ft2 / FT2_PER_M2})
        except Exception:
            continue
    return items


# ------------------------------------------------------------ Schedule
def _field_by_bip(sd, names):
    want = [int(getattr(DB.BuiltInParameter, n)) for n in names
            if getattr(DB.BuiltInParameter, n, None) is not None]
    for sf in sd.GetSchedulableFields():
        try:
            if id_value(sf.ParameterId) in want:
                return sf
        except Exception:
            continue
    return None


def make_schedules():
    """สร้าง/แทนที่ Schedule 2 ตัว → (ชื่อที่สร้างได้, ข้อความปัญหา)"""
    made, problems = [], []
    for s in list(DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule)):
        try:
            if ename(s) in (SCHED_FRAME, SCHED_COVER):
                doc.Delete(s.Id)
        except Exception:
            pass
    specs = [
        (SCHED_FRAME, DB.BuiltInCategory.OST_StructuralFraming,
         ["ELEM_FAMILY_AND_TYPE_PARAM", "SYMBOL_NAME_PARAM"],
         ["STRUCTURAL_FRAME_CUT_LENGTH", "CURVE_ELEM_LENGTH"], False),
        (SCHED_COVER, DB.BuiltInCategory.OST_GenericModel,
         ["ALL_MODEL_INSTANCE_COMMENTS"], [], True),
    ]
    for name, cat, key_bips, len_bips, use_filter in specs:
        try:
            sch = DB.ViewSchedule.CreateSchedule(doc, DB.ElementId(cat))
            sch.Name = name
            sd = sch.Definition
            kf = _field_by_bip(sd, key_bips)
            if kf is None:
                problems.append(name + u": ไม่พบฟิลด์หลัก")
                continue
            key_field = sd.AddField(kf)
            if use_filter:
                sd.AddFilter(DB.ScheduleFilter(
                    key_field.FieldId, DB.ScheduleFilterType.Contains, MARK))
            sd.AddField(DB.ScheduleFieldType.Count, DB.ElementId.InvalidElementId)
            lf = _field_by_bip(sd, len_bips) if len_bips else None
            if lf is not None:
                f = sd.AddField(lf)
                try:
                    f.DisplayType = DB.ScheduleFieldDisplayType.Totals
                except Exception:
                    pass
            elif len_bips:
                problems.append(name + u": ไม่พบฟิลด์ความยาว")
            sd.AddSortGroupField(DB.ScheduleSortGroupField(key_field.FieldId))
            sd.IsItemized = False
            try:
                sd.ShowGrandTotal = True
            except Exception:
                pass
            made.append(name)
        except Exception as ex:
            problems.append(u"{}: {}".format(name, ex))
    return made, problems


# ------------------------------------------------------------ ฟอร์ม
class QtoForm(ui.RevoWindow):
    def __init__(self, n_frame, n_cover, frame_rows, cover_rows, note):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"QTO ", u"TABLES",
            u"สรุปปริมาณโครงหลังคาและวัสดุมุง — REVOTECH",
            u"สร้างผลลัพธ์", width=640, max_height=720)
        self.tb_info.Text = (u"Structural Framing {} ท่อน · ชิ้นวัสดุมุง Roof Cover {} ชิ้น"
                             .format(n_frame, n_cover))
        self._fill(self.tbl_frame, qc.HEAD_FRAME, frame_rows,
                   [90, 130, 60, 90, 55, 90])
        self._fill(self.tbl_cover, qc.HEAD_COVER, cover_rows, [260, 90, 110])
        self.tb_note.Text = note

    def _fill(self, panel, head, rows, widths):
        from System.Windows.Controls import Grid, TextBlock, ColumnDefinition
        from System.Windows import GridLength, GridUnitType, TextWrapping, Thickness
        if not rows:
            tb = TextBlock()
            tb.Text = u"(ไม่พบข้อมูล)"
            tb.Foreground = self.FindResource("TxtDim")
            panel.Children.Add(tb)
            return
        for ri, row in enumerate([head] + rows):
            g = Grid()
            g.Margin = Thickness(0, 1, 0, 1)
            for w in widths:
                cd = ColumnDefinition()
                cd.Width = GridLength(w, GridUnitType.Pixel)
                g.ColumnDefinitions.Add(cd)
            for ci, cell in enumerate(row):
                tb = TextBlock()
                tb.Text = u"{}".format(cell)
                tb.FontSize = 11
                tb.TextWrapping = TextWrapping.Wrap
                tb.Foreground = self.FindResource(
                    "Accent" if ri == 0 else "TxtMain")
                Grid.SetColumn(tb, ci)
                g.Children.Add(tb)
            panel.Children.Add(g)

    def collect(self):
        return {"sched": bool(self.cb_sched.IsChecked),
                "csv": bool(self.cb_csv.IsChecked)}


# ---------------------------------------------------------------- main
framing = read_framing()
cover = read_cover()
kinds, types, unknown = qc.summarize_framing(framing)
cover_sum = qc.summarize_cover(cover)
frows = qc.frame_rows(kinds, types)
crows = qc.cover_rows(cover_sum)

if not frows and not crows:
    ui.summary(u"REVOTECH — QTO Tables", u"ไม่พบโครงหลังคาหรือวัสดุมุง",
               [u"Structural Framing {} ท่อน (ไม่มีชื่อ type ตรงชนิดใด)".format(len(framing)),
                u"ชิ้นวัสดุมุง Roof Cover: {}".format(len(cover))])
    script.exit()

notes = []
if qc.weight_note(kinds):
    notes.append(qc.weight_note(kinds))
if unknown:
    notes.append(u"ไม่นับ Structural Framing {} ท่อน ใน type ที่ชื่อไม่ตรงชนิด: {}".format(
        sum(unknown.values()), u", ".join(sorted(unknown.keys()))))
if qc.COVER_UNKNOWN in cover_sum:
    notes.append(u"วัสดุมุง {} ชิ้นแยกชนิดไม่ได้ (ไม่ได้ทา material หรือชื่อไม่ตรงคำค้น)".format(
        cover_sum[qc.COVER_UNKNOWN]["pieces"]))

form = QtoForm(len(framing), len(cover), frows, crows, u"\n".join(notes))
v = form.show()
if not v:
    script.exit()

log = [u"Structural Framing {} ท่อน, วัสดุมุง {} ชิ้น".format(len(framing), len(cover))]
log.extend(notes)
log.append(u"แถวโครง:")
log.extend(u"  " + u" | ".join(u"{}".format(c) for c in r) for r in frows)
log.append(u"แถววัสดุมุง:")
log.extend(u"  " + u" | ".join(u"{}".format(c) for c in r) for r in crows)

lines = []
if v["sched"]:
    tg = DB.TransactionGroup(doc, "REVOTECH - QTO Tables")
    tg.Start()
    t = DB.Transaction(doc, "REVOTECH - QTO Tables")
    t.Start()
    try:
        made, problems = make_schedules()
        t.Commit()
        tg.Assimilate()
        for m in made:
            lines.append(u"Schedule: " + m)
        for pr in problems:
            lines.append(u"⚠ " + pr)
        log.extend(problems)
        if made:
            lines.append(u"Ctrl+Z ครั้งเดียว ย้อน Schedule ทั้งชุด")
    except Exception:
        log.append(traceback.format_exc())
        try:
            t.RollBack()
        except Exception:
            pass
        tg.RollBack()
        lines.append(u"⚠ สร้าง Schedule ไม่สำเร็จ (ย้อนกลับแล้ว) ดู log")

if v["csv"]:
    try:
        if not os.path.isdir(ui.LOG_DIR):
            os.makedirs(ui.LOG_DIR)
        p = qc.write_csv(os.path.join(ui.LOG_DIR, "QTO_tables.csv"),
                         qc.csv_tables(kinds, types, cover_sum, unknown))
        lines.append(u"CSV: " + p)
    except Exception as ex:
        lines.append(u"⚠ ส่งออก CSV ไม่สำเร็จ: {}".format(ex))
        log.append(traceback.format_exc())

path = ui.write_log(LOG, log)
tot = [r for r in frows if r[0] == u"รวมโครงหลังคา"]
head = u"✅ สรุปแล้ว"
if tot:
    head += u" — โครง {} ท่อน ยาว {} ม.".format(tot[0][2], tot[0][3])
if notes:
    lines.append(u"มีหมายเหตุ (น้ำหนักไม่ครบ/ไม่นับบางรายการ) ดู log")
ui.summary(u"REVOTECH — QTO Tables", head, lines, path)
