# -*- coding: utf-8 -*-
"""Roof Cover — สร้างวัสดุมุงบนหลังคาที่เลือก

เลือก Roof ก่อนกดปุ่ม (ไม่เลือก = แจ้งเตือน) แล้วติ๊กขั้นที่ต้องการ:
 1) แผ่นหลังคา: ทุกผืนบน เต็มพื้นผิว (ตัวแข็งหนา t ดันขึ้นจากผิว)
 2) ครอบสัน + ครอบตะเฆ่สัน: ตามแนวพับนูนของผืนสองผืน
 3) ครอบข้าง (ปั้นลม): ขอบลาดที่ไม่มีผืนใดชน — ขั้นทดลอง (ผู้พูดในคลิปบอกว่ายังพัฒนาอยู่)
 4) เชิงชาย: ขอบชายคา (ขอบราบ ผืนยกขึ้นเข้าด้านใน)

ชิ้นงานเป็น DirectShape (Generic Models) ทาสีผิวด้วย material ของ type ที่เลือก
Comments = "PKRevit:roofcover:<id หลังคา>" เพื่อให้ "แทนที่ของเดิม" ลบเฉพาะของเรา
Transaction เดียว — Ctrl+Z ครั้งเดียวย้อนทั้งชุด
ยังไม่เคยรันใน Revit
"""

import os
import traceback
from System.Collections.Generic import List
from pyrevit import revit, DB, script

from revotech import ui
from revotech import roofgeo as rg
from revotech.rvt import ename, id_value, selected, types_of
from revotech.units import mm_to_ft, ft_to_mm

doc = revit.doc
uidoc = revit.uidoc
MARK = u"PKRevit:roofcover:"

# (หมวด, ป้ายหน้าชื่อ) ที่ให้เลือกเป็นวัสดุ
SOURCES = [
    (DB.BuiltInCategory.OST_Roofs, u"หลังคา"),
    (DB.BuiltInCategory.OST_Fascia, u"Fascia"),
    (DB.BuiltInCategory.OST_CurtainWallPanels, u"Curtain"),
    (DB.BuiltInCategory.OST_GenericModel, u"Generic"),
]
NONE_LABEL = u"(ไม่ระบุ — ไม่ทาวัสดุ)"
HINTS = {
    "sheet": [u"monier", u"prestige", u"oriental", u"metal", u"sheet"],
    "ridge": [u"ridge", u"ครอบ", u"cap"],
    "verge": [u"verge", u"ปั้นลม"],
    "fascia": [u"fascia", u"เชิงชาย"],
}


def collect_type_options():
    """{ป้าย: type element} จากโปรเจกต์"""
    opts = {}
    for bic, label in SOURCES:
        try:
            for name, t in types_of(doc, bic).items():
                opts[u"[{}] {}".format(label, name)] = t
        except Exception:
            continue
    return opts


def pick_default(labels, hints):
    for h in hints:
        for lb in labels:
            if h in lb.lower():
                return lb
    return NONE_LABEL


class CoverForm(ui.RevoWindow):
    def __init__(self, n_roofs, options):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"ROOF ", u"COVER",
            u"วัสดุมุง ครอบสัน ปั้นลม เชิงชาย — PK Revit",
            u"สร้างวัสดุมุง")
        self.options = options
        labels = sorted(options.keys())
        self.tb_info.Text = u"หลังคาที่เลือก: {} ผืน/ตัว".format(n_roofs)
        for key, cmb in (("sheet", self.cmb_sheet), ("ridge", self.cmb_ridge),
                         ("verge", self.cmb_verge), ("fascia", self.cmb_fascia)):
            ui.combo_fill(cmb, [NONE_LABEL] + labels,
                          pick_default(labels, HINTS[key]))
        self.tb_check.Text = (u"พบ type ในโปรเจกต์ {} รายการ — ขั้น 3 (ครอบข้าง) "
                              u"ยังเป็นขั้นทดลอง".format(len(labels)))

    def collect(self):
        v = {
            "replace": bool(self.cb_replace.IsChecked),
            "sheet": bool(self.cb_sheet.IsChecked),
            "ridge": bool(self.cb_ridge.IsChecked),
            "verge": bool(self.cb_verge.IsChecked),
            "fascia": bool(self.cb_fascia.IsChecked),
            "t_sheet": self.cmb_sheet.SelectedItem,
            "t_ridge": self.cmb_ridge.SelectedItem,
            "t_verge": self.cmb_verge.SelectedItem,
            "t_fascia": self.cmb_fascia.SelectedItem,
            "sheet_t": ui.num(self.tb_sheet_t.Text, 0.0),
            "cap_w": ui.num(self.tb_cap_w.Text, 300.0),
            "cap_h": ui.num(self.tb_cap_h.Text, 80.0),
            "fas_h": ui.num(self.tb_fas_h.Text, 200.0),
            "fas_t": ui.num(self.tb_fas_t.Text, 30.0),
        }
        if not (v["sheet"] or v["ridge"] or v["verge"] or v["fascia"]):
            self.tb_check.Text = u"✗ ติ๊กอย่างน้อย 1 ขั้น"
            return None
        for k in ("cap_w", "cap_h", "fas_h", "fas_t"):
            if v[k] <= 0:
                self.tb_check.Text = u"✗ ขนาดต้องมากกว่า 0"
                return None
        return v


def make_shape(solid, mat_id, tag):
    """สร้าง DirectShape จาก solid → (element, ทาสีสำเร็จหรือไม่)"""
    ds = DB.DirectShape.CreateElement(
        doc, DB.ElementId(DB.BuiltInCategory.OST_GenericModel))
    objs = List[DB.GeometryObject]()
    objs.Add(solid)
    ds.SetShape(objs)
    p = ds.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p is not None and not p.IsReadOnly:
        p.Set(tag)
    painted = True
    if mat_id is not None:
        painted = False
        try:
            opt = DB.Options()
            for g in ds.get_Geometry(opt):
                if isinstance(g, DB.Solid):
                    for f in g.Faces:
                        doc.Paint(ds.Id, f, mat_id)
                    painted = True
        except Exception:
            painted = False
    return ds, painted


# ---------------------------------------------------------------- main
roofs = selected(uidoc, doc, DB.BuiltInCategory.OST_Roofs)
if not roofs:
    ui.need_selection(u"หลังคา (Roof)", u"(คลิกหลังคาที่ต้องการ แล้วกดปุ่มใหม่)")

options = collect_type_options()
form = CoverForm(len(roofs), options)
v = form.show()
if not v:
    script.exit()


def chosen(key):
    t = options.get(v[key])
    return t, (rg.material_id(t) if t is not None else None)


log = []
counts = {"sheet": 0, "ridge": 0, "verge": 0, "fascia": 0}
unpainted = 0
failed = 0

tg = DB.TransactionGroup(doc, "PK Revit - Roof Cover")
tg.Start()
t = DB.Transaction(doc, "PK Revit - Roof Cover")
t.Start()
try:
    roof_ids = set(id_value(r.Id) for r in roofs)
    if v["replace"]:
        old = []
        for ds in DB.FilteredElementCollector(doc).OfClass(DB.DirectShape):
            try:
                p = ds.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                s = (p.AsString() or u"") if p is not None else u""
                if s.startswith(MARK) and int(s[len(MARK):]) in roof_ids:
                    old.append(ds.Id)
            except Exception:
                continue
        for eid in old:
            doc.Delete(eid)
        log.append(u"ลบวัสดุมุงเดิม {} ชิ้น".format(len(old)))

    faces = rg.top_faces(roofs)
    log.append(u"พบผืนบน {} ผืน".format(len(faces)))
    if not faces:
        log.append(u"ไม่พบผืนบนของหลังคา — ไม่ได้สร้างอะไร")
    cls = rg.classify(faces) if faces else {"folds": [], "eaves": [],
                                            "verges": [], "notes": []}
    log.extend(cls["notes"])
    log.append(u"แนวพับนูน {} / ชายคา {} / ขอบข้าง {}".format(
        len([f for f in cls["folds"] if f[2]]), len(cls["eaves"]),
        len(cls["verges"])))

    def tag_for(roof):
        return MARK + str(id_value(roof.Id))

    # 1) แผ่นหลังคา
    if v["sheet"]:
        tp, mid = chosen("t_sheet")
        th = v["sheet_t"]
        thick = mm_to_ft(th) if th > 0 else (rg.type_thickness_ft(tp)
                                              if tp is not None else None)
        if not thick:
            thick = mm_to_ft(20.0)
            log.append(u"แผ่นหลังคา: ไม่ทราบความหนา ใช้ 20 มม. (ตั้งค่าเองในฟอร์มได้)")
        for fd in faces:
            try:
                s = rg.sheet_solid(fd, thick)
                _ds, ok = make_shape(s, mid, tag_for(fd["roof"]))
                counts["sheet"] += 1
                if not ok:
                    unpainted += 1
            except Exception as ex:
                failed += 1
                log.append(u"แผ่นหลังคา: สร้างไม่ได้ ({})".format(ex))

    # 2) ครอบสัน/ตะเฆ่สัน
    if v["ridge"]:
        tp, mid = chosen("t_ridge")
        prof = rg.cap_profile(mm_to_ft(v["cap_w"]), mm_to_ft(v["cap_h"]),
                              mm_to_ft(v["cap_h"] * 0.25))
        skipped_valley = 0
        for (a, b, convex, flat, roof) in cls["folds"]:
            if not convex:
                skipped_valley += 1
                continue
            try:
                s = rg.prism(a, b, prof)
                if s is None:
                    failed += 1
                    continue
                _ds, ok = make_shape(s, mid, tag_for(roof))
                counts["ridge"] += 1
                if not ok:
                    unpainted += 1
            except Exception as ex:
                failed += 1
                log.append(u"ครอบสัน: สร้างไม่ได้ ({})".format(ex))
        if skipped_valley:
            log.append(u"ข้ามแนวรางเว้า {} เส้น (ไม่ใช่งานครอบสัน)".format(
                skipped_valley))

    # 3) ครอบข้าง (ทดลอง) และ 4) เชิงชาย ใช้แผ่นตั้งเหมือนกัน
    for key, edges, label in (("verge", cls["verges"], u"ครอบข้าง"),
                              ("fascia", cls["eaves"], u"เชิงชาย")):
        if not v[key]:
            continue
        tp, mid = chosen("t_" + key)
        if key == "fascia":
            prof = rg.board_profile(mm_to_ft(v["fas_t"]), mm_to_ft(v["fas_h"]),
                                    mm_to_ft(20.0))
        else:
            prof = rg.board_profile(mm_to_ft(v["cap_h"] * 0.5),
                                    mm_to_ft(v["fas_h"]), mm_to_ft(20.0))
        for (a, b, out, roof) in edges:
            try:
                s = rg.prism(a, b, prof, out)
                if s is None:
                    failed += 1
                    continue
                _ds, ok = make_shape(s, mid, tag_for(roof))
                counts[key] += 1
                if not ok:
                    unpainted += 1
            except Exception as ex:
                failed += 1
                log.append(u"{}: สร้างไม่ได้ ({})".format(label, ex))
    t.Commit()
    tg.Assimilate()
except Exception:
    log.append(traceback.format_exc())
    try:
        t.RollBack()
    except Exception:
        pass
    tg.RollBack()
    path = ui.write_log("Roof_cover.txt", log)
    ui.summary(u"PK Revit — Roof Cover", u"❌ เกิดข้อผิดพลาด — ย้อนกลับทั้งหมดแล้ว",
               [], path)
    script.exit()

if unpainted:
    log.append(u"ทาวัสดุไม่สำเร็จ {} ชิ้น (ชิ้นงานยังอยู่ ไม่มีสี)".format(unpainted))
path = ui.write_log("Roof_cover.txt", log)
total = sum(counts.values())
head = u"✅ สร้างวัสดุมุง {} ชิ้น".format(total)
if failed:
    head += u" (สร้างไม่สำเร็จ {} ชิ้น)".format(failed)
lines = []
if v["sheet"]:
    lines.append(u"แผ่นหลังคา {} ผืน".format(counts["sheet"]))
if v["ridge"]:
    lines.append(u"ครอบสัน/ตะเฆ่สัน {} แนว".format(counts["ridge"]))
if v["verge"]:
    lines.append(u"ครอบข้าง {} แนว (ทดลอง)".format(counts["verge"]))
if v["fascia"]:
    lines.append(u"เชิงชาย {} แนว".format(counts["fascia"]))
if unpainted:
    lines.append(u"ทาวัสดุไม่สำเร็จ {} ชิ้น".format(unpainted))
lines.append(u"Ctrl+Z ครั้งเดียว ย้อนทั้งชุด")
ui.summary(u"PK Revit — Roof Cover", head, lines, path)
