# -*- coding: utf-8 -*-
"""การคำนวณล้วนๆ (ไม่แตะ Revit API) ของโมดูล Rebar คาน — ทดสอบนอก Revit ได้

พิกัดท้องถิ่นของคาน (หน่วย มม. ทั้งหมด):
  s = ตามแนวแกนคาน, u = แนวขวางด้านข้าง, v = แนวดิ่ง (บวกขึ้น)
คาน = กล่อง [s0,s1] x [u0,u1] x [v0,v1]

ค่ามาตรฐานที่ยังต้องให้วิศวกรยืนยันอยู่ใน docs/accept-rebar-beam.md
"""
from __future__ import division
import math

MIN_CLEAR_MM = 25.0   # ระยะห่างเหล็กแนวนอนขั้นต่ำ = max(25 มม., d) — รอยืนยัน


def clear_gap(d):
    return max(MIN_CLEAR_MM, d)


def row_xs(n, x0, x1):
    """ตำแหน่ง n เส้นเรียงสม่ำเสมอระหว่าง x0..x1 (n=1 → กึ่งกลาง)"""
    if n <= 0:
        return []
    if n == 1:
        return [(x0 + x1) / 2.0]
    return [x0 + (x1 - x0) * i / (n - 1.0) for i in range(n)]


def row_fits(n, d, span):
    """n เส้นขนาด d วางในช่วงศูนย์กลาง span ได้ไหม (ระยะใสไม่น้อยกว่า clear_gap)"""
    if n <= 1:
        return True
    return (n - 1) * (d + clear_gap(d)) <= span + 1e-6


def splice_n(length, max_len, lap):
    """จำนวนช่วงเท่าๆ กัน n (≥2) ที่ทำให้ท่อนยาวสุด (แบบเหล็กล่างเลื่อนจุด) + lap ไม่เกิน max_len
    คืน 1 ถ้าไม่ต้องต่อ"""
    if length <= max_len + 1e-9:
        return 1
    if max_len - lap <= 0:
        raise ValueError("max_len must exceed lap length")
    n = 2
    while 1.5 * length / n + lap > max_len + 1e-9:
        n += 1
    return n


def splice_cuts(length, n, kind):
    """จุดกึ่งกลางรอยต่อทาบ (พิกัดสัมพัทธ์ 0..length) เมื่อแบ่ง n ช่วง (n=1 → ไม่ต่อ)

    kind 'top'    : ต่อที่ i*L/n (n=2 → กลางคาน)
    kind 'bottom' : เลื่อนเข้าหาปลายคาน (ที่เสา) L/(2n) จากจุดของเหล็กบน
                    ใช้ n เดียวกันจึงไม่ซ้ำจุดเดียวกับเหล็กบนเสมอ (ห่างกัน L/(2n))
    """
    if n <= 1:
        return []
    top = [length * i / float(n) for i in range(1, n)]
    if kind == 'top':
        return top
    return [c - length / (2.0 * n) for c in top]


def pieces(length, cuts, lap):
    """ท่อนเหล็ก [(a,b)] สัมพัทธ์ 0..length ปลายท่อนที่ติดรอยต่อขยายออกครึ่งหนึ่งของ lap"""
    pts = [0.0] + list(cuts) + [length]
    out = []
    last = len(pts) - 2
    for i in range(len(pts) - 1):
        a = pts[i] - (lap / 2.0 if i > 0 else 0.0)
        b = pts[i + 1] + (lap / 2.0 if i < last else 0.0)
        out.append((a, b))
    return out


def min_splice_separation(cuts_a, cuts_b):
    """ระยะห่างน้อยสุดระหว่างจุดต่อของสองชุด (None ถ้าชุดใดว่าง)"""
    if not cuts_a or not cuts_b:
        return None
    return min(abs(a - b) for a in cuts_a for b in cuts_b)


def extra_segments(length, mode, div):
    """ช่วงเหล็กเสริมพิเศษ [(a, b, ติดปลายซ้าย, ติดปลายขวา)]

    mode 'ends': L/div จากปลายทั้งสองข้าง · mode 'mid': กลางช่วงเว้นปลายละ L/div
    """
    q = length / float(div)
    if mode == 'ends':
        return [(0.0, q, True, False), (length - q, length, False, True)]
    if length - 2 * q <= 0:
        return []
    return [(q, length - q, False, False)]


def stirrup_count(length, spacing):
    """จำนวนปลอกในโซนยาว length ระยะห่างสูงสุด spacing (ตาม Maximum Spacing: ปลายถึงปลาย)"""
    if length <= 1e-9:
        return 1
    return int(math.ceil(length / spacing - 1e-9)) + 1


def stirrup_zones(z0, z1, end_len, sp_end, sp_mid):
    """โซนปลอก [(เริ่ม, ยาว, ระยะ)] ตาม s: ปลายถี่-กลาง-ปลายถี่

    คานสั้นที่ไม่พอแบ่งสามโซน → โซนเดียวใช้ระยะถี่ (sp_end)
    """
    total = z1 - z0
    if total <= 0:
        return []
    if total <= 2 * end_len + sp_mid:
        return [(z0, total, sp_end)]
    zones = [(z0, end_len, sp_end)]
    zm = z0 + end_len + sp_mid
    zt = z1 - end_len
    mid_len = zt - sp_mid - zm
    zones.append((zm, max(mid_len, 0.0), sp_mid))
    zones.append((zt, end_len, sp_end))
    return zones


def _layers(face, groups, edge0, sign, u0, u1, cover, dt, errors, tag):
    """วางชั้นเหล็กของด้านหนึ่ง คืน [(role, name, d, v, [u...])]
    groups = [(n, d, name, role)]; edge0 = ผิวคาน (v1 หรือ v0); sign -1 ลง / +1 ขึ้น"""
    out = []
    prev_c = None
    prev_d = None
    for (n, d, name, role) in groups:
        if n <= 0:
            continue
        if prev_c is None:
            c = edge0 + sign * (cover + dt + d / 2.0)
        else:
            gap = max(MIN_CLEAR_MM, prev_d, d)
            c = prev_c + sign * (prev_d / 2.0 + gap + d / 2.0)
        x0 = u0 + cover + dt + d / 2.0
        x1 = u1 - cover - dt - d / 2.0
        if x1 < x0 or not row_fits(n, d, x1 - x0):
            errors.append(u"{}: เหล็ก {} เส้น {} ไม่พอดีความกว้างคาน".format(
                role, n, name))
        out.append((role, name, d, c, row_xs(n, x0, x1)))
        prev_c, prev_d = c, d
    return out


def plan_longitudinal(s0, s1, u0, u1, v0, v1, spec):
    """วางแผนเหล็กตามยาวทั้งหมดของคาน 1 ตัว

    spec: cover, d_tie, max_len, lap_d, hook_mult,
          top=[(n,d,name)...ชั้น 1,2], bot=[...],
          xtop/xbot=(n,d,name,mode,div) หรือ None, side=(n,d,name) หรือ None
    คืน (bars, errors, warnings, info)
      bars = list dict: role, name, dia, u, v, s_a, s_b, hook_a, hook_b ('down'/'up'/None)
      info = {'top_cuts','bot_cuts'} (พิกัด s สัมบูรณ์)
    """
    errors = []
    warnings = []
    cover = spec['cover']
    dt = spec['d_tie']
    sa = s0 + cover
    sb = s1 - cover
    Lb = sb - sa
    if Lb <= 0 or (u1 - u0) <= 2 * (cover + dt) or (v1 - v0) <= 2 * (cover + dt):
        return [], [u"คานเล็กเกินไปเมื่อเทียบกับระยะหุ้ม"], warnings, {}

    top_g = [(n, d, nm, 'top%d' % (i + 1))
             for i, (n, d, nm) in enumerate(spec['top'])]
    bot_g = [(n, d, nm, 'bot%d' % (i + 1))
             for i, (n, d, nm) in enumerate(spec['bot'])]
    nlayers_top = len([g for g in top_g if g[0] > 0])
    nlayers_bot = len([g for g in bot_g if g[0] > 0])
    xt, xb = spec.get('xtop'), spec.get('xbot')
    if xt and xt[0] > 0:
        top_g.append((xt[0], xt[1], xt[2], 'xtop'))
    if xb and xb[0] > 0:
        bot_g.append((xb[0], xb[1], xb[2], 'xbot'))

    top_l = _layers('top', top_g, v1, -1, u0, u1, cover, dt, errors, 'top')
    bot_l = _layers('bot', bot_g, v0, +1, u0, u1, cover, dt, errors, 'bot')

    # ชั้นบนกับล่างต้องไม่ชนกัน
    if top_l and bot_l:
        lowest_top = min(c - d / 2.0 for (_, _, d, c, _) in top_l)
        highest_bot = max(c + d / 2.0 for (_, _, d, c, _) in bot_l)
        if lowest_top - highest_bot < MIN_CLEAR_MM:
            errors.append(u"เหล็กบนกับเหล็กล่างซ้อนกัน — คานตื้นเกินไปสำหรับจำนวนชั้นนี้")

    def dmax(groups):
        ds = [d for (n, d, nm, r) in groups if n > 0 and not r.startswith('x')]
        return max(ds) if ds else 0.0

    lap_top = spec['lap_d'] * dmax(top_g)
    lap_bot = spec['lap_d'] * dmax(bot_g)
    max_len = spec['max_len']
    n_sp = splice_n(Lb, max_len, max(lap_top, lap_bot))
    top_cuts = splice_cuts(Lb, n_sp, 'top')
    bot_cuts = splice_cuts(Lb, n_sp, 'bottom')
    sep = min_splice_separation(top_cuts, bot_cuts)
    if sep is not None and sep < max(lap_top, lap_bot):
        errors.append(u"จุดต่อทาบเหล็กบนกับล่างใกล้กันเกินไป ({:.0f} มม.)".format(sep))
    for c in top_cuts + bot_cuts:
        if c < 0.5 * max(lap_top, lap_bot) or Lb - c < 0.5 * max(lap_top, lap_bot):
            errors.append(u"จุดต่อทาบอยู่ใกล้ปลายคานเกินไป")
            break

    hook_mult = spec['hook_mult']
    bars = []

    def add_full(layers, direction, cuts, lap):
        for (role, name, d, v, us) in layers:
            if role.startswith('x'):
                continue
            if hook_mult * d > (v1 - v0) - 2 * cover:
                warnings.append(u"{}: ขางอ {:.0f} มม. ยาวกว่าความลึกคาน".format(
                    role, hook_mult * d))
            ps = pieces(Lb, cuts, lap)
            for u in us:
                for k, (a, b) in enumerate(ps):
                    bars.append({
                        'role': role, 'name': name, 'dia': d, 'u': u, 'v': v,
                        's_a': sa + a, 's_b': sa + b,
                        'hook_a': direction if k == 0 else None,
                        'hook_b': direction if k == len(ps) - 1 else None})

    add_full(top_l, 'down', top_cuts, lap_top)
    add_full(bot_l, 'up', bot_cuts, lap_bot)

    def add_extra(layers, direction, ex):
        for (role, name, d, v, us) in layers:
            if not role.startswith('x'):
                continue
            for (a, b, ha, hb) in extra_segments(Lb, ex[3], ex[4]):
                for u in us:
                    bars.append({
                        'role': role, 'name': name, 'dia': d, 'u': u, 'v': v,
                        's_a': sa + a, 's_b': sa + b,
                        'hook_a': direction if ha else None,
                        'hook_b': direction if hb else None})

    if xt and xt[0] > 0:
        add_extra(top_l, 'down', xt)
    if xb and xb[0] > 0:
        add_extra(bot_l, 'up', xb)

    # เหล็กข้าง: n เส้นต่อด้าน เรียงระหว่างชั้นแรกบน-ล่าง
    side = spec.get('side')
    if side and side[0] > 0:
        n, d, name = side
        t0 = [c for (r, _, _, c, _) in top_l if r == 'top1']
        b0 = [c for (r, _, _, c, _) in bot_l if r == 'bot1']
        vt = t0[0] if t0 else v1 - cover - dt
        vb = b0[0] if b0 else v0 + cover + dt
        ps = pieces(Lb, top_cuts, spec['lap_d'] * d)
        ux = [u0 + cover + dt + d / 2.0, u1 - cover - dt - d / 2.0]
        for i in range(1, n + 1):
            v = vb + (vt - vb) * i / (n + 1.0)
            for u in ux:
                for (a, b) in ps:
                    bars.append({
                        'role': 'side', 'name': name, 'dia': d, 'u': u, 'v': v,
                        's_a': sa + a, 's_b': sa + b,
                        'hook_a': None, 'hook_b': None})

    info = {'top_cuts': [sa + c for c in top_cuts],
            'bot_cuts': [sa + c for c in bot_cuts]}
    return bars, errors, warnings, info


def plan_stirrups(s0, s1, u0, u1, v0, v1, spec):
    """ปลอก: คืน (zones, (ua,ub,va,vb)) — zones = [(s เริ่ม, ยาว, ระยะ)], สี่เหลี่ยมถึงกึ่งกลางเส้นลวดปลอก"""
    cover = spec['cover']
    dt = spec['d_tie']
    zones = stirrup_zones(s0 + cover, s1 - cover, spec['end_len'],
                          spec['sp_end'], spec['sp_mid'])
    rect = (u0 + cover + dt / 2.0, u1 - cover - dt / 2.0,
            v0 + cover + dt / 2.0, v1 - cover - dt / 2.0)
    return zones, rect
