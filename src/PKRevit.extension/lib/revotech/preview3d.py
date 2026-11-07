# -*- coding: utf-8 -*-
"""ตัวสร้างหน้าต่าง 3D preview (WPF Viewport3D) จาก revotech.scene3d.Scene

การใช้ในฟอร์ม:
    pv = Preview3D()
    host_panel.Child = pv.view          # ใส่ลงพื้นที่ preview ของ RevoWindow(preview=True)
    pv.update(scene3d.column_scene(...))              # วาดทันที
    pv.schedule(lambda: scene3d.column_scene(...))    # หน่วงเวลาเล็กน้อย (ใช้กับ TextChanged)

เมาส์: ลากซ้าย = หมุน, ล้อ = ซูม, ลากกลาง = เลื่อน, ดับเบิลคลิก/ปุ่ม "รีเซ็ตมุม" = กลับมุมเริ่มต้น
เหล็กแต่ละกลุ่ม = MeshGeometry3D เดียว (ท่อปริซึมหลายเหลี่ยมเล็ก) จึงลื่นแม้เหล็กหลายร้อยเส้น
"""
import math
import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
import System
from System.Windows import (Thickness, HorizontalAlignment, VerticalAlignment,
                            FontWeights, TextWrapping, Point, Size, Rect)
from System.Windows.Controls import (Grid, Border, Viewport3D, StackPanel, TextBlock,
                                     Button, Orientation)
from System.Windows.Input import MouseButton, MouseButtonState, Mouse
from System.Windows.Media import (Color, SolidColorBrush, Colors, Brushes,
                                  RenderOptions, EdgeMode)
from System.Windows.Media import Media3D as M3
from System.Windows.Media.Media3D import (DiffuseMaterial, EmissiveMaterial,
                                          MaterialGroup)
from System.Windows.Media.Imaging import RenderTargetBitmap, PngBitmapEncoder, BitmapFrame
from System.Windows.Threading import DispatcherTimer

from revotech import scene3d

BG = Color.FromRgb(0xF3, 0xF4, 0xF6)          # พื้นหลังอ่อน
DEFAULT_YAW = -52.0     # องศา รอบแกน z (0 = มองจาก -y)
DEFAULT_PITCH = 24.0    # องศาเหนือแนวนอน
FOV = 38.0
MIN_RADIUS_FRAC = 0.0012    # รัศมีเหล็กขั้นต่ำเทียบเส้นทแยงชิ้นงาน (กันเส้นบางจนมองไม่เห็น)
MAX_SIDES_BARS = 1200       # เหล็กเกินนี้ลดหน้าตัดเหลือ 4 เหลี่ยม


def _color(rgb, a=255):
    return Color.FromArgb(a, rgb[0], rgb[1], rgb[2])


def _mesh(pos, idx):
    m = M3.MeshGeometry3D()
    pts = M3.Point3DCollection()
    for i in range(0, len(pos), 3):
        pts.Add(M3.Point3D(pos[i], pos[i + 1], pos[i + 2]))
    tri = System.Windows.Media.Int32Collection()
    for i in idx:
        tri.Add(i)
    m.Positions = pts
    m.TriangleIndices = tri
    return m


def _model(pos, idx, material, back=None):
    g = M3.GeometryModel3D(_mesh(pos, idx), material)
    if back is not None:
        g.BackMaterial = back
    return g


def _solid_material(rgb, alpha=255, emissive=0.0):
    brush = SolidColorBrush(_color(rgb, alpha))
    brush.Freeze()
    dm = DiffuseMaterial(brush)
    if emissive <= 0:
        return dm
    eb = SolidColorBrush(Color.FromArgb(alpha, int(rgb[0] * emissive),
                                        int(rgb[1] * emissive), int(rgb[2] * emissive)))
    eb.Freeze()
    mg = MaterialGroup()
    mg.Children.Add(dm)
    mg.Children.Add(EmissiveMaterial(eb))
    return mg


def build_model_group(scene, min_radius=None):
    """Scene -> Model3DGroup (เหล็กก่อน แล้ว host โปร่งทีหลังเพื่อให้เห็นเหล็กทะลุ host)"""
    (x0, y0, z0), (x1, y1, z1) = scene.bounds()
    diag = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2) or 1.0
    rmin = diag * MIN_RADIUS_FRAC if min_radius is None else min_radius
    sides = 4 if scene.bar_count() > MAX_SIDES_BARS else 6
    grp = M3.Model3DGroup()
    for g in scene.groups:
        if not g.polys:
            continue
        pos, idx = scene3d.tube_mesh(g.polys, max(g.radius, rmin), sides)
        grp.Children.Add(_model(pos, idx, _solid_material(g.color, 255, 0.25)))
    for h in scene.hosts:
        a = int(255 * h.alpha)
        pos, idx = scene3d.host_mesh(h)
        grp.Children.Add(_model(pos, idx, _solid_material(h.color, a),
                                _solid_material(h.color, a)))
        epos, eidx = scene3d.tube_mesh(scene3d.host_edges(h), rmin * 0.7, 4)
        grp.Children.Add(_model(epos, eidx, _solid_material((70, 74, 84), 255, 0.3)))
    return grp


class Preview3D(object):
    """หน้าต่าง preview ที่ใช้ซ้ำ: .view คือ UIElement (Border) ที่เอาไปใส่ฟอร์มได้"""

    def __init__(self, delay_ms=140, show_legend=True):
        self.scene = None
        self._pending = None
        self._center = M3.Point3D(0, 0, 0)
        self._radius = 1000.0
        self.yaw = DEFAULT_YAW
        self.pitch = DEFAULT_PITCH
        self.dist = 3000.0
        self.pan = M3.Vector3D(0, 0, 0)
        self._drag = None
        self._last = None
        self.show_legend = show_legend

        self.viewport = Viewport3D()
        self.viewport.ClipToBounds = True
        self.cam = M3.PerspectiveCamera()
        self.cam.FieldOfView = FOV
        self.cam.UpDirection = M3.Vector3D(0, 0, 1)
        self.cam.NearPlaneDistance = 1.0
        self.cam.FarPlaneDistance = 1.0e8
        self.viewport.Camera = self.cam
        self._content = M3.ModelVisual3D()
        self.viewport.Children.Add(self._content)
        self._model_holder = None
        lights = M3.Model3DGroup()
        lights.Children.Add(M3.AmbientLight(Color.FromRgb(110, 110, 115)))
        lights.Children.Add(M3.DirectionalLight(Color.FromRgb(200, 200, 205),
                                                M3.Vector3D(-0.5, 0.8, -1.0)))
        lights.Children.Add(M3.DirectionalLight(Color.FromRgb(120, 125, 140),
                                                M3.Vector3D(0.8, -0.4, -0.3)))
        lv = M3.ModelVisual3D()
        lv.Content = lights
        self.viewport.Children.Add(lv)

        # ซ้อน overlay: ชื่อ/คำอธิบายสี/คำแนะนำ/ปุ่มรีเซ็ต
        self.title_tb = TextBlock()
        self.title_tb.FontSize = 13
        self.title_tb.FontWeight = FontWeights.Bold
        self.title_tb.Foreground = SolidColorBrush(Color.FromRgb(0x11, 0x11, 0x11))
        self.title_tb.Margin = Thickness(12, 8, 0, 0)
        self.title_tb.HorizontalAlignment = HorizontalAlignment.Left
        self.title_tb.VerticalAlignment = VerticalAlignment.Top
        self.title_tb.IsHitTestVisible = False

        self.legend = StackPanel()
        self.legend.IsHitTestVisible = False
        self.legend_box = Border()
        self.legend_box.Child = self.legend
        self.legend_box.Background = SolidColorBrush(Color.FromArgb(205, 255, 255, 255))
        self.legend_box.CornerRadius = System.Windows.CornerRadius(5)
        self.legend_box.Padding = Thickness(7, 4, 9, 4)
        self.legend_box.Margin = Thickness(10, 0, 0, 28)
        self.legend_box.HorizontalAlignment = HorizontalAlignment.Left
        self.legend_box.VerticalAlignment = VerticalAlignment.Bottom
        self.legend_box.IsHitTestVisible = False

        self.note_tb = TextBlock()
        self.note_tb.FontSize = 10.5
        self.note_tb.TextWrapping = TextWrapping.Wrap
        self.note_tb.Foreground = SolidColorBrush(Color.FromRgb(0xC0, 0x30, 0x20))
        self.note_tb.Margin = Thickness(12, 28, 12, 0)
        self.note_tb.VerticalAlignment = VerticalAlignment.Top
        self.note_tb.IsHitTestVisible = False

        hint = TextBlock()
        hint.Text = u"ลาก = หมุน · ล้อ = ซูม · ลากกลาง = เลื่อน · ดับเบิลคลิก = รีเซ็ต"
        hint.FontSize = 10
        hint.Foreground = SolidColorBrush(Color.FromRgb(0x77, 0x77, 0x77))
        hint.Margin = Thickness(12, 0, 0, 8)
        hint.HorizontalAlignment = HorizontalAlignment.Left
        hint.VerticalAlignment = VerticalAlignment.Bottom
        hint.IsHitTestVisible = False

        self.reset_btn = Button()
        self.reset_btn.Content = u"รีเซ็ตมุม"
        self.reset_btn.FontSize = 10.5
        self.reset_btn.Padding = Thickness(8, 2, 8, 2)
        self.reset_btn.Margin = Thickness(0, 8, 10, 0)
        self.reset_btn.HorizontalAlignment = HorizontalAlignment.Right
        self.reset_btn.VerticalAlignment = VerticalAlignment.Top
        self.reset_btn.Cursor = System.Windows.Input.Cursors.Hand
        self.reset_btn.Click += lambda s, a: self.reset_view()

        grid = Grid()
        grid.Children.Add(self.viewport)
        grid.Children.Add(self.note_tb)
        grid.Children.Add(self.title_tb)
        grid.Children.Add(self.legend_box)
        grid.Children.Add(hint)
        grid.Children.Add(self.reset_btn)
        self.view = Border()
        self.view.Background = SolidColorBrush(BG)    # ต้องมีพื้นหลังจึงรับเมาส์
        self.view.ClipToBounds = True
        self.view.Child = grid
        RenderOptions.SetEdgeMode(self.viewport, EdgeMode.Unspecified)

        self.view.MouseLeftButtonDown += self._down
        self.view.MouseDown += self._down_any
        self.view.MouseUp += self._up
        self.view.MouseMove += self._move
        self.view.MouseWheel += self._wheel
        self.view.SizeChanged += lambda s, a: self._apply_camera()

        self._timer = DispatcherTimer()
        self._timer.Interval = System.TimeSpan.FromMilliseconds(delay_ms)
        self._timer.Tick += self._tick
        self._apply_camera()

    # ------------------------------------------------------------ API
    def update(self, scene, keep_view=True):
        """วาด scene ทันที; keep_view=False จะจัดกล้องใหม่ให้เห็นทั้งชิ้น"""
        self._timer.Stop()
        self._pending = None
        first = self.scene is None
        self.scene = scene
        self._content.Content = build_model_group(scene)
        lo, hi = scene.bounds()
        self._center = M3.Point3D((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0,
                                  (lo[2] + hi[2]) / 2.0)
        old_r = self._radius
        self._radius = max(0.5 * math.sqrt((hi[0] - lo[0]) ** 2 + (hi[1] - lo[1]) ** 2 +
                                           (hi[2] - lo[2]) ** 2), 1.0)
        if not first and keep_view:
            ratio = self._radius / old_r
            if ratio > 1.3 or ratio < 0.77:     # ขนาดชิ้นงานเปลี่ยนมาก → ปรับระยะกล้องตาม (คงมุม)
                self.dist *= ratio
        if first or not keep_view:
            self.reset_view()
        else:
            self._apply_camera()
        self._refresh_overlay(scene)

    def schedule(self, build_fn):
        """หน่วงเวลา: เรียก build_fn() (คืน Scene) หลังไม่มีการเรียกซ้ำภายใน delay_ms
        ใช้กับ TextChanged ของช่องกรอก — ถ้า build_fn โยน exception จะข้ามเงียบๆ (คง scene เดิม)"""
        self._pending = build_fn
        self._timer.Stop()
        self._timer.Start()

    def reset_view(self):
        self.yaw = DEFAULT_YAW
        self.pitch = DEFAULT_PITCH
        self.pan = M3.Vector3D(0, 0, 0)
        self.dist = self._fit_distance()
        self._apply_camera()

    def clear(self):
        self.scene = None
        self._content.Content = None
        self.legend.Children.Clear()
        self.title_tb.Text = u""
        self.note_tb.Text = u""

    # ------------------------------------------------------------ ภายใน
    def _tick(self, sender, args):
        self._timer.Stop()
        fn = self._pending
        self._pending = None
        if fn is None:
            return
        try:
            sc = fn()
        except Exception:
            return
        if sc is not None:
            self.update(sc)

    def _aspect(self):
        w = self.view.ActualWidth
        h = self.view.ActualHeight
        return (w / h) if (w > 1 and h > 1) else 1.0

    def _fit_distance(self):
        # แนวตั้งใช้ FOV ตรง; ถ้ากรอบแคบ (aspect<1) ต้องถอยเพิ่มตามแนวนอน
        half = math.radians(FOV) / 2.0
        d = self._radius / math.sin(half) * 1.2
        a = self._aspect()
        if a < 1.0:
            d /= max(a, 0.4)
        return d

    def _apply_camera(self):
        yaw = math.radians(self.yaw)
        pit = math.radians(self.pitch)
        cx = self._center.X + self.pan.X
        cy = self._center.Y + self.pan.Y
        cz = self._center.Z + self.pan.Z
        px = cx + self.dist * math.cos(pit) * math.sin(yaw)
        py = cy - self.dist * math.cos(pit) * math.cos(yaw)
        pz = cz + self.dist * math.sin(pit)
        self.cam.Position = M3.Point3D(px, py, pz)
        self.cam.LookDirection = M3.Vector3D(cx - px, cy - py, cz - pz)

    def _refresh_overlay(self, scene):
        self.title_tb.Text = scene.title
        self.note_tb.Text = u"\n".join(u"⚠ " + n for n in scene.notes[:3])
        self.legend.Children.Clear()
        self.legend_box.Visibility = (System.Windows.Visibility.Visible
                                      if self.show_legend and scene.legend()
                                      else System.Windows.Visibility.Collapsed)
        if not self.show_legend:
            return
        for (label, rgb, n) in scene.legend():
            row = StackPanel()
            row.Orientation = Orientation.Horizontal
            sw = Border()
            sw.Width = 12
            sw.Height = 12
            sw.CornerRadius = System.Windows.CornerRadius(2)
            sw.Background = SolidColorBrush(_color(rgb))
            sw.Margin = Thickness(0, 0, 6, 0)
            tb = TextBlock()
            tb.Text = u"{} ({})".format(label, n)
            tb.FontSize = 10.5
            tb.Foreground = SolidColorBrush(Color.FromRgb(0x33, 0x33, 0x33))
            row.Children.Add(sw)
            row.Children.Add(tb)
            row.Margin = Thickness(0, 1, 0, 1)
            self.legend.Children.Add(row)

    # ------------------------------------------------------------ เมาส์
    def _down(self, sender, e):
        if e.ClickCount >= 2:
            self.reset_view()
            return
        self._drag = "rotate"
        self._last = e.GetPosition(self.view)
        self.view.CaptureMouse()

    def _down_any(self, sender, e):
        if e.ChangedButton == MouseButton.Middle:
            self._drag = "pan"
            self._last = e.GetPosition(self.view)
            self.view.CaptureMouse()

    def _up(self, sender, e):
        self._drag = None
        self.view.ReleaseMouseCapture()

    def _move(self, sender, e):
        if self._drag is None:
            return
        p = e.GetPosition(self.view)
        dx = p.X - self._last.X
        dy = p.Y - self._last.Y
        self._last = p
        if self._drag == "rotate":
            self.yaw -= dx * 0.4
            self.pitch = max(-89.0, min(89.0, self.pitch + dy * 0.4))
        else:
            h = max(self.view.ActualHeight, 1.0)
            k = 2.0 * self.dist * math.tan(math.radians(FOV) / 2.0) / h
            yaw = math.radians(self.yaw)
            pit = math.radians(self.pitch)
            right = (math.cos(yaw), math.sin(yaw), 0.0)
            up = (-math.sin(pit) * math.sin(yaw), math.sin(pit) * math.cos(yaw),
                  math.cos(pit))
            self.pan = M3.Vector3D(self.pan.X + (-dx * right[0] + dy * up[0]) * k,
                                   self.pan.Y + (-dx * right[1] + dy * up[1]) * k,
                                   self.pan.Z + dy * up[2] * k)
        self._apply_camera()

    def _wheel(self, sender, e):
        f = 0.88 if e.Delta > 0 else 1.0 / 0.88
        self.dist = max(self._radius * 0.15, min(self.dist * f, self._radius * 40.0))
        self._apply_camera()


def render_png(preview, path, width=460, height=420, dpi=96.0):
    """วาด preview.view ลงไฟล์ PNG (ใช้ในเดโม/ทดสอบ ไม่ต้องแสดงหน้าต่าง)"""
    v = preview.view
    v.Measure(Size(width, height))
    v.Arrange(Rect(0, 0, width, height))
    v.UpdateLayout()
    preview.reset_view()
    v.UpdateLayout()
    rtb = RenderTargetBitmap(int(width), int(height), dpi, dpi,
                             System.Windows.Media.PixelFormats.Pbgra32)
    rtb.Render(v)
    enc = PngBitmapEncoder()
    enc.Frames.Add(BitmapFrame.Create(rtb))
    fs = System.IO.File.Create(path)
    try:
        enc.Save(fs)
    finally:
        fs.Close()
