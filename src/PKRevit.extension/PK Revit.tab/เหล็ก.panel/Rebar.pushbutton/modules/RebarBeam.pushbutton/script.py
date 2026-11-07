# -*- coding: utf-8 -*-
"""Rebar คาน — ใส่เหล็กบน/ล่าง (2 ชั้น), เหล็กเสริมพิเศษ, เหล็กข้าง, ปลอก ให้คานที่เลือก

ขั้นตอน: เลือกคาน (Structural Framing ชนิด Beam) → กดปุ่ม → ตั้งค่า → สร้าง
- การคำนวณตำแหน่ง/ท่อน/โซนปลอกอยู่ใน revotech.beamcalc (ทดสอบนอก Revit ได้)
- คานยาวเกิน "ความยาวสูงสุดต่อท่อน" ตัดท่อนต่อทาบ เหล็กบนต่อกลางช่วง
  เหล็กล่างต่อใกล้ปลาย — ไม่ซ้ำจุดเดียวกัน
- Transaction เดียว Ctrl+Z ย้อนทั้งชุด; Comments = "PKRevit:beam" ใช้แทนที่ของเดิม

สมมติ: คานตรง (LocationCurve เป็น Line) หน้าตัดสี่เหลี่ยม
ทิศงอของขา 90° (Left/Right) ยังไม่เคยทดสอบใน Revit — ดู docs/accept-rebar-beam.md
"""

import os
import math
import traceback
from pyrevit import revit, DB, forms, script

from revotech import rebar as rb
from revotech import rebaropts as ro
from revotech import ui
from revotech import formpreview as fpv
from revotech import hostconfig
from revotech import beamcalc as bc
from revotech.rvt import ename, id_value, selected, type_name
from revotech.units import mm_to_ft, ft_to_mm

doc = revit.doc
uidoc = revit.uidoc
MARK = u"PKRevit:beam"
LOGNAME = "Rebar_beam.txt"
POS_ITEMS = [u"ปลายทั้งสองข้าง", u"กลางช่วง"]
POS_MODE = {POS_ITEMS[0]: 'ends', POS_ITEMS[1]: 'mid'}
HOOK_ITEMS = [u"12d (มยผ. 1103-64)", u"กำหนดเอง (× d)"]


# ---------------------------------------------------------------- geometry
def is_beam(e):
    try:
        return e.StructuralType == DB.Structure.StructuralType.Beam
    except Exception:
        return False


def beam_frame(inst):
    """(p0, d, side, up, s0,s1,u0,u1,v0,v1 [มม.]) หรือ None — คานตรงเท่านั้น"""
    loc = inst.Location
    if not isinstance(loc, DB.LocationCurve):
        return None
    c = loc.Curve
    if not isinstance(c, DB.Line):
        return None
    p0 = c.GetEndPoint(0)
    d = (c.GetEndPoint(1) - p0).Normalize()
    side = DB.XYZ.BasisZ.CrossProduct(d)
    if side.GetLength() < 1e-6:
        return None
    side = side.Normalize()
    up = d.CrossProduct(side).Normalize()
    opts = DB.Options()
    opts.DetailLevel = DB.ViewDetailLevel.Fine
    geom = inst.get_Geometry(opts)
    if geom is None:
        return None
    pts = []
    for g in geom:
        items = g.GetInstanceGeometry() if isinstance(g, DB.GeometryInstance) \
            else [g]
        for s in items:
            if isinstance(s, DB.Solid) and s.Volume > 0:
                for e in s.Edges:
                    cv = e.AsCurve()
                    pts.append(cv.GetEndPoint(0))
                    pts.append(cv.GetEndPoint(1))
    if not pts:
        return None
    ss, us, vs = [], [], []
    for p in pts:
        r = p - p0
        ss.append(r.DotProduct(d))
        us.append(r.DotProduct(side))
        vs.append(r.DotProduct(up))
    return (p0, d, side, up, ft_to_mm(min(ss)), ft_to_mm(max(ss)),
            ft_to_mm(min(us)), ft_to_mm(max(us)),
            ft_to_mm(min(vs)), ft_to_mm(max(vs)))


def hook90(doc_, mult):
    """หา/สร้าง RebarHookType 90° ที่ตัวคูณ = mult"""
    from Autodesk.Revit.DB.Structure import RebarHookType
    want = math.radians(90.0)
    for h in DB.FilteredElementCollector(doc_).OfClass(RebarHookType):
        try:
            if abs(h.HookAngle - want) < 1e-3 and abs(h.Multiplier - mult) < 1e-3:
                return h
        except Exception:
            continue
    h = RebarHookType.Create(doc_, want, float(mult))
    try:
        h.Name = u"PKRevit_Hook90_{}d".format(mult)
    except Exception:
        pass
    return h


# ---------------------------------------------------------------- form
class BeamForm(ui.RevoWindow):
    def __init__(self, n_sel, bar_types, preview_ext=None, shapes=None):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"REBAR ", u"คาน",
            u"ใส่เหล็กบน/ล่าง เสริมพิเศษ เหล็กข้าง ปลอก ให้คานที่เลือก — PK Revit",
            u"สร้างเหล็กคาน", max_height=600, preview=True)
        self.bar_types = bar_types
        self.n_sel = n_sel
        self.preview_ext = preview_ext     # (L,b,h) มม. ของคานตัวแรก หรือ None
        self.tb_info.Text = u"คานที่เลือก: {} ตัว".format(n_sel)
        have = rb.names_in_project(bar_types) or rb.MAIN_BAR_NAMES
        sel = u"DB16" if u"DB16" in have else None
        counts = list(range(0, 11))
        for nm, dflt in (("top1", 3), ("top2", 0), ("bot1", 3), ("bot2", 0),
                         ("xtop", 0), ("xbot", 0), ("side", 0)):
            ui.combo_fill(getattr(self, "cmb_%s_n" % nm), counts, dflt)
            ui.combo_fill(getattr(self, "cmb_%s_d" % nm), have, sel)
        for nm, pos in (("xtop", POS_ITEMS[0]), ("xbot", POS_ITEMS[1])):
            ui.combo_fill(getattr(self, "cmb_%s_pos" % nm), POS_ITEMS, pos)
            ui.combo_fill(getattr(self, "cmb_%s_div" % nm), [3, 4, 5, 6], 4)
        have_t = rb.names_in_project(bar_types) or rb.TIE_BAR_NAMES
        ui.combo_fill(self.cmb_tie, have_t, u"RB9" if u"RB9" in have_t else None)
        ui.combo_fill(self.cmb_hook, HOOK_ITEMS, HOOK_ITEMS[0])
        self.tb_hook.Text = u"12"
        sh_main, sh_tie = shapes or ((), ())
        ro.fill(self, list(sh_main), list(sh_tie), hooks=True, stagger=False)
        missing = [] if bar_types else [u"(ไม่มี Bar Type เลย)"]
        if missing:
            self.tb_check.Text = (u"✗ ไม่พบ Rebar Bar Type ในโปรเจกต์: {} — ขนาดที่ไม่ได้ใช้ไม่เป็นไร"
                                  .format(u", ".join(missing)))
        else:
            self.tb_check.Text = u"✓ พบ Rebar Bar Type {} ชนิดในโปรเจกต์".format(len(bar_types))
        fpv.bind(self, self._scene, lambda: fpv.beam_preview(self.preview_ext, None, self.n_sel))

    def _scene(self):
        """ภาพประมาณของคานตัวแรก — ใช้ build_spec/beamcalc ตัวเดียวกับที่สร้างจริง ไม่ตรวจ Bar Type"""
        g = dict((nm, self._grp(nm)) for nm in
                 ("top1", "top2", "bot1", "bot2", "xtop", "xbot", "side"))
        custom = (self.cmb_hook.SelectedItem == HOOK_ITEMS[1])
        v = {"g": g,
             "xtop_pos": POS_MODE[self.cmb_xtop_pos.SelectedItem],
             "xtop_div": int(self.cmb_xtop_div.SelectedItem),
             "xbot_pos": POS_MODE[self.cmb_xbot_pos.SelectedItem],
             "xbot_div": int(self.cmb_xbot_div.SelectedItem),
             "tie": self.cmb_tie.SelectedItem,
             "sp_mid": ui.num(self.tb_sp_mid.Text, 0.20) * 1000.0,
             "sp_end": ui.num(self.tb_sp_end.Text, 0.10) * 1000.0,
             "end_len": ui.num(self.tb_end_len.Text, 0.80) * 1000.0,
             "hook_mult": ui.num(self.tb_hook.Text, rb.HOOK90_EXT_D) if custom
             else rb.HOOK90_EXT_D,
             "max_len": ui.num(self.tb_maxlen.Text, 10.0) * 1000.0,
             "lap_d": ui.num(self.tb_lap.Text, rb.LAP_D),
             "cover": ui.num(self.tb_cover.Text, 0.025) * 1000.0}
        v.update(ro.read(self))
        return fpv.beam_preview(self.preview_ext, build_spec(v), self.n_sel)

    def _grp(self, nm):
        return (int(getattr(self, "cmb_%s_n" % nm).SelectedItem),
                getattr(self, "cmb_%s_d" % nm).SelectedItem)

    def collect(self):
        g = dict((nm, self._grp(nm)) for nm in
                 ("top1", "top2", "bot1", "bot2", "xtop", "xbot", "side"))
        tie = self.cmb_tie.SelectedItem
        need = [tie] + [d for (n, d) in g.values() if n > 0]
        miss = [n for n in need if n not in self.bar_types]
        if miss:
            self.tb_check.Text = (u"✗ ยังไม่มี Bar Type ในโปรเจกต์: {}"
                                  .format(u", ".join(sorted(set(miss)))))
            return None
        if g["top1"][0] + g["bot1"][0] == 0:
            self.tb_check.Text = u"✗ ต้องมีเหล็กบนหรือล่างอย่างน้อยชั้นที่ 1"
            return None
        custom = (self.cmb_hook.SelectedItem == HOOK_ITEMS[1])
        return {
            "same": bool(self.cb_same.IsChecked),
            "replace": bool(self.cb_replace.IsChecked),
            "g": g,
            "xtop_pos": POS_MODE[self.cmb_xtop_pos.SelectedItem],
            "xtop_div": int(self.cmb_xtop_div.SelectedItem),
            "xbot_pos": POS_MODE[self.cmb_xbot_pos.SelectedItem],
            "xbot_div": int(self.cmb_xbot_div.SelectedItem),
            "tie": tie,
            "sp_mid": ui.num(self.tb_sp_mid.Text, 0.20) * 1000.0,
            "sp_end": ui.num(self.tb_sp_end.Text, 0.10) * 1000.0,
            "end_len": ui.num(self.tb_end_len.Text, 0.80) * 1000.0,
            "hook_mult": ui.num(self.tb_hook.Text, rb.HOOK90_EXT_D) if custom
            else rb.HOOK90_EXT_D,
            "max_len": ui.num(self.tb_maxlen.Text, 10.0) * 1000.0,
            "lap_d": ui.num(self.tb_lap.Text, rb.LAP_D),
            "cover": ui.num(self.tb_cover.Text, 0.025) * 1000.0,
        }
        v.update(ro.read(self))     # รูปเหล็ก/ตะขอปลายคาน
        return v


def build_spec(v):
    g = v["g"]

    def tri(k):
        return (g[k][0], rb.bar_dia_mm(g[k][1]), g[k][1])

    def ext(k):
        n, nm = g[k]
        return (n, rb.bar_dia_mm(nm), nm, v[k + "_pos"], v[k + "_div"]) if n > 0 else None

    return {
        "cover": v["cover"], "d_tie": rb.bar_dia_mm(v["tie"]),
        "max_len": v["max_len"], "lap_d": v["lap_d"], "hook_mult": v["hook_mult"],
        "top": [tri("top1"), tri("top2")], "bot": [tri("bot1"), tri("bot2")],
        "xtop": ext("xtop"), "xbot": ext("xbot"),
        "side": tri("side") if g["side"][0] > 0 else None,
        "end_len": v["end_len"], "sp_end": v["sp_end"], "sp_mid": v["sp_mid"],
        # ตะขอปลายคานซ้าย/ขวา: 'keep' (ตามเดิม 90°) | 'none' | (องศา, ตัวคูณ×d)
        "hk_a": ro.hook_spec(v, "a"), "hk_b": ro.hook_spec(v, "b"),
    }


def preview_extents(bm):
    """(L,b,h) มม. ของคานสำหรับ preview หรือ None (คานโค้ง/อ่านไม่ได้)"""
    try:
        f = beam_frame(bm)
        if f is None:
            return None
        s0, s1, u0, u1, v0, v1 = f[4:10]
        return (s1 - s0, u1 - u0, v1 - v0)
    except Exception:
        return None


# ---------------------------------------------------------------- main
try:
    _OVR = CONFIG_OVERRIDE      # Propagate Rebar: รันโดยไม่เปิดฟอร์ม
except NameError:
    _OVR = None

types = rb.bar_types(doc)
if _OVR is None:
    beams = [b for b in selected(uidoc, doc, DB.BuiltInCategory.OST_StructuralFraming)
             if is_beam(b)]
    if not beams:
        ui.need_selection(u"คาน", u"(คลิกคานที่ต้องการ แล้วกดปุ่มใหม่ — เลือกได้หลายตัว)")
    shapes_main, shapes_tie = rb.shape_names(doc)
    form = BeamForm(len(beams), types, preview_extents(beams[0]),
                    (list(shapes_main), list(shapes_tie)))
    v = form.show()
    if not v:
        script.exit()
else:
    shapes_main, shapes_tie = rb.shape_names(doc)
    beams = [b for b in hostconfig.hosts_from_override(doc, _OVR) if is_beam(b)]
    v, _miss = hostconfig.override_values(_OVR, rb.BAR_NAMES, types)
    _prob = hostconfig.override_problem(beams, _miss)
    if _prob:
        forms.alert(_prob, title=u"PK Revit — Rebar คาน", exitscript=True)

if v["same"]:
    names = set(type_name(doc, b) for b in beams)
    allb = DB.FilteredElementCollector(doc) \
        .OfCategory(DB.BuiltInCategory.OST_StructuralFraming) \
        .WhereElementIsNotElementType().ToElements()
    beams = [b for b in allb if is_beam(b) and type_name(doc, b) in names]

spec = build_spec(v)
log = []
sh_main = ro.shape_choice(v, "shape_main", shapes_main)
sh_tie = ro.shape_choice(v, "shape_tie", shapes_tie)
for _k, _sh in (("shape_main", shapes_main), ("shape_tie", shapes_tie)):
    _m = ro.missing_shape(v, _k, _sh)
    if _m:
        log.append(u"ไม่พบ Rebar Shape '{}' ในโปรเจกต์นี้ — ใช้แบบอัตโนมัติแทน".format(_m))
if sh_main is not None and (spec["hk_a"] != "keep" or spec["hk_b"] != "keep"):
    log.append(u"เลือก Rebar Shape เหล็กหลัก — ตัวเลือกตะขอปลายซ้าย/ขวาถูกข้าม (ใช้ตะขอในตัว shape)")
_hook_cache = {}


def end_hook(spec_hk, dia):
    """ตะขอปลายคานตามที่เลือก: keep→90° เดิม, none→ไม่มี, (องศา,×d)→hook type ใหม่/ที่มี"""
    key = (spec_hk, dia)
    if key not in _hook_cache:
        _hook_cache[key] = rb.resolve_hook(doc, spec_hk, dia, keep=hook90t)             if spec_hk != "keep" else hook90t
    return _hook_cache[key]

counts = {}
made_tie = failed = 0
skipped = []
done_beams = 0

tg = DB.TransactionGroup(doc, "PK Revit - Rebar คาน")
tg.Start()
t = DB.Transaction(doc, "PK Revit - Rebar คาน")
t.Start()
try:
    if v["replace"]:
        host_ids = set(id_value(b.Id) for b in beams)
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
    hook90t = hook90(doc, spec["hook_mult"])
    tie_t = types[v["tie"]]

    for beam in beams:
        label = u"{} id {}".format(ename(beam), id_value(beam.Id))
        fr = beam_frame(beam)
        if fr is None:
            skipped.append(label + u" (ไม่ใช่คานตรง/อ่านรูปทรงไม่ได้)")
            continue
        p0, d, side, up, s0, s1, u0, u1, v0, v1 = fr

        def P(s, u, w):
            return p0 + d * mm_to_ft(s) + side * mm_to_ft(u) + up * mm_to_ft(w)

        bars, errs, warns, info = bc.plan_longitudinal(s0, s1, u0, u1, v0, v1, spec)
        if errs:
            skipped.append(label + u" (" + u"; ".join(errs) + u")")
            continue
        for w_ in warns:
            log.append(u"{} เตือน: {}".format(label, w_))
        created = []
        for b in bars:
            tmap = types[b["name"]]
            hdir = b["hook_a"] or b["hook_b"]
            w = -up if hdir == 'down' else up
            n = d.CrossProduct(w).Normalize()   # n x d = w → ขางอ "Left" ชี้ไปทาง w
            ln = rb.line(P(b["s_a"], b["u"], b["v"]), P(b["s_b"], b["u"], b["v"]))
            if sh_main is not None:
                # Rebar Shape: กล่อง = ความยาวท่อน × ขา (ขาหันตามทิศ w ของตะขอเดิม)
                L_ = mm_to_ft(b["s_b"] - b["s_a"])
                r = rb.create_from_shape(
                    doc, beam, sh_main, tmap, P(b["s_a"], b["u"], b["v"]),
                    d.Multiply(L_),
                    w.Multiply(rb.short_side_ft(L_, mm_to_ft(b["dia"]))))
            else:
                r = rb.create(doc, beam, tmap, [ln], n,
                              hook_start=end_hook(spec["hk_a"], b["dia"]) if b["hook_a"] else None,
                              hook_end=end_hook(spec["hk_b"], b["dia"]) if b["hook_b"] else None)
            if r is None:
                failed += 1
            else:
                created.append(r)
                counts[b["role"]] = counts.get(b["role"], 0) + 1

        zones, (ua, ub, va, vb) = bc.plan_stirrups(s0, s1, u0, u1, v0, v1, spec)
        nties = 0
        for (zs, ln_, sp) in zones:
            loop = [rb.line(P(zs, ua, va), P(zs, ub, va)),
                    rb.line(P(zs, ub, va), P(zs, ub, vb)),
                    rb.line(P(zs, ub, vb), P(zs, ua, vb)),
                    rb.line(P(zs, ua, vb), P(zs, ua, va))]
            if sh_tie is not None:
                r = rb.create_from_shape(
                    doc, beam, sh_tie, tie_t, P(zs, ua, va),
                    side.Multiply(mm_to_ft(ub - ua)), up.Multiply(mm_to_ft(vb - va)))
            else:
                r = rb.create(doc, beam, tie_t, loop, d,
                              style=DB.Structure.RebarStyle.StirrupTie,
                              hook_start=hook135, hook_end=hook135)
            if r is None:
                failed += 1
                continue
            if ln_ > 1e-6:
                rb.layout_max_spacing(r, sp, ln_)
            created.append(r)
            nties += bc.stirrup_count(ln_, sp)
        made_tie += nties

        for r in created:
            p = r.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p is not None and not p.IsReadOnly:
                p.Set(MARK)
        if created:
            hostconfig.save(beam, "beam", v)   # จำค่าไว้ที่คานตัวนี้
        done_beams += 1
        log.append(u"{}: ยาว {:.0f} มม. หน้าตัด {:.0f}x{:.0f} · ท่อนเหล็ก {} · ปลอก ~{} ตัว · "
                   u"จุดต่อบน {} / ล่าง {}".format(
                       label, s1 - s0, u1 - u0, v1 - v0, len(bars), nties,
                       [int(x) for x in info.get("top_cuts", [])],
                       [int(x) for x in info.get("bot_cuts", [])]))
    t.Commit()
    tg.Assimilate()
except Exception:
    log.append(traceback.format_exc())
    try:
        t.RollBack()
    except Exception:
        pass
    tg.RollBack()
    path = ui.write_log(LOGNAME, log)
    ui.summary(u"PK Revit — Rebar คาน", u"❌ เกิดข้อผิดพลาด — ย้อนกลับทั้งหมดแล้ว", [], path)
    script.exit()

for s in skipped:
    log.append(u"ข้าม: " + s)
path = ui.write_log(LOGNAME, log)
head = u"✅ ใส่เหล็กแล้ว {} คาน".format(done_beams)
if failed:
    head += u" (มี {} ชิ้นสร้างไม่สำเร็จ)".format(failed)
labels = [("top1", u"เหล็กบนชั้น 1"), ("top2", u"เหล็กบนชั้น 2"),
          ("bot1", u"เหล็กล่างชั้น 1"), ("bot2", u"เหล็กล่างชั้น 2"),
          ("xtop", u"เสริมบน"), ("xbot", u"เสริมล่าง"), ("side", u"เหล็กข้าง")]
lines = [u"{} {} ท่อน".format(lb, counts[k]) for (k, lb) in labels if k in counts]
lines.append(u"ปลอก ~{} ตัว".format(made_tie))
if skipped:
    lines.append(u"ข้าม {} คาน (ดูใน log)".format(len(skipped)))
lines.append(u"Ctrl+Z ครั้งเดียว ย้อนทั้งชุด")
ui.summary(u"PK Revit — Rebar คาน", head, lines, path)
