# -*- coding: utf-8 -*-
"""Rebar ฐานราก — ใส่ตะแกรงเหล็กล่าง + เหล็กรัดรอบ ให้ฐานรากที่เลือก

ขั้นตอน: เลือกฐานราก (Structural Foundations) → กดปุ่ม → ตั้งค่าในฟอร์ม → สร้าง
- ฐานสี่เหลี่ยม (F1P/F2/F4): ตะแกรงล่าง 2 ทิศ ตามด้านยาว/ด้านสั้น (ขนาด+จำนวน)
- ฐานสามเหลี่ยม 3 เสาเข็ม: เหล็ก 3 ทิศ 0°/60°/120° ขนาด/จำนวนต่อทิศ
- ตะขอ 3 แบบ (เลือก 1), เหล็กรัดรอบ (ไม่บังคับ), ระยะหุ้ม
- Transaction เดียว Ctrl+Z ย้อนทั้งชุด; เหล็กมี Comments = "PKRevit:footing"
  เพื่อให้ "แทนที่ของเดิม" ลบเฉพาะของเรา

ชนิดฐานราก (สี่เหลี่ยม/สามเหลี่ยม) ตัดสินจากรูปผังด้านล่างของ geometry ไม่ใช่จากชื่อ type
สมมติ: ฐานรากแกน Z ตั้ง, ผิวล่างเป็นระนาบ; ผังนูน 3 หรือ 4 มุม (4 มุมต้องเป็นสี่เหลี่ยมมุมฉาก)
คำนวณทั้งหมดอยู่ใน footing_calc.py (ทดสอบนอก Revit ได้) ค่ามาตรฐานต้องให้วิศวกรยืนยัน
"""

import os
import sys
import traceback
from pyrevit import revit, DB, forms, script

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import footing_calc as fc  # noqa: E402

from revotech import rebar as rb  # noqa: E402
from revotech import rebaropts as ro  # noqa: E402
from revotech import hostconfig  # noqa: E402
from revotech import ui  # noqa: E402
from revotech import formpreview as fpv  # noqa: E402
from revotech.rvt import ename, id_value, selected, type_name  # noqa: E402
from revotech.units import mm_to_ft, ft_to_mm  # noqa: E402

doc = revit.doc
uidoc = revit.uidoc
MARK = u"PKRevit:footing"


# ---------------------------------------------------------------- geometry
def _solids(inst):
    opts = DB.Options()
    opts.DetailLevel = DB.ViewDetailLevel.Fine
    geom = inst.get_Geometry(opts)
    out = []
    if geom is None:
        return out
    for g in geom:
        items = g.GetInstanceGeometry() if isinstance(g, DB.GeometryInstance) \
            else [g]
        for s in items:
            if isinstance(s, DB.Solid) and s.Volume > 0:
                out.append(s)
    return out


def footprint(inst):
    """ผังฐานราก (local, มม., CCW) + ความสูง (มม.) + z ผิวล่าง (ฟุต, local)
    คืน dict {tf, poly, height, z0} หรือ None"""
    tf = inst.GetTransform()
    inv = tf.Inverse
    solids = _solids(inst)
    if not solids:
        return None
    zs = []
    best = None   # (z, -area, face)
    for s in solids:
        for e in s.Edges:
            c = e.AsCurve()
            for i in (0, 1):
                zs.append(inv.OfPoint(c.GetEndPoint(i)).Z)
        for f in s.Faces:
            if not isinstance(f, DB.PlanarFace):
                continue
            n = inv.OfVector(f.FaceNormal)
            if n.Z < -0.99:
                z = inv.OfPoint(f.Origin).Z
                key = (round(z, 4), -f.Area)
                if best is None or key < best[0]:
                    best = (key, f)
    if not zs:
        return None
    z0, z1 = min(zs), max(zs)
    pts = None
    if best is not None:
        loops = best[1].GetEdgesAsCurveLoops()
        if loops and loops.Count > 0:
            pts = []
            for c in loops[0]:
                p = inv.OfPoint(c.GetEndPoint(0))
                pts.append((ft_to_mm(p.X), ft_to_mm(p.Y)))
    if pts is None:
        # สำรอง: กรอบสี่เหลี่ยมจาก bounding ใน local frame
        xs, ys = [], []
        for s in solids:
            for e in s.Edges:
                c = e.AsCurve()
                for i in (0, 1):
                    p = inv.OfPoint(c.GetEndPoint(i))
                    xs.append(p.X)
                    ys.append(p.Y)
        pts = [(ft_to_mm(min(xs)), ft_to_mm(min(ys))),
               (ft_to_mm(max(xs)), ft_to_mm(min(ys))),
               (ft_to_mm(max(xs)), ft_to_mm(max(ys))),
               (ft_to_mm(min(xs)), ft_to_mm(max(ys)))]
    poly = fc.clean_polygon(pts)
    return {"tf": tf, "poly": poly, "kind": fc.classify(poly),
            "height": ft_to_mm(z1 - z0), "z0": z0}


# ---------------------------------------------------------------- form
class FootingForm(ui.RevoWindow):
    def __init__(self, n_sel, n_rect, n_tri, n_other, bar_types, preview_shape=None,
                 shapes=None):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"REBAR ", u"ฐานราก",
            u"ใส่ตะแกรงเหล็กล่าง + เหล็กรัดรอบ ให้ฐานรากที่เลือก — PK Revit",
            u"สร้างเหล็กฐานราก", max_height=680, preview=True)
        self.bar_types = bar_types
        self.n_sel = n_sel
        self.preview_shape = preview_shape   # {poly,kind,height} ของฐานแรก หรือ None
        self.has_rect = n_rect > 0
        self.has_tri = n_tri > 0
        info = u"ฐานรากที่เลือก: {} ฐาน (สี่เหลี่ยม {} · สามเหลี่ยม {})".format(
            n_sel, n_rect, n_tri)
        if n_other:
            info += u" · รูปทรงที่ยังไม่รองรับ {} (จะข้าม)".format(n_other)
        self.tb_info.Text = info
        from System.Windows import Visibility as vis
        self.sp_rect.Visibility = vis.Visible if self.has_rect else vis.Collapsed
        self.sp_tri.Visibility = vis.Visible if self.has_tri else vis.Collapsed

        have_main = rb.names_in_project(bar_types)
        have_ring = rb.names_in_project(bar_types)
        # ไม่มีค่าตั้งต้น: ต้องเลือกเอง ไม่งั้นด่านตรวจขึ้น ✗
        main_items = [fc.PLACEHOLDER] + (have_main or rb.MAIN_BAR_NAMES)
        ring_items = [fc.PLACEHOLDER] + (have_ring or rb.TIE_BAR_NAMES)
        self.main_cmbs = [self.cmb_long, self.cmb_short,
                          self.cmb_t0, self.cmb_t60, self.cmb_t120]
        for c in self.main_cmbs:
            ui.combo_fill(c, main_items)
            c.SelectionChanged += self._changed
        ui.combo_fill(self.cmb_ring, ring_items)
        self.cmb_ring.SelectionChanged += self._changed
        for tb in (self.tb_long_n, self.tb_short_n, self.tb_t0_n, self.tb_t60_n,
                   self.tb_t120_n, self.tb_ring_n, self.tb_ring_sp, self.tb_cover):
            tb.TextChanged += self._changed
        for r in (self.rb_h1, self.rb_h2, self.rb_h3, self.cb_ring):
            r.Click += self._changed
        sh_main, sh_tie = shapes or ((), ())
        ro.fill(self, list(sh_main), list(sh_tie), hooks=False, stagger=False)
        self._check()
        fpv.bind(self, self._scene,
                 lambda: fpv.footing_preview(fc, self.preview_shape, self._read_safe(), self.n_sel))

    def _changed(self, sender, args):
        self._check()

    def _read_safe(self):
        try:
            return self._read()
        except Exception:
            return {"long": (None, 0), "short": (None, 0), "tri": {}, "hook": None,
                    "ring": (False, None, 0, 0), "cover": 0}

    def _scene(self):
        """ภาพประมาณของฐานรากแรก — ใช้ footing_calc.plan_mat ตัวเดียวกับที่สร้างจริง"""
        return fpv.footing_preview(fc, self.preview_shape, self._read(), self.n_sel)

    def _sel(self, cmb):
        s = cmb.SelectedItem
        return s if s is not None else fc.PLACEHOLDER

    def _hook(self):
        if self.rb_h1.IsChecked:
            return fc.HOOK_90
        if self.rb_h2.IsChecked:
            return fc.HOOK_FULL
        if self.rb_h3.IsChecked:
            return fc.HOOK_NONE
        return None

    def _read(self):
        return {
            "long": (self._sel(self.cmb_long), ui.intval(self.tb_long_n.Text, 0)),
            "short": (self._sel(self.cmb_short), ui.intval(self.tb_short_n.Text, 0)),
            "tri": {0: (self._sel(self.cmb_t0), ui.intval(self.tb_t0_n.Text, 0)),
                    60: (self._sel(self.cmb_t60), ui.intval(self.tb_t60_n.Text, 0)),
                    120: (self._sel(self.cmb_t120), ui.intval(self.tb_t120_n.Text, 0))},
            "hook": self._hook(),
            "ring": (bool(self.cb_ring.IsChecked), self._sel(self.cmb_ring),
                     ui.intval(self.tb_ring_n.Text, 0),
                     ui.num(self.tb_ring_sp.Text, 0) * 1000.0),
            "cover": ui.num(self.tb_cover.Text, 0) * 1000.0,
        }

    def _check(self):
        items = fc.gate(self._read(), self.has_rect, self.has_tri,
                        list(self.bar_types.keys()))
        self.tb_check.Text = u"\n".join(t for _ok, t in items)
        return items

    def collect(self):
        items = self._check()
        if not fc.gate_ok(items):
            return None     # ยังมี ✗ — ไม่ปิดหน้าต่าง
        v = self._read()
        v["same"] = bool(self.cb_same.IsChecked)
        v["replace"] = bool(self.cb_replace.IsChecked)
        v.update(ro.read(self, hooks=False))    # Rebar Shape ตะแกรง/เหล็กรัดรอบ
        return v


# ---------------------------------------------------------------- main
try:
    _OVR = CONFIG_OVERRIDE      # Propagate Rebar: รันโดยไม่เปิดฟอร์ม
except NameError:
    _OVR = None

types = rb.bar_types(doc)
if _OVR is None:
    foots = selected(uidoc, doc, DB.BuiltInCategory.OST_StructuralFoundation)
    if not foots:
        ui.need_selection(u"ฐานราก", u"(คลิกฐานรากที่ต้องการ แล้วกดปุ่มใหม่ — เลือกได้หลายฐาน)")
else:
    shapes_main, shapes_tie = rb.shape_names(doc)
    foots = hostconfig.hosts_from_override(doc, _OVR)
    v, _miss = hostconfig.override_values(_OVR, rb.BAR_NAMES, types)
    _prob = hostconfig.override_problem(foots, _miss)
    if _prob:
        forms.alert(_prob, title=u"PK Revit — Rebar ฐานราก", exitscript=True)


def _expand_same(cur):
    names = set(type_name(doc, c) for c in cur)
    allf = DB.FilteredElementCollector(doc) \
        .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation) \
        .WhereElementIsNotElementType().ToElements()
    return [c for c in allf if type_name(doc, c) in names]


# ผังของฐานที่เลือก (ใช้ตัดสินว่าฟอร์มต้องแสดงส่วนไหน)
fps = {}
for f in foots:
    try:
        fps[id_value(f.Id)] = footprint(f)
    except Exception:
        fps[id_value(f.Id)] = None


def _count(fl):
    r = t = o = 0
    for f in fl:
        fp = fps.get(id_value(f.Id))
        k = fp["kind"] if fp else None
        if k == "rect":
            r += 1
        elif k == "tri":
            t += 1
        else:
            o += 1
    return r, t, o


nr, nt, no = _count(foots)


def _preview_shape(f):
    """ผังฐานแรกสำหรับ preview หรือ None"""
    p = fps.get(id_value(f.Id))
    if not p:
        return None
    return {"poly": p["poly"], "kind": p["kind"], "height": p["height"]}


if _OVR is None:
    shapes_main, shapes_tie = rb.shape_names(doc)
    form = FootingForm(len(foots), nr, nt, no, types, _preview_shape(foots[0]),
                       (list(shapes_main), list(shapes_tie)))
    v = form.show()
    if not v:
        script.exit()

if v["same"]:
    foots = _expand_same(foots)
    for f in foots:
        if id_value(f.Id) not in fps:
            try:
                fps[id_value(f.Id)] = footprint(f)
            except Exception:
                fps[id_value(f.Id)] = None

cover = v["cover"]
ring_on, ring_size, ring_n, ring_sp = v["ring"]
d_ring = rb.bar_dia_mm(ring_size) if ring_on else 0.0
t_ring = types[ring_size] if ring_on else None
hook_pat = v["hook"]
log = []
sh_main = ro.shape_choice(v, "shape_main", shapes_main)
sh_tie = ro.shape_choice(v, "shape_tie", shapes_tie)
for _k, _sh in (("shape_main", shapes_main), ("shape_tie", shapes_tie)):
    _m = ro.missing_shape(v, _k, _sh)
    if _m:
        log.append(u"ไม่พบ Rebar Shape '{}' ในโปรเจกต์นี้ — ใช้แบบอัตโนมัติแทน".format(_m))
made_mat = made_ring = failed = 0
done = 0
skipped = []


def dia_of(name):
    return rb.bar_dia_mm(name)


tg = DB.TransactionGroup(doc, "PK Revit - Rebar ฐานราก")
tg.Start()
t = DB.Transaction(doc, "PK Revit - Rebar ฐานราก")
t.Start()
try:
    if v["replace"]:
        host_ids = set(id_value(f.Id) for f in foots)
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

    for ft in foots:
        label = u"{} id {}".format(ename(ft), id_value(ft.Id))
        fp = fps.get(id_value(ft.Id))
        if fp is None or fp["kind"] is None:
            skipped.append(label + u" (อ่านผังไม่ได้/รูปทรงไม่ใช่สี่เหลี่ยมมุมฉากหรือสามเหลี่ยม)")
            continue
        kind, poly, H = fp["kind"], fp["poly"], fp["height"]
        tf, z0 = fp["tf"], fp["z0"]
        if kind == "rect":
            groups = {"long": v["long"], "short": v["short"]}
        else:
            groups = v["tri"]
        bars = fc.plan_mat(poly, kind, groups, cover, d_ring, H, dia_of)
        if not bars:
            skipped.append(label + u" (ฐานเล็กเกินระยะหุ้ม/ขนาดเหล็ก)")
            continue

        def P(xy, z_mm):
            return tf.OfPoint(DB.XYZ(mm_to_ft(xy[0]), mm_to_ft(xy[1]),
                                     z0 + mm_to_ft(z_mm)))

        created = []
        n_mat = 0
        for b in bars:
            a, c = b["a"], b["b"]
            ln = ((c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2) ** 0.5
            ux, uy = (c[0] - a[0]) / ln, (c[1] - a[1]) / ln
            nrm = tf.OfVector(DB.XYZ(-uy, ux, 0))
            leg = fc.hook_leg(hook_pat, b["dia"], b["z"], H, cover,
                              rb.HOOK90_EXT_D)
            pa, pb = P(a, b["z"]), P(c, b["z"])
            if leg > 1.0:
                curves = [rb.line(P(a, b["z"] + leg), pa), rb.line(pa, pb),
                          rb.line(pb, P(c, b["z"] + leg))]
            else:
                curves = [rb.line(pa, pb)]
            if sh_main is not None:
                # Rebar Shape: ความยาว = แนวเส้น, ขา = ชี้ขึ้นแบบ short_side (ปรับขนาดด้วย ScaleToBox)
                L_ = mm_to_ft(ln)
                r = rb.create_from_shape(
                    doc, ft, sh_main, types[b["size"]], pa,
                    pb.Subtract(pa),
                    tf.BasisZ.Multiply(rb.short_side_ft(L_, mm_to_ft(b["dia"]))))
            else:
                r = rb.create(doc, ft, types[b["size"]], curves, nrm)
            if r is None:
                failed += 1
            else:
                n_mat += 1
                created.append(r)

        n_ring = 0
        if ring_on:
            rp = fc.offset_polygon(poly, cover + d_ring / 2.0)
            mat_thick = sum(dia_of(g[0]) for g in groups.values()
                            if g[0] and g[1] > 0 and g[0] != fc.PLACEHOLDER)
            if rp is not None:
                for zr in fc.ring_levels(H, cover, mat_thick, d_ring,
                                         ring_n, ring_sp):
                    m = len(rp)
                    loop = [rb.line(P(rp[i], zr), P(rp[(i + 1) % m], zr))
                            for i in range(m)]
                    if sh_tie is not None and kind == "rect" and m == 4:
                        p0_ = P(rp[0], zr)
                        r = rb.create_from_shape(
                            doc, ft, sh_tie, t_ring, p0_,
                            P(rp[1], zr).Subtract(p0_), P(rp[3], zr).Subtract(p0_))
                    else:
                        r = rb.create(doc, ft, t_ring, loop, tf.BasisZ,
                                      style=DB.Structure.RebarStyle.StirrupTie)
                    if r is None:
                        failed += 1
                    else:
                        n_ring += 1
                        created.append(r)

        for r in created:
            p = r.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p is not None and not p.IsReadOnly:
                p.Set(MARK)
        if created:
            hostconfig.save(ft, "footing", v)   # จำค่าไว้ที่ฐานรากตัวนี้
        made_mat += n_mat
        made_ring += n_ring
        done += 1
        log.append(u"{} [{}]: ตะแกรง {} เส้น, รัดรอบ {} วง, สูง {:.0f} มม., ตะขอ: {}"
                   .format(label, u"สี่เหลี่ยม" if kind == "rect" else u"สามเหลี่ยม",
                           n_mat, n_ring, H, fc.HOOK_LABELS[hook_pat]))
    t.Commit()
    tg.Assimilate()
except Exception:
    log.append(traceback.format_exc())
    try:
        t.RollBack()
    except Exception:
        pass
    tg.RollBack()
    path = ui.write_log("Rebar_footing.txt", log)
    ui.summary(u"PK Revit — Rebar ฐานราก", u"❌ เกิดข้อผิดพลาด — ย้อนกลับทั้งหมดแล้ว",
               [], path)
    script.exit()

for s in skipped:
    log.append(u"ข้าม: " + s)
path = ui.write_log("Rebar_footing.txt", log)
head = u"✅ ใส่เหล็กแล้ว {} ฐาน".format(done)
if failed:
    head += u" (มี {} ชิ้นสร้างไม่สำเร็จ)".format(failed)
ui.summary(u"PK Revit — Rebar ฐานราก", head,
           [u"ตะแกรง {} เส้น · รัดรอบ {} วง".format(made_mat, made_ring)] +
           ([u"ข้าม {} ฐาน".format(len(skipped))] if skipped else []) +
           [u"Ctrl+Z ครั้งเดียว ย้อนทั้งชุด"], path)
