# -*- coding: utf-8 -*-
"""ทดสอบ RevoWindow(preview=True/False) ด้วย WPF จริง โดยจำลอง pyrevit/preset แบบจิ๋ว
(ui.py import pyrevit ซึ่งมีเฉพาะใน Revit) — render เป็น PNG:
  window_plain.png     = preview=False (ต้องหน้าตาเหมือนเดิม)
  window_preview.png   = preview=True + scene เสา 8 เส้น
  window_preview2.png  = หลัง pv.update() ด้วยค่าใหม่ (เสา 12 เส้น สูงขึ้น)"""
import os
import sys
import clr
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
clr.AddReference('WindowsBase')
import System
from System.Windows import Size, Rect
from System.Windows.Markup import XamlReader
from System.Windows.Media.Imaging import RenderTargetBitmap, PngBitmapEncoder, BitmapFrame


class _WPFWindow(object):
    def __init__(self, xaml, literal_string=False):
        self.__dict__["_w"] = XamlReader.Parse(xaml)

    def __getattr__(self, name):
        n = self.__dict__["_w"].FindName(name)
        if n is not None:
            return n
        return getattr(self.__dict__["_w"], name)


def _mod(name, **kw):
    m = type(sys)(name)
    for k, v in kw.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class _Stub(object):
    def __getattr__(self, n):
        return lambda *a, **k: ([] if n in ("local_list", "project_names") else {})


forms = _Stub()
forms.WPFWindow = _WPFWindow
_mod("pyrevit", forms=forms, DB=_Stub())
import revotech
revotech.presetlogic = _mod("revotech.presetlogic", safe_name=lambda t: t or None)
revotech.presetstore = _mod("revotech.presetstore", local_list=lambda m: [],
                            project_names=lambda a, m: [], project_read=lambda d: {})

from revotech import ui, scene3d


def find_body(module):
    for root, dirs, files in os.walk(EXT_ROOT):
        if os.path.basename(root) == module + ".pushbutton" and "body.xaml" in files:
            return os.path.join(root, "body.xaml")
    raise Exception("ไม่พบ body.xaml ของ " + module)


def shot(win, name):
    root = win._w.Content
    root.Measure(Size(2000, 3000))
    root.Arrange(Rect(0, 0, root.DesiredSize.Width, root.DesiredSize.Height))
    root.UpdateLayout()
    w, h = int(root.DesiredSize.Width), int(root.DesiredSize.Height)
    return root, w, h


def save(root, w, h, path):
    rtb = RenderTargetBitmap(w, h, 96.0, 96.0, System.Windows.Media.PixelFormats.Pbgra32)
    rtb.Render(root)
    enc = PngBitmapEncoder()
    enc.Frames.Add(BitmapFrame.Create(rtb))
    fs = System.IO.File.Create(path)
    enc.Save(fs)
    fs.Close()
    print("%s %dx%d" % (path, w, h))


body = find_body("RebarColumn")
args = (body, u"REBAR ", u"เสา", u"ใส่เหล็กยืน + ปลอก ให้เสาที่เลือก — PK Revit", u"สร้างเหล็กเสา")

w0 = ui.RevoWindow(*args)
assert w0.preview is None
r, w, h = shot(w0, "plain")
save(r, w, h, os.path.join(OUT_DIR, "window_plain.png"))

w1 = ui.RevoWindow(*args, preview=True)
assert w1.preview is not None
pv = w1.preview
r, w, h = shot(w1, "preview")
pv.update(scene3d.column_scene(400, 400, 3000, 8, 16.0, 9.0), keep_view=False)
r, w, h = shot(w1, "preview")
pv.reset_view()
r, w, h = shot(w1, "preview")
save(r, w, h, os.path.join(OUT_DIR, "window_preview.png"))

pv.update(scene3d.column_scene(500, 350, 3600, 12, 20.0, 9.0, sp_end=75.0))
r, w, h = shot(w1, "preview")
save(r, w, h, os.path.join(OUT_DIR, "window_preview2.png"))

# debounce: schedule() ต้องไม่วาดทันที (ตัวจับเวลาต้องมี dispatcher วิ่ง จึงตรวจแค่ว่าไม่ error)
pv.schedule(lambda: scene3d.column_scene(400, 400, 3000, 4, 16.0, 9.0))
print("schedule ok; pending scene unchanged:", pv.scene.title)
