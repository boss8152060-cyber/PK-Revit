# -*- coding: utf-8 -*-
"""Dang Gen — ฟังก์ชันคำนวณจุดวางดั้ง (ล้วน ไม่พึ่ง Revit; หน่วย มม. ทั้งหมด)

ดั้ง = เสาสั้นตั้งใต้อกไก่/จุดรวมตะเข้สัน ลงไปถึงโครงรับด้านล่าง
ใช้ได้ทั้ง IronPython 2.7 และ Python 3 (รัน test นอก Revit ได้)

โครงข้อมูล:
  member = {"id": int, "kind": "hip"|"ridge", "p0": (x,y,z), "p1": (x,y,z)}
           (พิกัดเส้นอ้างอิงของคาน — Hip Ridge Gen ใช้ Z-justify = top)
  node   = {"x","y","top_z","kinds","count","src"}   top_z = ใต้ท้องคาน
"""
from __future__ import division
import math


def _dxy(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def candidate_ends(members):
    """ปลายคานที่นับเป็น "จุดรวมบน": อกไก่ทั้งสองปลาย / ตะเข้สันเฉพาะปลายบน
    (ปลายล่างของตะเข้สันอยู่ที่ชายคา ไม่ต้องมีดั้ง)"""
    ends = []
    for m in members:
        p0, p1 = m["p0"], m["p1"]
        if m["kind"] == "ridge":
            ends.append({"mid": m["id"], "kind": "ridge", "p": p0})
            ends.append({"mid": m["id"], "kind": "ridge", "p": p1})
        else:
            if abs(p0[2] - p1[2]) < 1.0:
                pick = [p0, p1]
            else:
                pick = [p0 if p0[2] > p1[2] else p1]
            for p in pick:
                ends.append({"mid": m["id"], "kind": "hip", "p": p})
    return ends


def cluster_ends(ends, tol_xy, tol_z):
    """จัดกลุ่มปลายที่อยู่ใกล้กัน (ระยะในแปลน ≤ tol_xy และต่างระดับ ≤ tol_z)
    แบบโยงถึงกันเป็นทอด (single-link)"""
    n = len(ends)
    seen = [False] * n
    groups = []
    for i in range(n):
        if seen[i]:
            continue
        seen[i] = True
        grp = [i]
        q = 0
        while q < len(grp):
            cur = ends[grp[q]]["p"]
            q += 1
            for j in range(n):
                if seen[j]:
                    continue
                pj = ends[j]["p"]
                if _dxy(cur, pj) <= tol_xy and abs(cur[2] - pj[2]) <= tol_z:
                    seen[j] = True
                    grp.append(j)
        groups.append([ends[k] for k in grp])
    return groups


def find_nodes(members, tol_xy=300.0, tol_z=600.0, min_members=2,
               ridge_ends_always=True, member_depth=100.0):
    """จุดที่ต้องมีดั้ง = กลุ่มปลายที่มีคานมาชุมนุม ≥ min_members เส้น
    (+ ปลายอกไก่ทุกจุด ถ้า ridge_ends_always — อกไก่ต้องมีที่รับ)
    top_z = ระดับต่ำสุดของปลายในกลุ่ม − ความลึกคาน (ดั้งรับท้องคาน)"""
    nodes = []
    for grp in cluster_ends(candidate_ends(members), tol_xy, tol_z):
        ids = set(e["mid"] for e in grp)
        kinds = sorted(set(e["kind"] for e in grp))
        if len(ids) < min_members and not (ridge_ends_always
                                           and "ridge" in kinds):
            continue
        cnt = float(len(grp))
        x = sum(e["p"][0] for e in grp) / cnt
        y = sum(e["p"][1] for e in grp) / cnt
        z = min(e["p"][2] for e in grp)
        nodes.append({"x": x, "y": y, "top_z": z - member_depth,
                      "kinds": kinds, "count": len(ids), "src": "junction"})
    return nodes


def ridge_mid_nodes(members, max_span, member_depth=100.0):
    """ดั้งกลางแนวอกไก่ ถ้าอกไก่ยาว (ในแปลน) เกิน max_span — แบ่งเท่าๆ กัน
    max_span ≤ 0 = ปิด"""
    out = []
    if max_span is None or max_span <= 0:
        return out
    for m in members:
        if m["kind"] != "ridge":
            continue
        p0, p1 = m["p0"], m["p1"]
        L = _dxy(p0, p1)
        if L <= max_span:
            continue
        n = int(math.ceil(L / max_span))
        for i in range(1, n):
            t = i / float(n)
            out.append({"x": p0[0] + (p1[0] - p0[0]) * t,
                        "y": p0[1] + (p1[1] - p0[1]) * t,
                        "top_z": p0[2] + (p1[2] - p0[2]) * t - member_depth,
                        "kinds": ["ridge"], "count": 1, "src": "ridge-mid"})
    return out


def merge_nodes(primary, extra, tol_xy):
    """รวมรายการ โดย extra ที่อยู่ใกล้ primary (ในแปลน) ≤ tol_xy ถูกทิ้ง"""
    res = list(primary)
    for e in extra:
        if all(_dxy((e["x"], e["y"], 0), (n["x"], n["y"], 0)) > tol_xy
               for n in res):
            res.append(e)
    return res


def choose_bottom(top_z, hit_zs, fallback_len, min_len=200.0, max_len=4000.0):
    """เลือกระดับล่างของดั้ง
    hit_zs = ระดับผิวบนของสิ่งที่ยิงเจอใต้จุด (โครงรับ/คาน/พื้น)
    — เอาผิวที่ "ใกล้ที่สุดใต้ top_z" ที่ห่างอย่างน้อย min_len และไม่เกิน max_len
    ไม่มี → ใช้ความยาวที่กรอก (fallback_len)
    คืน (bottom_z, 'support'|'fallback')"""
    cands = [z for z in (hit_zs or [])
             if top_z - z >= min_len and top_z - z <= max_len]
    if cands:
        return max(cands), "support"
    return top_z - fallback_len, "fallback"


def plan_dang(nodes, hits, fallback_len, min_len=200.0, max_len=4000.0):
    """รวมผล: hits[i] = รายการระดับที่ยิงเจอใต้ nodes[i] (ว่างได้)
    คืนรายการ {"x","y","top_z","bottom_z","length","source"} ข้ามตัวที่สั้นกว่า min_len"""
    plan = []
    for i, n in enumerate(nodes):
        hz = hits[i] if i < len(hits) else []
        b, src = choose_bottom(n["top_z"], hz, fallback_len, min_len, max_len)
        length = n["top_z"] - b
        if length < min_len:
            continue
        plan.append({"x": n["x"], "y": n["y"], "top_z": n["top_z"],
                     "bottom_z": b, "length": length, "source": src,
                     "kinds": n.get("kinds", [])})
    return plan
