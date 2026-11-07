# -*- coding: utf-8 -*-
"""ส่งออกตารางตัดเหล็ก: .xlsx (zipfile + XML เขียนเอง ไม่พึ่ง library) และ .csv UTF-8-BOM
ข้อมูลเป็น list ของแถว (เซลล์ = ข้อความหรือตัวเลข) — ไม่พึ่ง Revit"""
from __future__ import unicode_literals

import io
import zipfile

try:
    text_type = unicode  # noqa: F821  (IronPython 2)
except NameError:
    text_type = str


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _col(i):
    s = ""
    i += 1
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[r] + s
    return s


def _sheet_xml(rows):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<sheetData>']
    for ri, row in enumerate(rows):
        out.append('<row r="{}">'.format(ri + 1))
        for ci, v in enumerate(row):
            ref = "{}{}".format(_col(ci), ri + 1)
            if v is None or v == "":
                continue
            if isinstance(v, bool):
                v = text_type(v)
            if isinstance(v, (int, float)):
                out.append('<c r="{}"><v>{}</v></c>'.format(ref, repr(v)))
            else:
                out.append('<c r="{}" t="inlineStr"><is><t xml:space="preserve">{}</t></is></c>'
                           .format(ref, _esc(text_type(v))))
        out.append('</row>')
    out.append('</sheetData></worksheet>')
    return "".join(out)


def _sheet_name(n, used):
    n = "".join("_" if c in '[]:*?/\\' else c for c in n)[:31] or "Sheet"
    base, k = n, 2
    while n in used:
        suf = "_{}".format(k)
        n = base[:31 - len(suf)] + suf
        k += 1
    used.add(n)
    return n


def write_xlsx(path, sheets):
    """sheets = [(ชื่อชีต, rows)] — เขียน .xlsx ที่ Excel เปิดได้ (ไม่มีสไตล์/ความกว้างคอลัมน์)"""
    used = set()
    names = [_sheet_name(n, used) for n, _ in sheets]
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i, nm in enumerate(names):
        ct.append('<Override PartName="/xl/worksheets/sheet{0}.xml" ContentType='
                  '"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'.format(i + 1))
        wb.append('<sheet name="{}" sheetId="{}" r:id="rId{}"/>'.format(_esc(nm), i + 1, i + 1))
        rels.append('<Relationship Id="rId{0}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{0}.xml"/>'.format(i + 1))
    ct.append('</Types>')
    wb.append('</sheets></workbook>')
    rels.append('</Relationships>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                 '</Relationships>')
    z = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED)
    try:
        z.writestr("[Content_Types].xml", "".join(ct).encode("utf-8"))
        z.writestr("_rels/.rels", root_rels.encode("utf-8"))
        z.writestr("xl/workbook.xml", "".join(wb).encode("utf-8"))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels).encode("utf-8"))
        for i, (_, rows) in enumerate(sheets):
            z.writestr("xl/worksheets/sheet{}.xml".format(i + 1),
                       _sheet_xml(rows).encode("utf-8"))
    finally:
        z.close()
    return path


def _csv_cell(v):
    if v is None:
        return ""
    s = text_type(v)
    if any(c in s for c in ',"\n\r'):
        s = '"' + s.replace('"', '""') + '"'
    return s


def write_csv(path, sheets):
    """CSV UTF-8 มี BOM (Excel ไทยเปิดไม่เพี้ยน) — sheets เหมือน write_xlsx ต่อกันเป็นไฟล์เดียวคั่นด้วยแถวชื่อ"""
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        for name, rows in sheets:
            f.write(_csv_cell("# " + name) + "\r\n")
            for row in rows:
                f.write(",".join(_csv_cell(v) for v in row) + "\r\n")
            f.write("\r\n")
    return path


def build_tables(rows, plan, summary_line, note=""):
    """สร้างตาราง 3 ชุด (ตารางตัดเหล็ก / แผนตัด / สรุป) เป็น [(ชื่อ, rows)]"""
    import bar_cut_calc as bc
    cut = [["เลข", "ขนาด", "รูปตัด+มิติ (มม.)", "จำนวนท่อน", "ความยาวตัด (มม.)",
            "ความยาวรวม (ม.)", "น้ำหนัก (กก.)", "ชนิดงาน"]]
    for r in rows:
        cut.append([r["no"], r["size"], bc.shape_label(r["shape"]), r["count"],
                    round(r["length_mm"], 1), round(r["total_m"], 3),
                    round(r["weight_kg"], 2),
                    "/".join(bc.KIND_LABEL.get(k, k) for k in r["kinds"])])
    cut.append(["รวม", "", "", sum(r["count"] for r in rows), "",
                round(sum(r["total_m"] for r in rows), 3),
                round(sum(r["weight_kg"] for r in rows), 2), ""])
    pl = [["ขนาด", "แบบ", "จำนวนท่อนสต็อกแบบนี้", "ชิ้นที่ตัด (มม.)", "เศษต่อท่อน (มม.)"]]
    for p in plan["patterns"]:
        pl.append([p["size"], p["name"], p["n"],
                   " + ".join("{:.0f}".format(x) for x in p["pieces"]),
                   round(p["waste_mm"], 1)])
    pl.append([])
    pl.append(["ขนาด", "สั่ง (ท่อน)", "ยาวสต็อก (ม.)", "ใช้งาน (ม.)", "เศษ (ม.)",
               "เศษ % ตามความยาว", "น้ำหนักสั่ง (กก.)", "น้ำหนักเศษ (กก.)",
               "เศษ % ตามน้ำหนัก", "ชิ้นยาวเกินสต็อก (ต้องต่อทาบ)"])
    for s in plan["by_size"]:
        pl.append([s["size"], s["n_stock"], round(s["stock_len_m"], 2),
                   round(s["use_len_m"], 2), round(s["waste_len_m"], 2),
                   round(s["waste_pct"], 2), round(s["stock_kg"], 2),
                   round(s["waste_kg"], 2), round(s["waste_pct"], 2),
                   ", ".join("{:.0f}".format(x) for x in s["oversize"])])
    t = plan["total"]
    pl.append(["รวม", t["stock"], round(t["stock_len_m"], 2), round(t["use_len_m"], 2),
               round(t["waste_len_m"], 2), round(t["waste_pct_len"], 2),
               round(t["stock_kg"], 2), round(t["waste_kg"], 2),
               round(t["waste_pct_kg"], 2), ""])
    sm = [["สรุป", summary_line],
          ["ท่อนสต็อก (ม.)", plan["stock_m"]],
          ["เผื่อรอยตัด (มม./รอยตัด)", plan["kerf_mm"]],
          ["หมายเหตุ", note or "น้ำหนักหน่วยเป็นค่าตั้งต้น ต้องยืนยันกับตารางมาตรฐานก่อนสั่งซื้อ"]]
    return [("ตารางตัดเหล็ก", cut), ("แผนตัด", pl), ("สรุป", sm)]
