# -*- coding: utf-8 -*-
"""Rebar เสา — ใส่เหล็กยืน + ปลอก ให้เสาคอนกรีตที่เลือก

ขั้นตอน: เลือกเสา (Structural Columns) → กดปุ่ม → ตั้งค่าในฟอร์ม → สร้าง
- เหล็กยืน n เส้น (4,6,...,16) เรียงรอบหน้าตัดสี่เหลี่ยม ปลายล่างเสมอตัวเสา
  ปลายบนยื่นเหนือเสาตามระยะทาบ
- ปลอกสี่เหลี่ยมปลาย 135° แยกโซน: โซนปลาย (ล่าง/บน) ถี่, กลางเสา ห่างกว่า
- Transaction เดียว Ctrl+Z ย้อนทั้งชุด; เหล็กที่สร้างมี Comments = "PKRevit:column"
  เพื่อให้ "แทนที่ของเดิม" ลบเฉพาะของเรา

สมมติ: หน้าตัดสี่เหลี่ยม แกนเสาตั้ง (local Z ของ instance ชี้ขึ้น)
ค่ามาตรฐาน (ตะขอ 135°, ระยะทาบ) เป็นค่าตั้งต้นจาก revotech.rebar — ต้องยืนยัน
"""

import os
import traceback
from pyrevit import revit, DB, forms, script

from revotech import rebar as rb
from revotech import hostconfig
from revotech import ui
from revotech.rvt import ename, id_value, selected, type_name
from revotech.units import mm_to_ft, ft_to_mm

doc = revit.doc
uidoc = revit.uidoc
MARK = u"PKRevit:column"


# ---------------------------------------------------------------- geometry
def local_extents(inst):
    """ขอบเขตหน้าตัด/ความสูงของเสาใน local frame ของ instance (หน่วยฟุต)
    คืน (tf, xmin, xmax, ymin, ymax, zmin, zmax) หรือ None"""
    tf = inst.GetTransform()
    inv = tf.Inverse
    opts = DB.Options()
    opts.DetailLevel = DB.ViewDetailLevel.Fine
    pts = []
    geom = inst.get_Geometry(opts)
    if geom is None:
        return None
    for g in geom:
        items = g.GetInstanceGeometry() if isinstance(g, DB.GeometryInstance) \
            else [g]
        for s in items:
            if isinstance(s, DB.Solid) and s.Volume > 0:
                for e in s.Edges:
                    c = e.AsCurve()
                    pts.append(c.GetEndPoint(0))
                    pts.append(c.GetEndPoint(1))
    if not pts:
        return None
    loc = [inv.OfPoint(p) for p in pts]
    xs = [p.X for p in loc]
    ys = [p.Y for p in loc]
    zs = [p.Z for p in loc]
    return tf, min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def side_counts(extra_pairs, w, h):
    """แบ่งเหล็กเสริมกลางด้านให้ด้านที่ห่างกว่าก่อน → (ต่อด้านขนาน x, ต่อด้านขนาน y)"""
    nx = ny = 0
    for _ in range(extra_pairs):
        if w / (nx + 1.0) >= h / (ny + 1.0):
            nx += 1
        else:
            ny += 1
    return nx, ny


def main_positions(n, x0, x1, y0, y1):
    """ตำแหน่ง (x,y) เหล็กยืนบนสี่เหลี่ยม [x0,x1]x[y0,y1] (n เลขคู่ ≥4)"""
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    nx, ny = side_counts(max((n - 4) // 2, 0), x1 - x0, y1 - y0)
    for i in range(1, nx + 1):
        x = x0 + (x1 - x0) * i / (nx + 1.0)
        pts.append((x, y0))
        pts.append((x, y1))
    for j in range(1, ny + 1):
        y = y0 + (y1 - y0) * j / (ny + 1.0)
        pts.append((x0, y))
        pts.append((x1, y))
    return pts


# ---------------------------------------------------------------- form
class ColumnForm(ui.RevoWindow):
    def __init__(self, n_sel, bar_types):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"REBAR ", u"เสา",
            u"ใส่เหล็กยืน + ปลอก ให้เสาที่เลือก — PK Revit",
            u"สร้างเหล็กเสา")
        self.bar_types = bar_types
        self.tb_info.Text = u"เสาที่เลือก: {} ต้น".format(n_sel)
        ui.combo_fill(self.cmb_n, [4, 6, 8, 10, 12, 14, 16], 4)
        have = rb.names_in_project(bar_types)
        ui.combo_fill(self.cmb_main, have or rb.MAIN_BAR_NAMES, u"DB16"
                      if u"DB16" in have else None)
        have_t = rb.names_in_project(bar_types)
        ui.combo_fill(self.cmb_tie, have_t or rb.TIE_BAR_NAMES, u"RB9"
                      if u"RB9" in have_t else None)
        self._check()

    def _check(self):
        missing = [] if self.bar_types else [u"(ไม่มี Bar Type เลย)"]
        if missing:
            self.tb_check.Text = (u"✗ ไม่พบ Rebar Bar Type ในโปรเจกต์: {} — "
                                  u"สร้าง/โหลดใน Structure > Reinforcement "
                                  u"Settings ก่อน (ขนาดที่ไม่ได้ใช้ไม่เป็นไร)"
                                  .format(u", ".join(missing)))
        else:
            self.tb_check.Text = u"✓ พบ Rebar Bar Type {} ชนิดในโปรเจกต์".format(len(self.bar_types))

    def collect(self):
        main = self.cmb_main.SelectedItem
        tie = self.cmb_tie.SelectedItem
        if main not in self.bar_types or tie not in self.bar_types:
            self.tb_check.Text = (u"✗ ขนาดเหล็กที่เลือก ({} / {}) ยังไม่มี Bar Type "
                                  u"ในโปรเจกต์".format(main, tie))
            return None
        return {
            "same": bool(self.cb_same.IsChecked),
            "replace": bool(self.cb_replace.IsChecked),
            "n": int(self.cmb_n.SelectedItem),
            "main": main,
            "tie": tie,
            "lap_d": ui.num(self.tb_lap.Text, rb.LAP_D),
            "sp_mid": ui.num(self.tb_sp_mid.Text, 0.15) * 1000.0,
            "sp_end": ui.num(self.tb_sp_end.Text, 0.10) * 1000.0,
            "end_len": ui.num(self.tb_end_len.Text, 0.60) * 1000.0,
            "cover": ui.num(self.tb_cover.Text, 0.025) * 1000.0,
        }


# ---------------------------------------------------------------- main
try:
    _OVR = CONFIG_OVERRIDE      # Propagate Rebar: รันโดยไม่เปิดฟอร์ม
except NameError:
    _OVR = None

types = rb.bar_types(doc)
if _OVR is None:
    cols = selected(uidoc, doc, DB.BuiltInCategory.OST_StructuralColumns)
    if not cols:
        ui.need_selection(u"เสา", u"(คลิกเสาที่ต้องการ แล้วกดปุ่มใหม่ — เลือกได้หลายต้น)")
    form = ColumnForm(len(cols), types)
    v = form.show()
    if not v:
        script.exit()
else:
    cols = hostconfig.hosts_from_override(doc, _OVR)
    v, _miss = hostconfig.override_values(_OVR, rb.BAR_NAMES, types)
    _prob = hostconfig.override_problem(cols, _miss)
    if _prob:
        forms.alert(_prob, title=u"PK Revit — Rebar เสา", exitscript=True)

# ขยายเป็นเสาชื่อ type เดียวกันทั้งอาคาร (ถ้าติ๊ก)
if v["same"]:
    names = set(type_name(doc, c) for c in cols)
    allc = DB.FilteredElementCollector(doc) \
        .OfCategory(DB.BuiltInCategory.OST_StructuralColumns) \
        .WhereElementIsNotElementType().ToElements()
    cols = [c for c in allc if type_name(doc, c) in names]

main_t = types[v["main"]]
tie_t = types[v["tie"]]
d_main = rb.bar_dia_mm(v["main"])
d_tie = rb.bar_dia_mm(v["tie"])
cover = v["cover"]
log = []
made_main = made_tie = failed = 0
skipped = []

tg = DB.TransactionGroup(doc, "PK Revit - Rebar เสา")
tg.Start()
t = DB.Transaction(doc, "PK Revit - Rebar เสา")
t.Start()
try:
    # ลบของเดิม
    if v["replace"]:
        host_ids = set(id_value(c.Id) for c in cols)
        old = []
        for r in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar):
            try:
                if id_value(r.GetHostId()) not in host_ids:
                    continue
                p = r.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if p is not None and (p.AsString() or u"").startswith(MARK):
                    old.append(r.Id)
            except Exception:
                continue
        for rid in old:
            doc.Delete(rid)
        log.append(u"ลบเหล็กเดิม {} ชิ้น".format(len(old)))

    hook135, _new = rb.hook_type(doc, 135, rb.HOOK135_EXT_D)
    lap = mm_to_ft(v["lap_d"] * d_main)
    inset_main = mm_to_ft(cover + d_tie + d_main / 2.0)
    inset_tie = mm_to_ft(cover + d_tie / 2.0)
    cov_ft = mm_to_ft(cover)

    for col in cols:
        label = u"{} id {}".format(ename(col), id_value(col.Id))
        ext = local_extents(col)
        if ext is None:
            skipped.append(label + u" (อ่านรูปทรงไม่ได้)")
            continue
        tf, x0, x1, y0, y1, z0, z1 = ext
        w, h, H = (x1 - x0), (y1 - y0), (z1 - z0)
        if min(w, h) <= 2 * inset_main or H <= 2 * cov_ft:
            skipped.append(label + u" (หน้าตัด/ความสูงเล็กเกินไป)")
            continue

        def P(x, y, z):
            return tf.OfPoint(DB.XYZ(x, y, z))

        created = []
        # --- เหล็กยืน
        for (x, y) in main_positions(v["n"], x0 + inset_main, x1 - inset_main,
                                     y0 + inset_main, y1 - inset_main):
            r = rb.create(doc, col, main_t,
                          [rb.line(P(x, y, z0), P(x, y, z1 + lap))],
                          tf.BasisX)
            if r is None:
                failed += 1
            else:
                made_main += 1
                created.append(r)

        # --- ปลอก (3 โซน)
        a, b = x0 + inset_tie, x1 - inset_tie
        c, d = y0 + inset_tie, y1 - inset_tie
        end_len = mm_to_ft(v["end_len"])
        sp_e, sp_m = v["sp_end"], v["sp_mid"]
        zs, ze = z0 + cov_ft, z1 - cov_ft
        zones = []   # (z เริ่ม, ยาว ฟุต, ระยะเรียง mm)
        if ze - zs > 2 * end_len + mm_to_ft(sp_m):
            zones.append((zs, end_len, sp_e))
            zm = zs + end_len + mm_to_ft(sp_m)
            zt = ze - end_len
            if zt - zm > 0:
                zones.append((zm, zt - zm - mm_to_ft(sp_m), sp_m))
            zones.append((zt, end_len, sp_e))
        else:
            zones.append((zs, ze - zs, sp_m))
        for (zz, ln, sp) in zones:
            loop = [rb.line(P(a, c, zz), P(b, c, zz)),
                    rb.line(P(b, c, zz), P(b, d, zz)),
                    rb.line(P(b, d, zz), P(a, d, zz)),
                    rb.line(P(a, d, zz), P(a, c, zz))]
            r = rb.create(doc, col, tie_t, loop, tf.BasisZ,
                          style=DB.Structure.RebarStyle.StirrupTie,
                          hook_start=hook135, hook_end=hook135)
            if r is None:
                failed += 1
                continue
            made_tie += 1
            if ln > mm_to_ft(sp):
                rb.layout_max_spacing(r, sp, ft_to_mm(ln))
            created.append(r)

        for r in created:
            p = r.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p is not None and not p.IsReadOnly:
                p.Set(MARK)
        if created:
            hostconfig.save(col, "column", v)   # จำค่าไว้ที่เสาต้นนี้ (ให้ Propagate)
        log.append(u"{}: เหล็กยืน {} เส้น, ปลอก {} ชุด, ขนาดหน้าตัด {:.0f}x{:.0f} มม. สูง {:.0f} มม."
                   .format(label, v["n"], len(zones), ft_to_mm(w), ft_to_mm(h),
                           ft_to_mm(H)))
    t.Commit()
    tg.Assimilate()
except Exception:
    log.append(traceback.format_exc())
    try:
        t.RollBack()
    except Exception:
        pass
    tg.RollBack()
    path = ui.write_log("Rebar_column.txt", log)
    ui.summary(u"PK Revit — Rebar เสา", u"❌ เกิดข้อผิดพลาด — ย้อนกลับทั้งหมดแล้ว",
               [], path)
    script.exit()

for s in skipped:
    log.append(u"ข้าม: " + s)
path = ui.write_log("Rebar_column.txt", log)
head = u"✅ ใส่เหล็กแล้ว {} ต้น".format(len(cols) - len(skipped))
if failed:
    head += u" (มี {} ชิ้นสร้างไม่สำเร็จ)".format(failed)
ui.summary(u"PK Revit — Rebar เสา", head,
           [u"เหล็กยืน {} เส้น".format(made_main),
            u"ปลอก {} ชุด".format(made_tie)] +
           ([u"ข้าม {} ต้น".format(len(skipped))] if skipped else []) +
           [u"Ctrl+Z ครั้งเดียว ย้อนทั้งชุด"], path)
