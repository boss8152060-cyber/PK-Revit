# -*- coding: utf-8 -*-
"""บาร์คัท — ตารางตัดเหล็ก + แผนตัดท่อนสต็อก + Excel + ชีต Revit จากเหล็กที่ Comments ขึ้นต้น "PKRevit:"

ขั้นตอน: (เลือกเหล็ก/element ถ้าต้องการเฉพาะที่เลือก) → กดปุ่ม → ตั้งค่า → สร้าง
- อ่านรูปเหล็กจาก Rebar.GetCenterlineCurves (ตัดรัศมีโค้งทิ้ง = ความยาวแนวศูนย์กลางแบบมุมแหลม)
- จัดกลุ่มเป็นเลขบาร์ (ขนาด, รูปทรง, ความยาวตัดปัด 5 มม.) แล้วเขียนเลขลงพารามิเตอร์ Mark
- Transaction เดียว (สร้างชีต/ตารางทั้งหมดอยู่ใน Transaction เดียว Ctrl+Z ย้อนทั้งชุด)
- ส่งออก .xlsx/.csv หลัง commit (ไฟล์ไม่เกี่ยวกับ Undo)
คำนวณทั้งหมดอยู่ใน bar_cut_calc.py / bar_cut_export.py (ทดสอบนอก Revit ได้)
ยังไม่เคยรันใน Revit — ดูข้อจำกัดใน docs/accept-bar-cut.md
"""

import os
import sys
import math
import traceback
from pyrevit import revit, DB, forms, script

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bar_cut_calc as bc  # noqa: E402
import bar_cut_export as ex  # noqa: E402

from revotech import ui  # noqa: E402
from revotech.rvt import ename, id_value  # noqa: E402
from revotech.units import ft_to_mm  # noqa: E402

doc = revit.doc
uidoc = revit.uidoc
SHEET_NAME_PREFIX = u"บาร์คัท"
SCHED_NAME_PREFIX = u"PK Revit BarCut"
LOG = "BarCut.txt"
COMMENTS = DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS


# ------------------------------------------------------------ อ่านเหล็ก
def _comment(r):
    p = r.get_Parameter(COMMENTS)
    return (p.AsString() or u"") if p is not None else u""


def read_shape(rebar):
    """(shape_signature, length_mm) ของเหล็ก 1 เส้นในชุด — None ถ้าอ่านไม่ได้"""
    curves = rebar.GetCenterlineCurves(
        False, False, True,
        DB.Structure.MultiplanarOption.IncludeAllMultiplanarCurves, 0)
    segs = []
    prev_dir = None
    for c in curves:
        ln = ft_to_mm(c.Length)
        if isinstance(c, DB.Line):
            d = c.Direction
        else:
            d = None
        segs.append([ln, 0.0, d])
    if not segs:
        return None
    for i in range(len(segs) - 1):
        a, b = segs[i][2], segs[i + 1][2]
        if a is not None and b is not None:
            dot = max(-1.0, min(1.0, a.DotProduct(b)))
            segs[i][1] = math.degrees(math.acos(dot))
    total = sum(s[0] for s in segs)
    sig = bc.shape_signature([(s[0], s[1]) for s in segs])
    return sig, total


def n_bars(rebar):
    try:
        return int(rebar.NumberOfBarPositions)
    except Exception:
        try:
            return int(rebar.Quantity)
        except Exception:
            return 1


def collect(scope_sel, kinds, log):
    """คืน (list ของ dict {rebar, size, shape, length_mm, count, kind, host}, ข้ามกี่เส้น)"""
    rebars = []
    if scope_sel:
        ids = set(id_value(i) for i in uidoc.Selection.GetElementIds())
        for r in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar):
            try:
                if id_value(r.Id) in ids or id_value(r.GetHostId()) in ids:
                    rebars.append(r)
            except Exception:
                continue
    else:
        rebars = list(DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar))
    recs = []
    skipped = 0
    for r in rebars:
        kind = bc.parse_kind(_comment(r))
        if kind is None or kind not in kinds:
            continue
        try:
            got = read_shape(r)
            if got is None:
                raise ValueError("no curves")
            sig, ln = got
            size = ename(doc.GetElement(r.GetTypeId()))
            recs.append({"rebar": r, "size": size, "shape": sig, "length_mm": ln,
                         "count": n_bars(r), "kind": kind,
                         "host": id_value(r.GetHostId())})
        except Exception as e:
            skipped += 1
            log.append(u"ข้ามเหล็ก id {}: {}".format(id_value(r.Id), e))
    return recs, skipped


# ------------------------------------------------------------ ชีต/ตาราง
def title_blocks():
    d = {}
    for t in DB.FilteredElementCollector(doc).OfCategory(
            DB.BuiltInCategory.OST_TitleBlocks).WhereElementIsElementType():
        try:
            fam = t.FamilyName
        except Exception:
            fam = u""
        d[u"{} : {}".format(fam, ename(t))] = t
    return d


def _field_by_bip(sched_def, bip_names):
    """SchedulableField ที่ ParameterId ตรง BuiltInParameter ตัวแรกที่มีจริง"""
    want = []
    for n in bip_names:
        b = getattr(DB.BuiltInParameter, n, None)
        if b is not None:
            want.append(int(b))
    for sf in sched_def.GetSchedulableFields():
        try:
            if id_value(sf.ParameterId) in want:
                return sf
        except Exception:
            continue
    return None


def make_schedule(kind, title):
    """Schedule ของ Rebar กรอง Comments มี 'PKRevit:<kind>' จัดกลุ่มตาม Mark
    คืน ViewSchedule (หรือ None ถ้า API ไม่ให้) พร้อมรายชื่อคอลัมน์ที่ใส่ไม่ได้"""
    sched = DB.ViewSchedule.CreateSchedule(
        doc, DB.ElementId(DB.BuiltInCategory.OST_Rebar))
    sched.Name = title
    sd = sched.Definition
    missing = []
    cols = [(u"Mark", ["ALL_MODEL_MARK"]),
            (u"Bar Diameter", ["REBAR_BAR_DIAMETER"]),
            (u"Bar Length", ["REBAR_ELEM_LENGTH"]),
            (u"Quantity", ["REBAR_ELEM_QUANTITY_OF_BARS"]),
            (u"Total Bar Length", ["REBAR_ELEM_TOTAL_LENGTH"])]
    fields = {}
    for nm, bips in cols:
        sf = _field_by_bip(sd, bips)
        if sf is None:
            missing.append(nm)
            continue
        fields[nm] = sd.AddField(sf)
    cf = _field_by_bip(sd, ["ALL_MODEL_INSTANCE_COMMENTS"])
    if cf is not None:
        f = sd.AddField(cf)
        sd.AddFilter(DB.ScheduleFilter(
            f.FieldId, DB.ScheduleFilterType.Contains, bc.PREFIX + kind))
        f.IsHidden = True
    else:
        missing.append(u"Comments(ตัวกรอง)")
    if u"Mark" in fields:
        sd.AddSortGroupField(DB.ScheduleSortGroupField(fields[u"Mark"].FieldId))
    sd.IsItemized = False
    return sched, missing


def place_on_sheet(sheet, view_id, x_off=0.0):
    try:
        o = sheet.Outline
        x, y = o.Min.U + 0.15 + x_off, o.Max.V - 0.15
    except Exception:
        x, y = 0.15, 1.0
    return DB.ScheduleSheetInstance.Create(doc, sheet.Id, view_id, DB.XYZ(x, y, 0))


def add_note(sheet, text):
    try:
        o = sheet.Outline
        pt = DB.XYZ(o.Min.U + 0.15, o.Min.V + 0.9, 0)
    except Exception:
        pt = DB.XYZ(0.15, 0.5, 0)
    tid = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
    DB.TextNote.Create(doc, sheet.Id, pt, text, tid)


# ------------------------------------------------------------ ฟอร์ม
class BarCutForm(ui.RevoWindow):
    def __init__(self, n_total, counts, tbs):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"BAR ", u"CUT",
            u"ตารางตัดเหล็ก + แผนตัดท่อนสต็อก + ชีต + Excel — PK Revit",
            u"สร้างบาร์คัท", max_height=700)
        self.tbs = tbs
        self.tb_info.Text = u"เหล็ก PK Revit ในโมเดล {} ชิ้น ({})".format(
            n_total, u" · ".join(u"{} {}".format(bc.KIND_LABEL[k], counts.get(k, 0))
                                 for k in bc.KINDS))
        ui.combo_fill(self.cmb_stock, [u"10", u"12"], u"10")
        ui.combo_fill(self.cmb_fmt, [u"Excel (.xlsx)", u"CSV (UTF-8 BOM)"])
        names = sorted(tbs.keys())
        ui.combo_fill(self.cmb_tb, names)
        if not names:
            self.cb_sheet.IsChecked = False
            self.cb_sheet.IsEnabled = False
            self.cmb_tb.IsEnabled = False
            self.tb_warn.Text = (u"ไม่พบ Title Block ในโปรเจกต์ — จะข้ามการสร้างชีต "
                                 u"(ยังได้ตาราง/Excel)")

    def collect(self):
        kinds = [k for k in bc.KINDS
                 if getattr(self, "cb_" + k).IsChecked]
        if not kinds:
            self.tb_warn.Text = u"เลือกชนิดงานอย่างน้อย 1 ชนิด"
            return None
        tb = self.cmb_tb.SelectedItem
        return {
            "sel": bool(self.rb_sel.IsChecked), "kinds": kinds,
            "stock": float(self.cmb_stock.SelectedItem),
            "kerf": max(0.0, ui.num(self.tb_kerf.Text, bc.DEFAULT_KERF_MM)),
            "sheet": bool(self.cb_sheet.IsChecked) and tb is not None,
            "tb": self.tbs.get(tb) if tb else None,
            "replace": bool(self.cb_replace.IsChecked),
            "mark": bool(self.cb_mark.IsChecked),
            "excel": bool(self.cb_excel.IsChecked),
            "csv": self.cmb_fmt.SelectedIndex == 1}


# ------------------------------------------------------------ main
log = []
all_recs = []
counts = {}
for r in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar):
    k = bc.parse_kind(_comment(r))
    if k in bc.KINDS:
        counts[k] = counts.get(k, 0) + 1
        all_recs.append(r)
if not all_recs:
    forms.alert(u"ไม่พบเหล็กที่ Comments ขึ้นต้น PKRevit: ในโมเดล — สร้างเหล็กด้วยปุ่ม "
                u"Rebar เสา/คาน/ฐานราก/พื้น/บันได ก่อน", title=u"PK Revit",
                exitscript=True)

form = BarCutForm(len(all_recs), counts, title_blocks())
v = form.show()
if v is None:
    script.exit()

recs, skipped = collect(v["sel"], v["kinds"], log)
if not recs:
    forms.alert(u"ไม่มีเหล็กตามขอบเขตที่เลือก" +
                (u" (เลือก element/เหล็กในโมเดลก่อน)" if v["sel"] else u""),
                title=u"PK Revit", exitscript=True)

rows = bc.group_bars(recs)
plan = bc.cutting_plan(rows, v["stock"], v["kerf"])
hosts = len(set(r["host"] for r in recs))
st = bc.summary_totals(rows, plan, hosts)
line = bc.summary_text(st)
no_by_key = dict(((r["size"], r["shape"], r["length_mm"]), r["no"]) for r in rows)
kinds_present = [k for k in bc.KINDS if any(r["kind"] == k for r in recs)]

xlsx_path = None
if v["excel"]:
    ext = "csv" if v["csv"] else "xlsx"
    xlsx_path = forms.save_file(file_ext=ext, default_name=u"BarCut." + ext)

notes = []
made_sheets = []
t = DB.Transaction(doc, "PK Revit - บาร์คัท")
t.Start()
try:
    deleted_numbers = set()
    if v["replace"]:
        old = []
        for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
            if ename(s).startswith(SHEET_NAME_PREFIX):
                deleted_numbers.add(s.SheetNumber)
                old.append(s.Id)
        for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
            if ename(s).startswith(SCHED_NAME_PREFIX):
                old.append(s.Id)
        for i in old:
            try:
                doc.Delete(i)
            except Exception:
                pass
        log.append(u"ลบชีต/ตารางบาร์คัทเดิม {} รายการ".format(len(old)))

    if v["mark"]:
        for r in recs:
            key = (r["size"], r["shape"], bc.round_len(r["length_mm"]))
            p = r["rebar"].get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
            if p is not None and not p.IsReadOnly:
                p.Set(str(no_by_key[key]))

    if v["sheet"]:
        existing = set(s.SheetNumber for s in
                       DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)
                       if s.SheetNumber not in deleted_numbers)
        nums = bc.sheet_numbers(kinds_present, existing)
        tb_id = v["tb"].Id
        for k in kinds_present:
            sh = DB.ViewSheet.Create(doc, tb_id)
            sh.SheetNumber = nums[k]
            sh.Name = u"{} {}".format(SHEET_NAME_PREFIX, bc.KIND_LABEL[k])
            kr = [r for r in recs if r["kind"] == k]
            kg = sum(r["length_mm"] * r["count"] / 1000.0 * bc.unit_weight(r["size"])
                     for r in kr)
            if v["mark"]:
                try:
                    sched, miss = make_schedule(
                        k, u"{} {} {}".format(SCHED_NAME_PREFIX, bc.KIND_LABEL[k],
                                              nums[k]))
                    place_on_sheet(sh, sched.Id)
                    if miss:
                        notes.append(u"{}: ตารางไม่มีคอลัมน์ {}".format(
                            nums[k], u", ".join(miss)))
                except Exception as e:
                    notes.append(u"{}: สร้าง Schedule ไม่ได้ ({})".format(nums[k], e))
            else:
                notes.append(u"{}: ไม่ได้เขียน Mark จึงไม่สร้าง Schedule".format(nums[k]))
            add_note(sh, u"{}: เหล็ก {} เส้น · {:,.0f} กก.".format(
                bc.KIND_LABEL[k], sum(r["count"] for r in kr), kg))
            made_sheets.append(nums[k])
        # ชีตสรุปรวม
        sh = DB.ViewSheet.Create(doc, tb_id)
        sh.SheetNumber = nums["all"]
        sh.Name = SHEET_NAME_PREFIX + u" สรุปรวม"
        txt = [line, u"ท่อนสต็อก {:g} ม. · เผื่อรอยตัด {:g} มม.".format(
            plan["stock_m"], plan["kerf_mm"])]
        for s in plan["by_size"]:
            txt.append(u"{}: สั่ง {} ท่อน · เศษ {:.1f}%".format(
                s["size"], s["n_stock"], s["waste_pct"]))
        add_note(sh, u"\n".join(txt))
        made_sheets.append(nums["all"])
    t.Commit()
except Exception:
    log.append(traceback.format_exc())
    try:
        t.RollBack()
    except Exception:
        pass
    path = ui.write_log(LOG, log)
    ui.summary(u"PK Revit — บาร์คัท", u"❌ เกิดข้อผิดพลาด — ย้อนกลับทั้งหมดแล้ว", [], path)
    script.exit()

export_msg = u""
if xlsx_path:
    try:
        tabs = ex.build_tables(rows, plan, line)
        if v["csv"]:
            ex.write_csv(xlsx_path, tabs)
        else:
            ex.write_xlsx(xlsx_path, tabs)
        export_msg = u"ส่งออก: " + xlsx_path
    except Exception as e:
        export_msg = u"ส่งออกไฟล์ไม่สำเร็จ: {}".format(e)
        log.append(traceback.format_exc())
elif v["excel"]:
    export_msg = u"ยกเลิกการเลือกไฟล์ — ไม่ส่งออก"

# log รายละเอียดเต็ม
log.append(line)
log.append(u"ข้ามเหล็กที่อ่านไม่ได้ {} เส้น".format(skipped))
for r in rows:
    log.append(u"เลข {:>3} {:<5} {:<28} x{:<5} ตัด {:>7.0f} มม. รวม {:>8.2f} ม. {:>8.2f} กก."
               .format(r["no"], r["size"], bc.shape_label(r["shape"]), r["count"],
                       r["length_mm"], r["total_m"], r["weight_kg"]))
for p in plan["patterns"]:
    log.append(u"แผนตัด {} แบบ {} x{}: {} เศษ {:.0f} มม.".format(
        p["size"], p["name"], p["n"],
        u" + ".join(u"{:.0f}".format(x) for x in p["pieces"]), p["waste_mm"]))
for s in plan["by_size"]:
    if s["oversize"]:
        log.append(u"{}: ชิ้นยาวเกินสต็อก (ต้องต่อทาบ ไม่ได้นับในแผน): {}".format(
            s["size"], u", ".join(u"{:.0f}".format(x) for x in s["oversize"])))
for n in notes:
    log.append(u"หมายเหตุ: " + n)
path = ui.write_log(LOG, log)

tt = plan["total"]
lines = [u"เศษ {:.1f}% ตามความยาว · {:.1f}% ตามน้ำหนัก".format(
    tt["waste_pct_len"], tt["waste_pct_kg"])]
if tt["oversize"]:
    lines.append(u"⚠ มี {} ชิ้นยาวเกินท่อนสต็อก (ต้องต่อทาบ) ไม่นับในแผนตัด".format(
        tt["oversize"]))
if made_sheets:
    lines.append(u"ชีต: " + u", ".join(made_sheets))
elif v["sheet"] is False:
    lines.append(u"ไม่สร้างชีต (ไม่มี Title Block หรือไม่ได้เลือก)")
lines += notes
if skipped:
    lines.append(u"ข้ามเหล็กที่อ่านรูปไม่ได้ {} เส้น".format(skipped))
if export_msg:
    lines.append(export_msg)
lines.append(u"Ctrl+Z ครั้งเดียว ย้อนทั้งชุด (ไม่รวมไฟล์ที่ส่งออก)")
ui.summary(u"PK Revit — บาร์คัท", u"✅ " + line, lines, path)
