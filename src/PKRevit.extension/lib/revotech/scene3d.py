# -*- coding: utf-8 -*-
"""ตรรกะล้วนของ "หน้าต่าง 3D preview" ของฟอร์มเหล็ก — ไม่พึ่ง .NET/Revit ทดสอบนอก Revit ได้

หน่วยทั้งหมด มม. แกน: x,y แนวนอน, z ขึ้น (ชิ้นงานวางอยู่บน z=0)
Scene = host (กล่อง/ปริซึมโปร่งของคาน เสา ฐานราก พื้น บันได) + กลุ่มเหล็ก (polyline + สี + รัศมี)
ตัว WPF อยู่ใน revotech.preview3d (รับ Scene แล้วสร้าง Viewport3D)

ตัวสร้าง scene ต่อโมดูล (รับค่าเดียวกับที่ฟอร์มส่งให้ฟังก์ชันคำนวณเดิม):
  column_scene  — เหล็กยืน + ปลอก (คัดลอก main_positions/โซนปลอกจาก RebarColumn script.py)
  beam_scene    — เรียก revotech.beamcalc.plan_longitudinal/plan_stirrups ตรงๆ
  footing_scene — ตะแกรงฐานรากสี่เหลี่ยม (คำนวณเองแบบเดียวกับ footing_calc.plan_mat กรณี rect)
  footing_scene_from_bars — รับผลของ footing_calc.plan_mat (รูปอื่น เช่น สามเหลี่ยม)
  slab_scene / slab_scene_from_bars — เหล็ก 2 ชั้น 2 ทิศ (ผลของ slab_calc.plan_layers)
  stair_scene   — รับผลของ stair_calc.plan_run/plan_landing (ชุด szplane/transverse)
ไฟล์ *_calc.py ของฟอร์มอยู่ในโฟลเดอร์ pushbutton (ย้ายที่ได้) จึงไม่ import ตรงๆ
ฟอร์มเรียกฟังก์ชันคำนวณของตัวเองแล้วส่งผลมาที่นี่ ดู docs/preview3d.md
"""
from __future__ import division
import math
from revotech import hookcalc

# ------------------------------------------------------------ สี (RGB 0-255)
RED = (220, 50, 47)
ORANGE = (240, 120, 40)
AMBER = (235, 175, 20)
BLUE = (38, 110, 230)
SKY = (70, 170, 235)
GREEN = (35, 165, 85)
TEAL = (0, 170, 175)
PURPLE = (150, 70, 200)
GRAY = (120, 120, 125)
HOST_COLOR = (130, 135, 145)

BEAM_COLORS = {
    "top1": RED, "top2": ORANGE, "bot1": BLUE, "bot2": SKY,
    "side": GREEN, "xtop": PURPLE, "xbot": TEAL, "stirrup": AMBER,
}
BEAM_LABELS = {
    "top1": u"เหล็กบน ชั้น 1", "top2": u"เหล็กบน ชั้น 2",
    "bot1": u"เหล็กล่าง ชั้น 1", "bot2": u"เหล็กล่าง ชั้น 2",
    "side": u"เหล็กข้าง", "xtop": u"เสริมบน", "xbot": u"เสริมล่าง",
    "stirrup": u"ปลอก",
}
STAIR_COLORS = {"waist": (220, 50, 47), "ext": (38, 110, 230),
                "tread": (35, 165, 85), "crack": (235, 175, 20)}
STAIR_LABELS = {"waist": u"เหล็กหลักท้องบันได", "ext": u"เหล็กต่อ/ยืด",
                "tread": u"เหล็กลูกนอน-ลูกตั้ง", "crack": u"เหล็กกันร้าว/ตามขวาง"}
SLAB_COLORS = {"TX": RED, "TY": ORANGE, "BX": BLUE, "BY": TEAL}
SLAB_LABELS = {"TX": u"บน ทิศ X", "TY": u"บน ทิศ Y",
               "BX": u"ล่าง ทิศ X", "BY": u"ล่าง ทิศ Y"}
FOOT_COLORS = {"long": RED, "short": BLUE, 0: RED, 60: BLUE, 120: GREEN,
               "ring": AMBER, "dowel": GREEN}


# ------------------------------------------------------------ โครงข้อมูล
class Host(object):
    """ชิ้นงานโปร่ง: ปริซึม = รูปหลายเหลี่ยม poly (จุด 2D) ดันตามแกน
    axis='z': poly=(x,y) ดันจาก lo..hi ตาม z; axis='y': poly=(x,z) ดันจาก lo..hi ตาม y
    กล่องก็คือปริซึมสี่เหลี่ยม (ใช้ Host.box)"""

    def __init__(self, poly, axis, lo, hi, color=HOST_COLOR, alpha=0.16, label=u""):
        self.poly = [(float(a), float(b)) for (a, b) in poly]
        self.axis = axis
        self.lo = float(lo)
        self.hi = float(hi)
        self.color = color
        self.alpha = alpha
        self.label = label

    @staticmethod
    def box(x0, y0, z0, x1, y1, z1, color=HOST_COLOR, alpha=0.16, label=u""):
        return Host([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], 'z', z0, z1,
                    color, alpha, label)

    def to3d(self, a, b, c):
        """(พิกัดในระนาบ a,b ; พิกัดแกนดัน c) -> (x,y,z)"""
        if self.axis == 'z':
            return (a, b, c)
        return (a, c, b)

    def points(self):
        return [self.to3d(a, b, c) for (a, b) in self.poly for c in (self.lo, self.hi)]


class BarGroup(object):
    """เหล็กกลุ่มเดียวกัน (สี/ขนาดเดียวกัน): polys = list ของ polyline [(x,y,z)...]"""

    def __init__(self, key, label, color, radius, polys=None):
        self.key = key
        self.label = label
        self.color = color
        self.radius = float(radius)
        self.polys = polys if polys is not None else []

    def add(self, pts):
        if len(pts) >= 2:
            self.polys.append([(float(x), float(y), float(z)) for (x, y, z) in pts])


class Scene(object):
    def __init__(self, title=u"", hosts=None, groups=None, notes=None):
        self.title = title
        self.hosts = hosts or []
        self.groups = [g for g in (groups or [])]
        self.notes = notes or []      # ข้อความเตือน เช่น "เหล็กไม่พอดีความกว้าง"

    def bar_count(self):
        return sum(len(g.polys) for g in self.groups)

    def bounds(self):
        """((minx,miny,minz),(maxx,maxy,maxz)) ของ host+เหล็กทั้งหมด"""
        pts = []
        for h in self.hosts:
            pts.extend(h.points())
        for g in self.groups:
            for p in g.polys:
                pts.extend(p)
        if not pts:
            return (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def legend(self):
        """[(label, color, จำนวนเส้น)] เฉพาะกลุ่มที่มีเหล็ก"""
        return [(g.label, g.color, len(g.polys)) for g in self.groups if g.polys]


# ------------------------------------------------------------ เรขาคณิตเมช (ล้วน)
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def tube_mesh(polys, radius, sides=6, pos=None, idx=None):
    """ท่อปริซึม sides เหลี่ยมตาม polyline ทุกเส้น รวมเป็นเมชเดียว
    คืน (pos, idx): pos = [x,y,z,x,y,z,...] , idx = [i,j,k,...] (สามเหลี่ยม)
    แต่ละท่อน (segment) มีหน้าตัดของตัวเอง — มุมหักเป็นรอยต่อซ้อนกัน เห็นเป็นเหล็กงอเพียงพอสำหรับ preview"""
    pos = pos if pos is not None else []
    idx = idx if idx is not None else []
    ang = [2.0 * math.pi * k / sides for k in range(sides)]
    cs = [(math.cos(a), math.sin(a)) for a in ang]
    for poly in polys:
        n = len(poly)
        for i in range(n - 1):
            a, b = poly[i], poly[i + 1]
            d = _sub(b, a)
            if _norm(d) == (0.0, 0.0, 0.0):
                continue
            d = _norm(d)
            ref = (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (1.0, 0.0, 0.0)
            u = _norm(_cross(d, ref))
            v = _cross(d, u)
            base = len(pos) // 3
            for p in (a, b):
                for (c, s) in cs:
                    pos.extend((p[0] + radius * (c * u[0] + s * v[0]),
                                p[1] + radius * (c * u[1] + s * v[1]),
                                p[2] + radius * (c * u[2] + s * v[2])))
            for k in range(sides):
                k2 = (k + 1) % sides
                idx.extend((base + k, base + k2, base + sides + k2,
                            base + k, base + sides + k2, base + sides + k))
            # ฝาปลาย
            for (p, off, flip) in ((a, 0, True), (b, sides, False)):
                cidx = len(pos) // 3
                pos.extend(p)
                for k in range(sides):
                    k2 = (k + 1) % sides
                    if flip:
                        idx.extend((cidx, base + off + k2, base + off + k))
                    else:
                        idx.extend((cidx, base + off + k, base + off + k2))
    return pos, idx


def signed_area2(poly):
    a = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def triangulate(poly):
    """แบ่งรูปหลายเหลี่ยมเรียบง่าย (ไม่ตัดตัวเอง) เป็นสามเหลี่ยมด้วย ear clipping
    คืน list ของ (i,j,k) ดัชนีจุดใน poly — ทิศทวนเข็ม"""
    n = len(poly)
    if n < 3:
        return []
    order = list(range(n))
    if signed_area2(poly) < 0:
        order.reverse()
    tris = []

    def cross(o, a, b):
        return (poly[a][0] - poly[o][0]) * (poly[b][1] - poly[o][1]) - \
               (poly[a][1] - poly[o][1]) * (poly[b][0] - poly[o][0])

    def inside(p, a, b, c):
        return (cross(a, b, p) >= -1e-9 and cross(b, c, p) >= -1e-9 and
                cross(c, a, p) >= -1e-9)
    guard = 0
    while len(order) > 3 and guard < 10000:
        guard += 1
        m = len(order)
        clipped = False
        for i in range(m):
            a, b, c = order[i - 1], order[i], order[(i + 1) % m]
            if cross(a, b, c) <= 1e-9:
                continue
            if any(inside(p, a, b, c) for p in order if p not in (a, b, c)):
                continue
            tris.append((a, b, c))
            del order[i]
            clipped = True
            break
        if not clipped:
            # รูปเสื่อม (จุดร่วมเส้น) — ตัดจุดแรกทิ้งเพื่อไม่ให้วนไม่จบ
            tris.append((order[0], order[1], order[2]))
            del order[1]
    if len(order) == 3:
        tris.append((order[0], order[1], order[2]))
    return tris


def host_mesh(host):
    """เมชผิวของ Host (ปริซึม) คืน (pos, idx) — หน้าฝาสองด้าน + ผนังข้าง"""
    pos = []
    idx = []
    poly = host.poly
    n = len(poly)
    for c in (host.lo, host.hi):
        for (a, b) in poly:
            pos.extend(host.to3d(a, b, c))
    tris = triangulate(poly)
    for (i, j, k) in tris:
        idx.extend((i, j, k))                 # ฝาล่าง
        idx.extend((n + i, n + k, n + j))     # ฝาบน (กลับด้าน)
    for i in range(n):
        j = (i + 1) % n
        idx.extend((i, j, n + j, i, n + j, n + i))
    return pos, idx


def host_edges(host):
    """เส้นขอบของ Host เป็น polyline (ใช้ลากเป็นท่อบางให้เห็นรูปทรงชัด)"""
    out = []
    n = len(host.poly)
    for c in (host.lo, host.hi):
        loop = [host.to3d(a, b, c) for (a, b) in host.poly]
        loop.append(loop[0])
        out.append(loop)
    for (a, b) in host.poly:
        out.append([host.to3d(a, b, host.lo), host.to3d(a, b, host.hi)])
    return out


# ------------------------------------------------------------ ตัวช่วยตำแหน่ง
def spread(n, lo, hi, edge=True):
    """n จุดกระจายสม่ำเสมอบน [lo,hi]; edge=True ปลายอยู่ที่ขอบ (n=1 กึ่งกลาง)"""
    n = int(n)
    if n <= 0:
        return []
    if n == 1:
        return [(lo + hi) / 2.0]
    if edge:
        return [lo + (hi - lo) * i / (n - 1.0) for i in range(n)]
    return [lo + (hi - lo) * (i + 1) / (n + 1.0) for i in range(n)]


def positions(lo, hi, spacing):
    """คัดลอกจาก slab_calc.positions: เริ่มที่ lo ทุก spacing + เส้นท้ายที่ hi ถ้าช่องสุดท้าย >= 0.25 spacing"""
    if hi < lo or spacing <= 0:
        return []
    n = int(math.floor((hi - lo) / spacing + 1e-9)) + 1
    ps = [lo + k * spacing for k in range(n)]
    if hi - ps[-1] >= 0.25 * spacing:
        ps.append(hi)
    return ps


def count_for(span, spacing):
    """คัดลอกจาก stair_calc.count_for"""
    if spacing <= 0 or span <= 1e-6:
        return 1
    return int(math.ceil(span / spacing - 1e-9)) + 1


def rect_loop(a, b, c, d, z):
    return [(a, c, z), (b, c, z), (b, d, z), (a, d, z), (a, c, z)]


# ------------------------------------------------------------ เสา
def side_counts(extra_pairs, w, h):
    """คัดลอกจาก RebarColumn script.py"""
    nx = ny = 0
    for _ in range(extra_pairs):
        if w / (nx + 1.0) >= h / (ny + 1.0):
            nx += 1
        else:
            ny += 1
    return nx, ny


def main_positions(n, x0, x1, y0, y1):
    """คัดลอกจาก RebarColumn script.py: ตำแหน่ง (x,y) เหล็กยืนบนสี่เหลี่ยม (n เลขคู่ >= 4)"""
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    nx, ny = side_counts(max((n - 4) // 2, 0), x1 - x0, y1 - y0)
    for i in range(1, nx + 1):
        x = x0 + (x1 - x0) * i / (nx + 1.0)
        pts.append((x, y0))
        pts.append((x, y1))
    for j in range(1, ny + 1):
        y = y0 + (y1 - y0) * j / (ny + 1.0)
        pts.append((x0, y))
        pts.append((x1, y))
    return pts


def column_tie_zones(z_start, z_end, end_len, sp_mid, sp_end):
    """โซนปลอก [(z เริ่ม, ยาว, ระยะ)] — ตรรกะเดียวกับ RebarColumn script.py"""
    zones = []
    if z_end - z_start > 2 * end_len + sp_mid:
        zones.append((z_start, end_len, sp_end))
        zm = z_start + end_len + sp_mid
        zt = z_end - end_len
        if zt - zm > 0:
            zones.append((zm, zt - zm - sp_mid, sp_mid))
        zones.append((zt, end_len, sp_end))
    else:
        zones.append((z_start, z_end - z_start, sp_mid))
    return zones


def hook_tail(p, d, w, angle, ext):
    """ปลายตะขอ (ภาพประมาณ): จุดสิ้นสุดเส้น p, ทิศเส้นออกจากปลายนั้น d, ทิศที่ตะขอเบนไป w (ตั้งฉาก d)
    angle = องศาที่เหล็กหักจากแนวเดิม (90 = ตั้งฉาก, 135/180 = หักย้อนกลับ), ext = ช่วงตรงปลาย (มม.)
    คืนจุดปลายสุด — วาดเป็นเส้นตรงตัดมุม ไม่วาดส่วนโค้ง"""
    a = math.radians(angle)
    c, s_ = math.cos(a), math.sin(a)
    return tuple(p[i] + (d[i] * c + w[i] * s_) * ext for i in range(3))


def column_scene(w, h, H, n, d_main, d_tie, cover=25.0, end_len=600.0,
                 sp_mid=150.0, sp_end=100.0, lap_d=40.0, title=u"เสา",
                 hook_a=None, hook_b=None, stagger=False):
    """เสา w x h มม. สูง H; เหล็กยืน n เส้น (เลขคู่ >=4) ขนาด d_main; ปลอก d_tie
    ค่าอื่นตรงกับ collect() ของฟอร์มเสา (cover, end_len, sp_mid, sp_end, lap_d)
    hook_a/hook_b = (องศา, ตัวคูณ×d) ตะขอปลายล่าง/บนของเหล็กยืน หรือ None; stagger=True สลับเส้นคี่ยื่นเพิ่ม 1.3×ทาบ
    (ภาพประมาณ — ตะขอวาดเป็นเส้นตรงเบนเข้าหาแกนเสา)"""
    n = max(4, int(n))
    host = Host.box(-w / 2.0, -h / 2.0, 0, w / 2.0, h / 2.0, H, label=u"เสา")
    g_main = BarGroup("main", u"เหล็กยืน", RED, d_main / 2.0)
    g_tie = BarGroup("stirrup", u"ปลอก", AMBER, d_tie / 2.0)
    notes = []
    inset_main = cover + d_tie + d_main / 2.0
    inset_tie = cover + d_tie / 2.0
    if min(w, h) <= 2 * inset_main or H <= 2 * cover:
        notes.append(u"หน้าตัด/ความสูงเล็กเกินไปเมื่อเทียบกับระยะหุ้ม")
        return Scene(title, [host], [g_main, g_tie], notes)
    lap = lap_d * d_main
    for i, (x, y) in enumerate(main_positions(n, -w / 2.0 + inset_main, w / 2.0 - inset_main,
                                              -h / 2.0 + inset_main, h / 2.0 - inset_main)):
        top = H + lap + (hookcalc.stagger_extra_mm(i, lap, hookcalc.STAGGER_ALT)
                         if stagger else 0.0)
        pts = [(x, y, 0), (x, y, top)]
        if hook_a or hook_b:
            # ทิศเข้าหาแกนเสา: แกนที่ห่างศูนย์กลางมากกว่า (สัดส่วน)
            if abs(x) / (w / 2.0) >= abs(y) / (h / 2.0):
                wv = (-1.0 if x > 0 else 1.0, 0.0, 0.0)
            else:
                wv = (0.0, -1.0 if y > 0 else 1.0, 0.0)
            if hook_a:
                pts.insert(0, hook_tail((x, y, 0), (0, 0, 1), wv, hook_a[0],
                                        hookcalc.hook_ext_mm(hook_a[0], hook_a[1], d_main)))
            if hook_b:
                pts.append(hook_tail((x, y, top), (0, 0, -1), wv, hook_b[0],
                                     hookcalc.hook_ext_mm(hook_b[0], hook_b[1], d_main)))
        g_main.add(pts)
    a, b = -w / 2.0 + inset_tie, w / 2.0 - inset_tie
    c, d = -h / 2.0 + inset_tie, h / 2.0 - inset_tie
    for (zz, ln, sp) in column_tie_zones(cover, H - cover, end_len, sp_mid, sp_end):
        cnt = count_for(ln, sp) if ln > sp else 1
        for i in range(cnt):
            z = zz + (min(ln, i * sp))
            g_tie.add(rect_loop(a, b, c, d, z))
    return Scene(title, [host], [g_main, g_tie], notes)


# ------------------------------------------------------------ คาน
def default_beam_spec():
    """ค่าตั้งต้นของ spec ที่ beamcalc ต้องการ (มม.) — ฟอร์มคานใส่ค่าจริงทับ"""
    return {"cover": 40.0, "d_tie": 9.0, "max_len": 12000.0, "lap_d": 40.0,
            "hook_mult": 12.0,
            "top": [(2, 16.0, "DB16")], "bot": [(3, 16.0, "DB16")],
            "xtop": None, "xbot": None, "side": None,
            "end_len": 500.0, "sp_end": 100.0, "sp_mid": 200.0}


def beam_scene(L, b, h, spec=None, title=u"คาน"):
    """คานยาว L กว้าง b ลึก h (ตามแกน x, กึ่งกลางที่ y=0, ผิวล่าง z=0)
    spec = dict แบบเดียวกับ beamcalc.plan_longitudinal/plan_stirrups
    (top=[(n,d,ชื่อ)], bot=[...], xtop/xbot=(n,d,ชื่อ,mode,div), side=(n,d,ชื่อ),
     cover,d_tie,max_len,lap_d,hook_mult,end_len,sp_end,sp_mid)
    s->x, u->y, v->z"""
    from revotech import beamcalc
    sp = default_beam_spec()
    sp.update(spec or {})
    host = Host.box(0, -b / 2.0, 0, L, b / 2.0, h, label=u"คาน")
    groups = {}

    def grp(role, d):
        key = role
        if key not in groups:
            groups[key] = BarGroup(key, BEAM_LABELS.get(key, key),
                                   BEAM_COLORS.get(key, GRAY), d / 2.0)
        return groups[key]
    bars, errors, warnings, _info = beamcalc.plan_longitudinal(
        0.0, float(L), -b / 2.0, b / 2.0, 0.0, float(h), sp)
    for br in bars:
        g = grp(br["role"], br["dia"])
        hk = sp["hook_mult"] * br["dia"]
        hk = min(hk, max(h - 2 * sp["cover"], 0.0))
        pts = [(br["s_a"], br["u"], br["v"]), (br["s_b"], br["u"], br["v"])]
        for end, which in ((0, "hook_a"), (1, "hook_b")):
            kind = br[which]
            ov = sp.get("hk_a" if end == 0 else "hk_b", "keep")    # override จากฟอร์ม
            if kind and ov != "none":
                s = pts[0][0] if end == 0 else pts[-1][0]
                dz = -hk if kind == "down" else hk
                tip = (s, br["u"], br["v"] + dz)
                if isinstance(ov, (tuple, list)):
                    ext = hookcalc.hook_ext_mm(ov[0], ov[1], br["dia"])
                    wv = (0.0, 0.0, -1.0 if kind == "down" else 1.0)
                    dv = (-1.0, 0.0, 0.0) if end == 0 else (1.0, 0.0, 0.0)
                    tip = hook_tail((s, br["u"], br["v"]), dv, wv, ov[0], ext)
                if end == 0:
                    pts.insert(0, tip)
                else:
                    pts.append(tip)
        g.add(pts)
    if bars:
        zones, rect = beamcalc.plan_stirrups(0.0, float(L), -b / 2.0, b / 2.0,
                                             0.0, float(h), sp)
        ua, ub, va, vb = rect
        gs = grp("stirrup", sp["d_tie"])
        for (z0, ln, spc) in zones:
            cnt = beamcalc.stirrup_count(ln, spc)
            for i in range(cnt):
                s = z0 + min(ln, i * spc)
                gs.add([(s, ua, va), (s, ub, va), (s, ub, vb), (s, ua, vb), (s, ua, va)])
    order = ["top1", "top2", "xtop", "side", "bot1", "bot2", "xbot", "stirrup"]
    gl = [groups[k] for k in order if k in groups] + \
         [v for k, v in groups.items() if k not in order]
    return Scene(title, [host], gl, list(errors) + list(warnings))


# ------------------------------------------------------------ ฐานราก
HOOK_NONE = "none"
HOOK_12D = "12d"        # งอขึ้น 12d
HOOK_FULL = "full"      # งอขึ้นถึงใต้ระยะหุ้มบน


def hook_leg(kind, dia, z_bar, height, cover):
    """ความยาวขางอขึ้น (เหมือน footing_calc.hook_leg แต่รับชื่อแบบสตริง)"""
    if kind == HOOK_NONE:
        return 0.0
    top = height - cover - dia / 2.0
    room = max(top - z_bar, 0.0)
    if kind == HOOK_FULL:
        return room
    return min(12.0 * dia, room)


def ring_levels(height, cover, mat_thick, d_tie, count, spacing):
    """คัดลอกจาก footing_calc.ring_levels"""
    z = cover + mat_thick + d_tie / 2.0
    out = []
    for i in range(int(count)):
        zi = z + i * spacing
        if zi > height - cover - d_tie / 2.0 + 1e-6:
            break
        out.append(zi)
    return out


def footing_scene(L, B, H, long_bar, short_bar, cover=75.0, hook=HOOK_12D,
                  ring=None, column=None, title=u"ฐานราก"):
    """ฐานรากสี่เหลี่ยม L (x) x B (y) หนา H
    long_bar/short_bar = (dia, n) เหล็กตามแนวยาว/สั้น (ตะแกรงล่าง; long อยู่ชั้นล่างสุด)
    ring = (dia, count, spacing) เหล็กรัดรอบ หรือ None; column = (cw, cd, สูง) เสาตอม่อ หรือ None"""
    hosts = [Host.box(-L / 2.0, -B / 2.0, 0, L / 2.0, B / 2.0, H, label=u"ฐานราก")]
    if column:
        cw, cd, ch = column
        hosts.append(Host.box(-cw / 2.0, -cd / 2.0, H, cw / 2.0, cd / 2.0, H + ch,
                              alpha=0.12, label=u"ตอม่อ"))
    d_ring = ring[0] if ring and ring[1] > 0 else 0.0
    g_long = BarGroup("long", u"เหล็กตามยาว", RED, long_bar[0] / 2.0)
    g_short = BarGroup("short", u"เหล็กตามสั้น", BLUE, short_bar[0] / 2.0)
    z_cursor = float(cover)
    for (g, bar, along_x) in ((g_long, long_bar, True), (g_short, short_bar, False)):
        d, n = bar
        if d <= 0 or n <= 0:
            continue
        z = z_cursor + d / 2.0
        z_cursor += d
        inset = cover + d_ring + d / 2.0
        ex = (L if along_x else B) / 2.0 - inset      # ครึ่งความยาวเส้น
        ey = (B if along_x else L) / 2.0 - inset      # ช่วงกระจายเส้น
        if ex <= 0 or ey <= 0:
            continue
        leg = hook_leg(hook, d, z, H, cover)
        for s in spread(n, -ey, ey, True):
            pts = [(-ex, s, z), (ex, s, z)] if along_x else [(s, -ex, z), (s, ex, z)]
            if leg > 0:
                if along_x:
                    pts = [(-ex, s, z + leg)] + pts + [(ex, s, z + leg)]
                else:
                    pts = [(s, -ex, z + leg)] + pts + [(s, ex, z + leg)]
            g.add(pts)
    groups = [g_long, g_short]
    if ring and ring[1] > 0:
        d, cnt, spc = ring
        g_r = BarGroup("ring", u"เหล็กรัดรอบ", AMBER, d / 2.0)
        a, b = L / 2.0 - cover - d / 2.0, B / 2.0 - cover - d / 2.0
        for z in ring_levels(H, cover, z_cursor - cover, d, cnt, spc):
            g_r.add(rect_loop(-a, a, -b, b, z))
        groups.append(g_r)
    return Scene(title, hosts, groups)


def footing_scene_from_bars(poly, H, bars, cover=75.0, hook=HOOK_NONE,
                            colors=None, title=u"ฐานราก"):
    """รับผลของ footing_calc.plan_mat (list ของ dict group,size,a,b,z,dia) + ผังฐาน poly
    ใช้กับฐานสามเหลี่ยม/รูปอื่น; กลุ่มสีตาม FOOT_COLORS (key long/short/0/60/120)"""
    colors = colors or FOOT_COLORS
    host = Host(poly, 'z', 0, H, label=u"ฐานราก")
    groups = {}
    order = []
    for br in bars:
        k = br["group"]
        if k not in groups:
            lab = u"เหล็ก {}°".format(k) if isinstance(k, int) else \
                {"long": u"เหล็กตามยาว", "short": u"เหล็กตามสั้น"}.get(k, u"เหล็ก")
            groups[k] = BarGroup(k, lab, colors.get(k, GRAY), br["dia"] / 2.0)
            order.append(k)
        (x0, y0), (x1, y1) = br["a"], br["b"]
        z = br["z"]
        pts = [(x0, y0, z), (x1, y1, z)]
        leg = hook_leg(hook, br["dia"], z, H, cover)
        if leg > 0:
            pts = [(x0, y0, z + leg)] + pts + [(x1, y1, z + leg)]
        groups[k].add(pts)
    return Scene(title, [host], [groups[k] for k in order])


# ------------------------------------------------------------ พื้น
def slab_levels(H, cover, layers):
    """คัดลอกจาก slab_calc.layer_levels (รับ layers = {key: (dia, spacing)})"""
    d = {}
    for k in ("TX", "TY", "BX", "BY"):
        d[k] = layers[k][0] if k in layers else 0.0
    lv = {}
    if "BX" in layers:
        lv["BX"] = cover + d["BX"] / 2.0
    if "BY" in layers:
        lv["BY"] = cover + d["BX"] + d["BY"] / 2.0
    if "TX" in layers:
        lv["TX"] = H - cover - d["TX"] / 2.0
    if "TY" in layers:
        lv["TY"] = H - cover - d["TX"] - d["TY"] / 2.0
    ok = cover + d["BX"] + d["BY"] <= H - cover - d["TX"] - d["TY"] + 1e-9
    return lv, ok


def slab_scene(L, B, H, layers, cover=20.0, title=u"พื้น"):
    """พื้นสี่เหลี่ยม L (x) x B (y) หนา H; layers = {"TX":(dia,spacing),...} เฉพาะชั้นที่ใช้
    ชั้นบน/ล่าง ทิศ X/Y เหมือน slab_calc (ทิศ X อยู่นอกสุด)"""
    host = Host.box(0, 0, 0, L, B, H, label=u"พื้น")
    notes = []
    lv, ok = slab_levels(H, cover, layers)
    groups = []
    if not ok:
        notes.append(u"ชั้นเหล็กรวมหนากว่าพื้น — ไม่แสดงเหล็ก")
        return Scene(title, [host], groups, notes)
    for key in ("TX", "TY", "BX", "BY"):
        if key not in layers:
            continue
        d, sp = layers[key]
        g = BarGroup(key, SLAB_LABELS[key], SLAB_COLORS[key], d / 2.0)
        z = lv[key]
        if key.endswith("X"):
            for y in positions(cover + d / 2.0, B - cover - d / 2.0, sp):
                g.add([(cover, y, z), (L - cover, y, z)])
        else:
            for x in positions(cover + d / 2.0, L - cover - d / 2.0, sp):
                g.add([(x, cover, z), (x, B - cover, z)])
        if not g.polys:
            notes.append(u"{}: พื้นเล็กเกินระยะหุ้ม/ระยะเหล็ก".format(SLAB_LABELS[key]))
        groups.append(g)
    return Scene(title, [host], groups, notes)


def slab_scene_from_bars(outer, holes, H, bars, title=u"พื้น"):
    """รับผลของ slab_calc.plan_layers (bars dict group,size,a,b,z,dia) + ขอบ outer
    holes ใช้ได้เฉพาะแสดงขอบ (ช่องเปิดไม่ถูกเจาะในเมช host)"""
    host = Host(outer, 'z', 0, H, label=u"พื้น")
    groups = {}
    for br in bars:
        k = br["group"]
        if k not in groups:
            groups[k] = BarGroup(k, SLAB_LABELS.get(k, k), SLAB_COLORS.get(k, GRAY),
                                 br["dia"] / 2.0)
        (x0, y0), (x1, y1) = br["a"], br["b"]
        groups[k].add([(x0, y0, br["z"]), (x1, y1, br["z"])])
    gl = [groups[k] for k in ("TX", "TY", "BX", "BY") if k in groups]
    return Scene(title, [host], gl)


# ------------------------------------------------------------ บันได
def stair_profile(geo, tw):
    """รูปตัด (s,z) ของช่วงบันได: ท้องบันไดลาด + ขั้นฟันปลา; geo = stair_calc.Geo
    (ใช้ n_t, g, r, Lh, soffit()) — จุดมุมในขั้นถูกตัดไม่ให้ต่ำกว่าท้อง"""
    z_s0 = geo.soffit(0.0, tw)
    pts = [(0.0, z_s0), (geo.Lh, geo.soffit(geo.Lh, tw)), (geo.Lh, geo.n_t * geo.r)]
    for k in range(geo.n_t, 0, -1):
        s_hi = k * geo.g
        s_lo = (k - 1) * geo.g
        pts.append((s_hi, k * geo.r))
        pts.append((s_lo, k * geo.r))
        pts.append((s_lo, max((k - 1) * geo.r, geo.soffit(s_lo, tw))))
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > 1e-6 or abs(p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-6 and \
            abs(out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def stair_scene(geo, W, sets, tw, landing=None, z0=0.0, title=u"บันได"):
    """ช่วงบันได 1 ช่วงกว้าง W (t = y กึ่งกลาง 0, s = x) + เหล็กจาก stair_calc.plan_run
    sets = list ของชุด (kind szplane/transverse; group; count) ตามที่ plan_run/plan_landing คืน
    landing = (s_lo,s_hi,t_lo,t_hi,z_top,tl) เพื่อวาดชาน (ไม่บังคับ)"""
    hosts = [Host([(s, z + z0) for (s, z) in stair_profile(geo, tw)], 'y',
                  -W / 2.0, W / 2.0, label=u"บันได")]
    if landing:
        s_lo, s_hi, t_lo, t_hi, z_top, tl = landing
        hosts.append(Host.box(s_lo, t_lo, z_top - tl, s_hi, t_hi, z_top, label=u"ชาน"))
    groups = {}
    for st in sets:
        k = st["group"]
        if k not in groups:
            groups[k] = BarGroup(k, STAIR_LABELS.get(k, k), STAIR_COLORS.get(k, GRAY),
                                 _stair_radius(st))
        g = groups[k]
        cnt = max(1, int(st["count"]))
        if st["kind"] == "szplane":
            for t in spread(cnt, st["t0"], st["t1"], True):
                g.add([(s, t, z) for (s, z) in st["pts"]])
        else:
            ds, dz = st["dir"]
            for i in range(cnt):
                f = (st["arr_len"] * i / (cnt - 1.0)) if cnt > 1 else 0.0
                s, z = st["s"] + ds * f, st["z"] + dz * f
                g.add([(s, st["t_lo"], z), (s, st["t_hi"], z)])
    gl = [groups[k] for k in ("waist", "ext", "tread", "crack") if k in groups]
    return Scene(title, hosts, gl)


def _stair_radius(st):
    """รัศมีจากชื่อขนาด (เช่น DB12 -> 6 มม.) ไม่เจอเลขใช้ 6"""
    import re
    m = re.search(r"(\d+)", str(st.get("size", "")))
    return (float(m.group(1)) / 2.0) if m else 6.0
