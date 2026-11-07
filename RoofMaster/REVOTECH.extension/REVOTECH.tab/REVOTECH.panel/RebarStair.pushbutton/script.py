# -*- coding: utf-8 -*-
"""Rebar บันได — ใส่เหล็กเสริมบันไดหล่อในที่ (Stairs แบบ Run + Landing) 1–2 ช่วง

ขั้นตอน: เลือกบันได (หรือ Run/Landing ของบันได) → กดปุ่ม → ตั้งค่าในฟอร์ม → สร้าง
- 4 กลุ่มเหล็ก (เปิด/ปิดได้ ขนาด + @ระยะ แยกกลุ่ม):
    waist  เหล็กหลักท้องบันได (ตามท้อง ยื่นเข้าชาน/คาน)
    ext    เหล็กต่อ/ยืดที่ชานและคาน (เหล็กบน ปลายบนของช่วง ลงมาตามท้อง)
    tread  เหล็กลูกนอน-ลูกตั้ง (ตัว L ตามรอยขั้น 1 ชุดต่อขั้น)
    crack  เหล็กกันร้าว/ตามขวาง (ตามแนวกว้าง วางบนเหล็กหลัก)
  ชาน (Landing) สี่เหลี่ยม: ตะแกรงล่างจากขนาด/ระยะของ waist (ตามแนวเดิน) และ crack (ขวาง)
- ระยะหุ้ม, ด่านตรวจก่อนสร้าง, Transaction เดียว Ctrl+Z ย้อนทั้งชุด
- เหล็กมี Comments = "REVOTECH:stair:<กลุ่ม>" เพื่อให้ "แทนที่ของเดิม" ลบเฉพาะของเรา
- สร้าง/อัปเดต 3D view ชื่อ "REVOTECH 3D เหล็กบันได" ใส่สีตามกลุ่ม (เฉพาะ view ที่เราสร้าง)

รองรับเฉพาะช่วงตรง (Run แนวตรงเส้นเดียว) และชานสี่เหลี่ยม
คำนวณทั้งหมดอยู่ใน stair_calc.py (ทดสอบนอก Revit ได้) ค่ามาตรฐานต้องให้วิศวกรยืนยัน
"""

import os
import sys
import math
import traceback
from pyrevit import revit, DB, forms, script

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stair_calc as sc  # noqa: E402

from revotech import rebar as rb  # noqa: E402
from revotech import ui  # noqa: E402
from revotech.rvt import ename, id_value, selected, type_name, param_mm  # noqa: E402
from revotech.units import mm_to_ft, ft_to_mm  # noqa: E402

doc = revit.doc
uidoc = revit.uidoc
MARK = u"REVOTECH:stair"
VIEW_NAME = u"REVOTECH 3D เหล็กบันได"


# ---------------------------------------------------------------- frame
class Frame(object):
    """พิกัดท้องถิ่น (s,t,z มม.) -> โลก (ฟุต): xy = dir*(s+s_off) + perp*(t+t_off)"""

    def __init__(self, dx, dy, s_off, t_off):
        self.dx, self.dy = dx, dy
        self.px, self.py = -dy, dx
        self.s_off, self.t_off = s_off, t_off

    def pt(self, s, t, z):
        S, T = s + self.s_off, t + self.t_off
        return DB.XYZ(mm_to_ft(self.dx * S + self.px * T),
                      mm_to_ft(self.dy * S + self.py * T), mm_to_ft(z))

    def vec_t(self):
        return DB.XYZ(self.px, self.py, 0)

    def vec_sz(self, ds, dz):
        return DB.XYZ(self.dx * ds, self.dy * ds, dz)


# ---------------------------------------------------------------- read stairs
def _loop_pts(loop):
    """จุดปลายของ CurveLoop (ฟุต, xy) — None ถ้ามีเส้นโค้งที่ไม่ใช่เส้นตรง"""
    pts = []
    for c in loop:
        if not isinstance(c, DB.Line):
            return None
        p = c.GetEndPoint(0)
        pts.append((p.X, p.Y))
    return pts


def _base_level_z(st):
    try:
        p = st.get_Parameter(DB.BuiltInParameter.STAIRS_BASE_LEVEL_PARAM)
        lv = doc.GetElement(p.AsElementId())
        return lv.Elevation
    except Exception:
        return None


def read_run(st, run, label):
    """อ่านช่วงบันได -> dict หรือ (None, เหตุผล)"""
    try:
        path = run.GetStairsPath()
        curves = [c for c in path]
        if len(curves) != 1 or not isinstance(curves[0], DB.Line):
            return None, u"ช่วงไม่ใช่แนวตรง (winder/โค้ง/หักมุม) — ยังไม่รองรับ"
        p0, p1 = curves[0].GetEndPoint(0), curves[0].GetEndPoint(1)
        dx, dy = p1.X - p0.X, p1.Y - p0.Y
        n = math.hypot(dx, dy)
        if n < 1e-9:
            return None, u"อ่านทิศทางเดินไม่ได้"
        dx, dy = dx / n, dy / n
        fp = _loop_pts(run.GetFootprintBoundary())
        if fp is None:
            return None, u"ขอบช่วงเป็นเส้นโค้ง — ยังไม่รองรับ"
        px, py = -dy, dx
        ss = [ft_to_mm(x * dx + y * dy) for x, y in fp]
        ts = [ft_to_mm(x * px + y * py) for x, y in fp]
        s_min, t_min, t_max = min(ss), min(ts), max(ts)
        lvz = _base_level_z(st)
        if lvz is None:
            return None, u"อ่าน Base Level ของบันไดไม่ได้"
        z0 = ft_to_mm(lvz + run.BaseElevation)
        rise = ft_to_mm(run.TopElevation - run.BaseElevation)
        geo = sc.Geo(rise, run.ActualRisersNumber, run.ActualTreadsNumber,
                     ft_to_mm(run.ActualTreadDepth))
        if not geo.valid():
            return None, u"ค่าขั้นบันไดอ่านไม่ได้/ไม่ถูกต้อง"
        note = None
        foot_len = max(ss) - s_min
        if abs(foot_len - geo.Lh) > 0.03 * geo.Lh:
            note = u"ความยาวผัง {:.0f} ≠ ลูกนอน×{} = {:.0f} มม. (ใช้ค่าลูกนอน)".format(
                foot_len, geo.n_t, geo.Lh)
        return {"run": run, "geo": geo, "W": t_max - t_min, "label": label,
                "frame": Frame(dx, dy, s_min, (t_min + t_max) / 2.0),
                "z0": z0, "top": z0 + rise, "dir": (dx, dy), "note": note}, None
    except Exception as ex:
        return None, u"อ่านช่วงไม่ได้: {}".format(ex)


def read_landing(st, land, run_infos, label, tl_form):
    """อ่านชาน -> dict หรือ (None, เหตุผล)"""
    try:
        if not run_infos:
            return None, u"ไม่มีช่วงอ้างอิงทิศทาง"
        dx, dy = run_infos[0]["dir"]
        fp = _loop_pts(land.GetFootprintBoundary())
        if fp is None:
            return None, u"ขอบชานเป็นเส้นโค้ง — ยังไม่รองรับ"
        px, py = -dy, dx
        pts = [(ft_to_mm(x * dx + y * dy), ft_to_mm(x * px + y * py)) for x, y in fp]
        rect = sc.is_axis_rect(pts)
        if rect is None:
            return None, u"ชานไม่ใช่สี่เหลี่ยมขนานแนวบันได — ยังไม่รองรับ"
        lvz = _base_level_z(st)
        cand = ft_to_mm(lvz + land.BaseElevation)
        tops = [r["top"] for r in run_infos]
        warn = None
        if any(abs(cand - t) < 2.0 for t in tops):
            ztop = cand
        elif any(abs(cand + tl_form - t) < 2.0 for t in tops):
            ztop = cand + tl_form
            warn = u"BaseElevation ของชานเป็นผิวล่าง → บวกความหนา"
        else:
            ztop = cand
            warn = u"ระดับชานไม่ตรงปลายบนของช่วงใด (ใช้ BaseElevation เป็นผิวบน)"
        return {"land": land, "rect": rect, "ztop": ztop, "label": label,
                "frame": Frame(dx, dy, 0.0, 0.0), "warn": warn}, None
    except Exception as ex:
        return None, u"อ่านชานไม่ได้: {}".format(ex)


def read_stair(st, tl_form):
    """-> dict {stair, runs[], lands[], problems[]}"""
    sid = id_value(st.Id)
    out = {"stair": st, "runs": [], "lands": [], "problems": [], "sid": sid}
    try:
        run_ids = list(st.GetStairsRuns())
        land_ids = list(st.GetStairsLandings())
    except Exception:
        out["problems"].append(u"ไม่ใช่บันไดแบบ Run/Landing (by component)")
        return out
    if len(run_ids) not in (1, 2):
        out["problems"].append(u"มี {} ช่วง — รองรับเฉพาะ 1–2 ช่วง".format(len(run_ids)))
        return out
    for i, rid in enumerate(run_ids):
        info, why = read_run(st, doc.GetElement(rid), u"บันได id {} ช่วง {}".format(sid, i + 1))
        if info is None:
            out["problems"].append(u"ช่วง {}: {}".format(i + 1, why))
        else:
            out["runs"].append(info)
    if out["problems"]:
        out["runs"] = []
        return out
    for i, lid in enumerate(land_ids):
        info, why = read_landing(st, doc.GetElement(lid), out["runs"],
                                 u"บันได id {} ชาน {}".format(sid, i + 1), tl_form)
        if info is None:
            out["problems"].append(u"ชาน {}: {} (ข้ามชานนี้)".format(i + 1, why))
        else:
            out["lands"].append(info)
    return out


def stairs_from_selection():
    out = {}
    for s in selected(uidoc, doc, DB.BuiltInCategory.OST_Stairs):
        out[id_value(s.Id)] = s
    for bic in (DB.BuiltInCategory.OST_StairsRuns, DB.BuiltInCategory.OST_StairsLandings):
        for e in selected(uidoc, doc, bic):
            try:
                s = e.GetStairs()
                if s is not None:
                    out[id_value(s.Id)] = s
            except Exception:
                pass
    return list(out.values())


# ---------------------------------------------------------------- form
class StairForm(ui.RevoWindow):
    KEYS = sc.GROUP_ORDER

    def __init__(self, info_text, bar_types, runs_for_gate, tw0, tl0):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"REBAR ", u"บันได",
            u"ใส่เหล็กเสริมบันไดหล่อในที่ 1–2 ช่วง แยก 4 กลุ่มสี — REVOTECH",
            u"สร้างเหล็กบันได", max_height=680)
        self.bar_types = bar_types
        self.runs_for_gate = runs_for_gate
        self.tb_info.Text = info_text
        names = [n for n in rb.BAR_NAMES if n in bar_types] or rb.BAR_NAMES
        items = [sc.PLACEHOLDER] + names
        self.cb = {"waist": self.cb_waist, "ext": self.cb_ext,
                   "tread": self.cb_tread, "crack": self.cb_crack}
        self.cmb = {"waist": self.cmb_waist, "ext": self.cmb_ext,
                    "tread": self.cmb_tread, "crack": self.cmb_crack}
        self.sp = {"waist": self.tb_waist_sp, "ext": self.tb_ext_sp,
                   "tread": self.tb_tread_sp, "crack": self.tb_crack_sp}
        for k in self.KEYS:
            ui.combo_fill(self.cmb[k], items, select=u"RB9" if u"RB9" in names else None)
            self.cmb[k].SelectionChanged += self._changed
            self.sp[k].TextChanged += self._changed
            self.cb[k].Click += self._changed
        self.tb_tw.Text = "{:.3f}".format(tw0 / 1000.0)
        self.tb_tl.Text = "{:.3f}".format(tl0 / 1000.0)
        for tb in (self.tb_cover, self.tb_tw, self.tb_tl, self.tb_anchor,
                   self.tb_ext_len, self.tb_ext_run):
            tb.TextChanged += self._changed
        self._check()

    def _changed(self, sender, args):
        self._check()

    def _read(self):
        g = {}
        for k in self.KEYS:
            s = self.cmb[k].SelectedItem
            g[k] = {"on": bool(self.cb[k].IsChecked),
                    "size": s if s is not None else sc.PLACEHOLDER,
                    "sp": ui.num(self.sp[k].Text, 0) * 1000.0}
        return {"groups": g,
                "cover": ui.num(self.tb_cover.Text, 0) * 1000.0,
                "tw": ui.num(self.tb_tw.Text, 0) * 1000.0,
                "tl": ui.num(self.tb_tl.Text, 0) * 1000.0,
                "anchor": ui.num(self.tb_anchor.Text, 0) * 1000.0,
                "ext_len": ui.num(self.tb_ext_len.Text, 0) * 1000.0,
                "ext_run": ui.num(self.tb_ext_run.Text, 0) * 1000.0,
                "ext_lower": bool(self.cb_ext_lower.IsChecked)}

    def _check(self):
        items = sc.gate(self._read(), self.runs_for_gate, list(self.bar_types.keys()))
        self.tb_check.Text = u"\n".join(t for _ok, t in items)
        return items

    def collect(self):
        items = self._check()
        if not sc.gate_ok(items):
            return None     # ยังมี ✗ — ไม่ปิดหน้าต่าง
        v = self._read()
        v["same"] = bool(self.cb_same.IsChecked)
        v["replace"] = bool(self.cb_replace.IsChecked)
        v["view"] = bool(self.cb_view.IsChecked)
        return v


# ---------------------------------------------------------------- main
sel = stairs_from_selection()
if not sel:
    ui.need_selection(u"บันได", u"(คลิกบันไดหล่อในที่ แล้วกดปุ่มใหม่ — เลือกได้หลายตัว)")

types = rb.bar_types(doc)


def _expand_same(cur):
    names = set(type_name(doc, c) for c in cur)
    allf = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Stairs) \
        .WhereElementIsNotElementType().ToElements()
    return [c for c in allf if type_name(doc, c) in names]


def _prefill(stairs):
    """ความหนาท้องบันได/ชาน จาก type ถ้าอ่านได้ ไม่งั้นค่าตั้งต้น"""
    tw, tl = sc.DEFAULT_TW, sc.DEFAULT_TL
    try:
        info = None
        st = stairs[0]
        rid = list(st.GetStairsRuns())
        if rid:
            rt = doc.GetElement(doc.GetElement(rid[0]).GetTypeId())
            v = param_mm(rt, [u"Structural Depth", u"ความลึกโครงสร้าง",
                              u"Structural depth"])
            if v:
                tw = v
        lid = list(st.GetStairsLandings())
        if lid:
            lt = doc.GetElement(doc.GetElement(lid[0]).GetTypeId())
            try:
                tl = ft_to_mm(lt.Thickness)
            except Exception:
                v = param_mm(lt, [u"Thickness", u"ความหนา"])
                if v:
                    tl = v
    except Exception:
        pass
    return tw, tl


tw0, tl0 = _prefill(sel)
infos = [read_stair(s, tl0) for s in sel]
ok_infos = [i for i in infos if i["runs"]]
gate_runs = [{"label": r["label"], "W": r["W"]} for i in ok_infos for r in i["runs"]]
n_bad = len(infos) - len(ok_infos)
text = u"บันไดที่เลือก: {} ตัว (ใช้ได้ {} · ช่วง {} · ชาน {})".format(
    len(infos), len(ok_infos), len(gate_runs), sum(len(i["lands"]) for i in ok_infos))
if n_bad:
    text += u" · ข้าม {} ตัว (ดูเหตุผลใน log)".format(n_bad)
form = StairForm(text, types, gate_runs, tw0, tl0)
v = form.show()
if not v:
    script.exit()

if v["same"]:
    have = set(i["sid"] for i in infos)
    for s in _expand_same(sel):
        if id_value(s.Id) not in have:
            infos.append(read_stair(s, v["tl"]))
    ok_infos = [i for i in infos if i["runs"]]

G = v["groups"]
dia_of = rb.bar_dia_mm
log = []
for i in infos:
    for p in i["problems"]:
        log.append(u"ข้าม/แจ้ง: บันได id {}: {}".format(i["sid"], p))
    for r in i["runs"]:
        if r["note"]:
            log.append(u"หมายเหตุ {}: {}".format(r["label"], r["note"]))
    for l in i["lands"]:
        if l["warn"]:
            log.append(u"หมายเหตุ {}: {}".format(l["label"], l["warn"]))

created = []        # (Rebar, group)
sets_n = bars_n = 0
failed = 0
per_group = {}
done_stairs = 0


def make_set(hosts, frame, s):
    """สร้าง 1 ชุด — ลอง host ตามลำดับ คืน Rebar หรือ None"""
    bt = types[s["size"]]
    if s["kind"] == "szplane":
        pts = s["pts"]
        curves = [rb.line(frame.pt(pts[j][0], s["t0"], pts[j][1]),
                          frame.pt(pts[j + 1][0], s["t0"], pts[j + 1][1]))
                  for j in range(len(pts) - 1)]
        normal = frame.vec_t()
        arr_len = s["t1"] - s["t0"]
    else:
        curves = [rb.line(frame.pt(s["s"], s["t_lo"], s["z"]),
                          frame.pt(s["s"], s["t_hi"], s["z"]))]
        normal = frame.vec_sz(s["dir"][0], s["dir"][1])
        arr_len = s["arr_len"]
    r = None
    for h in hosts:
        r = rb.create(doc, h, bt, curves, normal)
        if r is not None:
            break
    if r is None:
        return None
    n = s["count"]
    if n > 1 and not rb.layout_fixed_number(r, n, arr_len):
        n = 1
    p = r.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p is not None and not p.IsReadOnly:
        p.Set(u"{}:{}".format(MARK, s["group"]))
    return r, n


tg = DB.TransactionGroup(doc, "REVOTECH - Rebar บันได")
tg.Start()
t = DB.Transaction(doc, "REVOTECH - Rebar บันได")
t.Start()
view = None
try:
    if v["replace"]:
        host_ids = set()
        for i in ok_infos:
            host_ids.add(i["sid"])
            for r in i["runs"]:
                host_ids.add(id_value(r["run"].Id))
            for l in i["lands"]:
                host_ids.add(id_value(l["land"].Id))
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

    for i in ok_infos:
        st = i["stair"]
        st_sets = 0
        for r in i["runs"]:
            sets = sc.plan_run(r["geo"], r["W"], v, dia_of, r["z0"])
            for s in sets:
                res = make_set([r["run"], st], r["frame"], s)
                if res is None:
                    failed += 1
                    continue
                created.append((res[0], s["group"]))
                sets_n += 1
                bars_n += res[1]
                st_sets += 1
                a, b = per_group.get(s["group"], (0, 0))
                per_group[s["group"]] = (a + 1, b + res[1])
            log.append(u"{}: {} ชุด (กว้าง {:.0f} มม., ลูกนอน {} × {:.0f}, ลูกตั้ง {:.1f})".format(
                r["label"], len(sets), r["W"], r["geo"].n_t, r["geo"].g, r["geo"].r))
        for l in i["lands"]:
            s_lo, s_hi, t_lo, t_hi = l["rect"]
            sets = sc.plan_landing(s_lo, s_hi, t_lo, t_hi, l["ztop"], v, dia_of)
            for s in sets:
                res = make_set([l["land"], st], l["frame"], s)
                if res is None:
                    failed += 1
                    continue
                created.append((res[0], s["group"]))
                sets_n += 1
                bars_n += res[1]
                st_sets += 1
                a, b = per_group.get(s["group"], (0, 0))
                per_group[s["group"]] = (a + 1, b + res[1])
            log.append(u"{}: {} ชุด".format(l["label"], len(sets)))
        if st_sets:
            done_stairs += 1

    # 3D view แยกสี (ปรับเฉพาะ view ชื่อนี้ที่เราสร้าง)
    if v["view"] and created:
        try:
            for vw in DB.FilteredElementCollector(doc).OfClass(DB.View3D):
                if not vw.IsTemplate and vw.Name == VIEW_NAME:
                    view = vw
                    break
            if view is None:
                vft = [x for x in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                       if x.ViewFamily == DB.ViewFamily.ThreeDimensional][0]
                view = DB.View3D.CreateIsometric(doc, vft.Id)
                view.Name = VIEW_NAME
            solid = None
            for fpe in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement):
                try:
                    if fpe.GetFillPattern().IsSolidFill:
                        solid = fpe.Id
                        break
                except Exception:
                    continue
            try:
                view.DetailLevel = DB.ViewDetailLevel.Fine
                view.DisplayStyle = DB.DisplayStyle.Shading
            except Exception:
                pass
            for r_, grp in created:
                col = sc.GROUP_COLORS[grp]
                c = DB.Color(col[0], col[1], col[2])
                ogs = DB.OverrideGraphicSettings()
                ogs.SetProjectionLineColor(c)
                ogs.SetCutLineColor(c)
                try:
                    if solid is not None:
                        ogs.SetSurfaceForegroundPatternId(solid)
                        ogs.SetSurfaceForegroundPatternColor(c)
                except Exception:
                    pass
                view.SetElementOverrides(r_.Id, ogs)
                try:
                    r_.SetUnobscuredInView(view, True)
                except Exception:
                    pass
        except Exception:
            log.append(u"สร้าง/ใส่สี 3D view ไม่สำเร็จ (เหล็กยังถูกสร้างปกติ):\n" +
                       traceback.format_exc())
            view = None
    t.Commit()
    tg.Assimilate()
except Exception:
    log.append(traceback.format_exc())
    try:
        t.RollBack()
    except Exception:
        pass
    tg.RollBack()
    path = ui.write_log("Rebar_stair.txt", log)
    ui.summary(u"REVOTECH — Rebar บันได", u"❌ เกิดข้อผิดพลาด — ย้อนกลับทั้งหมดแล้ว", [], path)
    script.exit()

if view is not None:
    try:
        uidoc.ActiveView = view
    except Exception:
        pass

if failed:
    log.append(u"สร้างไม่สำเร็จ {} ชุด (host ไม่รับเหล็ก/เส้นโค้งผิดรูป)".format(failed))
path = ui.write_log("Rebar_stair.txt", log)
head = u"✅ บันได {} ตัว · เหล็ก {} ชุด {} เส้น".format(done_stairs, sets_n, bars_n)
if failed:
    head += u" (มี {} ชุดสร้างไม่สำเร็จ)".format(failed)
lines = []
for k in sc.GROUP_ORDER:
    if k in per_group:
        lines.append(u"{}: {} ชุด {} เส้น".format(sc.GROUP_LABELS[k], per_group[k][0], per_group[k][1]))
if n_bad:
    lines.append(u"ข้ามบันได {} ตัว (ดู log)".format(n_bad))
if view is not None:
    lines.append(u"3D view: " + VIEW_NAME)
lines.append(u"Ctrl+Z ครั้งเดียว ย้อนทั้งชุด")
ui.summary(u"REVOTECH — Rebar บันได", head, lines, path)
