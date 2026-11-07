# -*- coding: utf-8 -*-
"""FitPreview3D — Preview3D ที่จัดกล้องให้พอดีกับ "กรอบสี่เหลี่ยมจริง" ของชิ้นงาน

Preview3D เดิมคิดระยะกล้องจากทรงกลมล้อมรอบ (ครึ่งเส้นทแยง) ชิ้นยาวบางอย่างเสา
(400x400x3000) จึงเล็กในกรอบ ที่นี่คำนวณจากการฉายมุมทั้ง 8 ของกล่องล้อมรอบตามมุมกล้องปัจจุบัน
และสัดส่วนกรอบที่เห็นจริง (WPF: FieldOfView คือมุมแนวนอน)

ไม่แก้ preview3d.py — สืบทอดแล้ว override เฉพาะ _fit_distance / update / _tick / เมาส์
"""
import math
from revotech import preview3d as _p
from revotech.preview3d import Preview3D

MARGIN = 1.10       # เผื่อขอบ 10%


def fit_distance(bounds, center, yaw_deg, pitch_deg, aspect, fov_deg, margin=MARGIN):
    """ระยะกล้องจากจุดกึ่งกลาง (center) ที่ทำให้กล่อง bounds=((x0,y0,z0),(x1,y1,z1))
    พอดีกรอบ (perspective, FOV แนวนอน) — ตรรกะล้วน ทดสอบนอก WPF ได้"""
    lo, hi = bounds
    yaw = math.radians(yaw_deg)
    pit = math.radians(pitch_deg)
    cd = (math.cos(pit) * math.sin(yaw), -math.cos(pit) * math.cos(yaw), math.sin(pit))
    f = (-cd[0], -cd[1], -cd[2])
    right = (f[1], -f[0], 0.0)                 # f x (0,0,1)
    n = math.sqrt(right[0] ** 2 + right[1] ** 2) or 1.0
    right = (right[0] / n, right[1] / n, 0.0)
    up = (right[1] * f[2] - right[2] * f[1],   # right x f
          right[2] * f[0] - right[0] * f[2],
          right[0] * f[1] - right[1] * f[0])
    tx = math.tan(math.radians(fov_deg) / 2.0)
    ty = tx / max(aspect, 0.2)
    need = 0.0
    for X in (lo[0], hi[0]):
        for Y in (lo[1], hi[1]):
            for Z in (lo[2], hi[2]):
                v = (X - center[0], Y - center[1], Z - center[2])
                along = v[0] * cd[0] + v[1] * cd[1] + v[2] * cd[2]
                xr = abs(v[0] * right[0] + v[1] * right[1] + v[2] * right[2])
                yu = abs(v[0] * up[0] + v[1] * up[1] + v[2] * up[2])
                need = max(need, along + xr / tx, along + yu / ty)
    return max(need * margin, 1.0)


class FitPreview3D(Preview3D):
    def __init__(self, delay_ms=140, show_legend=True):
        self._touched = False       # ผู้ใช้หมุน/ซูมเองแล้ว → ไม่จัดกรอบทับตอนกรอบเปลี่ยนขนาด
        self._last_fit = None
        Preview3D.__init__(self, delay_ms=delay_ms, show_legend=show_legend)
        self.view.SizeChanged += self._on_size

    # ------------------------------------------------------------ กล้อง
    def _fit_distance(self):
        sc = self.scene
        if sc is None:
            return Preview3D._fit_distance(self)
        c = (self._center.X, self._center.Y, self._center.Z)
        return fit_distance(sc.bounds(), c, self.yaw, self.pitch, self._aspect(),
                            _p.FOV)

    def reset_view(self):
        self._touched = False
        Preview3D.reset_view(self)
        self._last_fit = self.dist

    def update(self, scene, keep_view=True):
        first = self.scene is None
        d_before = self.dist
        Preview3D.update(self, scene, keep_view=keep_view)
        fit = self._fit_distance()
        if first or not keep_view:
            self.dist = fit
        else:
            # ขนาดชิ้นงานเปลี่ยนมากจึงปรับระยะกล้องตาม (คงมุม); เล็กน้อยคงระยะเดิม
            prev = self._last_fit or fit
            ratio = fit / prev if prev else 1.0
            self.dist = d_before * ratio if (ratio > 1.3 or ratio < 0.77) else d_before
            if not (ratio > 1.3 or ratio < 0.77):
                fit = prev
        self._last_fit = fit
        self._apply_camera()

    def _on_size(self, sender, args):
        if self.scene is not None and not self._touched:
            self.dist = self._fit_distance()
            self._last_fit = self.dist
            self._apply_camera()

    # ------------------------------------------------------------ กันเด้งออกจาก Tick
    def _tick(self, sender, args):
        self._timer.Stop()
        fn = self._pending
        self._pending = None
        if fn is None:
            return
        try:
            sc = fn()
            if sc is not None:
                self.update(sc)
        except Exception:
            pass        # คง scene เดิม — ห้ามให้ exception หลุดจาก DispatcherTimer

    # ------------------------------------------------------------ เมาส์
    def _down(self, sender, e):
        Preview3D._down(self, sender, e)
        if self._drag is not None:
            self._touched = True

    def _down_any(self, sender, e):
        Preview3D._down_any(self, sender, e)
        if self._drag is not None:
            self._touched = True

    def _wheel(self, sender, e):
        self._touched = True
        Preview3D._wheel(self, sender, e)
