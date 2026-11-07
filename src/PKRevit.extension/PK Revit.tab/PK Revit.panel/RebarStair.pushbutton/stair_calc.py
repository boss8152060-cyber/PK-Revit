# -*- coding: utf-8 -*-
"""ฟังก์ชันคำนวณล้วนๆ ของ Rebar บันได — ไม่ import Revit/pyRevit ทดสอบนอก Revit ได้

หน่วยทั้งหมดเป็น มม. พิกัดใน "กรอบท้องถิ่น" ของแต่ละช่วง/ชาน:
  s = ระยะตามแนวเดินขึ้น (แนวนอน), t = ระยะขวาง (ตั้งฉาก s ในแนวนอน), z = ความสูง
ช่วงบันได: s=0 คือหน้าตั้งลูกแรก, z=0 คือระดับพื้นล่างของช่วง (BaseElevation)
เส้นจมูกขั้น (nosing line) z = r + s·r/g จาก s=0 ถึง s=Lh (Lh = จำนวนลูกนอน × g)
ผิวล่างท้องบันได (soffit) อยู่ต่ำกว่าเส้นจมูกขั้นในแนวดิ่ง tw/cosθ
(สมมติ: ความหนาท้องบันได "ความลึกโครงสร้าง" วัดตั้งฉากกับความลาด — รอยืนยัน)

ผลลัพธ์ของฟังก์ชันวางเหล็กคือ list ของ "ชุด" (set) แต่ละชุดคือเหล็ก 1 รูปทรง
เรียงซ้ำ count เส้น ชนิด:
  kind "szplane": เส้นหลายท่อน pts [(s,z)...] อยู่ในระนาบ s-z, เรียงซ้ำตามแนว t
        จาก t0 ไปยัง t1 (count เส้น)
  kind "transverse": เส้นตรงตามแนว t จาก t_lo ถึง t_hi ที่ตำแหน่ง (s,z)
        เรียงซ้ำตามทิศ dir=(ds,dz) (หน่วยเวกเตอร์ในระนาบ s-z) ยาว arr_len (count เส้น)
"""

import math
import re

PLACEHOLDER = u"— เลือก —"

GROUP_ORDER = ["waist", "ext", "tread", "crack"]
# ชื่อกลุ่มตั้งตามหน้าที่ทางวิศวกรรม (บางชื่อในคลิปอ่านไม่ชัด — รอผู้ใช้ยืนยัน)
GROUP_LABELS = {
    "waist": u"เหล็กหลักท้องบันได",
    "ext": u"เหล็กต่อ/ยืดที่ชานและคาน",
    "tread": u"เหล็กลูกนอน-ลูกตั้ง",
    "crack": u"เหล็กกันร้าว/ตามขวาง",
}
# สี RGB ของแต่ละกลุ่มใน 3D view
GROUP_COLORS = {
    "waist": (220, 50, 47),
    "ext": (38, 110, 230),
    "tread": (35, 165, 85),
    "crack": (235, 175, 20),
}

# ค่าตั้งต้น (ต้องให้วิศวกรยืนยัน)
DEFAULT_COVER = 25.0
DEFAULT_TW = 150.0        # ความหนาท้องบันได (ตั้งฉากความลาด)
DEFAULT_TL = 150.0        # ความหนาชาน
DEFAULT_ANCHOR = 300.0    # ยื่นเหล็กท้องบันไดเข้าชาน/คาน
DEFAULT_EXT_LEN = 400.0   # เหล็กต่อ ยื่นเข้าชาน/คาน
DEFAULT_EXT_RUN = 600.0   # เหล็กต่อ ลงมาตามท้องช่วงบันได
MIN_SPACING = 50.0


# ------------------------------------------------------------ basics
def count_for(span, spacing):
    """จำนวนเส้นที่ระยะห่างจริงไม่เกิน spacing ครอบคลุม span (เส้นแรก-เส้นสุดท้าย)"""
    if spacing <= 0 or span <= 1e-6:
        return 1
    return int(math.ceil(span / spacing - 1e-9)) + 1


def dia_from_name(name):
    m = re.search(r"(\d+)", name or u"")
    return float(m.group(1)) if m else 0.0


class Geo(object):
    """เรขาคณิตช่วงบันได (มม.)"""

    def __init__(self, rise_total, risers, treads, going):
        self.n_t = int(treads)
        self.n_r = int(risers)
        self.g = float(going)
        self.H = float(rise_total)
        self.r = self.H / max(1, self.n_r)
        self.Lh = self.n_t * self.g
        th = math.atan2(self.r, self.g) if self.g > 0 else 0.0
        self.theta = th
        self.cos = math.cos(th)
        self.sin = math.sin(th)

    def nosing(self, s):
        return self.r + s * self.r / self.g

    def soffit(self, s, tw):
        return self.nosing(s) - tw / self.cos

    def valid(self):
        return self.n_t >= 1 and self.n_r >= 1 and self.g > 0 and self.r > 0


# ------------------------------------------------------------ run
def plan_run(geo, W, v, dia_of, z0=0.0):
    """เหล็กของช่วงบันได 1 ช่วง -> list ของชุด (ดูหัวไฟล์) z เป็นค่าสัมบูรณ์ (+z0)
    W   : ความกว้างช่วง (มม.), t ในช่วง [-W/2, W/2]
    v   : ค่าจากฟอร์ม {"groups":{key:{on,size,sp}},cover,tw,anchor,ext_len,ext_run,ext_lower}"""
    out = []
    c = v["cover"]
    tw = v["tw"]
    G = v["groups"]
    cs = geo.cos
    d = {}
    for k in GROUP_ORDER:
        d[k] = dia_of(G[k]["size"]) if G[k]["on"] else 0.0

    def add(group, kind, **kw):
        kw["group"] = group
        kw["kind"] = kind
        kw["size"] = G[group]["size"]
        out.append(kw)

    # 1) เหล็กหลักท้องบันได
    if G["waist"]["on"]:
        dm = d["waist"]
        cp = c + dm / 2.0
        a = v["anchor"]

        def zb(s):
            return geo.soffit(s, tw) + cp / cs + z0
        if a > 0:
            pts = [(-a, zb(0.0)), (0.0, zb(0.0)),
                   (geo.Lh, zb(geo.Lh)), (geo.Lh + a, zb(geo.Lh))]
        else:
            pts = [(c, zb(c)), (geo.Lh - c, zb(geo.Lh - c))]
        t0, t1 = -W / 2.0 + c + dm / 2.0, W / 2.0 - c - dm / 2.0
        if t1 >= t0:
            add("waist", "szplane", pts=pts, t0=t0, t1=t1,
                count=count_for(t1 - t0, G["waist"]["sp"]))

    # 2) เหล็กต่อ/ยืด ปลายบน (และปลายล่างถ้าเลือก)
    if G["ext"]["on"]:
        de = d["ext"]
        cp = c + de / 2.0
        Lr = min(v["ext_run"], geo.Lh)
        Le = v["ext_len"]

        def nz(s):
            return geo.nosing(s) - cp / cs + z0
        t0, t1 = -W / 2.0 + c + de / 2.0, W / 2.0 - c - de / 2.0
        if t1 >= t0 and Lr > 0:
            cnt = count_for(t1 - t0, G["ext"]["sp"])
            zh = nz(geo.Lh)
            add("ext", "szplane", end="top",
                pts=[(geo.Lh + Le, zh), (geo.Lh, zh), (geo.Lh - Lr, nz(geo.Lh - Lr))],
                t0=t0, t1=t1, count=cnt)
            if v.get("ext_lower"):
                zl = nz(0.0)
                add("ext", "szplane", end="bottom",
                    pts=[(-Le, zl), (0.0, zl), (Lr, nz(Lr))],
                    t0=t0, t1=t1, count=cnt)

    # 3) เหล็กลูกนอน-ลูกตั้ง: 1 ชุดต่อขั้น รูปตัว L ตามรอยขั้น
    if G["tread"]["on"]:
        dt = d["tread"]
        cp = c + dt / 2.0
        stack = c + d["waist"] + d["crack"]
        t0, t1 = -W / 2.0 + c + dt / 2.0, W / 2.0 - c - dt / 2.0
        if t1 >= t0:
            cnt = count_for(t1 - t0, G["tread"]["sp"])
            for k in range(1, geo.n_t + 1):
                sk = (k - 1) * geo.g
                sv = sk + cp
                z_top = k * geo.r - cp + z0
                z_a = max((k - 1) * geo.r + z0,
                          geo.soffit(sv, tw) + stack / cs + z0)
                if z_top - z_a < 20.0 or geo.g - 2 * cp < 20.0:
                    continue
                add("tread", "szplane", step=k,
                    pts=[(sv, z_a), (sv, z_top), (sk + geo.g - cp, z_top)],
                    t0=t0, t1=t1, count=cnt)

    # 4) เหล็กกันร้าว/ตามขวาง วางบนเหล็กหลัก ตามแนว t เรียงตามความลาด
    if G["crack"]["on"]:
        dc = d["crack"]
        off = c + d["waist"] + dc / 2.0       # ตั้งฉากจากผิวล่างท้องบันได
        s_a = c + dc / 2.0
        s_b = geo.Lh - s_a
        t_lo, t_hi = -W / 2.0 + c, W / 2.0 - c
        if s_b > s_a and t_hi > t_lo:
            arr = (s_b - s_a) / cs
            z_a = geo.soffit(s_a, tw) + off / cs + z0
            add("crack", "transverse", s=s_a, z=z_a, t_lo=t_lo, t_hi=t_hi,
                dir=(cs, geo.sin), arr_len=arr,
                count=count_for(arr, G["crack"]["sp"]))
    return out


# ------------------------------------------------------------ landing
def plan_landing(s_lo, s_hi, t_lo, t_hi, z_top, v, dia_of):
    """ตะแกรงล่างของชาน (สี่เหลี่ยมในกรอบ s,t): ใช้ขนาด/ระยะของ "เหล็กหลัก" ตามแนว s
    และ "กันร้าว/ตามขวาง" ตามแนว t; z_top = ผิวบนชาน (สัมบูรณ์)"""
    out = []
    G = v["groups"]
    c = v["cover"]
    zb = z_top - v["tl"]
    dm = dia_of(G["waist"]["size"]) if G["waist"]["on"] else 0.0
    dc = dia_of(G["crack"]["size"]) if G["crack"]["on"] else 0.0
    if G["waist"]["on"]:
        z = zb + c + dm / 2.0
        t0, t1 = t_lo + c + dm / 2.0, t_hi - c - dm / 2.0
        if t1 >= t0 and s_hi - s_lo > 2 * c:
            out.append({"group": "waist", "kind": "szplane", "size": G["waist"]["size"],
                        "pts": [(s_lo + c, z), (s_hi - c, z)], "t0": t0, "t1": t1,
                        "count": count_for(t1 - t0, G["waist"]["sp"]), "landing": True})
    if G["crack"]["on"]:
        z = zb + c + dm + dc / 2.0
        s_a, s_b = s_lo + c + dc / 2.0, s_hi - c - dc / 2.0
        if s_b >= s_a and t_hi - t_lo > 2 * c:
            arr = s_b - s_a
            out.append({"group": "crack", "kind": "transverse", "size": G["crack"]["size"],
                        "s": s_a, "z": z, "t_lo": t_lo + c, "t_hi": t_hi - c,
                        "dir": (1.0, 0.0), "arr_len": arr,
                        "count": count_for(arr, G["crack"]["sp"]), "landing": True})
    return out


def is_axis_rect(pts, tol=0.02):
    """pts (s,t) ของขอบ: เป็นสี่เหลี่ยมขนานแกนไหม (พื้นที่ ≈ bbox) -> (s_lo,s_hi,t_lo,t_hi) หรือ None"""
    if len(pts) < 3:
        return None
    ss = [p[0] for p in pts]
    ts = [p[1] for p in pts]
    box = (max(ss) - min(ss)) * (max(ts) - min(ts))
    if box <= 0:
        return None
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    if abs(abs(a) / 2.0 - box) / box > tol:
        return None
    return (min(ss), max(ss), min(ts), max(ts))


def totals(sets):
    """(จำนวนชุด, จำนวนเส้น)"""
    return len(sets), sum(s["count"] for s in sets)


def by_group(sets):
    """{group: (ชุด, เส้น)}"""
    r = {}
    for s in sets:
        a, b = r.get(s["group"], (0, 0))
        r[s["group"]] = (a + 1, b + s["count"])
    return r


# ------------------------------------------------------------ gate
def gate(v, runs, available):
    """ด่านตรวจก่อนสร้าง -> list ของ (ok, ข้อความ)

    v    : ค่าจากฟอร์ม
    runs : list ของ dict {label, W} ของช่วงที่จะใส่ (ว่าง = ไม่มีช่วงที่ใช้ได้)
    available : ชื่อ Bar Type ที่มีในโปรเจกต์"""
    out = []
    G = v["groups"]
    n_on = 0
    for k in GROUP_ORDER:
        g = G[k]
        lab = GROUP_LABELS[k]
        if not g["on"]:
            out.append((True, u"– {}: ไม่ใส่".format(lab)))
            continue
        n_on += 1
        if not g["size"] or g["size"] == PLACEHOLDER:
            out.append((False, u"✗ {}: ยังไม่เลือกขนาด".format(lab)))
        elif g["size"] not in available:
            out.append((False, u"✗ {}: ไม่พบ Bar Type {} ในโปรเจกต์".format(lab, g["size"])))
        elif g["sp"] < MIN_SPACING:
            out.append((False, u"✗ {}: ระยะห่างต้อง ≥ {:.0f} มม.".format(lab, MIN_SPACING)))
        else:
            out.append((True, u"✓ {}: {} @{:.0f} มม.".format(lab, g["size"], g["sp"])))
    if n_on == 0:
        out.append((False, u"✗ ต้องเปิดอย่างน้อย 1 กลุ่ม"))
    if v["cover"] <= 0:
        out.append((False, u"✗ ระยะหุ้ม ต้องมากกว่า 0"))
    else:
        out.append((True, u"✓ ระยะหุ้ม {:.0f} มม.".format(v["cover"])))
    if v["tw"] <= 0:
        out.append((False, u"✗ ความหนาท้องบันได ต้องมากกว่า 0"))
    if v["tl"] <= 0:
        out.append((False, u"✗ ความหนาชาน ต้องมากกว่า 0"))
    if v["anchor"] < 0 or v["ext_len"] < 0 or v["ext_run"] < 0:
        out.append((False, u"✗ ระยะยื่น/ระยะเหล็กต่อ ต้องไม่ติดลบ"))
    if not runs:
        out.append((False, u"✗ ไม่พบช่วงบันไดตรงที่อ่านค่าได้"))
    else:
        dia = {}
        for k in GROUP_ORDER:
            ok_sz = G[k]["on"] and G[k]["size"] and G[k]["size"] != PLACEHOLDER
            dia[k] = dia_from_name(G[k]["size"]) if ok_sz else 0.0
        need = 2 * v["cover"] + dia["waist"] + dia["crack"] + 10.0
        if 0 < v["tw"] < need:
            out.append((False, u"✗ ท้องบันไดหนา {:.0f} มม. น้อยกว่าที่ต้องการ {:.0f} มม. "
                               u"(หุ้ม×2 + เหล็กหลัก + กันร้าว)".format(v["tw"], need)))
        for r in runs:
            if r["W"] < 2 * v["cover"] + 50.0:
                out.append((False, u"✗ {}: กว้าง {:.0f} มม. แคบเกินระยะหุ้ม".format(r["label"], r["W"])))
        if all(ok for ok, _ in out):
            out.append((True, u"✓ ช่วงบันไดที่ใช้ได้ {} ช่วง".format(len(runs))))
    return out


def gate_ok(items):
    return all(ok for ok, _ in items)
