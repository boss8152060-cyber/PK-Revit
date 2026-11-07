# -*- coding: utf-8 -*-
"""ระบบแปลข้อความ TH/EN/LO แบบพจนานุกรม key -> ข้อความ (ไม่พึ่ง Revit รันนอก Revit ได้)

ใช้:  from revotech.i18n import t;  t("ui.close");  t("ui.select_first", what=u"เสา", hint=u"")
ภาษาที่เลือกเก็บใน %LOCALAPPDATA%\\PK Revit\\settings.json (คีย์ "language")
ลำดับ fallback: ภาษาปัจจุบัน -> อังกฤษ -> ไทย -> ตัวคีย์เอง (ไม่ error เมื่อขาดคำแปล)

คำแปลลาว: ใส่เฉพาะที่แน่ใจ ที่เหลือจะ fallback เป็นอังกฤษ — ต้องให้เจ้าของภาษาตรวจ
(ดู docs/license-i18n.md) py2.7 / py3 ใช้ร่วมกันได้
"""

import os
import io
import json

LANGS = ("th", "en", "lo")
DEFAULT_LANG = "th"
LANG_NAMES = {"th": u"ไทย", "en": u"English", "lo": u"ລາວ"}
_FALLBACK = ("en", "th")

_current = [None]  # cache ภาษาที่โหลดแล้ว (None = ยังไม่โหลด)


def settings_dir():
    """โฟลเดอร์เก็บ settings; PKREVIT_HOME (env) ใช้ override เช่นตอนเทสต์"""
    env = os.environ.get("PKREVIT_HOME")
    if env:
        return env
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                        "PKRevit")


def settings_path():
    return os.path.join(settings_dir(), "settings.json")


def load_settings():
    """อ่าน settings.json — ไฟล์ไม่มี/เสีย คืน {}"""
    try:
        with io.open(settings_path(), encoding="utf-8") as f:
            data = json.loads(f.read())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data):
    """เขียน settings.json (คืน True/False) ไม่ throw"""
    try:
        d = settings_dir()
        if not os.path.isdir(d):
            os.makedirs(d)
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        if not isinstance(text, type(u"")):
            text = text.decode("utf-8")
        with io.open(settings_path(), "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception:
        return False


def normalize_lang(code):
    """รับ 'EN', 'en-US', ' lo ' -> 'en'/'lo' ; ไม่รู้จักคืน None"""
    if not code:
        return None
    c = str(code).strip().lower().replace("_", "-").split("-")[0]
    return c if c in LANGS else None


def get_language():
    if _current[0] is None:
        _current[0] = normalize_lang(load_settings().get("language")) \
            or DEFAULT_LANG
    return _current[0]


def set_language(code, persist=True):
    """ตั้งภาษา (และบันทึกถ้า persist) คืนรหัสที่ตั้งจริง; รหัสไม่รู้จัก -> ไม่เปลี่ยน"""
    c = normalize_lang(code)
    if c is None:
        return get_language()
    _current[0] = c
    if persist:
        s = load_settings()
        s["language"] = c
        save_settings(s)
    return c


def reset_cache():
    """ล้าง cache ภาษา (ให้โหลดจากไฟล์ใหม่) — ใช้ในเทสต์"""
    _current[0] = None


def lookup(key, lang, table=None):
    """คืนข้อความตามลำดับ fallback หรือ None ถ้าไม่มีเลย (ฟังก์ชันล้วน)"""
    entry = (STRINGS if table is None else table).get(key)
    if not entry:
        return None
    for lg in (lang,) + _FALLBACK:
        if entry.get(lg):
            return entry[lg]
    return None


def t(key, **fmt):
    """ข้อความของ key ตามภาษาปัจจุบัน; fmt ใช้ str.format; ไม่พบ key คืนตัว key"""
    s = lookup(key, get_language())
    if s is None:
        return key
    if fmt:
        try:
            return s.format(**fmt)
        except Exception:
            return s
    return s


def missing_translations(table=None, lang="en"):
    """รายการ key ที่ยังไม่มีคำแปลภาษา lang (ไว้ตรวจความครบ)"""
    tb = STRINGS if table is None else table
    return sorted(k for k, v in tb.items() if not v.get(lang))


# --------------------------------------------------------------------------
# พจนานุกรม  key -> {lang: ข้อความ}   (ไทยเป็นต้นฉบับ; "lo" ใส่เฉพาะที่แน่ใจ)
# --------------------------------------------------------------------------
STRINGS = {
    # ---- lib/revotech/ui.py (ตัวอย่างข้อความที่ย้ายมาใช้ t() ภายหลัง)
    "ui.close": {"th": u"ปิด", "en": u"Close", "lo": u"ປິດ"},
    "ui.details": {"th": u"รายละเอียด: ", "en": u"Details: ", "lo": u"ລາຍລະອຽດ: "},
    "ui.select_first": {
        "th": u"กรุณาเลือก{what}ก่อน {hint}",
        "en": u"Please select {what} first. {hint}",
        "lo": u"ກະລຸນາເລືອກ{what}ກ່ອນ {hint}"},
    "ui.element.column": {"th": u"เสา", "en": u"a column", "lo": u"ເສົາ"},
    "ui.element.beam": {"th": u"คาน", "en": u"a beam"},
    "ui.element.slab": {"th": u"พื้น", "en": u"a slab"},
    "ui.element.footing": {"th": u"ฐานราก", "en": u"a footing"},
    "ui.summary.done": {"th": u"เสร็จสิ้น", "en": u"Done"},
    "ui.summary.created": {"th": u"สร้างแล้ว {n} รายการ",
                           "en": u"Created {n} item(s)"},
    "ui.summary.failed": {"th": u"ไม่สำเร็จ {n} รายการ",
                          "en": u"{n} item(s) failed"},
    "ui.summary.log": {"th": u"รายละเอียด: {path}", "en": u"Details: {path}"},
    "ui.ctrl_z_hint": {"th": u"Ctrl+Z ครั้งเดียวย้อนทั้งชุด",
                       "en": u"A single Ctrl+Z undoes the whole batch"},

    # ---- ปุ่ม License
    "license.title": {"th": u"สิทธิ์การใช้งาน", "en": u"License"},
    "license.subtitle": {"th": u"เปิดสิทธิ์การใช้งาน และเลือกภาษา — PK Revit",
                         "en": u"Activate your license and choose a language — PK Revit"},
    "license.key_label": {"th": u"รหัสสิทธิ์การใช้งาน", "en": u"License key"},
    "license.machine_label": {"th": u"รหัสเครื่องนี้", "en": u"This machine ID"},
    "license.status_label": {"th": u"สถานะ", "en": u"Status", "lo": u"ສະຖານະ"},
    "license.language_label": {"th": u"ภาษา", "en": u"Language", "lo": u"ພາສາ"},
    "license.activate": {"th": u"เปิดสิทธิ์การใช้งาน", "en": u"Activate"},
    "license.lang_note": {"th": u"ภาษาจะมีผลเต็มที่เมื่อเปิดหน้าต่างครั้งถัดไป",
                          "en": u"Language fully applies the next time a window opens"},
    "license.status.dev": {
        "th": u"โหมดนักพัฒนา (dev) — เปิดใช้ทุกฟีเจอร์",
        "en": u"Developer mode (dev) — all features enabled"},
    "license.status.unlicensed": {"th": u"ยังไม่ได้เปิดสิทธิ์",
                                  "en": u"Not activated"},
    "license.status.licensed": {"th": u"เปิดสิทธิ์แล้ว (รหัส {key})",
                                "en": u"Activated (key {key})"},
    "license.status.other_machine": {
        "th": u"รหัสที่บันทึกไว้ผูกกับเครื่องอื่น — ต้องเปิดสิทธิ์ใหม่",
        "en": u"The saved key belongs to another machine — please activate again"},
    "license.note_not_enforced": {
        "th": u"หมายเหตุ: ขณะนี้ยังไม่บล็อกการใช้งานโมดูลใดๆ",
        "en": u"Note: no module is blocked by the license yet"},
    "license.msg.ok": {"th": u"เปิดสิทธิ์สำเร็จ", "en": u"Activated successfully"},
    # เหตุผลที่ validate ไม่ผ่าน (license.reason.<code>)
    "license.reason.ok": {"th": u"ผ่าน", "en": u"OK"},
    "license.reason.empty_key": {"th": u"กรุณาป้อนรหัส", "en": u"Please enter a key"},
    "license.reason.bad_format": {
        "th": u"รูปแบบรหัสไม่ถูกต้อง (ต้องเป็น XXXXX-XXXXX-XXXXX-XXXXX)",
        "en": u"Invalid key format (expected XXXXX-XXXXX-XXXXX-XXXXX)"},
    "license.reason.unknown_key": {"th": u"ไม่พบรหัสนี้", "en": u"Key not found"},
    "license.reason.revoked": {"th": u"รหัสนี้ถูกยกเลิกแล้ว",
                               "en": u"This key has been revoked"},
    "license.reason.machine_limit": {
        "th": u"รหัสนี้ถูกใช้ครบจำนวนเครื่องแล้ว ({limit} เครื่อง)",
        "en": u"This key is already used on the maximum number of machines ({limit})"},
    "license.reason.in_use_elsewhere": {
        "th": u"รหัสนี้กำลังใช้งานอยู่บนอีกเครื่อง (ใช้พร้อมกันไม่ได้)",
        "en": u"This key is currently in use on another machine (no simultaneous use)"},
    "license.reason.no_server": {
        "th": u"ยังไม่ได้ตั้งค่าเซิร์ฟเวอร์ตรวจสิทธิ์ — ตรวจรหัสไม่ได้",
        "en": u"No license server is configured — cannot verify the key"},
    "license.reason.server_error": {
        "th": u"ติดต่อเซิร์ฟเวอร์ไม่ได้ ลองใหม่ภายหลัง",
        "en": u"Could not reach the license server. Try again later"},
    "license.reason.dev_mode": {"th": u"โหมดนักพัฒนา", "en": u"Developer mode"},
}
