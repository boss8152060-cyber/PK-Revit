# -*- coding: utf-8 -*-
"""ตรรกะล้วนของ Color by Parameter (ไม่พึ่ง Revit ทดสอบนอก Revit ได้) py2.7 / py3

  - จัดสีอัตโนมัติ: ไล่เฉด (gradient) / คอนทราสต์สูง (contrast)
  - เรียงค่าแบบ natural (B2 มาก่อน B10)
  - จำสีล่าสุดต่อพารามิเตอร์ + จำ element ที่เครื่องมือระบายไว้ (สำหรับ Reset)
    เก็บเป็น JSON ที่ %LOCALAPPDATA%\\PKRevit\\ColorByParameter.json
สี = tuple (r, g, b) 0-255, เก็บใน JSON เป็นข้อความ "#RRGGBB"
"""

import io
import os
import re
import json

SCHEME_GRADIENT = "gradient"
SCHEME_CONTRAST = "contrast"
NONE_VALUE = u"(ไม่มีค่า)"


# ------------------------------------------------------------------ สี
def hsv_to_rgb(h, s, v):
    h = h % 360.0
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return (int(round((r + m) * 255)), int(round((g + m) * 255)),
            int(round((b + m) * 255)))


def generate_colors(count, scheme=SCHEME_CONTRAST, seed=0):
    """สีอัตโนมัติ count สี
    gradient: ไล่เฉดส้ม -> เขียว (ลำดับค่ามีความหมาย เช่นสถานะ)
    contrast: มุมทอง 137.5° + สลับความสว่าง/ความอิ่มตัว 3 ระดับ → สีที่อยู่ติดกันต่างกันชัด
    seed เลื่อนเฉดเพื่อ "สุ่มใหม่" (ผลเดิมเสมอเมื่อ seed เท่าเดิม)"""
    out = []
    levels = ((0.85, 0.95), (0.65, 0.78), (0.95, 0.60))
    for i in range(count):
        if scheme == SCHEME_GRADIENT:
            hue = 25 + 95.0 * i / max(count - 1, 1) + seed * 17
            out.append(hsv_to_rgb(hue, 0.78, 0.90))
        else:
            s, v = levels[i % 3]
            out.append(hsv_to_rgb(i * 137.508 + seed * 41, s, v))
    return out


def to_hex(rgb):
    return u"#%02X%02X%02X" % tuple(int(c) for c in rgb)


def from_hex(text):
    """'#RRGGBB' -> (r,g,b) หรือ None"""
    try:
        t = text.strip().lstrip("#")
        if len(t) != 6:
            return None
        return (int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16))
    except Exception:
        return None


# ----------------------------------------------------------- ค่า/กลุ่ม
def norm_value(s):
    if s is None:
        return NONE_VALUE
    s = u"%s" % s
    return s.strip() or NONE_VALUE


def natural_key(s):
    parts = re.split(r"(\d+)", u"%s" % s)
    return [(0, int(p), u"") if p.isdigit() else (1, 0, p.lower())
            for p in parts if p != u""]


def sorted_values(values):
    """เรียง natural; ค่า "(ไม่มีค่า)" ไว้ท้ายสุด"""
    vals = list(values)
    return (sorted([v for v in vals if v != NONE_VALUE], key=natural_key) +
            [v for v in vals if v == NONE_VALUE])


def group_values(items):
    """items: iterable ของ (view_key, element_id, value)
    -> {value: {view_key: [element_id,...]}}"""
    out = {}
    for view_key, eid, value in items:
        out.setdefault(norm_value(value), {}).setdefault(view_key, []).append(eid)
    return out


def count_of(per_view):
    return sum(len(v) for v in per_view.values())


def assign_colors(values, scheme, remembered=None, seed=0):
    """คืน {value: rgb} — ค่าที่เคยจำสีไว้ใช้สีเดิม ค่าใหม่ได้สีอัตโนมัติ
    (สีอัตโนมัติสร้างตามลำดับเฉพาะค่าใหม่ และเลี่ยงสีซ้ำกับที่จำไว้)"""
    values = sorted_values(values)
    remembered = remembered or {}
    colors = {}
    fresh = []
    for v in values:
        rgb = from_hex(remembered.get(v, u""))
        if rgb is not None:
            colors[v] = rgb
        else:
            fresh.append(v)
    if fresh:
        # สร้างเกินเล็กน้อยแล้วข้ามสีที่ซ้ำกับสีที่จำไว้
        taken = set(colors.values())
        pool = generate_colors(len(values) + len(fresh), scheme, seed)
        it = iter(pool)
        for v in fresh:
            c = next(it)
            while c in taken:
                c = next(it)
            taken.add(c)
            colors[v] = c
    return colors


# ------------------------------------------------------------ จำค่า JSON
def state_path(home=None):
    base = home or os.environ.get("PKREVIT_HOME") or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "PKRevit")
    return os.path.join(base, "ColorByParameter.json")


def load_state(path=None):
    """{'colors': {param_key: {value: '#RRGGBB'}}, 'applied': {doc: {view: {eid: '#RRGGBB'}}}}"""
    try:
        with io.open(path or state_path(), encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError
    except Exception:
        d = {}
    d.setdefault("colors", {})
    d.setdefault("applied", {})
    return d


def save_state(state, path=None):
    p = path or state_path()
    folder = os.path.dirname(p)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    text = json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True)
    if isinstance(text, bytes):  # py2 เมื่อมีแต่ ASCII
        text = text.decode("utf-8")
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(text)


def param_key(mode, param):
    return u"%s:%s" % (mode, param)


def remember_colors(state, key, colors):
    """colors {value: rgb}; รวมกับของเดิมของพารามิเตอร์เดียวกัน"""
    slot = state["colors"].setdefault(key, {})
    for v, rgb in colors.items():
        slot[v] = to_hex(rgb)


def remembered_for(state, key):
    return dict(state["colors"].get(key, {}))


def record_applied(state, doc_key, view_key, element_colors):
    """element_colors {element_id: rgb} — จำสิ่งที่ระบายไว้ (แทนของเดิมของ view นั้น
    เฉพาะ id ที่ระบายซ้ำ; id เดิมที่ไม่ได้ระบายใหม่ยังจำไว้)"""
    slot = state["applied"].setdefault(doc_key, {}).setdefault(u"%s" % view_key, {})
    for eid, rgb in element_colors.items():
        slot[u"%s" % eid] = to_hex(rgb)


def applied_for(state, doc_key, view_key=None):
    """{view_key: {eid(int): '#RRGGBB'}}; view_key=None = ทุก view ของเอกสาร"""
    doc = state["applied"].get(doc_key, {})
    out = {}
    for vk, m in doc.items():
        if view_key is None or vk == u"%s" % view_key:
            out[vk] = dict((int(e), c) for e, c in m.items())
    return out


def forget_applied(state, doc_key, view_key, element_ids=None):
    """ลบบันทึก (ทั้ง view หรือเฉพาะ id ที่ระบุ)"""
    doc = state["applied"].get(doc_key)
    if not doc:
        return
    vk = u"%s" % view_key
    if vk not in doc:
        return
    if element_ids is None:
        del doc[vk]
    else:
        for e in element_ids:
            doc[vk].pop(u"%s" % e, None)
        if not doc[vk]:
            del doc[vk]
    if not doc:
        del state["applied"][doc_key]


def should_reset(current_rgb, recorded_hex):
    """รีเซ็ตเฉพาะ element ที่สีปัจจุบันยังเป็นสีที่เราใส่ไว้ (ถ้าผู้ใช้เปลี่ยนไปแล้ว ไม่แตะ)
    current_rgb None = ไม่มี override อยู่แล้ว → ไม่ต้องรีเซ็ต แต่ลบบันทึกได้"""
    if current_rgb is None:
        return False
    return to_hex(current_rgb) == recorded_hex.upper()
