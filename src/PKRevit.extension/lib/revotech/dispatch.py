# -*- coding: utf-8 -*-
"""ตัวช่วยปุ่มรวม (Rebar / Roof): จัดชนิดชิ้นงาน, หาสคริปต์โมดูล, รันโมดูลด้วย execfile

ส่วนบน (classify / group_by_kind / find_script / plan_text) เป็นตรรกะล้วน
ทดสอบนอก Revit ได้ — ส่วน kind_of / set_selection / run_script ต้องมี Revit/pyRevit
(import ตอนเรียกใช้)

ข้อตกลงสคริปต์โมดูล: ในโฟลเดอร์โมดูลมี `script.py` หรือ `<ชื่อโมดูล>.py`
(เช่น RebarColumn.py) อย่างใดอย่างหนึ่ง — ตอนติดตั้งในเครื่องผู้ใช้อาจเปลี่ยนชื่อ
"""

import os
import sys

# ลำดับชนิดที่ใช้ทั้งในหน้าต่างเลือกและการทำทีละชนิด
KIND_ORDER = ("column", "beam", "footing", "slab", "stair")

# ชนิด → ชื่อ BuiltInCategory
KIND_CATEGORY = {
    "column": "OST_StructuralColumns",
    "beam": "OST_StructuralFraming",
    "footing": "OST_StructuralFoundation",
    "slab": "OST_Floors",
    "stair": "OST_Stairs",
}

# ชนิด → โฟลเดอร์โมดูลใน Rebar.pushbutton/modules/
KIND_FOLDERS = {
    "column": u"RebarColumn.pushbutton",
    "beam": u"RebarBeam.pushbutton",
    "footing": u"RebarFooting.pushbutton",
    "slab": u"RebarSlab.pushbutton",
    "stair": u"RebarStair.pushbutton",
}

KIND_LABELS = {"column": u"เสา", "beam": u"คาน", "footing": u"ฐานราก",
               "slab": u"พื้น", "stair": u"บันได"}


# ------------------------------------------------------------ ตรรกะล้วน
def classify(cat_name, is_beam=False):
    """ชื่อ BuiltInCategory (เช่น 'OST_Floors') → ชนิดโมดูลเหล็ก หรือ None

    Structural Framing นับเฉพาะที่เป็น Beam (is_beam=True) — เหล็กค้ำยัน/อื่นๆ ไม่รองรับ
    """
    for kind in KIND_ORDER:
        if KIND_CATEGORY[kind] == cat_name:
            if kind == "beam" and not is_beam:
                return None
            return kind
    return None


def group_by_kind(pairs):
    """[(kind, item), ...] → [(kind, [item, ...]), ...] เรียงตาม KIND_ORDER

    ข้ามรายการที่ kind เป็น None; ชนิดที่ไม่มีของจะไม่ถูกใส่
    """
    buckets = dict((k, []) for k in KIND_ORDER)
    for kind, item in pairs:
        if kind in buckets:
            buckets[kind].append(item)
    return [(k, buckets[k]) for k in KIND_ORDER if buckets[k]]


def script_candidates(folder_dir, folder_name):
    """ชื่อไฟล์สคริปต์ที่ยอมรับ ตามลำดับ: script.py แล้ว <ชื่อโมดูล>.py"""
    base = folder_name
    for ext in (u".pushbutton", u".pulldown"):
        if base.endswith(ext):
            base = base[:-len(ext)]
    return [os.path.join(folder_dir, u"script.py"),
            os.path.join(folder_dir, base + u".py")]


def find_script(parent_dir, folder_name):
    """หาสคริปต์ของโมดูล `folder_name` ใต้ `parent_dir` — None ถ้าไม่พบ"""
    folder_dir = os.path.join(parent_dir, folder_name)
    for c in script_candidates(folder_dir, folder_name):
        if os.path.isfile(c):
            return c
    return None


def find_in_dirs(parent_dirs, folder_name):
    """หาโมดูลจากหลายที่ (ตามลำดับ) — ใช้กับ Propagate Rebar"""
    for d in parent_dirs:
        p = find_script(d, folder_name)
        if p:
            return p
    return None


def plan_text(groups):
    """ข้อความถามก่อนทำทีละชนิด: groups = [(kind, [item...]), ...]"""
    lines = [u"{} {} ตัว".format(KIND_LABELS[k], len(v)) for k, v in groups]
    order = u" → ".join(KIND_LABELS[k] for k, _v in groups)
    return (u"ที่เลือกไว้มีหลายชนิด:\n  " + u"\n  ".join(lines) +
            u"\n\nจะทำทีละชนิดตามลำดับ {} (แต่ละชนิดมีหน้าต่างของตัวเอง) — ทำต่อไหม?"
            .format(order))


# ------------------------------------------------------------ ส่วนที่ใช้ Revit
def kind_of(e):
    """ชนิดโมดูลเหล็กของ element (None = ไม่รองรับ)"""
    from pyrevit import DB
    from revotech.rvt import cat_id
    cid = cat_id(e)
    if cid is None:
        return None
    bic = DB.BuiltInCategory
    for kind in KIND_ORDER:
        if cid == int(getattr(bic, KIND_CATEGORY[kind])):
            if kind != "beam":
                return kind
            try:
                is_beam = e.StructuralType == DB.Structure.StructuralType.Beam
            except Exception:
                is_beam = False
            return "beam" if is_beam else None
    return None


def set_selection(uidoc, ids):
    """ตั้ง selection ใน Revit เป็นรายการ ElementId"""
    from System.Collections.Generic import List
    from pyrevit import DB
    lst = List[DB.ElementId]()
    for i in ids:
        lst.Add(i)
    uidoc.Selection.SetElementIds(lst)


def run_script(path, extra_globals=None):
    """รันสคริปต์โมดูลด้วย execfile ใน namespace ใหม่ (เหมือนที่ Roof Master/Propagate ทำ)

    - ตั้ง __file__ / __name__ เป็นของโมดูล → body.xaml และ import ไฟล์ข้างๆ หาเจอ
    - ใส่โฟลเดอร์โมดูลใน sys.path (เช่น `import footing_calc`) ถ้ายังไม่มี
    - script.exit() ในโมดูลคือ SystemExit → ปล่อยให้ผู้เรียกจับเอง
      (โมดูลเหล็กจบด้วย script.exit() ตามปกติ จึงแยก "เสร็จ" กับ "ยกเลิก" ไม่ได้)
    """
    folder = os.path.dirname(os.path.abspath(path))
    if folder not in sys.path:
        sys.path.insert(0, folder)
    g = {"__file__": path, "__name__": "__main__"}
    if extra_globals:
        g.update(extra_globals)
    try:
        execfile(path, g)       # IronPython 2.7 (pyRevit)
    except NameError as ex:
        if "execfile" not in str(ex):
            raise
        with open(path, "rb") as f:     # CPython — ใช้ตอนทดสอบเท่านั้น
            code = compile(f.read(), path, "exec")
        exec(code, g)
    return g
