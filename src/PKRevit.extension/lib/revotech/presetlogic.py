# -*- coding: utf-8 -*-
"""ตรรกะล้วนของ Preset (ไม่แตะ Revit/WPF — ทดสอบนอก Revit ได้)

ข้อมูลของ control หนึ่งตัวเก็บเป็น {"k": ชนิด, "v": ค่า}
  k = "text"  (TextBox.Text)
      "combo" (ComboBox.SelectedItem)
      "check" (CheckBox/RadioButton.IsChecked)
ฝั่ง ui.py อ่านค่าจาก control จริงมาเป็น dict นี้ และเอา actions จาก plan_restore ไปตั้งกลับ
"""

import json
import re

FORMAT = 1
KINDS = ("text", "combo", "check")
MAX_NAME = 60
_BAD = re.compile(u'[<>:"/\\\\|?*\x00-\x1f]')
_RESERVED = set([u"CON", u"PRN", u"AUX", u"NUL"] +
                [u"COM%d" % i for i in range(1, 10)] +
                [u"LPT%d" % i for i in range(1, 10)])


def to_text(x):
    """แปลงเป็น unicode (ทั้ง py2 และ py3)"""
    if isinstance(x, bytes):
        return x.decode("utf-8", "replace")
    if isinstance(x, type(u"")):
        return x
    return u"%s" % (x,)


def safe_name(name):
    """ชื่อ preset ที่ใช้เป็นชื่อไฟล์ได้ปลอดภัย (ภาษาไทยคงไว้)
    คืน None ถ้าว่างหลังทำความสะอาด; ใช้ชื่อเดียวกันทั้ง Local และ Project"""
    if name is None:
        return None
    s = _BAD.sub(u"_", to_text(name))
    s = re.sub(u"\\s+", u" ", s).strip()
    s = s[:MAX_NAME].rstrip(u". ")
    if not s:
        return None
    if s.split(u".")[0].strip().upper() in _RESERVED:
        s = u"_" + s
    return s


def make_preset(module, controls):
    return {"format": FORMAT, "module": module, "controls": controls}


def dumps(preset):
    text = json.dumps(preset, ensure_ascii=False, indent=1, sort_keys=True,
                      default=to_text)
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    return text


def valid_preset(d):
    if not isinstance(d, dict) or not isinstance(d.get("controls"), dict):
        return False
    for name, c in d["controls"].items():
        if not isinstance(c, dict) or c.get("k") not in KINDS or "v" not in c:
            return False
    return True


def loads(text):
    """ข้อความ JSON → preset dict หรือ None ถ้าเสีย/รูปแบบไม่ถูก"""
    try:
        d = json.loads(text)
    except Exception:
        return None
    return d if valid_preset(d) else None


def _same(a, b):
    return a == b or to_text(a) == to_text(b)


_ORDER = {"check_off": 0, "text": 1, "combo": 2, "check_on": 3}


def plan_restore(controls, current):
    """วางแผนคืนค่า
    controls: {ชื่อ: {"k","v"}} ที่บันทึกไว้
    current : {ชื่อ: {"k": ชนิด, "items": [รายการปัจจุบัน] (เฉพาะ combo)}} ของฟอร์มตอนนี้
    คืน (actions, skipped)
      actions = [(ชื่อ, ชนิด, ค่า)]  — combo ค่าคือ index ในรายการปัจจุบัน
      skipped = [ข้อความไทยบอกเหตุผล]  (ไม่ใช่ error — ข้ามอย่างสุภาพ)"""
    actions, skipped = [], []
    for name in sorted(controls):
        c = controls[name]
        cur = current.get(name)
        if cur is None:
            skipped.append(u"ไม่มีช่อง “{}” ในฟอร์มนี้".format(to_text(name)))
            continue
        if cur.get("k") != c["k"]:
            skipped.append(u"ช่อง “{}” ชนิดไม่ตรงกับที่บันทึกไว้".format(to_text(name)))
            continue
        if c["k"] == "combo":
            idx = None
            for i, it in enumerate(cur.get("items") or []):
                if _same(it, c["v"]):
                    idx = i
                    break
            if idx is None:
                skipped.append(
                    u"“{}” ไม่มีในรายการของโปรเจกต์นี้ (ช่อง {}) — คงค่าเดิม".format(
                        to_text(c["v"]), to_text(name)))
                continue
            actions.append((name, "combo", idx))
        elif c["k"] == "check":
            actions.append((name, "check", bool(c["v"])))
        else:
            actions.append((name, "text", to_text(c["v"])))

    def key(a):
        if a[1] == "check":
            return (_ORDER["check_on" if a[2] else "check_off"], a[0])
        return (_ORDER[a[1]], a[0])
    actions.sort(key=key)
    return actions, skipped


def skipped_text(skipped, limit=4):
    """ข้อความสรุปรายการที่ข้าม (ตัดให้สั้น)"""
    if not skipped:
        return u""
    shown = list(skipped[:limit])
    if len(skipped) > limit:
        shown.append(u"…และอีก {} รายการ".format(len(skipped) - limit))
    return u"ข้ามบางค่า: " + u"; ".join(shown)
