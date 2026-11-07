# -*- coding: utf-8 -*-
"""ที่เก็บ Preset สองขอบเขต

  Local   : ไฟล์ %LOCALAPPDATA%\\PKRevit\\Presets\\<โมดูล>\\<ชื่อ>.json (เฉพาะเครื่องนี้)
  Project : ExtensibleStorage บน ProjectInformation ของไฟล์ .rvt (ติดไปกับไฟล์)
            เก็บทุกโมดูลรวมเป็น JSON เดียว {โมดูล: {ชื่อ: preset}}

ตรรกะ Local และการจัดการ dict ของ Project ทดสอบนอก Revit ได้ (ส่ง root เองได้);
ส่วนอ่าน/เขียน ProjectInformation ต้องมี Revit และการเขียนต้องอยู่ใน Transaction
"""

import io
import json
import os

from revotech import presetlogic as pl

PROJECT_SCHEMA_GUID = "141E55A9-4A16-4675-9305-921FF3CC74F8"
PROJECT_SCHEMA_NAME = "PKRevitProjectPresets"
PROJECT_FIELD = "PresetsJson"


def default_root():
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                        "PKRevit", "Presets")


# ------------------------------------------------------------ Local
def _dir(module, root):
    return os.path.join(root or default_root(), pl.safe_name(module) or u"_")


def _path(module, name, root):
    return os.path.join(_dir(module, root), pl.safe_name(name) + u".json")


def local_list(module, root=None):
    d = _dir(module, root)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        if fn.lower().endswith(".json"):
            out.append(fn[:-5])
    return sorted(out)


def local_save(module, name, preset, root=None):
    """เขียน preset ลงไฟล์ คืน path (โยน error ถ้าชื่อใช้ไม่ได้/เขียนไม่ได้)"""
    if pl.safe_name(name) is None:
        raise ValueError("invalid preset name")
    d = _dir(module, root)
    if not os.path.isdir(d):
        os.makedirs(d)
    path = _path(module, name, root)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(pl.dumps(preset))
    return path


def local_load(module, name, root=None):
    if pl.safe_name(name) is None:
        return None
    try:
        with io.open(_path(module, name, root), encoding="utf-8") as f:
            return pl.loads(f.read())
    except Exception:
        return None


def local_delete(module, name, root=None):
    if pl.safe_name(name) is None:
        return False
    try:
        os.remove(_path(module, name, root))
        return True
    except Exception:
        return False


# ------------------------------------------------------------ Project (dict ล้วน)
def project_loads(text):
    """ข้อความ JSON → {โมดูล: {ชื่อ: preset}} (เสีย/ว่าง → {}; ตัด preset ที่รูปแบบผิดทิ้ง)"""
    if not text:
        return {}
    try:
        d = json.loads(text)
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    out = {}
    for mod, presets in d.items():
        if not isinstance(presets, dict):
            continue
        good = dict((n, p) for n, p in presets.items() if pl.valid_preset(p))
        if good:
            out[mod] = good
    return out


def project_dumps(allp):
    text = json.dumps(allp, ensure_ascii=False, default=pl.to_text)
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    return text


def project_names(allp, module):
    return sorted(allp.get(module, {}).keys())


def project_put(allp, module, name, preset):
    allp.setdefault(module, {})[name] = preset
    return allp


def project_remove(allp, module, name):
    """ลบ preset; คืน True ถ้ามีให้ลบ"""
    mod = allp.get(module)
    if mod is None or name not in mod:
        return False
    del mod[name]
    if not mod:
        del allp[module]
    return True


# ------------------------------------------------------------ Project (Revit)
def _schema(create):
    import clr
    from System import Guid
    from Autodesk.Revit.DB.ExtensibleStorage import (
        Schema, SchemaBuilder, AccessLevel)
    guid = Guid(PROJECT_SCHEMA_GUID)
    s = Schema.Lookup(guid)
    if s is not None or not create:
        return s
    b = SchemaBuilder(guid)
    b.SetSchemaName(PROJECT_SCHEMA_NAME)
    b.SetReadAccessLevel(AccessLevel.Public)
    b.SetWriteAccessLevel(AccessLevel.Public)
    b.AddSimpleField(PROJECT_FIELD, clr.GetClrType(str))
    return b.Finish()


def project_read(doc):
    """อ่านทุก preset ของโปรเจกต์ที่เปิดอยู่ ({} ถ้าไม่มี/อ่านไม่ได้)"""
    try:
        schema = _schema(False)
        if schema is None:
            return {}
        ent = doc.ProjectInformation.GetEntity(schema)
        if not ent.IsValid():
            return {}
        return project_loads(ent.Get[str](PROJECT_FIELD))
    except Exception:
        return {}


def project_write(doc, allp):
    """เขียนกลับลง ProjectInformation — ต้องเรียกใน Transaction ที่เปิดอยู่"""
    from Autodesk.Revit.DB.ExtensibleStorage import Entity
    ent = Entity(_schema(True))
    ent.Set[str](PROJECT_FIELD, project_dumps(allp))
    doc.ProjectInformation.SetEntity(ent)
