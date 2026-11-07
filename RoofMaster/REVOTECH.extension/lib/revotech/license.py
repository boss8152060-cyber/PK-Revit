# -*- coding: utf-8 -*-
"""โครงตรวจสิทธิ์การใช้งาน REVOTECH (เบื้องต้น) — ไม่ฝังคีย์/ความลับใดๆ

หลักการ
- ผู้ใช้ป้อนรหัส -> ผูกกับ fingerprint เครื่อง -> ตัดสินที่ "validator" (interface เดียว):
      validator.validate(key, machine_id) -> Result(ok, reason, detail)
- ตอนนี้มี validator ให้: DevValidator (เปิดทุกอย่าง), NoServerValidator (ค่าเริ่มต้น
  ถ้าไม่ใช่ dev: ตอบไม่ผ่านเหตุผล no_server), InMemoryValidator (ไว้เทสต์/ต้นแบบ server)
  เซิร์ฟเวอร์จริงภายหลังให้เขียน RemoteValidator ที่ implement validate() เดียวกัน
- ลอจิก "ไม่เกิน 2 เครื่อง" อยู่ที่ฟังก์ชันล้วน check_activation() เพื่อเอาไปใช้ฝั่ง server ได้
- โหมด dev: ตั้ง env  REVOTECH_LICENSE_MODE=dev  -> ผ่านทุกอย่าง
- ไฟล์ license.json ฝั่งเครื่องผู้ใช้ "เชื่อถือไม่ได้" (แก้เองได้) ใช้แค่จำสถานะ/แสดงผล
  การบังคับจริงต้องพึ่ง server — ดู docs/license-i18n.md
- ยังไม่มีโมดูลใดเรียก license (ไม่บล็อกอะไร) py2.7 / py3 ใช้ร่วมกันได้
"""

import os
import io
import re
import json
import hashlib
import platform
import datetime

from revotech import i18n

MAX_MACHINES = 2
ENV_MODE = "REVOTECH_LICENSE_MODE"
KEY_RE = re.compile(r"^[A-Z0-9]{5}(-[A-Z0-9]{5}){3}$")

# reason codes (ตรงกับ i18n key "license.reason.<code>")
OK = "ok"
EMPTY_KEY = "empty_key"
BAD_FORMAT = "bad_format"
UNKNOWN_KEY = "unknown_key"
REVOKED = "revoked"
MACHINE_LIMIT = "machine_limit"
IN_USE_ELSEWHERE = "in_use_elsewhere"
NO_SERVER = "no_server"
SERVER_ERROR = "server_error"
DEV_MODE = "dev_mode"


class Result(object):
    """ผลตรวจ: ok (bool), reason (รหัสข้อความ), detail (dict เช่น {'limit': 2})"""

    def __init__(self, ok, reason, detail=None):
        self.ok = bool(ok)
        self.reason = reason
        self.detail = detail or {}

    def message(self):
        """ข้อความตามภาษาปัจจุบัน"""
        return i18n.t("license.reason." + self.reason, **self.detail)

    def __repr__(self):
        return "Result(ok=%r, reason=%r)" % (self.ok, self.reason)


# ------------------------------------------------------------ pure helpers
def normalize_key(key):
    """ตัดช่องว่าง ทำเป็นตัวพิมพ์ใหญ่; ใส่ขีดให้ถ้าป้อน 20 ตัวติดกัน"""
    k = (key or u"").strip().upper().replace(u" ", u"")
    if len(k) == 20 and u"-" not in k:
        k = u"-".join(k[i:i + 5] for i in range(0, 20, 5))
    return k


def check_key_format(key):
    """ตรวจรูปแบบอย่างเดียว (ไม่ได้บอกว่ารหัสถูกจริง) -> Result"""
    k = normalize_key(key)
    if not k:
        return Result(False, EMPTY_KEY)
    if not KEY_RE.match(k):
        return Result(False, BAD_FORMAT)
    return Result(True, OK)


def mask_key(key):
    """XXXXX-...-12345 -> *****-*****-*****-12345 (ไว้แสดงผล)"""
    k = normalize_key(key)
    if not KEY_RE.match(k):
        return u"?"
    return u"*****-*****-*****-" + k[-5:]


def machine_fingerprint(parts):
    """fingerprint จากรายการข้อความที่บอกตัวเครื่อง (ฟังก์ชันล้วน) -> hex 20 ตัวพิมพ์ใหญ่
    เก็บเฉพาะค่า hash ไม่เก็บ hostname/MAC ดิบ ลำดับ/ตัวพิมพ์ใหญ่เล็กไม่มีผล"""
    norm = sorted(u"%s" % p.strip().lower() for p in parts if p and p.strip())
    h = hashlib.sha256(u"\n".join(norm).encode("utf-8")).hexdigest()
    return h[:20].upper()


def collect_machine_parts():
    """ข้อมูลที่ใช้สร้าง fingerprint (อ่านจากเครื่องจริง; ไม่ throw)"""
    import uuid
    parts = []
    try:
        parts.append(platform.node())
    except Exception:
        pass
    try:
        node = uuid.getnode()
        if not (node >> 40) & 1:      # บิตนี้=1 แปลว่า MAC สุ่ม ไม่นำมาใช้
            parts.append("%012x" % node)
    except Exception:
        pass
    for var in ("PROCESSOR_IDENTIFIER", "USERDOMAIN"):
        v = os.environ.get(var)
        if v:
            parts.append(v)
    return parts


def machine_id():
    return machine_fingerprint(collect_machine_parts())


def check_activation(machines, mid, limit=MAX_MACHINES):
    """ฟังก์ชันล้วน (ใช้ฝั่ง server ได้): รหัสที่ผูกเครื่อง `machines` (list) ขอใช้บน `mid`
    -> (ok, reason, machines_ใหม่)  เครื่องเดิมผ่านเสมอ, เครื่องใหม่ผ่านถ้ายังไม่ถึง limit
    (ข้อ "ไม่พร้อมกัน" ต้องตรวจที่ server ด้วย session/heartbeat — ดู docs)"""
    ms = list(machines)
    if mid in ms:
        return True, OK, ms
    if len(ms) >= limit:
        return False, MACHINE_LIMIT, ms
    ms.append(mid)
    return True, OK, ms


def is_dev_mode(environ=None):
    env = os.environ if environ is None else environ
    return (env.get(ENV_MODE) or "").strip().lower() == "dev"


# --------------------------------------------------------------- validators
class BaseValidator(object):
    def validate(self, key, mid):
        """-> Result  (subclass ต้อง override)"""
        raise NotImplementedError


class DevValidator(BaseValidator):
    def validate(self, key, mid):
        return Result(True, DEV_MODE)


class NoServerValidator(BaseValidator):
    """ค่าเริ่มต้นเมื่อยังไม่มี server: ตรวจรูปแบบแล้วตอบ no_server (ไม่เดาว่าถูก)"""

    def validate(self, key, mid):
        r = check_key_format(key)
        if not r.ok:
            return r
        return Result(False, NO_SERVER)


class InMemoryValidator(BaseValidator):
    """ต้นแบบ server ในหน่วยความจำ — records: {key: {"machines": [...], "revoked": bool,
    "limit": int}}  ใช้เทสต์/อ้างอิง logic ก่อนทำ server จริง (ไม่มีรหัสจริงในโค้ด)"""

    def __init__(self, records=None):
        self.records = records if records is not None else {}

    def validate(self, key, mid):
        r = check_key_format(key)
        if not r.ok:
            return r
        k = normalize_key(key)
        rec = self.records.get(k)
        if rec is None:
            return Result(False, UNKNOWN_KEY)
        if rec.get("revoked"):
            return Result(False, REVOKED)
        limit = rec.get("limit", MAX_MACHINES)
        ok, reason, ms = check_activation(rec.get("machines", []), mid, limit)
        if not ok:
            return Result(False, reason, {"limit": limit})
        rec["machines"] = ms
        return Result(True, OK)


def default_validator(environ=None):
    """เลือก validator: dev ถ้าตั้ง env, ไม่งั้น NoServer (จุดต่อ RemoteValidator ภายหลัง)"""
    if is_dev_mode(environ):
        return DevValidator()
    return NoServerValidator()


# ------------------------------------------------------------ local state
def state_path():
    return os.path.join(i18n.settings_dir(), "license.json")


def load_state():
    try:
        with io.open(state_path(), encoding="utf-8") as f:
            d = json.loads(f.read())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(key, mid):
    try:
        d = i18n.settings_dir()
        if not os.path.isdir(d):
            os.makedirs(d)
        data = {"key": normalize_key(key), "machine_id": mid,
                "activated_at": datetime.datetime.now().isoformat()}
        text = json.dumps(data, indent=2, sort_keys=True)
        if not isinstance(text, type(u"")):
            text = text.decode("utf-8")
        with io.open(state_path(), "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception:
        return False


def status_of(state, mid, dev):
    """ฟังก์ชันล้วน: -> (code, key_masked) ; code = dev|unlicensed|licensed|other_machine"""
    if dev:
        return "dev", u""
    key = state.get("key")
    if not key or not check_key_format(key).ok:
        return "unlicensed", u""
    if state.get("machine_id") != mid:
        return "other_machine", u""
    return "licensed", mask_key(key)


def current_status(environ=None):
    """สถานะปัจจุบัน -> (code, key_masked)"""
    return status_of(load_state(), machine_id(), is_dev_mode(environ))


def is_licensed(environ=None):
    """True ถ้า dev หรือ licensed — โมดูลต่างๆ จะเรียกอันนี้ภายหลัง (ตอนนี้ยังไม่มีใครเรียก)"""
    return current_status(environ)[0] in ("dev", "licensed")


def activate(key, validator=None, mid=None):
    """ป้อนรหัส -> ตรวจ -> ถ้าผ่านบันทึกสถานะ  คืน Result"""
    v = validator or default_validator()
    mid = mid or machine_id()
    res = v.validate(key, mid)
    if res.ok and res.reason != DEV_MODE:
        save_state(key, mid)
    return res
