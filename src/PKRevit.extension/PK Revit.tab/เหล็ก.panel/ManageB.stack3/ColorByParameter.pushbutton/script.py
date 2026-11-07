# -*- coding: utf-8 -*-
"""Color by Parameter — ระบายสี element ใน view ตามค่าพารามิเตอร์

โหมดเหล็ก (Rebar/RebarInSystem/FabricSheet): Partition, Bar Type, Shape, Mark, Comments
โหมดชิ้นงานโครงสร้าง (คาน เสา ฐานราก พื้น ผนัง): Mark, Type Mark, Family, Type Name, Comments
- สแกนค่าที่ไม่ซ้ำ → สีอัตโนมัติ (ไล่เฉด / คอนทราสต์สูง) เปลี่ยนสีเองได้ จำสีล่าสุดต่อพารามิเตอร์
- ระบายด้วย OverrideGraphicSettings ต่อ element (View.SetElementOverrides) — ไม่ใช้
  ParameterFilterElement เพราะ PK Tool เจอว่าพังกับ Family/Type Name
- ใช้ได้กับหลาย view; fill ทึบหรือเส้นขอบอย่างเดียว
- จำ id ของ element ที่ระบายไว้ (JSON ใน %LOCALAPPDATA%\\PKRevit\\ColorByParameter.json)
  ปุ่ม Reset คืนเฉพาะ element เหล่านั้น และเฉพาะที่สียังเป็นสีที่เราใส่ (ไม่ทับสีที่ผู้ใช้เปลี่ยนเอง)
- ถ้าเลือก element ไว้ก่อนกดปุ่ม สแกน/ระบายเฉพาะที่เลือก; ไม่เลือก = ทุกตัวที่มองเห็นใน view
ตรรกะล้วนอยู่ lib/revotech/colorcalc.py (ทดสอบนอก Revit ได้) ยังไม่เคยรันใน Revit
"""

import os
import clr
import traceback
from System.Collections.Generic import List
from System.Windows import Thickness, TextAlignment, Visibility
from System.Windows.Input import Cursors
from System.Windows.Controls import CheckBox, Button, DockPanel, Dock, TextBlock
from System.Windows.Media import SolidColorBrush, Color
from pyrevit import revit, DB, forms
from Autodesk.Revit.DB.Structure import Rebar, RebarInSystem, FabricSheet

clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")
from System.Windows.Forms import ColorDialog, DialogResult  # noqa: E402
from System.Drawing import Color as DColor  # noqa: E402

from revotech import ui  # noqa: E402
from revotech import colorcalc as cl  # noqa: E402
from revotech.rvt import ename, id_value  # noqa: E402

doc = revit.doc
uidoc = revit.uidoc
BIP = DB.BuiltInParameter
DOC_KEY = doc.PathName or doc.Title

MODE_REBAR, MODE_STRUCT = "rebar", "struct"
PARAMS = {
    MODE_REBAR: [(u"Partition", "Partition"), (u"Bar Type", "BarType"), (u"Shape", "Shape"),
                 (u"Mark", "Mark"), (u"Comments", "Comments")],
    MODE_STRUCT: [(u"Mark", "Mark"), (u"Type Mark", "TypeMark"), (u"Family", "Family"),
                  (u"Type Name", "TypeName"), (u"Comments", "Comments")],
}
SCHEMES = [(u"คอนทราสต์สูง (ค่าไม่มีลำดับ)", cl.SCHEME_CONTRAST),
           (u"ไล่เฉด ส้ม→เขียว (ค่ามีลำดับ)", cl.SCHEME_GRADIENT)]
STRUCT_CATS = [("cb_beam", DB.BuiltInCategory.OST_StructuralFraming),
               ("cb_column", DB.BuiltInCategory.OST_StructuralColumns),
               ("cb_found", DB.BuiltInCategory.OST_StructuralFoundation),
               ("cb_floor", DB.BuiltInCategory.OST_Floors),
               ("cb_wall", DB.BuiltInCategory.OST_Walls)]
VIEW_TYPES = (DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan, DB.ViewType.Elevation,
              DB.ViewType.Section, DB.ViewType.ThreeD, DB.ViewType.Detail,
              DB.ViewType.EngineeringPlan, DB.ViewType.AreaPlan)


def _eid(v):
    return DB.ElementId(int(v))


def _clr(t):
    return clr.GetClrType(t)


# ------------------------------------------------------- อ่านค่าพารามิเตอร์
def _str(e, bip):
    try:
        p = e.get_Parameter(bip)
        return p.AsString() if p is not None else None
    except Exception:
        return None


def _type_of(e):
    try:
        tid = e.GetTypeId()
        return doc.GetElement(tid) if tid != DB.ElementId.InvalidElementId else None
    except Exception:
        return None


def param_value(e, kind):
    if kind == "Mark":
        return cl.norm_value(_str(e, BIP.ALL_MODEL_MARK))
    if kind == "TypeMark":
        t = _type_of(e)
        return cl.norm_value(_str(t, BIP.ALL_MODEL_TYPE_MARK) if t is not None else None)
    if kind == "Family":
        try:
            if isinstance(e, DB.FamilyInstance):
                return cl.norm_value(e.Symbol.Family.Name)
        except Exception:
            pass
        t = _type_of(e)    # ระบบ family (พื้น/ผนัง) ใช้ชื่อ family ของ type
        try:
            return cl.norm_value(t.FamilyName if t is not None else None)
        except Exception:
            return cl.NONE_VALUE
    if kind in ("TypeName", "BarType"):
        t = _type_of(e)
        return cl.norm_value(ename(t) if t is not None else None)
    if kind == "Comments":
        return cl.norm_value(_str(e, BIP.ALL_MODEL_INSTANCE_COMMENTS))
    if kind == "Partition":
        return cl.norm_value(_str(e, BIP.NUMBER_PARTITION_PARAM))
    if kind == "Shape":
        if isinstance(e, Rebar):
            try:
                sid = e.GetShapeId()
                if sid != DB.ElementId.InvalidElementId:
                    return cl.norm_value(ename(doc.GetElement(sid)))
            except Exception:
                pass
        return cl.NONE_VALUE
    return cl.NONE_VALUE


# ---------------------------------------------------------------- view
def eligible_views():
    out = []
    for v in DB.FilteredElementCollector(doc).OfClass(_clr(DB.View)):
        try:
            if v.IsTemplate or v.ViewType not in VIEW_TYPES:
                continue
            out.append(v)
        except Exception:
            continue
    return sorted(out, key=lambda v: (str(v.ViewType), ename(v).lower()))


def candidates(view, mode, cats, selected_ids):
    """element ที่มองเห็นใน view (ถ้ามีเลือกไว้ก่อน จำกัดเฉพาะที่เลือก)"""
    out = []
    if mode == MODE_REBAR:
        for cls in (Rebar, RebarInSystem, FabricSheet):
            out.extend(DB.FilteredElementCollector(doc, view.Id).OfClass(_clr(cls)))
    elif cats:
        lst = List[DB.BuiltInCategory]()
        for c in cats:
            lst.Add(c)
        flt = DB.ElementMulticategoryFilter(lst)
        out.extend(DB.FilteredElementCollector(doc, view.Id)
                   .WhereElementIsNotElementType().WherePasses(flt))
    if selected_ids:
        out = [e for e in out if id_value(e.Id) in selected_ids]
    return out


# ------------------------------------------------------------ ฟอร์ม
class ColorForm(ui.RevoWindow):
    def __init__(self, state, selected_ids):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"COLOR BY ", u"PARAMETER",
            u"ระบายสีตามค่าพารามิเตอร์ — PK Revit", u"ระบายสี",
            width=640, max_height=760)
        self.state = state
        self.sel = selected_ids
        self.groups = {}      # value -> {view_id_int: [element_id_int]}
        self.colors = {}      # value -> rgb
        self.included = {}    # value -> bool
        self.seed = 0
        self.views = []       # view ที่เลือกในโหมดหลาย view
        self.cur = doc.ActiveView
        self.tb_info.Text = (u"view ปัจจุบัน: {} · {}".format(
            ename(self.cur),
            u"เลือก element ไว้ {} ตัว → ระบายเฉพาะที่เลือก".format(len(selected_ids))
            if selected_ids else u"ไม่ได้เลือก → ทุกตัวที่มองเห็นใน view"))
        ui.combo_fill(self.cmb_scheme, [s[0] for s in SCHEMES])
        self._fill_params()
        self.rb_rebar.Checked += self._on_mode
        self.rb_struct.Checked += self._on_mode
        self.rb_multi.Checked += self._on_views_mode
        self.rb_cur.Checked += self._on_views_mode
        self.btn_scan.Click += self._on_scan
        self.btn_regen.Click += self._on_regen
        self.btn_all.Click += lambda s, a: self._set_all(True)
        self.btn_none.Click += lambda s, a: self._set_all(False)
        self.btn_views.Click += self._on_pick_views
        self.btn_reset_cur.Click += lambda s, a: self._finish({"action": "reset_cur"})
        self.btn_reset_all.Click += lambda s, a: self._finish({"action": "reset_all"})
        self.tb_filter.TextChanged += lambda s, a: self._render()

    # --- เตรียม
    def mode(self):
        return MODE_REBAR if self.rb_rebar.IsChecked else MODE_STRUCT

    def _fill_params(self):
        ui.combo_fill(self.cmb_param, [p[0] for p in PARAMS[self.mode()]])

    def kind(self):
        return PARAMS[self.mode()][max(self.cmb_param.SelectedIndex, 0)][1]

    def key(self):
        return cl.param_key(self.mode(), self.kind())

    def scheme(self):
        return SCHEMES[max(self.cmb_scheme.SelectedIndex, 0)][1]

    def _on_mode(self, s, a):
        self.pnl_cats.Visibility = Visibility.Visible if self.mode() == MODE_STRUCT \
            else Visibility.Collapsed
        self._fill_params()
        self._clear_values()

    def _on_views_mode(self, s, a):
        self.btn_views.IsEnabled = bool(self.rb_multi.IsChecked)
        self._show_views()

    def _show_views(self):
        if self.rb_multi.IsChecked:
            self.tb_views.Text = (u"view ที่เลือก {} view: ".format(len(self.views)) +
                                  u", ".join(ename(v) for v in self.views[:6]) +
                                  (u" ..." if len(self.views) > 6 else u"")) \
                if self.views else u"ยังไม่ได้เลือก view — กด \"เลือก view...\""
        else:
            self.tb_views.Text = u""

    def _on_pick_views(self, s, a):
        names = {}
        for v in eligible_views():
            names[u"{} [{}] #{}".format(ename(v), v.ViewType, id_value(v.Id))] = v
        keys = sorted(names.keys())
        chosen = forms.SelectFromList.show(
            keys, title=u"เลือก view ที่จะระบายสี", multiselect=True, button_name=u"ตกลง")
        if chosen is not None:
            self.views = [names[k] for k in chosen]
            self._clear_values()
            self._show_views()

    def target_views(self):
        return list(self.views) if self.rb_multi.IsChecked else [self.cur]

    def _cats(self):
        return [bic for name, bic in STRUCT_CATS if getattr(self, name).IsChecked]

    # --- สแกน
    def _clear_values(self):
        self.groups, self.colors, self.included = {}, {}, {}
        self.pnl_values.Children.Clear()
        self.tb_scan.Text = u"เปลี่ยนเงื่อนไขแล้ว — กด \"สแกนค่า\" ใหม่"

    def _on_scan(self, s, a):
        self.tb_warn.Text = u""
        views = self.target_views()
        if not views:
            self.tb_warn.Text = u"ยังไม่ได้เลือก view"
            return
        mode = self.mode()
        cats = self._cats()
        if mode == MODE_STRUCT and not cats:
            self.tb_warn.Text = u"ติ๊กหมวดอย่างน้อย 1 หมวด"
            return
        kind = self.kind()
        cache, items, total = {}, [], 0
        for v in views:
            for e in candidates(v, mode, cats, self.sel):
                k = id_value(e.Id)
                if k not in cache:
                    try:
                        cache[k] = param_value(e, kind)
                    except Exception:
                        cache[k] = cl.NONE_VALUE
                items.append((id_value(v.Id), k, cache[k]))
                total += 1
        self.groups = cl.group_values(items)
        if not self.groups:
            self.tb_warn.Text = u"ไม่พบ element ที่ตรงเงื่อนไขใน view ที่เลือก"
            self._render()
            return
        self.colors = cl.assign_colors(list(self.groups.keys()), self.scheme(),
                                       cl.remembered_for(self.state, self.key()), self.seed)
        self.included = dict((v, True) for v in self.groups)
        self.tb_scan.Text = u"พบ {} ค่า จาก element {:,} รายการ ({} view) — สีที่เคยใช้ถูกจำไว้".format(
            len(self.groups), len(cache), len(views))
        self._render()

    def _on_regen(self, s, a):
        if not self.groups:
            return
        self.seed += 1
        # สุ่มใหม่ทุกค่า (ไม่ใช้สีที่จำ)
        self.colors = cl.assign_colors(list(self.groups.keys()), self.scheme(), {}, self.seed)
        self._render()

    def _set_all(self, flag):
        for v in self.included:
            self.included[v] = flag
        self._render()

    # --- รายการค่า
    def _render(self):
        self.pnl_values.Children.Clear()
        q = (self.tb_filter.Text or u"").strip().lower()
        for val in cl.sorted_values(self.groups.keys()):
            if q and q not in val.lower():
                continue
            self.pnl_values.Children.Add(self._row(val))

    def _row(self, val):
        dock = DockPanel()
        dock.LastChildFill = True
        dock.Margin = Thickness(0, 2, 0, 0)
        sw = Button()
        sw.Width, sw.Height = 40, 20
        sw.Margin = Thickness(8, 4, 0, 0)
        sw.Cursor = Cursors.Hand
        sw.Background = self._brush(self.colors[val])
        sw.ToolTip = u"คลิกเพื่อเลือกสีเอง"
        sw.Tag = val
        sw.Click += self._on_swatch
        DockPanel.SetDock(sw, Dock.Right)
        cnt = TextBlock()
        cnt.Text = u"{:,}".format(cl.count_of(self.groups[val]))
        cnt.Margin = Thickness(8, 8, 0, 0)
        cnt.MinWidth = 44
        cnt.TextAlignment = TextAlignment.Right
        DockPanel.SetDock(cnt, Dock.Right)
        cb = CheckBox()
        cb.Content = val
        cb.IsChecked = self.included.get(val, True)
        cb.Tag = val
        cb.Checked += self._on_check
        cb.Unchecked += self._on_check
        dock.Children.Add(sw)
        dock.Children.Add(cnt)
        dock.Children.Add(cb)
        return dock

    @staticmethod
    def _brush(rgb):
        return SolidColorBrush(Color.FromRgb(rgb[0], rgb[1], rgb[2]))

    def _on_check(self, s, a):
        self.included[s.Tag] = bool(s.IsChecked)

    def _on_swatch(self, s, a):
        val = s.Tag
        r, g, b = self.colors[val]
        dlg = ColorDialog()
        dlg.FullOpen = True
        dlg.Color = DColor.FromArgb(r, g, b)
        if dlg.ShowDialog() == DialogResult.OK:
            c = dlg.Color
            self.colors[val] = (int(c.R), int(c.G), int(c.B))
            s.Background = self._brush(self.colors[val])

    # --- ส่งค่ากลับ
    def _finish(self, vals):
        self.values = vals
        self.Close()

    def collect(self):
        if not self.groups:
            self.tb_warn.Text = u"กด \"สแกนค่า\" ก่อน"
            return None
        chosen = [v for v in self.groups if self.included.get(v, True)]
        if not chosen:
            self.tb_warn.Text = u"ติ๊กเลือกอย่างน้อย 1 ค่า"
            return None
        return {"action": "apply", "key": self.key(),
                "groups": dict((v, self.groups[v]) for v in chosen),
                "colors": dict(self.colors),
                "views": self.target_views(),
                "solid": bool(self.rb_solid.IsChecked)}


# ----------------------------------------------------------- ระบาย/คืนสี
def _solid_fill_id():
    for fp in DB.FilteredElementCollector(doc).OfClass(_clr(DB.FillPatternElement)):
        try:
            if fp.GetFillPattern().IsSolidFill:
                return fp.Id
        except Exception:
            continue
    return None


def make_override(rgb, solid, fill_id):
    c = DB.Color(rgb[0], rgb[1], rgb[2])
    ogs = DB.OverrideGraphicSettings()
    ogs.SetProjectionLineColor(c)
    ogs.SetCutLineColor(c)
    if solid and fill_id is not None:
        ogs.SetSurfaceForegroundPatternColor(c)
        ogs.SetSurfaceForegroundPatternId(fill_id)
        ogs.SetSurfaceForegroundPatternVisible(True)
        ogs.SetSurfaceBackgroundPatternColor(c)
        ogs.SetSurfaceBackgroundPatternId(fill_id)
        ogs.SetSurfaceBackgroundPatternVisible(True)
        ogs.SetCutForegroundPatternColor(c)
        ogs.SetCutForegroundPatternId(fill_id)
        ogs.SetCutForegroundPatternVisible(True)
        ogs.SetCutBackgroundPatternColor(c)
        ogs.SetCutBackgroundPatternId(fill_id)
        ogs.SetCutBackgroundPatternVisible(True)
    return ogs


def current_rgb(view, eid):
    try:
        c = view.GetElementOverrides(eid).ProjectionLineColor
        if c is not None and c.IsValid:
            return (int(c.Red), int(c.Green), int(c.Blue))
    except Exception:
        pass
    return None


def reset_recorded(view, recorded):
    """recorded {eid_int: '#RRGGBB'} → รีเซ็ตเฉพาะที่สียังเป็นของเรา
    คืน (รีเซ็ตแล้ว, ข้ามเพราะผู้ใช้เปลี่ยนสีเอง, ไม่พบแล้ว) และ id ที่ควรลืมจากบันทึก"""
    done = skipped = gone = 0
    forget = []
    blank = DB.OverrideGraphicSettings()
    for k, hexc in recorded.items():
        eid = _eid(k)
        if doc.GetElement(eid) is None:
            gone += 1
            forget.append(k)
            continue
        cur = current_rgb(view, eid)
        if cur is None:                 # ไม่มี override แล้ว
            forget.append(k)
            continue
        if cl.should_reset(cur, hexc):
            try:
                view.SetElementOverrides(eid, blank)
                done += 1
                forget.append(k)
            except Exception:
                skipped += 1
        else:
            skipped += 1                # สีถูกเปลี่ยนโดยคนอื่น — ไม่แตะ แต่เลิกจำ
            forget.append(k)
    return done, skipped, gone, forget


def do_reset(state, which):
    if which == "reset_cur":
        recs = cl.applied_for(state, DOC_KEY, id_value(doc.ActiveView.Id))
    else:
        recs = cl.applied_for(state, DOC_KEY)
    if not recs:
        forms.alert(u"ยังไม่มี element ที่เครื่องมือนี้เคยระบายสีไว้ใน{}".format(
            u"view นี้" if which == "reset_cur" else u"โปรเจกต์นี้"), title=u"PK Revit")
        return
    totals = [0, 0, 0]
    with revit.Transaction(u"PK Revit: Reset สี Color by Parameter"):
        for vk, m in recs.items():
            view = doc.GetElement(_eid(vk))
            if view is None:
                cl.forget_applied(state, DOC_KEY, vk)
                continue
            d, sk, g, forget = reset_recorded(view, m)
            totals[0] += d
            totals[1] += sk
            totals[2] += g
            cl.forget_applied(state, DOC_KEY, vk, forget)
    cl.save_state(state)
    msg = u"คืนสีแล้ว {:,} element".format(totals[0])
    lines = []
    if totals[1]:
        lines.append(u"ข้าม {:,} element ที่สีถูกเปลี่ยนไปจากที่เครื่องมือใส่ (ไม่แตะ)".format(totals[1]))
    if totals[2]:
        lines.append(u"{:,} element ถูกลบไปแล้ว".format(totals[2]))
    lines.append(u"Ctrl+Z ย้อนกลับได้")
    ui.summary(u"PK Revit — Color by Parameter", u"✅ " + msg, lines)


def do_apply(state, v):
    solid = v["solid"]
    fill = _solid_fill_id() if solid else None
    notes = []
    if solid and fill is None:
        notes.append(u"ไม่พบ Solid fill pattern ในโปรเจกต์ — ระบายเฉพาะเส้นขอบ")
    applied = {}   # view_id_int -> {eid_int: rgb}
    failed = 0
    cleared = 0
    with revit.Transaction(u"PK Revit: Color by Parameter"):
        for view in v["views"]:
            vk = id_value(view.Id)
            # ล้างสีเดิมของเครื่องมือใน view นี้ก่อน (เฉพาะที่เป็นของเรา) กันสีเก่าค้างบน element ที่ไม่ถูกเลือกรอบนี้
            old = cl.applied_for(state, DOC_KEY, vk).get(u"%s" % vk, {})
            if old:
                d, sk, g, forget = reset_recorded(view, old)
                cleared += d
                cl.forget_applied(state, DOC_KEY, vk, forget)
            for val, per_view in v["groups"].items():
                ids = per_view.get(vk)
                if not ids:
                    continue
                rgb = v["colors"][val]
                ogs = make_override(rgb, solid, fill)
                for k in ids:
                    try:
                        view.SetElementOverrides(_eid(k), ogs)
                        applied.setdefault(vk, {})[k] = rgb
                    except Exception:
                        failed += 1
    for vk, m in applied.items():
        cl.record_applied(state, DOC_KEY, vk, m)
    cl.remember_colors(state, v["key"], v["colors"])
    cl.save_state(state)
    n = sum(len(m) for m in applied.values())
    lines = [u"{} ค่า · {} view".format(len(v["groups"]), len(v["views"]))]
    if failed:
        lines.append(u"ระบายไม่สำเร็จ {:,} element (เช่น view ถูกล็อกด้วย template)".format(failed))
    lines += notes
    lines.append(u"Reset คืนสีเฉพาะ element ที่ระบายไว้ได้ · Ctrl+Z ย้อนทั้งชุด")
    ui.summary(u"PK Revit — Color by Parameter",
               u"✅ ระบายสี {:,} element".format(n), lines)


# ------------------------------------------------------------ main
state = cl.load_state()
sel_ids = set(id_value(i) for i in uidoc.Selection.GetElementIds())
form = ColorForm(state, sel_ids)
res = form.show()
if res:
    try:
        if res["action"] == "apply":
            do_apply(state, res)
        else:
            do_reset(state, res["action"])
    except Exception:
        ui.write_log("ColorByParameter_error.txt", [traceback.format_exc()])
        forms.alert(u"เกิดข้อผิดพลาด:\n" + traceback.format_exc().splitlines()[-1],
                    title=u"PK Revit — Color by Parameter")
