# -*- coding: utf-8 -*-
"""Rebar Collision — ตรวจเหล็กชนกันระหว่าง host ต่างตัว รายงานเป็นต้นไม้ คลิกแล้วซูม/เลือกใน view

ขั้นแรก  bounding box overlap (+ระยะ clearance) แบบ sweep-and-prune — ไม่พลาดการชนจริง
ขั้นสอง  เฉพาะคู่ที่ผ่านขั้นแรก (จำกัดจำนวนคู่ ยกเลิกได้):
         - Rebar: ระยะเส้นศูนย์กลาง (GetCenterlineCurves ทุกตำแหน่งในชุด) ลบรัศมี Bar Type
           → ชน (gap<=0) / ใกล้เกินระยะที่ตั้ง / นับจำนวนจุดชนในชุด
         - FabricSheet / RebarInSystem (ไม่มีเส้นศูนย์กลาง): ตัดกันของ solid จริง (BooleanOperationsUtils)
         - ตรวจละเอียดไม่ได้ → รายงานเป็น "bbox ซ้อน (ยังไม่ยืนยัน)" ไม่ทิ้ง
ตรรกะล้วนอยู่ lib/revotech/collisioncalc.py (ทดสอบนอก Revit ได้) — ไม่แก้โมเดล ไม่ต้องใช้ Transaction
ยังไม่เคยรันใน Revit — ดู docs/accept-collision-color.md
"""

import os
import clr
import traceback
from System import Action
from System.Collections.Generic import List
from System.Windows.Threading import DispatcherPriority
from System.Windows import FontWeights
from System.Windows.Controls import TreeViewItem
from pyrevit import revit, DB, forms
from Autodesk.Revit.DB.Structure import (
    Rebar, RebarInSystem, FabricSheet, MultiplanarOption)

from revotech import ui, hostpick
from revotech import reinforcement as rf
from revotech import collisioncalc as cc
from revotech.rvt import ename, id_value
from revotech.units import ft_to_mm, mm_to_ft

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

HOST_CATS = set(int(c) for c in (
    DB.BuiltInCategory.OST_StructuralFraming, DB.BuiltInCategory.OST_StructuralColumns,
    DB.BuiltInCategory.OST_StructuralFoundation, DB.BuiltInCategory.OST_Floors,
    DB.BuiltInCategory.OST_Walls))
MARK = DB.BuiltInParameter.ALL_MODEL_MARK


def _is_host(e):
    try:
        return e.Category is not None and id_value(e.Category.Id) in HOST_CATS
    except Exception:
        return False


def _clr(t):
    return clr.GetClrType(t)


def _ids(seq):
    out = List[DB.ElementId]()
    for i in seq:
        out.Add(i)
    return out


# ------------------------------------------------------------ ป้ายชื่อ
def label(e):
    if e is None:
        return u"(ไม่ทราบ)"
    try:
        cat = e.Category.Name if e.Category is not None else u""
    except Exception:
        cat = u""
    tn = u""
    try:
        t = doc.GetElement(e.GetTypeId())
        if t is not None:
            tn = ename(t)
    except Exception:
        pass
    mk = u""
    try:
        p = e.get_Parameter(MARK)
        if p is not None and p.AsString():
            mk = u" [" + p.AsString() + u"]"
    except Exception:
        pass
    return u"{} {}{} #{}".format(cat, tn, mk, id_value(e.Id)).replace(u"  ", u" ")


# --------------------------------------------------- เก็บเหล็ก/กล่อง
def box_of(e):
    bb = e.get_BoundingBox(None)
    if bb is None:
        return None
    return (bb.Min.X, bb.Min.Y, bb.Min.Z, bb.Max.X, bb.Max.Y, bb.Max.Z)


def gather(scope, host_ids):
    """คืน list ของ (element, host_id_int หรือ None)"""
    out, seen = [], set()
    if scope == "hosts":
        for hid in host_ids:
            hv = id_value(hid)
            for e in rf.on_host(doc, hid):
                k = id_value(e.Id)
                if k not in seen:
                    seen.add(k)
                    out.append((e, hv))
        return out
    for cls in (Rebar, RebarInSystem, FabricSheet):
        col = DB.FilteredElementCollector(doc, view.Id) if scope == "view" \
            else DB.FilteredElementCollector(doc)
        for e in col.OfClass(_clr(cls)):
            k = id_value(e.Id)
            if k in seen:
                continue
            seen.add(k)
            host = None
            if not isinstance(e, RebarInSystem):   # หา host ของ RebarInSystem แพงมาก → ไม่ทราบ
                try:
                    h = rf.host_of(doc, e)
                    host = id_value(h) if h is not None else None
                except Exception:
                    host = None
            out.append((e, host))
    return out


# ------------------------------------------------ ข้อมูลตรวจละเอียด
class Detail(object):
    """cache ของ polyline เส้นศูนย์กลาง/รัศมี/solid ต่อ element"""

    def __init__(self):
        self._poly, self._rad, self._sol = {}, {}, {}

    def polys(self, e):
        k = id_value(e.Id)
        if k in self._poly:
            return self._poly[k]
        res = None
        if isinstance(e, Rebar):
            try:
                res = []
                n = max(int(e.NumberOfBarPositions), 1)
                for idx in range(n):
                    curves = e.GetCenterlineCurves(
                        False, False, False,
                        MultiplanarOption.IncludeAllMultiplanarCurves, idx)
                    pts = []
                    for c in curves:
                        tess = [c.GetEndPoint(0), c.GetEndPoint(1)] \
                            if isinstance(c, DB.Line) else list(c.Tessellate())
                        for p in tess:
                            t = (p.X, p.Y, p.Z)
                            if not pts or pts[-1] != t:
                                pts.append(t)
                    if pts:
                        res.append(pts)
                if not res:
                    res = None
            except Exception:
                res = None
        self._poly[k] = res
        return res

    def radius(self, e):
        k = id_value(e.Id)
        if k in self._rad:
            return self._rad[k]
        r = None
        try:
            t = doc.GetElement(e.GetTypeId())
            try:
                d = t.BarModelDiameter
            except Exception:
                d = t.BarDiameter
            r = d / 2.0
        except Exception:
            r = None
        self._rad[k] = r
        return r

    def solids(self, e):
        k = id_value(e.Id)
        if k in self._sol:
            return self._sol[k]
        res = []
        try:
            opts = DB.Options()
            opts.DetailLevel = DB.ViewDetailLevel.Fine
            opts.ComputeReferences = False
            opts.IncludeNonVisibleObjects = True
            res = self._collect(e.get_Geometry(opts))
        except Exception:
            res = []
        self._sol[k] = res
        return res

    def _collect(self, geo):
        out = []
        if geo is None:
            return out
        for g in geo:
            if isinstance(g, DB.Solid):
                if g.Volume > 1e-12:
                    out.append(g)
            elif isinstance(g, DB.GeometryInstance):
                out.extend(self._collect(g.GetInstanceGeometry()))
        return out


def solid_hits(sa, sb):
    """(จำนวนคู่ solid ที่ตัดกัน, ตรวจได้ไหม)"""
    n, ok = 0, False
    for a in sa:
        for b in sb:
            try:
                r = DB.BooleanOperationsUtils.ExecuteBooleanOperation(
                    a, b, DB.BooleanOperationsType.Intersect)
                ok = True
                if r is not None and r.Volume > 1e-9:
                    n += 1
            except Exception:
                continue
    return n, ok


# ------------------------------------------------------------ ฟอร์ม
class CollisionForm(ui.RevoWindow):
    def __init__(self, preset_hosts):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"REBAR ", u"COLLISION",
            u"ตรวจเหล็กชนกันระหว่าง host ต่างตัว — PK Revit",
            u"ตรวจเหล็กชนกัน", width=660, max_height=780)
        self.hosts = list(preset_hosts or [])
        self.cancel = False
        self.busy = False
        self.records = []
        self.groups = []
        if self.hosts:
            self.rb_hosts.IsChecked = True
            self.tb_info.Text = u"host ที่เลือกไว้ {} ตัว".format(len(self.hosts))
        else:
            self.rb_hosts.IsEnabled = False
            self.tb_info.Text = (u"ยังไม่ได้เลือก host — ตรวจจาก view ปัจจุบัน หรือกด "
                                 u"\"เลือก host\" เพื่อเลือกก่อน")
        self.tb_note.Text = (u"ผลเป็นการตรวจเชิงเรขาคณิตของโมเดล ไม่ใช่การรับรองทางวิศวกรรม — "
                             u"ควรตรวจสอบด้วยสายตาในจุดสำคัญ")
        self.btn_cancel.Click += self._on_cancel
        self.btn_csv.Click += self._on_csv
        self.btn_pick.Click += self._on_pick
        self.btn_clear_sel.Click += self._on_clear_sel
        self.tree.SelectedItemChanged += self._on_tree

    # --- ปุ่มเสริม
    def _on_cancel(self, s, a):
        self.cancel = True

    def _on_close(self, s, a):
        self.cancel = True
        ui.RevoWindow._on_close(self, s, a)

    def _on_pick(self, s, a):
        if self.busy:
            return
        self.values = {"pick": True}
        self.Close()

    def _on_clear_sel(self, s, a):
        try:
            uidoc.Selection.SetElementIds(List[DB.ElementId]())
        except Exception:
            pass

    def _pump(self):
        self.Dispatcher.Invoke(Action(lambda: None), DispatcherPriority.Background)

    def _progress(self, text):
        self.tb_progress.Text = text
        self._pump()

    # --- กดตรวจ (ไม่ปิดหน้าต่าง)
    def _on_run(self, s, a):
        if self.busy:
            return
        self.busy = True
        self.cancel = False
        self.run_btn.IsEnabled = False
        self.btn_cancel.IsEnabled = True
        self.btn_csv.IsEnabled = False
        self.tree.Items.Clear()
        try:
            self._check()
        except Exception:
            self.tb_progress.Text = u"เกิดข้อผิดพลาด: " + traceback.format_exc().splitlines()[-1]
            ui.write_log("RebarCollision_error.txt", [traceback.format_exc()])
        self.busy = False
        self.run_btn.IsEnabled = True
        self.btn_cancel.IsEnabled = False
        self.btn_csv.IsEnabled = bool(self.records)

    def _check(self):
        clear_mm = max(0.0, ui.num(self.tb_clear.Text, 0))
        clear = mm_to_ft(clear_mm)
        max_pairs = max(1, ui.intval(self.tb_max.Text, 2000))
        exact = bool(self.cb_exact.IsChecked)
        scope = "hosts" if self.rb_hosts.IsChecked else \
            ("model" if self.rb_model.IsChecked else "view")

        self._progress(u"กำลังรวบรวมเหล็ก...")
        found = gather(scope, self.hosts)
        items, elems = [], []
        for e, host in found:
            b = box_of(e)
            if b is not None:
                items.append((id_value(e.Id), host, b))
                elems.append(e)
        if len(items) < 2:
            self._progress(u"ต้องมีเหล็กอย่างน้อย 2 ชิ้นในขอบเขตที่เลือก (พบ {})".format(len(items)))
            self.records, self.groups = [], []
            return

        self._progress(u"ขั้นที่ 1: เทียบ bounding box ของเหล็ก {} ชิ้น...".format(len(items)))
        pairs, total, trunc = cc.candidate_pairs(items, clear)
        self._pump()

        records = []
        unverified = 0
        checked = 0
        det = Detail()
        if not exact:
            todo = pairs
        else:
            todo = pairs[:max_pairs]
            unverified = max(0, total - len(todo))
        for n, (i, j, depth) in enumerate(todo):
            if exact and n % 10 == 0:
                self._progress(u"ขั้นที่ 2: ตรวจละเอียด {:,}/{:,} คู่ (จาก bbox ซ้อน {:,} คู่) "
                               u"พบแล้ว {:,}".format(n, len(todo), total, len(records)))
                if self.cancel:
                    unverified += len(todo) - n
                    break
            ea, eb = elems[i], elems[j]
            rec = self._pair(ea, eb, items[i][1], items[j][1], clear, exact, det)
            if rec is not None:
                records.append(rec)
            checked += 1
        cancelled = self.cancel
        self.records = records
        self.groups = cc.group_by_host_pair(records)
        self._fill_tree()
        hit = sum(1 for r in records if r["status"] == cc.STATUS_HIT)
        near = sum(1 for r in records if r["status"] == cc.STATUS_NEAR)
        boxonly = sum(1 for r in records if r["status"] == cc.STATUS_BOX)
        msg = u"เหล็ก {:,} ชิ้น · bbox ซ้อน {:,} คู่ · ตรวจละเอียด {:,} คู่ → ชน {:,} · ใกล้เกิน {:,}".format(
            len(items), total, checked if exact else 0, hit, near)
        if boxonly:
            msg += u" · ยังไม่ยืนยัน {:,}".format(boxonly)
        if unverified:
            msg += (u" · ยังไม่ได้ตรวจละเอียด {:,} คู่ (เกินจำนวนคู่สูงสุด/ยกเลิก — "
                    u"เพิ่มจำนวนคู่หรือลดขอบเขต)".format(unverified))
        if cancelled:
            msg += u" · ยกเลิกกลางคัน"
        if not records:
            msg += u" · ไม่พบเหล็กชนกันระหว่าง host ต่างตัว"
        self._progress(msg)
        ui.write_log("RebarCollision.txt", [msg] + [
            u"{} | {} ↔ {} | {} | gap {} มม. | {} จุด".format(
                g["key"], r["a_label"], r["b_label"], r["status"],
                r["gap_txt"], r["points"])
            for g in self.groups for r in g["records"]])

    def _pair(self, ea, eb, ha, hb, clear, exact, det):
        gap_ft, points, loc, status = None, 1, None, cc.STATUS_BOX
        if exact:
            pa, pb = det.polys(ea), det.polys(eb)
            ra, rb = det.radius(ea), det.radius(eb)
            if pa and pb and ra is not None and rb is not None:
                r = cc.centerline_gap(pa, pb, ra, rb, clear)
                st = cc.classify(r["min_gap"], clear)
                if st is None:
                    return None            # ยืนยันแล้วว่าไม่ชน/ไม่ใกล้เกิน
                status, gap_ft, loc = st, r["min_gap"], r["loc"]
                points = r["hits"] if st == cc.STATUS_HIT else r["nears"]
                points = max(points, 1)
            else:
                sa, sb = det.solids(ea), det.solids(eb)
                if sa and sb:
                    n, ok = solid_hits(sa, sb)
                    if ok:
                        if n == 0:
                            return None
                        status, points = cc.STATUS_HIT, n
                        gap_ft = 0.0
        return {
            "a_id": id_value(ea.Id), "b_id": id_value(eb.Id),
            "host_a": ha, "host_b": hb,
            "a_label": label(ea), "b_label": label(eb),
            "status": status, "points": points,
            "gap": None if gap_ft is None else ft_to_mm(gap_ft),
            "gap_txt": u"" if gap_ft is None else u"{:.1f}".format(ft_to_mm(gap_ft)),
            "loc": None if loc is None else tuple(ft_to_mm(v) for v in loc)}

    # --- ต้นไม้รายงาน
    def _host_name(self, hid):
        if hid is None:
            return u"(ไม่ทราบ host)"
        return label(doc.GetElement(DB.ElementId(hid)))

    def _fill_tree(self):
        self.tree.Items.Clear()
        for g in self.groups:
            head = u"{}  ↔  {}   —   {} จุด  (ชน {} · ใกล้เกิน {} · รวม {} คู่)".format(
                self._host_name(g["host_a"]), self._host_name(g["host_b"]),
                g["points"], g["hits"], g["nears"], len(g["records"]))
            node = TreeViewItem()
            node.Header = head
            node.FontWeight = FontWeights.SemiBold
            node.Tag = [r["a_id"] for r in g["records"][:300]] + \
                       [r["b_id"] for r in g["records"][:300]]
            for r in g["records"]:
                ch = TreeViewItem()
                ch.Header = u"{}  ↔  {}   ·   {}{}   ·   {} จุด".format(
                    r["a_label"], r["b_label"], r["status"],
                    u"  gap {} มม.".format(r["gap_txt"]) if r["gap_txt"] else u"",
                    r["points"])
                ch.Tag = [r["a_id"], r["b_id"]]
                node.Items.Add(ch)
            self.tree.Items.Add(node)

    def _on_tree(self, s, a):
        item = self.tree.SelectedItem
        if item is None or not item.Tag:
            return
        try:
            ids = _ids([DB.ElementId(int(i)) for i in set(item.Tag)])
            uidoc.Selection.SetElementIds(ids)
            uidoc.ShowElements(ids)
        except Exception:
            pass

    def _on_csv(self, s, a):
        if not self.records:
            return
        path = forms.save_file(file_ext="csv", default_name="PKRevit_RebarCollision.csv",
                               title=u"ส่งออกรายงานเหล็กชนกัน")
        if not path:
            return
        header = [u"host A", u"host B", u"เหล็ก A", u"เหล็ก B", u"id A", u"id B",
                  u"สถานะ", u"gap (มม.)", u"จำนวนจุด", u"X (มม.)", u"Y (มม.)", u"Z (มม.)"]
        rows = []
        for g in self.groups:
            for r in g["records"]:
                loc = r["loc"] or (u"", u"", u"")
                rows.append([self._host_name(r["host_a"]), self._host_name(r["host_b"]),
                             r["a_label"], r["b_label"], r["a_id"], r["b_id"],
                             r["status"], r["gap_txt"], r["points"]] +
                            [u"" if v == u"" else u"{:.0f}".format(v) for v in loc])
        try:
            cc.write_csv(path, header, rows)
            self.tb_progress.Text = u"ส่งออกแล้ว: " + path
        except Exception as ex:
            self.tb_progress.Text = u"ส่งออกไม่สำเร็จ: {}".format(ex)


# ------------------------------------------------------------ main
preset = [i for i in uidoc.Selection.GetElementIds()
          if doc.GetElement(i) is not None and _is_host(doc.GetElement(i))]
while True:
    form = CollisionForm(preset)
    res = form.show()
    if res and res.get("pick"):
        uidoc.Selection.SetElementIds(List[DB.ElementId]())  # ไม่ให้ใช้ selection เดิมแทนการเลือกใหม่
        picked = hostpick.resolve(uidoc, doc, _is_host, u"host")
        if picked:
            preset = picked
        continue
    break
