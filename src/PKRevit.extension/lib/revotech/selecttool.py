# -*- coding: utf-8 -*-
"""ปุ่ม "เลือก" ปุ่มเดียว = Select Rebar + Select Host เดิม (ตรรกะเลือก/สรุปผลย้ายมาจากสองสคริปต์เดิม ไม่เปลี่ยน)

  เลือก host อยู่  → เลือกเหล็กทุกชนิดบน host นั้น
  เลือกเหล็กอยู่   → เลือก host ของเหล็กนั้น
  ไม่ได้เลือกอะไร   → ถามว่าจะเลือกทางไหน
  เลือกปนทั้งสอง   → ถามว่าจะใช้ส่วนไหน
ส่วน import ของ Revit อยู่ในฟังก์ชัน เพื่อให้ decide() ทดสอบนอก Revit ได้
"""

MODE_BARS = "bars_on_hosts"     # host -> เหล็ก
MODE_HOSTS = "host_of_bars"     # เหล็ก -> host
ASK_WAY = "ask_way"             # ไม่ได้เลือกอะไร
ASK_MIXED = "ask_mixed"         # เลือกปน


def decide(n_hosts, n_bars):
    """จากจำนวน host / เหล็ก ที่เลือกอยู่ → โหมด"""
    if n_hosts and n_bars:
        return ASK_MIXED
    if n_hosts:
        return MODE_BARS
    if n_bars:
        return MODE_HOSTS
    return ASK_WAY


def _ask(title, instruction, link1, link2):
    """TaskDialog 2 ตัวเลือก → 1, 2 หรือ None (ยกเลิก)"""
    from Autodesk.Revit.UI import TaskDialog, TaskDialogCommandLinkId, TaskDialogResult
    td = TaskDialog(title)
    td.MainInstruction = instruction
    td.AllowCancellation = True
    td.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, link1[0], link1[1])
    td.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, link2[0], link2[1])
    r = td.Show()
    if r == TaskDialogResult.CommandLink1:
        return 1
    if r == TaskDialogResult.CommandLink2:
        return 2
    return None


_BARS_LINK = (u"เลือก host แล้วเลือกเหล็กบนนั้น",
              u"คาน เสา ฐานราก พื้น ผนัง ฯลฯ → เลือกเหล็กทุกชนิดที่อยู่บน host")
_HOSTS_LINK = (u"เลือกเหล็ก แล้วเลือก host ของมัน",
               u"Rebar / ไวร์เมช / Area-Path → เลือก host ที่เหล็กนั้นอยู่")


def run(uidoc, doc):
    from revotech import manage
    sel = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    sel = [e for e in sel if e is not None]
    hosts = [e.Id for e in sel if manage.is_host_candidate(e)]
    bars = [e.Id for e in sel if manage.is_bar_element(e)]
    mode = decide(len(hosts), len(bars))
    if mode == ASK_WAY:
        a = _ask(u"เลือก", u"จะเลือกอะไร?", _BARS_LINK, _HOSTS_LINK)
        if a is None:
            return
        mode = MODE_BARS if a == 1 else MODE_HOSTS
    elif mode == ASK_MIXED:
        a = _ask(u"เลือก",
                 u"เลือกทั้ง host ({}) และเหล็ก ({}) อยู่ — จะใช้ส่วนไหน?".format(len(hosts), len(bars)),
                 (u"ใช้ host ที่เลือก → เลือกเหล็กบนนั้น", u"ส่วนที่เป็นเหล็กจะไม่นับ"),
                 (u"ใช้เหล็กที่เลือก → เลือก host ของมัน", u"ส่วนที่เป็น host จะไม่นับ"))
        if a is None:
            return
        mode = MODE_BARS if a == 1 else MODE_HOSTS
    if mode == MODE_BARS:
        select_bars_on_hosts(uidoc, doc, hosts if sel else None)
    else:
        select_host_of_bars(uidoc, doc, bars if sel else None)


def select_bars_on_hosts(uidoc, doc, host_ids=None):
    """เดิม: Select Rebar (host_ids=None → ใช้ hostpick.resolve เหมือนเดิม)"""
    from pyrevit import DB, forms
    from System.Collections.Generic import List
    from revotech import hostpick, ui, reinforcement as rf
    from revotech import manage, managecalc as mc
    from revotech.rvt import id_value
    title = u"เลือกเหล็กบน host — PK Revit"
    if not host_ids:
        host_ids = hostpick.resolve(uidoc, doc, manage.is_host_candidate, u"host")
    if host_ids is None:
        return    # ผู้ใช้ยกเลิก
    if not host_ids:
        forms.alert(u"ไม่ได้เลือก host", title=title)
        return
    found, hosts_hit = [], 0
    for hid in host_ids:
        els = rf.on_host(doc, hid)
        if els:
            hosts_hit += 1
            found.extend(els)
    seen, uniq = set(), []
    for e in found:
        k = id_value(e.Id)
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    if not uniq:
        forms.alert(u"ไม่พบเหล็กบน host ที่เลือก ({} ตัว)".format(len(host_ids)), title=title)
        return
    uidoc.Selection.SetElementIds(List[DB.ElementId]([e.Id for e in uniq]))
    counts = mc.count_kinds([rf.kind(e) for e in uniq])
    lines = mc.count_lines(counts)
    skip = mc.skipped_summary(len(host_ids), hosts_hit)
    if skip:
        lines.append(u"")
        lines.append(skip)
    ui.summary(title, u"เลือกเหล็กแล้ว {} รายการ จาก host {} ตัว".format(len(uniq), hosts_hit), lines)


def select_host_of_bars(uidoc, doc, ids=None):
    """เดิม: Select Host (ids=None → ใช้ hostpick.resolve เหมือนเดิม)"""
    from pyrevit import DB, forms
    from System.Collections.Generic import List
    from revotech import hostpick, ui, reinforcement as rf
    from revotech import manage, managecalc as mc
    title = u"เลือก host ของเหล็ก — PK Revit"
    if not ids:
        ids = hostpick.resolve(uidoc, doc, manage.is_bar_element, u"เหล็ก")
    if ids is None:
        return
    if not ids:
        forms.alert(u"ไม่ได้เลือกเหล็ก", title=title)
        return
    bars = [doc.GetElement(i) for i in ids]
    bars = [b for b in bars if b is not None]
    host_ids, missing = manage.hosts_of_many(doc, bars)
    if not host_ids:
        forms.alert(u"หา host ของเหล็กที่เลือกไม่พบ ({} เส้น) — "
                    u"อาจเป็นเหล็กที่ host ถูกลบหรือไม่มีความสัมพันธ์กับ host".format(len(bars)),
                    title=title)
        return
    uidoc.Selection.SetElementIds(List[DB.ElementId](host_ids))
    counts = {}
    for h in host_ids:
        el = doc.GetElement(h)
        n = el.Category.Name if el is not None and el.Category is not None else u"?"
        counts[n] = counts.get(n, 0) + 1
    lines = [u"  {}: {} ตัว".format(k, counts[k]) for k in sorted(counts)]
    lines.append(u"  เหล็กที่เลือก: " + u", ".join(
        u"{} {}".format(mc.KIND_TH.get(k, k), n)
        for k, n in mc.count_kinds([rf.kind(b) for b in bars])))
    if missing:
        lines.append(u"")
        lines.append(u"ข้าม {} เส้นที่หา host ไม่เจอ".format(missing))
    ui.summary(title, u"เลือก host แล้ว {} ตัว".format(len(host_ids)), lines)
