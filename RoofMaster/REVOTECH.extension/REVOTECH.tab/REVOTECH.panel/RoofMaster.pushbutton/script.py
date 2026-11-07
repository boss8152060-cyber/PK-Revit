# -*- coding: utf-8 -*-
"""Roof Master — ปุ่มเดียวสร้างโครงหลังคาทั้งชุด

เด้งฟอร์มกรอกค่าหลัก แล้วรันปุ่มลูกไล่ตาม "ลำดับที่ทูพิสูจน์แล้วว่า
ผิดพลาดน้อยสุด":
  1) Hip Ridge Gen  — ตะเข้สัน + อกไก่
  2) Purlin Gen     — แป (+ตัดเฉียงที่ตะเข้ +จอยหลังคา)
  3) Valley Gen     — รางน้ำ + ตะเข้ราง
  4) Rafter Gen     — จันทัน (mirror layout +ตัดหัวเข้าตะเข้/ราง)
  5) Dang Gen       — ดั้ง (เสาสั้นรับอกไก่/จุดรวมตะเข้สัน ลงถึงโครงรับ)

กลไก: execfile สคริปต์ปุ่มลูกตัวจริง (ไม่ก็อปโค้ดมาซ้ำ — แก้ปุ่มลูก
ที่เดียวมีผลทั้งคู่) พร้อม inject CONFIG_OVERRIDE จากฟอร์ม
ทั้งหมดห่อ TransactionGroup เดียว → Ctrl+Z ครั้งเดียวย้อนทั้งชุด
ขั้นไหนล้ม: หยุดตรงนั้น ของที่ทำแล้วยังอยู่ (ย้อนได้)
ต้องเลือก Roof ก่อนกด — ทำเฉพาะหลังที่เลือก (ส่งผลทุกขั้น)
"""

import os
import traceback
from pyrevit import revit, DB, forms, script

doc = revit.doc
out = script.get_output()


def _selected_roofs():
    roofs = []
    for eid in revit.uidoc.Selection.GetElementIds():
        e = doc.GetElement(eid)
        try:
            if e.Category.Id.IntegerValue == int(DB.BuiltInCategory.OST_Roofs):
                roofs.append(e)
        except Exception:
            try:
                if e.Category.Id.Value == int(DB.BuiltInCategory.OST_Roofs):
                    roofs.append(e)
            except Exception:
                pass
    return roofs


_roofs_at_start = _selected_roofs()
if not _roofs_at_start:
    forms.alert(u"กรุณาเลือกหลังคาก่อน — คลิกหลังคา (Roof) ที่ต้องการ "
                u"แล้วกดปุ่ม Roof Master ใหม่ (เลือกได้หลายหลัง)",
                title=u"REVOTECH — Roof Master", exitscript=True)

# ===================== ฟอร์ม (WPF ธีมเข้ม-ส้ม REVOTECH) =====================

# คำค้นสำหรับเลือก type อัตโนมัติ (key = ชื่อ combobox)
AUTO_PICK = [
    ("cmb_hip", u"ตะเข้สัน"),
    ("cmb_ridge", u"อกไก่"),
    ("cmb_purlin", u"แป"),
    ("cmb_rafter", u"จันทัน"),
    ("cmb_gutter", u"รางน้ำ"),
    ("cmb_dang", u"ดั้ง"),
]
NONE_LABEL = u"— ไม่ระบุ (ค้นหาตามชื่อแบบเดิม) —"


def _scan_framing_types():
    names = []
    for t in DB.FilteredElementCollector(doc)               .OfCategory(DB.BuiltInCategory.OST_StructuralFraming)               .WhereElementIsElementType():
        try:
            nm = DB.Element.Name.__get__(t)
        except Exception:
            continue
        names.append(nm)
    return sorted(set(names))


def _scan_column_types():
    """type เสา (Structural Column) — ดั้งเป็นเสาสั้น จึงต้องโชว์ใน dropdown ดั้งด้วย"""
    names = []
    for t in DB.FilteredElementCollector(doc) \
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns) \
               .WhereElementIsElementType():
        try:
            names.append(DB.Element.Name.__get__(t))
        except Exception:
            continue
    return sorted(set(names))


class MasterForm(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, script.get_bundle_file("ui.xaml"))
        self.values = None
        self._busy = False
        self.run_btn.Click += self._go
        self.close_btn.Click += self._cancel
        self.title_bar.MouseLeftButtonDown += self._drag
        self.cb_all.Click += self._toggle_all
        for cb in self._step_boxes():
            cb.Click += self._sync_all
        self._fill_types()

    def _step_boxes(self):
        return [self.cb_hip, self.cb_purlin, self.cb_valley, self.cb_rafter,
                self.cb_dang]

    def _toggle_all(self, sender, args):
        on = bool(self.cb_all.IsChecked)
        for cb in self._step_boxes():
            cb.IsChecked = on

    def _sync_all(self, sender, args):
        self.cb_all.IsChecked = all(bool(cb.IsChecked)
                                    for cb in self._step_boxes())

    def _fill_types(self):
        """เติม dropdown ด้วย type เหล็กในโปรเจกต์ + เลือกอัตโนมัติจากคำในชื่อ"""
        framing_names = _scan_framing_types()
        dang_names = sorted(set(_scan_column_types() + framing_names))
        for cmb_name, kw in AUTO_PICK:
            names = dang_names if cmb_name == "cmb_dang" else framing_names
            cmb = getattr(self, cmb_name)
            cmb.Items.Add(NONE_LABEL)
            for nm in names:
                cmb.Items.Add(nm)
            pick = 0
            for i, nm in enumerate(names):
                # "แป" สั้นมาก — กันไปชนชื่ออื่นที่มีคำว่าแป (เช่น แปลง) ด้วยการ
                # ไม่เอาชื่อที่มีคำของ type อื่นอยู่ด้วย
                if kw in nm and not self._clash(kw, nm):
                    pick = i + 1
                    break
            cmb.SelectedIndex = pick

    @staticmethod
    def _clash(kw, nm):
        others = [k for _, k in AUTO_PICK if k != kw and kw in k]
        return any(o in nm for o in others)

    def _drag(self, sender, args):
        try:
            self.DragMove()
        except Exception:
            pass

    def _cancel(self, sender, args):
        self.Close()

    @staticmethod
    def _chosen(cmb):
        """ชื่อ type ที่เลือก หรือ None ถ้าเลือก "ไม่ระบุ" """
        item = cmb.SelectedItem
        if item is None or item == NONE_LABEL:
            return None
        return item

    def _go(self, sender, args):
        self.values = {
            "do_hip": True if self.cb_hip.IsChecked else False,
            "do_purlin": True if self.cb_purlin.IsChecked else False,
            "do_valley": True if self.cb_valley.IsChecked else False,
            "do_rafter": True if self.cb_rafter.IsChecked else False,
            "do_dang": True if self.cb_dang.IsChecked else False,
            "dang_len": self.tb_dang.Text,
            "purlin_sp": self.tb_purlin.Text,
            "eave_off": self.tb_eave.Text,
            "ridge_off": self.tb_ridge.Text,
            "rafter_sp": self.tb_rafter.Text,
            "t_hip": self._chosen(self.cmb_hip),
            "t_ridge": self._chosen(self.cmb_ridge),
            "t_purlin": self._chosen(self.cmb_purlin),
            "t_rafter": self._chosen(self.cmb_rafter),
            "t_gutter": self._chosen(self.cmb_gutter),
            "t_dang": self._chosen(self.cmb_dang),
        }
        self.Close()


_form = MasterForm()
_form.ShowDialog()
if not _form.values:
    script.exit()
v = _form.values


def num(key, default):
    try:
        return float(str(v.get(key, default)).strip())
    except Exception:
        return float(default)


# ===================== ลำดับขั้น =====================
HERE = os.path.dirname(__file__)
PANEL = os.path.dirname(HERE)   # REVOTECH.panel


def step_path(folder):
    """หาสคริปต์ปุ่มลูก — รองรับ 2 แบบ:
    (ก) วางเป็นปุ่มพี่น้องข้างแผงเดียวกัน (เครื่องหลัก มีครบ 6 ปุ่ม)
    (ข) ฝังใน engines/ ในตัว Roof Master (แพ็คแจกเพื่อน เห็นปุ่มเดียว)"""
    base = folder.replace(".pushbutton", "")
    cands = [os.path.join(PANEL, folder, "script.py"),
             os.path.join(HERE, "engines", folder, "script.py"),
             # แพ็คที่ติดตั้งแล้วตั้งชื่อไฟล์ตามโฟลเดอร์ (เช่น HipRidgeGen.py)
             os.path.join(HERE, "engines", folder, base + ".py")]
    for c in cands:
        if os.path.isfile(c):
            return c
    return cands[0]


def kw(name):
    """ชื่อ type ที่เลือก → รายการคำค้น (engine ใช้ all-keywords-in-name)"""
    return [name] if name else None


def only(d):
    """ตัดคีย์ที่ผู้ใช้เลือก "ไม่ระบุ" ออก → engine ใช้ค่าตั้งต้นของตัวเอง"""
    return dict((k, x) for k, x in d.items() if x is not None)


T_HIP, T_RIDGE = v.get("t_hip"), v.get("t_ridge")
T_PURLIN, T_RAFTER, T_GUTTER = (v.get("t_purlin"), v.get("t_rafter"),
                                v.get("t_gutter"))
T_DANG = v.get("t_dang")
_hip_hit = [x for x in (T_HIP, T_RIDGE) if x]

STEPS = []
if v.get("do_hip"):
    STEPS.append((u"1) ตะเข้สัน + อกไก่", "HipRidgeGen.pushbutton", only({
        "TYPE_KEYWORDS": kw(T_HIP),
        "RIDGE_TYPE_KEYWORDS": kw(T_RIDGE),
    })))
if v.get("do_purlin"):
    STEPS.append((u"2) แป", "PurlinGen.pushbutton", only({
        "MAX_SPACING_MM": num("purlin_sp", 340),
        "EAVE_OFFSET_MM": num("eave_off", 340),
        "RIDGE_OFFSET_MM": num("ridge_off", 50),
        "TYPE_KEYWORDS": kw(T_PURLIN),
    })))
if v.get("do_valley"):
    # ตะเข้รางขนาบ/รางน้ำยก ใช้ค่าที่จูนไว้ใน Valley Gen เอง (100/110)
    # — ทูให้ซ่อนจากฟอร์ม คนทั่วไปไม่ต้องยุ่ง
    STEPS.append((u"3) รางน้ำ + ตะเข้ราง", "ValleyGen.pushbutton", only({
        "GUTTER_TYPE_KEYWORDS": kw(T_GUTTER),
        "BASE_TYPE_KEYWORDS": kw(T_HIP),
    })))
if v.get("do_rafter"):
    STEPS.append((u"4) จันทัน", "RafterGen.pushbutton", only({
        "FIXED_SPACING_MM": num("rafter_sp", 1000),
        "TYPE_KEYWORDS": kw(T_RAFTER),
        "HIP_TYPE_KEYWORDS": _hip_hit or None,
    })))
if v.get("do_dang"):
    STEPS.append((u"5) ดั้ง", "DangGen.pushbutton", only({
        "FALLBACK_LENGTH_MM": num("dang_len", 1000),
        "TYPE_KEYWORDS": kw(T_DANG),
        "HIP_TYPE_KEYWORDS": kw(T_HIP),
        "RIDGE_TYPE_KEYWORDS": kw(T_RIDGE),
    })))
if not STEPS:
    forms.alert(u"ไม่ได้เลือกขั้นตอนไหนเลย", exitscript=True)

out.print_md(u"# 🏠 Roof Master — เริ่มสร้างโครงหลังคา ({} ขั้น)".format(
    len(STEPS)))

tg = DB.TransactionGroup(doc, "REVOTECH - Roof Master")
tg.Start()
done, failed = [], None
for title, folder, ovr in STEPS:
    out.print_md(u"\n---\n\n# ▶ {}".format(title))
    path = step_path(folder)
    g = {"__file__": path, "__name__": "__main__", "CONFIG_OVERRIDE": ovr}
    try:
        execfile(path, g)
        done.append(title)
    except SystemExit:
        # ปุ่มลูกหยุดเอง (forms.alert exitscript) — ข้อความแจ้งขึ้นไปแล้ว
        failed = title
        out.print_md(u"\n⚠ **{} หยุดกลางทาง** (ดูกล่องข้อความ/รายงานข้างบน) "
                     u"— ขั้นถัดไปไม่รัน".format(title))
        break
    except Exception:
        failed = title
        out.print_md(u"\n❌ **{} ผิดพลาด:**\n```\n{}\n```".format(
            title, traceback.format_exc()))
        break
try:
    tg.Assimilate()
except Exception:
    try:
        tg.RollBack()
    except Exception:
        pass

out.print_md(u"\n---\n\n# 🏁 Roof Master จบแล้ว")
if done:
    out.print_md(u"- สำเร็จ: **{}**".format(u" → ".join(done)))
if failed:
    out.print_md(u"- ⚠ หยุดที่: **{}** — แก้ตามข้อความแล้วกดใหม่ "
                 u"(ติ๊กเฉพาะขั้นที่เหลือได้)".format(failed))
else:
    out.print_md(u"- ครบทุกขั้น ✅")
out.print_md(u"ไม่พอใจผลลัพธ์ → **Ctrl+Z ครั้งเดียว** ย้อนได้ทั้งชุด")


def _count_framing():
    """นับ Structural Framing ในโมเดลตามชื่อ type (สำหรับสรุปผล)"""
    counts = {}
    for e in DB.FilteredElementCollector(doc) \
               .OfCategory(DB.BuiltInCategory.OST_StructuralFraming) \
               .WhereElementIsNotElementType():
        try:
            t = doc.GetElement(e.GetTypeId())
            nm = DB.Element.Name.__get__(t)
        except Exception:
            continue
        counts[nm] = counts.get(nm, 0) + 1
    # ดั้งเป็น Structural Column
    for e in DB.FilteredElementCollector(doc) \
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns) \
               .WhereElementIsNotElementType():
        try:
            t = doc.GetElement(e.GetTypeId())
            nm = DB.Element.Name.__get__(t)
        except Exception:
            continue
        counts[nm] = counts.get(nm, 0) + 1
    return counts


def _summary_lines():
    counts = _count_framing()
    lines = []
    for label, chosen, kws in (
            (u"ตะเข้สัน", T_HIP, [u"ตะเข้สัน"]),
            (u"อกไก่", T_RIDGE, [u"อกไก่"]),
            (u"แป", T_PURLIN, [u"แป"]),
            (u"จันทัน", T_RAFTER, [u"จันทัน"]),
            (u"รางน้ำ", T_GUTTER, [u"รางน้ำ"]),
            (u"ดั้ง", T_DANG, [u"ดั้ง"]),
            (u"ตะเข้ราง", None, [u"ตะเข้ราง"])):
        if chosen:
            n = counts.get(chosen, 0)
        else:
            n = sum(c for nm, c in counts.items()
                    if all(k in nm for k in kws))
        lines.append(u"{}: {} ตัว".format(label, n))
    return lines


# สรุปผลเป็น popup สั้นๆ — รายละเอียดเต็มอยู่ในหน้าต่าง output
_head = (u"❌ หยุดที่ขั้น {} — ดูรายละเอียดในหน้าต่าง output".format(failed)
         if failed else u"✅ โครงหลังคาพร้อมแล้ว ({}/{} ขั้น)".format(
             len(done), len(STEPS)))
forms.alert(_head + u"\n\n" + u"\n".join(_summary_lines()) +
            u"\n\nCtrl+Z ครั้งเดียว ย้อนทั้งชุด",
            title=u"REVOTECH — Roof Master")
