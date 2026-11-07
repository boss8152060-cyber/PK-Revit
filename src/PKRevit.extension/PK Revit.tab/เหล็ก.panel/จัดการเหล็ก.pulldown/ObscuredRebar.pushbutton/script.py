# -*- coding: utf-8 -*-
"""Show/Hide Obscured — SetUnobscuredInView ใน view ปัจจุบัน ตามหมวด host × ชนิดเหล็ก

สวิตช์เดียวในหน้าต่าง: "แสดง" (unobscured=True) / "กลับเป็นปกติ" (False)
ต่างจาก PK Tool: RebarInSystem จับคู่กับ host ตามหมวดจริง (ผ่าน Area/Path ที่ผูกกับ host)
แทนการเหมารวมทุกเส้นใน view; แจ้งผลแยกตามชนิดและจำนวนที่ตั้งค่าไม่สำเร็จ
Transaction เดียว Ctrl+Z ย้อนได้
"""

import os
import traceback
from pyrevit import revit, DB, forms
from Autodesk.Revit.DB.Structure import Rebar, RebarInSystem, FabricSheet

from revotech import ui, manage, managecalc as mc
from revotech.rvt import id_value

doc = revit.doc
uidoc = revit.uidoc
TITLE = u"Show/Hide Obscured — PK Revit"
view = doc.ActiveView

_CB = (("cb_beam", u"OST_StructuralFraming"), ("cb_col", u"OST_StructuralColumns"),
       ("cb_found", u"OST_StructuralFoundation"), ("cb_floor", u"OST_Floors"),
       ("cb_wall", u"OST_Walls"))


class ObscuredForm(ui.RevoWindow):
    def __init__(self, view_name):
        body = os.path.join(os.path.dirname(os.path.abspath(__file__)), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"SHOW/HIDE ", u"OBSCURED",
            u"เหล็กที่ถูกบังใน view ปัจจุบัน — PK Revit", u"ตกลง", width=440)
        self.tb_view.Text = u"view ปัจจุบัน: " + view_name

    def _cats(self):
        return [n for cb, n in _CB if getattr(self, cb).IsChecked]

    def _types(self):
        return mc.obscured_types(bool(self.cb_rebar.IsChecked),
                                 bool(self.cb_area.IsChecked),
                                 bool(self.cb_fabric.IsChecked))

    def collect(self):
        err = mc.validate_obscured(self._cats(), self._types())
        self.tb_err.Text = err or u""
        if err:
            return None
        return {"cats": self._cats(), "types": self._types(),
                "unobscured": bool(self.rb_show.IsChecked)}


def _in_view(cls):
    return DB.FilteredElementCollector(doc, view.Id).OfClass(manage.rf._clr(cls))


def _apply(els, flag):
    ok = bad = 0
    for e in els:
        try:
            e.SetUnobscuredInView(view, flag)
            ok += 1
        except Exception:
            bad += 1
    return ok, bad


try:
    vals = ObscuredForm(view.Name).show()
    if vals is not None:
        cats, types, flag = vals["cats"], vals["types"], vals["unobscured"]
        cat_set = set(cats)
        plan = []   # (ชื่อไทย, [elements])
        if mc.T_REBAR in types:
            els = []
            for r in _in_view(Rebar):
                try:
                    if manage.cat_name_of(doc, r.GetHostId()) in cat_set:
                        els.append(r)
                except Exception:
                    continue
            plan.append((u"Rebar", els))
        if mc.T_FABRIC in types:
            els = []
            for f in _in_view(FabricSheet):
                try:
                    if manage.cat_name_of(doc, f.HostId) in cat_set:
                        els.append(f)
                except Exception:
                    continue
            plan.append((u"Fabric Sheet", els))
        if mc.obscured_needs_area_path_hosts(cats, types):
            ids = manage.view_ris_ids_on_hosts(doc, cats)
            plan.append((u"Area/Path (RebarInSystem)",
                         [r for r in _in_view(RebarInSystem)
                          if id_value(r.Id) in ids]))
        total = sum(len(e) for _n, e in plan)
        if total == 0:
            forms.alert(u"ไม่พบเหล็กที่ตรงกับหมวด/ชนิดที่เลือกใน view นี้", title=TITLE)
        else:
            lines, fails = [], 0
            t = DB.Transaction(doc, u"PK Revit: " + (u"Show Obscured" if flag else u"Hide Obscured"))
            t.Start()
            try:
                for name, els in plan:
                    ok, bad = _apply(els, flag)
                    fails += bad
                    lines.append(u"  {}: ตั้งค่าแล้ว {} รายการ{}".format(
                        name, ok, u" (ไม่สำเร็จ {})".format(bad) if bad else u""))
                t.Commit()
            except Exception:
                t.RollBack()
                raise
            head = u"{} ใน view \"{}\"".format(
                u"แสดงเหล็กที่ถูกบังแล้ว" if flag else u"คืนค่าการบังเป็นปกติแล้ว", view.Name)
            if fails:
                lines += [u"", u"บางรายการตั้งค่าไม่ได้ (view ชนิดนี้อาจไม่รองรับ หรือเหล็กไม่แสดงใน view)"]
            lines += [u"", u"Ctrl+Z ครั้งเดียวย้อนกลับได้"]
            ui.summary(TITLE, head, lines)
except Exception:
    ui.summary(TITLE, u"เกิดข้อผิดพลาด (ย้อนกลับแล้ว)",
               [traceback.format_exc().splitlines()[-1]],
               ui.write_log("ObscuredRebar.txt", traceback.format_exc().splitlines()))
