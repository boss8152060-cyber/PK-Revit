# -*- coding: utf-8 -*-
"""Rebar พื้น — ใส่เหล็กเส้น (ชั้นบน/ล่าง ทิศ X/Y) หรือไวร์เมช ให้พื้นที่เลือก

ขั้นตอน: เลือกพื้น (Floors / Structural Floor) หลายผืน → กดปุ่ม → ตั้งค่าในฟอร์ม → สร้าง
- โหมด "เหล็กเส้น": 4 ชั้น (บน/ล่าง × X/Y) ขนาด @ระยะ เลือกเฉพาะชั้นที่ต้องการ
- โหมด "ไวร์เมช": ใช้ Fabric Sheet Type ในโปรเจกต์ ถ้าไม่มีจะไม่สร้าง (ด่านตรวจแจ้ง)
- รูปทรงพื้นอ่านจากผิวบนของ geometry (ขอบนอก + ช่องเปิดทุกลูป) ไม่สมมติว่าเป็นสี่เหลี่ยม
- เหล็กเสริมริม/หนวดกุ้ง (ปิดไว้เป็นค่าตั้งต้น — ความหมายในคลิปยังไม่ชัด)
- Transaction เดียว Ctrl+Z ย้อนทั้งชุด; ของที่สร้างมี Comments = "PKRevit:slab"

สมมติ: พื้นราบ (ผิวบนแนวนอน) ทิศ X/Y คือแกน X/Y ของโมเดล
คำนวณทั้งหมดอยู่ใน slab_calc.py (ทดสอบนอก Revit ได้) ค่ามาตรฐานต้องให้วิศวกรยืนยัน
"""

import os
import sys
import traceback
from pyrevit import revit, DB, forms, script

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slab_calc as sc  # noqa: E402

from revotech import rebar as rb  # noqa: E402
from revotech import hostconfig  # noqa: E402
from revotech import ui  # noqa: E402
from revotech.rvt import ename, id_value, selected, type_name  # noqa: E402
from revotech.units import mm_to_ft, ft_to_mm  # noqa: E402

doc = revit.doc
uidoc = revit.uidoc
MARK = u"PKRevit:slab"
COMMENTS = DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS


# ---------------------------------------------------------------- geometry
def _solids(el):
    opts = DB.Options()
    opts.DetailLevel = DB.ViewDetailLevel.Fine
    geom = el.get_Geometry(opts)
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


def _loop_pts(loop):
    pts = []
    for c in loop:
        if isinstance(c, DB.Line):
            seq = [c.GetEndPoint(0)]
        else:
            seq = list(c.Tessellate())[:-1]     # ส่วนโค้ง -> เส้นตรงสั้นๆ
        for p in seq:
            pts.append((ft_to_mm(p.X), ft_to_mm(p.Y)))
    return pts


def slab_shape(fl):
    """ผังพื้นจากผิวบน: dict {outer, holes, H (มม.), z0 (ฟุต ผิวล่าง), note} หรือ None
    ใช้ผิวบนแนวนอนที่ใหญ่สุด; ผิวล่างแนวนอนที่ใหญ่สุดให้ความหนา"""
    solids = _solids(fl)
    if not solids:
        return None
    top = bot = None
    for s in solids:
        for f in s.Faces:
            if not isinstance(f, DB.PlanarFace):
                continue
            n = f.FaceNormal
            if n.Z > 0.999 and (top is None or f.Area > top.Area):
                top = f
            elif n.Z < -0.999 and (bot is None or f.Area > bot.Area):
                bot = f
    if top is None:
        return {"error": u"ไม่มีผิวบนแนวราบ (พื้นเอียง/ผิวโค้ง ยังไม่รองรับ)"}
    zt = top.Origin.Z
    if bot is not None:
        zb = bot.Origin.Z
    else:
        p = fl.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)
        if p is None:
            return {"error": u"อ่านความหนาพื้นไม่ได้"}
        zb = zt - p.AsDouble()
    loops = []
    for lp in top.GetEdgesAsCurveLoops():
        loops.append(_loop_pts(lp))
    outer, holes = sc.split_loops(loops)
    if outer is None:
        return {"error": u"อ่านขอบพื้นไม่ได้"}
    return {"outer": outer, "holes": holes, "H": ft_to_mm(zt - zb), "z0": zb,
            "top_z": zt}


# ---------------------------------------------------------------- mesh
def make_mesh(fl, sh, sheet_type, area_type_id):
    """สร้างไวร์เมชหนึ่งผืนต่อพื้น — API Fabric ยังไม่เคยรันจริง ลองหลายวิธี
    คืน (element|None, ข้อความ log)"""
    from System.Collections.Generic import List
    msgs = []
    z = sh["top_z"]
    pts = sh["outer"]
    curves = List[DB.Curve]()
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        curves.Add(DB.Line.CreateBound(
            DB.XYZ(mm_to_ft(a[0]), mm_to_ft(a[1]), z),
            DB.XYZ(mm_to_ft(b[0]), mm_to_ft(b[1]), z)))
    if area_type_id is not None:
        try:
            fa = DB.Structure.FabricArea.Create(
                doc, fl, curves, DB.XYZ.BasisX, area_type_id, sheet_type.Id)
            return fa, u"FabricArea.Create สำเร็จ"
        except Exception as ex:
            msgs.append(u"FabricArea.Create: {}".format(ex))
    try:
        fs = DB.Structure.FabricSheet.Create(doc, fl.Id, sheet_type.Id)
        return fs, u"FabricSheet.Create สำเร็จ (วางตำแหน่งตามค่าตั้งต้น ไม่ได้จัดตามขอบ)"
    except Exception as ex:
        msgs.append(u"FabricSheet.Create: {}".format(ex))
    return None, u"; ".join(msgs)


def _fabric_types():
    d = {}
    try:
        for t in DB.FilteredElementCollector(doc).OfClass(DB.Structure.FabricSheetType):
            d[ename(t)] = t
    except Exception:
        pass
    return d


def _fabric_area_type_id():
    try:
        return DB.FilteredElementCollector(doc).OfClass(
            DB.Structure.FabricAreaType).FirstElementId()
    except Exception:
        return None


def _host_id(el):
    for attr in ("GetHostId", "GetHostElementId"):
        f = getattr(el, attr, None)
        if f is not None:
            try:
                return id_value(f())
            except Exception:
                pass
    try:
        return id_value(el.HostId)
    except Exception:
        return None


# ---------------------------------------------------------------- form
class SlabForm(ui.RevoWindow):
    def __init__(self, n_sel, n_bad, bar_types, fabric_types):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"REBAR ", u"พื้น",
            u"เหล็กเส้น / ไวร์เมช ให้พื้นที่เลือก — PK Revit",
            u"สร้างเหล็กพื้น", max_height=680)
        self.bar_types = bar_types
        self.fabric_names = sorted(fabric_types.keys())
        info = u"พื้นที่เลือก: {} ผืน".format(n_sel)
        if n_bad:
            info += u" · อ่านรูปทรงไม่ได้/เอียง {} (จะข้าม)".format(n_bad)
        self.tb_info.Text = info

        have = rb.names_in_project(bar_types)
        items = [sc.PLACEHOLDER] + (have or rb.BAR_NAMES)
        self.cmbs = {"TX": self.cmb_tx, "TY": self.cmb_ty,
                     "BX": self.cmb_bx, "BY": self.cmb_by}
        self.tbs = {"TX": self.tb_tx, "TY": self.tb_ty,
                    "BX": self.tb_bx, "BY": self.tb_by}
        for c in list(self.cmbs.values()) + [self.cmb_edge]:
            ui.combo_fill(c, items)
            c.SelectionChanged += self._changed
        ui.combo_fill(self.cmb_mesh, [sc.PLACEHOLDER] + self.fabric_names)
        self.cmb_mesh.SelectionChanged += self._changed
        for tb in list(self.tbs.values()) + [self.tb_edge_sp, self.tb_edge_len,
                                             self.tb_cover]:
            tb.TextChanged += self._changed
        for r in (self.rb_bar, self.rb_mesh, self.cb_edge):
            r.Click += self._changed
        self._check()

    def _changed(self, sender, args):
        self._check()

    def _sel(self, cmb):
        s = cmb.SelectedItem
        return s if s is not None else sc.PLACEHOLDER

    def _read(self):
        mode = sc.MODE_MESH if self.rb_mesh.IsChecked else sc.MODE_BAR
        mesh = self._sel(self.cmb_mesh)
        return {
            "mode": mode,
            "layers": dict((k, (self._sel(self.cmbs[k]),
                                ui.num(self.tbs[k].Text, 0) * 1000.0))
                           for k in sc.LAYER_KEYS),
            "edge": (bool(self.cb_edge.IsChecked), self._sel(self.cmb_edge),
                     ui.num(self.tb_edge_sp.Text, 0) * 1000.0,
                     ui.num(self.tb_edge_len.Text, 0) * 1000.0),
            "mesh": mesh if mesh != sc.PLACEHOLDER else u"",
            "cover": ui.num(self.tb_cover.Text, 0) * 1000.0,
        }

    def _check(self):
        from System.Windows import Visibility as vis
        v = self._read()
        is_bar = v["mode"] == sc.MODE_BAR
        self.sp_bar.Visibility = vis.Visible if is_bar else vis.Collapsed
        self.sp_mesh.Visibility = vis.Collapsed if is_bar else vis.Visible
        items = sc.gate(v, list(self.bar_types.keys()), len(self.fabric_names),
                        self.fabric_names)
        self.tb_check.Text = u"\n".join(t for _ok, t in items)
        return items

    def collect(self):
        items = self._check()
        if not sc.gate_ok(items):
            return None     # ยังมี ✗ — ไม่ปิดหน้าต่าง
        v = self._read()
        v["same"] = bool(self.cb_same.IsChecked)
        v["replace"] = bool(self.cb_replace.IsChecked)
        return v


# ---------------------------------------------------------------- main
try:
    _OVR = CONFIG_OVERRIDE      # Propagate Rebar: รันโดยไม่เปิดฟอร์ม
except NameError:
    _OVR = None

types = rb.bar_types(doc)
if _OVR is None:
    floors = selected(uidoc, doc, DB.BuiltInCategory.OST_Floors)
    if not floors:
        ui.need_selection(u"พื้น", u"(คลิกพื้นที่ต้องการ แล้วกดปุ่มใหม่ — เลือกได้หลายผืน)")
else:
    floors = hostconfig.hosts_from_override(doc, _OVR)
    v, _miss = hostconfig.override_values(_OVR, rb.BAR_NAMES, types)
    _prob = hostconfig.override_problem(floors, _miss)
    if _prob:
        forms.alert(_prob, title=u"PK Revit — Rebar พื้น", exitscript=True)
fabrics = _fabric_types()


def _shape_safe(fl):
    try:
        return slab_shape(fl)
    except Exception:
        return {"error": u"อ่าน geometry ไม่ได้: " + traceback.format_exc().splitlines()[-1]}


def _expand_same(cur):
    names = set(type_name(doc, c) for c in cur)
    allf = DB.FilteredElementCollector(doc) \
        .OfCategory(DB.BuiltInCategory.OST_Floors) \
        .WhereElementIsNotElementType().ToElements()
    return [c for c in allf if type_name(doc, c) in names]


shapes = {}
for f in floors:
    shapes[id_value(f.Id)] = _shape_safe(f)
n_bad = sum(1 for s in shapes.values() if s is None or "error" in s)

if _OVR is None:
    form = SlabForm(len(floors), n_bad, types, fabrics)
    v = form.show()
    if not v:
        script.exit()

if v["same"]:
    floors = _expand_same(floors)
    for f in floors:
        if id_value(f.Id) not in shapes:
            shapes[id_value(f.Id)] = _shape_safe(f)

cover = v["cover"]
mode = v["mode"]
layers = dict((k, val) for k, val in v["layers"].items()
              if val[0] != sc.PLACEHOLDER) if mode == sc.MODE_BAR else {}
edge_on, edge_size, edge_sp, edge_len = v["edge"]
edge_dia = rb.bar_dia_mm(edge_size) if edge_on else 0.0
dia_of = rb.bar_dia_mm

log = [u"โหมด: " + (u"เหล็กเส้น" if mode == sc.MODE_BAR else u"ไวร์เมช"),
       u"ระยะหุ้ม {:.0f} มม.".format(cover)]
skipped = []
n_sets = n_bars = n_mesh = failed = done = 0

tg = DB.TransactionGroup(doc, "PK Revit - Rebar พื้น")
tg.Start()
t = DB.Transaction(doc, "PK Revit - Rebar พื้น")
t.Start()
try:
    if v["replace"]:
        host_ids = set(id_value(f.Id) for f in floors)
        old = []
        classes = [DB.Structure.Rebar]
        for nm in ("FabricArea", "FabricSheet"):
            if hasattr(DB.Structure, nm):
                classes.append(getattr(DB.Structure, nm))
        for cls in classes:
            for r in DB.FilteredElementCollector(doc).OfClass(cls):
                try:
                    p = r.get_Parameter(COMMENTS)
                    if p is None or not (p.AsString() or u"") == MARK:
                        continue
                    if _host_id(r) in host_ids:
                        old.append(r.Id)
                except Exception:
                    continue
        removed = 0
        for rid in old:
            try:
                doc.Delete(rid)
                removed += 1
            except Exception:
                pass    # ถูกลบพร้อมตัวแม่แล้ว (เช่น FabricSheet ใน FabricArea)
        log.append(u"ลบของเดิม {} ชิ้น".format(removed))

    area_type_id = _fabric_area_type_id() if mode == sc.MODE_MESH else None

    for fl in floors:
        label = u"{} id {}".format(ename(fl), id_value(fl.Id))
        sh = shapes.get(id_value(fl.Id))
        if sh is None or "error" in sh:
            skipped.append(label + u" — " + (sh["error"] if sh else u"อ่านผังไม่ได้"))
            continue
        outer, holes, H, z0 = sh["outer"], sh["holes"], sh["H"], sh["z0"]

        def P(xy, z_mm):
            return DB.XYZ(mm_to_ft(xy[0]), mm_to_ft(xy[1]), z0 + mm_to_ft(z_mm))

        created = []
        sets = 0
        nb = 0
        if mode == sc.MODE_BAR:
            bars, notes = sc.plan_layers(outer, holes, H, cover, layers, dia_of)
            for nt in notes:
                log.append(label + u": " + nt)
            for b in bars:
                a, c = b["a"], b["b"]
                ln = ((c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2) ** 0.5
                ux, uy = (c[0] - a[0]) / ln, (c[1] - a[1]) / ln
                nrm = DB.XYZ(-uy, ux, 0)
                r = rb.create(doc, fl, types[b["size"]],
                              [rb.line(P(a, b["z"]), P(c, b["z"]))], nrm)
                if r is None:
                    failed += 1
                else:
                    nb += 1
                    created.append(r)
            sets += sc.count_groups(bars)
        else:
            el, msg = make_mesh(fl, sh, fabrics[v["mesh"]], area_type_id)
            log.append(u"{} ไวร์เมช: {}".format(label, msg))
            if el is None:
                failed += 1
            else:
                n_mesh += 1
                created.append(el)

        if edge_on:
            z_e = sc.edge_level(H, cover, layers, dia_of, edge_dia)
            ebars, esk = sc.edge_bars(outer, holes, H, cover, edge_dia,
                                      edge_sp, edge_len, z_e)
            n_e = 0
            for b in ebars:
                a, c = b["a"], b["b"]
                ln = ((c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2) ** 0.5
                ux, uy = (c[0] - a[0]) / ln, (c[1] - a[1]) / ln
                nrm = DB.XYZ(-uy, ux, 0)
                crv = [rb.line(P(a, b["z"]), P(c, b["z"]))]
                if b["leg"] > 1.0:
                    crv.insert(0, rb.line(P(a, b["z"] - b["leg"]), P(a, b["z"])))
                r = rb.create(doc, fl, types[edge_size], crv, nrm)
                if r is None:
                    failed += 1
                else:
                    n_e += 1
                    created.append(r)
            nb += n_e
            if n_e:
                sets += 1
            log.append(u"{} เหล็กเสริมริม {} เส้น (ข้าม {} เส้น/ขอบสั้น)".format(
                label, n_e, esk))

        for r in created:
            p = r.get_Parameter(COMMENTS)
            if p is not None and not p.IsReadOnly:
                p.Set(MARK)
        if created:
            hostconfig.save(fl, "slab", v)   # จำค่าไว้ที่พื้นผืนนี้
        n_sets += sets
        n_bars += nb
        done += 1
        log.append(u"{}: {} เส้น {} ชุด, หนา {:.0f} มม., ช่องเปิด {}".format(
            label, nb, sets, H, len(holes)))
    t.Commit()
    tg.Assimilate()
except Exception:
    log.append(traceback.format_exc())
    try:
        t.RollBack()
    except Exception:
        pass
    tg.RollBack()
    path = ui.write_log("Rebar_slab.txt", log)
    ui.summary(u"PK Revit — Rebar พื้น", u"❌ เกิดข้อผิดพลาด — ย้อนกลับทั้งหมดแล้ว",
               [], path)
    script.exit()

for s in skipped:
    log.append(u"ข้าม: " + s)
path = ui.write_log("Rebar_slab.txt", log)
head = u"✅ ใส่เหล็กแล้ว {} ผืน — {}".format(done, sc.summary_text(n_sets, n_mesh))
if failed:
    head += u" (มี {} ชิ้นสร้างไม่สำเร็จ)".format(failed)
ui.summary(u"PK Revit — Rebar พื้น", head,
           [u"เหล็กเส้นรวม {} เส้น".format(n_bars)] +
           ([u"ข้าม {} ผืน".format(len(skipped))] if skipped else []) +
           [u"Ctrl+Z ครั้งเดียว ย้อนทั้งชุด"], path)
