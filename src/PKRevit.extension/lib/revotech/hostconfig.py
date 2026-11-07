# -*- coding: utf-8 -*-
"""จำค่าฟอร์มไว้ที่ host element (ExtensibleStorage) — ใช้กับ Propagate Rebar

แนวคิดเดียวกับ `HostConfigStore` ของ PK Tool: ทุกครั้งที่สร้างเหล็กสำเร็จ
บันทึก dict ค่าฟอร์ม (JSON) ติดไว้ที่ host เอง แล้วปุ่ม Propagate Rebar อ่านกลับ
ไปรันโมดูลเดิมกับ host ตัวอื่น (คำนวณใหม่จากขนาดของแต่ละตัวเอง)

ส่วนบน (dumps/loads/missing_bar_names) เป็นตรรกะล้วน ทดสอบนอก Revit ได้
ส่วนล่าง (save/load/hosts_from_override) ต้องมี Revit API — import ตอนเรียกใช้

Schema GUID ด้านล่างเป็นของ PK Revit โดยเฉพาะ (ไม่ซ้ำกับ PK Tool) — ห้ามเปลี่ยน
หลังเริ่มใช้งานจริง เพราะ Revit ค้นหา schema ด้วย GUID นี้
"""

import json

SCHEMA_GUID = "225EDFDD-7030-4A87-8305-B9BF06962BBE"
SCHEMA_NAME = "PKRevitHostConfig"
FIELD = "ConfigJson"
FORMAT = 1

# ชนิดของโมดูลเหล็ก (ค่าเดียวกับ MARK "PKRevit:<ชนิด>") → โฟลเดอร์ปุ่มที่ต้องรัน
KINDS = {
    "column": u"RebarColumn.pushbutton",
    "beam": u"RebarBeam.pushbutton",
    "footing": u"RebarFooting.pushbutton",
    "slab": u"RebarSlab.pushbutton",
    "stair": u"RebarStair.pushbutton",
}
KIND_LABELS = {"column": u"เสา", "beam": u"คาน", "footing": u"ฐานราก",
               "slab": u"พื้น", "stair": u"บันได"}


# ------------------------------------------------------------ ตรรกะล้วน
def dumps(kind, values):
    """dict ค่าฟอร์ม → ข้อความ JSON (tuple กลายเป็น list ซึ่งโมดูลอ่านได้ปกติ)"""
    text = json.dumps({"format": FORMAT, "kind": kind, "values": values},
                      ensure_ascii=False, default=str)
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    return text


def loads(text):
    """ข้อความ JSON → (kind, values) หรือ None ถ้าว่าง/เสีย/รูปแบบไม่ถูก"""
    if not text:
        return None
    try:
        d = json.loads(text)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    kind, values = d.get("kind"), d.get("values")
    if kind not in KINDS or not isinstance(values, dict):
        return None
    return kind, values


def iter_strings(obj):
    """ข้อความทุกตัวที่ซ้อนอยู่ใน dict/list/tuple"""
    if isinstance(obj, dict):
        for x in obj.values():
            for s in iter_strings(x):
                yield s
    elif isinstance(obj, (list, tuple)):
        for x in obj:
            for s in iter_strings(x):
                yield s
    elif isinstance(obj, (type(u""), str)):
        yield obj


def missing_bar_names(values, known_names, available):
    """ชื่อ Bar Type ที่ค่าที่จำไว้ใช้ แต่โปรเจกต์นี้ไม่มี (เรียงตามชื่อ)
    known_names = ชื่อเหล็กที่โปรแกรมรู้จัก (เช่น rb.BAR_NAMES) — ข้อความอื่นไม่นับ"""
    known = set(known_names)
    have = set(available)
    return sorted(set(s for s in iter_strings(values)
                      if s in known and s not in have))


# ------------------------------------------------------------ Revit
def _schema(create=True):
    import clr
    from System import Guid
    from Autodesk.Revit.DB.ExtensibleStorage import (
        Schema, SchemaBuilder, AccessLevel)
    guid = Guid(SCHEMA_GUID)
    s = Schema.Lookup(guid)
    if s is not None or not create:
        return s
    b = SchemaBuilder(guid)
    b.SetSchemaName(SCHEMA_NAME)
    b.SetReadAccessLevel(AccessLevel.Public)
    b.SetWriteAccessLevel(AccessLevel.Public)
    b.AddSimpleField(FIELD, clr.GetClrType(str))
    return b.Finish()


def save(host, kind, values):
    """บันทึกค่าลง host — ต้องเรียกใน Transaction ที่เปิดอยู่
    คืน True/False (ไม่โยน error: การจำค่าล้มต้องไม่ทำให้การสร้างเหล็กล้ม)"""
    try:
        from Autodesk.Revit.DB.ExtensibleStorage import Entity
        ent = Entity(_schema(True))
        ent.Set[str](FIELD, dumps(kind, values))
        host.SetEntity(ent)
        return True
    except Exception:
        return False


def load(host):
    """อ่านค่าที่จำไว้ที่ host → (kind, values) หรือ None ถ้าไม่เคยมี"""
    try:
        schema = _schema(False)
        if schema is None:
            return None
        ent = host.GetEntity(schema)
        if not ent.IsValid():
            return None
        return loads(ent.Get[str](FIELD))
    except Exception:
        return None


def override_values(override, known_names, available):
    """ค่าฟอร์มจาก CONFIG_OVERRIDE → (values, ชื่อ Bar Type ที่โปรเจกต์นี้ไม่มี)
    ปิด "same" เสมอ (hosts ถูกระบุมาแล้ว ห้ามขยายเป็นทั้งอาคาร)"""
    v = dict((override or {}).get("values") or {})
    v["same"] = False
    return v, missing_bar_names(v, known_names, available)


def override_problem(hosts, missing):
    """ข้อความแจ้งปัญหาเมื่อรันแบบ override (None = ไม่มีปัญหา)"""
    if not hosts:
        return u"ไม่พบ host ปลายทางที่จะใส่เหล็ก"
    if missing:
        return (u"โปรเจกต์นี้ยังไม่มี Bar Type: {} — สร้าง/โหลดใน Structure > "
                u"Reinforcement Settings ก่อน".format(u", ".join(missing)))
    return None


def hosts_from_override(doc, override):
    """override {"values":..., "hosts":[ElementId]} → list ของ Element (ข้ามที่หาไม่เจอ)"""
    out = []
    for eid in (override or {}).get("hosts") or []:
        try:
            e = doc.GetElement(eid)
        except Exception:
            e = None
        if e is not None:
            out.append(e)
    return out
