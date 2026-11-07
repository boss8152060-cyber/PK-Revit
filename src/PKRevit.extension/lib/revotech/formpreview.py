# -*- coding: utf-8 -*-
"""ต่อ 3D preview เข้าฟอร์มเหล็ก (เสา/คาน/ฐานราก/พื้น/บันได)

ส่วนบน = ตัวสร้าง scene แบบล้วน (ไม่พึ่ง WPF/Revit) รับ "ขนาดชิ้นงานจริง" + "ค่าจากฟอร์ม"
  - เรียกฟังก์ชันคำนวณตัวเดียวกับที่สร้างเหล็กจริง (beamcalc / footing_calc.plan_mat /
    slab_calc.plan_layers / stair_calc.plan_run) เท่าที่ทำได้ — เสาใช้สำเนาใน scene3d
  - ค่าไม่ครบ / อ่านรูปทรงไม่ได้ → แสดงเฉพาะชิ้นงาน (หรือกรอบตัวอย่าง) + ข้อความแจ้ง ไม่โยน exception
ส่วนล่าง = bind(): ใส่ FitPreview3D ลงฟอร์มและอัปเดตเมื่อค่าเปลี่ยน (หน่วงเวลา)

preview เป็น "ภาพประมาณ" — ดู docs/preview3d.md
"""
import re
from revotech import scene3d
from revotech.scene3d import Scene, Host, BarGroup

MIN_SPACING = 20.0      # มม. ระยะเรียงที่เล็กกว่านี้ไม่วาด (กันเส้นหลายพันเส้น)
MAX_COUNT = 300         # จำนวนเส้นสูงสุดต่อกลุ่มที่วาดใน preview

GENERIC = {
    "column": (400.0, 400.0, 3000.0),
    "beam": (4000.0, 250.0, 500.0),
    "footing": [(-1000.0, -750.0), (1000.0, -750.0), (1000.0, 750.0), (-1000.0, 750.0)],
    "footing_h": 500.0,
    "slab": (4000.0, 3000.0, 150.0),
}


def dia_mm(name):
    """DB16 -> 16.0 (เหมือน rebar.bar_dia_mm แต่ไม่ import Revit)"""
    m = re.search(r"(\d+)", name or u"")
    return float(m.group(1)) if m else 0.0


def _valid_size(s, placeholder=None):
    return bool(s) and s != placeholder and not (s or u"").startswith(u"—")


def _finish(scene, n_sel, notes):
    pre = []
    if n_sel and n_sel > 1:
        pre.append(u"แสดงตัวอย่างชิ้นที่ 1 จาก {}".format(n_sel))
    scene.notes = pre + list(notes) + list(scene.notes)
    return scene


def _hostonly(title, host_list, notes, n_sel):
    return _finish(Scene(title, host_list, [], []), n_sel, notes)


# ------------------------------------------------------------ เสา
def column_preview(ext, v, n_sel=1):
    """ext=(w,h,H) มม. หรือ None; v = {n,d_main,d_tie,cover,end_len,sp_mid,sp_end,lap_d} (บางค่าเป็น None ได้)"""
    notes = []
    if ext is None or min(ext) <= 0:
        w, h, H = GENERIC["column"]
        notes.append(u"อ่านรูปทรงเสาไม่ได้ — แสดงกรอบตัวอย่าง {:.0f}×{:.0f}×{:.0f} มม.".format(w, h, H))
    else:
        w, h, H = ext
    box = [Host.box(-w / 2.0, -h / 2.0, 0, w / 2.0, h / 2.0, H, label=u"เสา")]
    dm, dt = v.get("d_main"), v.get("d_tie")
    if not dm or not dt:
        return _hostonly(u"เสา", box, notes + [u"ยังไม่ได้เลือกขนาดเหล็ก — แสดงเฉพาะเสา"], n_sel)
    if min(v.get("sp_mid") or 0, v.get("sp_end") or 0) < MIN_SPACING:
        return _hostonly(u"เสา", box, notes + [u"ระยะเรียงปลอกน้อยเกินไป — ไม่แสดงเหล็ก"], n_sel)
    sc = scene3d.column_scene(w, h, H, v.get("n") or 4, dm, dt, v.get("cover", 25.0),
                              v.get("end_len", 600.0), v.get("sp_mid", 150.0),
                              v.get("sp_end", 100.0), v.get("lap_d", 40.0))
    return _finish(sc, n_sel, notes)


# ------------------------------------------------------------ คาน
def beam_preview(ext, spec, n_sel=1):
    """ext=(L,b,h) มม. หรือ None; spec = dict ตาม beamcalc หรือ None"""
    notes = []
    if ext is None or min(ext) <= 0:
        L, b, h = GENERIC["beam"]
        notes.append(u"อ่านรูปทรงคานไม่ได้ — แสดงกรอบตัวอย่าง {:.0f}×{:.0f}×{:.0f} มม.".format(L, b, h))
    else:
        L, b, h = ext
    box = [Host.box(0, -b / 2.0, 0, L, b / 2.0, h, label=u"คาน")]
    if spec is None:
        return _hostonly(u"คาน", box, notes + [u"ค่ายังไม่ครบ — แสดงเฉพาะคาน"], n_sel)
    if min(spec.get("sp_mid", 0), spec.get("sp_end", 0)) < MIN_SPACING:
        spec = dict(spec)
        spec["sp_mid"] = max(spec.get("sp_mid", 0), MIN_SPACING)
        spec["sp_end"] = max(spec.get("sp_end", 0), MIN_SPACING)
        notes.append(u"ระยะเรียงปลอกน้อยเกินไป — ใช้ 20 มม. ในภาพตัวอย่าง")
    try:
        sc = scene3d.beam_scene(L, b, h, spec)
    except Exception:
        return _hostonly(u"คาน", box, notes + [u"คำนวณเหล็กคานไม่ได้ — แสดงเฉพาะคาน"], n_sel)
    if sc.bar_count() == 0:
        notes.append(u"ยังไม่มีเหล็กที่วางได้ — แสดงเฉพาะคาน")
    return _finish(sc, n_sel, notes)


# ------------------------------------------------------------ ฐานราก
def footing_preview(fc, shape, v, n_sel=1):
    """fc = module footing_calc; shape={poly,kind,height} หรือ None; v = ผล form._read()"""
    notes = []
    if shape is None or not shape.get("poly"):
        poly, H, kind = GENERIC["footing"], GENERIC["footing_h"], "rect"
        notes.append(u"อ่านรูปทรงฐานรากไม่ได้ — แสดงกรอบตัวอย่าง 2000×1500×500 มม.")
    else:
        poly, H, kind = shape["poly"], shape["height"], shape.get("kind")
    host = Host(poly, 'z', 0, H, label=u"ฐานราก")
    if kind not in ("rect", "tri"):
        return _hostonly(u"ฐานราก", [host], notes + [u"รูปทรงฐานรากยังไม่รองรับ — แสดงเฉพาะรูปทรง"], n_sel)
    ph = fc.PLACEHOLDER
    if kind == "rect":
        raw = {"long": v["long"], "short": v["short"]}
    else:
        raw = dict(v["tri"])
    groups = {}
    for k, (size, n) in raw.items():
        if _valid_size(size, ph) and n >= 1:
            groups[k] = (size, min(int(n), MAX_COUNT))
        else:
            groups[k] = (None, 0)
    if any(n > MAX_COUNT for (_s, n) in raw.values()):
        notes.append(u"จำนวนเหล็กมากเกินไป — ภาพตัวอย่างแสดงไม่เกิน {} เส้นต่อทิศ".format(MAX_COUNT))
    cover = max(v.get("cover") or 0.0, 0.0)
    on, rsize, rn, rsp = v["ring"]
    ring_ok = bool(on) and _valid_size(rsize, ph) and rn >= 1 and rsp > 0
    d_ring = dia_mm(rsize) if ring_ok else 0.0
    if not any(s for (s, _n) in groups.values()):
        return _hostonly(u"ฐานราก", [host], notes + [u"ยังไม่ได้เลือกขนาดเหล็ก — แสดงเฉพาะฐานราก"], n_sel)
    bars = fc.plan_mat(poly, kind, groups, cover, d_ring, H, dia_mm)
    hook = {fc.HOOK_90: scene3d.HOOK_12D, fc.HOOK_FULL: scene3d.HOOK_FULL}.get(
        v.get("hook"), scene3d.HOOK_NONE)
    sc = scene3d.footing_scene_from_bars(poly, H, bars, cover, hook)
    if not bars:
        notes.append(u"ฐานเล็กเกินระยะหุ้ม/ขนาดเหล็ก — ไม่มีเหล็กที่วางได้")
    if ring_ok:
        rp = fc.offset_polygon(poly, cover + d_ring / 2.0)
        thick = sum(dia_mm(s) for (s, n) in groups.values() if s and n > 0)
        if rp is not None:
            g = BarGroup("ring", u"เหล็กรัดรอบ", scene3d.AMBER, d_ring / 2.0)
            for z in fc.ring_levels(H, cover, thick, d_ring, min(int(rn), MAX_COUNT), rsp):
                g.add([(p[0], p[1], z) for p in rp] + [(rp[0][0], rp[0][1], z)])
            sc.groups.append(g)
    return _finish(sc, n_sel, notes)


# ------------------------------------------------------------ พื้น
def slab_preview(sc_mod, shape, v, n_sel=1):
    """sc_mod = module slab_calc; shape = ผล slab_shape (dict outer/holes/H หรือ {"error"}) หรือ None"""
    notes = []
    if shape is None or "error" in shape or not shape.get("outer"):
        L, B, H = GENERIC["slab"]
        outer, holes = [(0, 0), (L, 0), (L, B), (0, B)], []
        why = (shape or {}).get("error") if shape else None
        notes.append(u"อ่านรูปทรงพื้นไม่ได้{} — แสดงกรอบตัวอย่าง {:.0f}×{:.0f}×{:.0f} มม.".format(
            u" ({})".format(why) if why else u"", L, B, H))
    else:
        outer, holes, H = shape["outer"], shape["holes"], shape["H"]
    host = Host(outer, 'z', 0, H, label=u"พื้น")
    if v.get("mode") == sc_mod.MODE_MESH:
        return _hostonly(u"พื้น", [host], notes + [u"โหมดไวร์เมช — preview แสดงเฉพาะแผ่นพื้น"], n_sel)
    layers = {}
    for k, (size, sp) in v["layers"].items():
        if _valid_size(size, sc_mod.PLACEHOLDER) and sp >= MIN_SPACING:
            layers[k] = (size, sp)
    if not layers:
        return _hostonly(u"พื้น", [host], notes + [u"ยังไม่ได้เลือกขนาด/ระยะเหล็ก — แสดงเฉพาะพื้น"], n_sel)
    bars, pnotes = sc_mod.plan_layers(outer, holes, H, max(v.get("cover") or 0.0, 0.0),
                                      layers, dia_mm)
    sc = scene3d.slab_scene_from_bars(outer, holes, H, bars)
    sc.notes = list(pnotes)
    if v.get("edge") and v["edge"][0]:
        notes.append(u"ไม่แสดงเหล็กเสริมริมใน preview")
    return _finish(sc, n_sel, notes)


# ------------------------------------------------------------ บันได
def stair_preview(sc_mod, run, v, n_sel=1, extra_note=None):
    """sc_mod = module stair_calc; run = {"geo": Geo, "W": มม.} หรือ None"""
    notes = []
    if run is None:
        geo, W = sc_mod.Geo(3000.0, 17, 16, 250.0), 1200.0
        notes.append(u"อ่านรูปทรงบันไดไม่ได้ — แสดงกรอบตัวอย่าง (สูง 3.0 ม. กว้าง 1.2 ม.)")
    else:
        geo, W = run["geo"], run["W"]
    if extra_note:
        notes.append(extra_note)
    tw = v.get("tw") or 0.0
    if tw <= 0:
        tw = sc_mod.DEFAULT_TW
    G = {}
    any_on = False
    for k in sc_mod.GROUP_ORDER:
        g = v["groups"][k]
        ok = bool(g["on"]) and _valid_size(g["size"], sc_mod.PLACEHOLDER) and \
            g["sp"] >= max(sc_mod.MIN_SPACING, 1.0)
        G[k] = {"on": ok, "size": g["size"], "sp": g["sp"]}
        any_on = any_on or ok
    ve = dict(v)
    ve["groups"] = G
    ve["tw"] = tw
    if not any_on:
        return _finish(scene3d.stair_scene(geo, W, [], tw), n_sel,
                       notes + [u"ยังไม่ได้เลือกขนาด/ระยะเหล็ก — แสดงเฉพาะบันได"])
    try:
        sets = sc_mod.plan_run(geo, W, ve, dia_mm, 0.0)
        sc = scene3d.stair_scene(geo, W, sets, tw)
    except Exception:
        return _finish(scene3d.stair_scene(geo, W, [], tw), n_sel,
                       notes + [u"คำนวณเหล็กบันไดไม่ได้ — แสดงเฉพาะบันได"])
    return _finish(sc, n_sel, notes)


# ============================================================ ผูกกับฟอร์ม (WPF)
def _hook_controls(win, handler):
    from System.Windows import LogicalTreeHelper, DependencyObject
    from System.Windows.Controls import TextBox, ComboBox
    from System.Windows.Controls.Primitives import ToggleButton

    def walk(obj):
        try:
            kids = list(LogicalTreeHelper.GetChildren(obj))
        except Exception:
            return
        for c in kids:
            if not isinstance(c, DependencyObject):
                continue
            name = getattr(c, "Name", u"") or u""
            if name == "preview_host":
                continue
            if not name.startswith("pk_"):
                if isinstance(c, TextBox):
                    c.TextChanged += handler
                elif isinstance(c, ComboBox):
                    c.SelectionChanged += handler
                elif isinstance(c, ToggleButton):
                    c.Checked += handler
                    c.Unchecked += handler
            walk(c)
    walk(win.Content)


def bind(win, build_fn, fallback_fn=None, delay_ms=140):
    """ใส่ FitPreview3D แทน preview เดิมของ RevoWindow(preview=True) แล้วอัปเดตเมื่อค่าในฟอร์มเปลี่ยน
    build_fn() -> Scene (โยน exception/None ได้ → ใช้ fallback_fn); คืน preview หรือ None
    ต้องเรียกท้าย __init__ หลังเติมค่าฟอร์มแล้ว — preview พังต้องไม่ทำให้ฟอร์มเปิดไม่ได้"""
    try:
        if getattr(win, "preview", None) is None:
            return None
        from revotech.previewfit import FitPreview3D
        pv = FitPreview3D(delay_ms=delay_ms)
        win.preview_host.Child = pv.view
        win.preview = pv

        def make():
            sc = None
            try:
                sc = build_fn()
            except Exception:
                sc = None
            if sc is None and fallback_fn is not None:
                try:
                    sc = fallback_fn()
                except Exception:
                    sc = None
            return sc

        _hook_controls(win, lambda s, a: pv.schedule(make))
        sc = make()
        if sc is not None:
            pv.update(sc, keep_view=False)
        return pv
    except Exception:
        return None
