# -*- coding: utf-8 -*-
"""หน้าต่างเลือกแบบปุ่มใหญ่ (ใช้กับปุ่มรวม Rebar / Roof) — สร้างบน revotech.ui.RevoWindow

body.xaml ของปุ่มรวมต้องมี Button ที่ x:Name ตรงกับ `hub_<key>` ของแต่ละตัวเลือก
กดแล้ว self.choice = key แล้วปิดหน้าต่าง; ปิดด้วย ✕ → choice = None
ซ่อนปุ่มรันและแถบ Preset ของ RevoWindow (ไม่ใช้ในหน้าต่างเลือก)
"""

from revotech import ui


class HubWindow(ui.RevoWindow):
    def __init__(self, body_path, title_white, title_accent, subtitle, keys,
                 info_text=u""):
        ui.RevoWindow.__init__(self, body_path, title_white, title_accent,
                               subtitle, u"", width=440, max_height=560)
        from System.Windows import Visibility
        self.choice = None
        self.run_btn.Visibility = Visibility.Collapsed
        self._hide_preset_bar()
        for key in keys:
            getattr(self, "hub_" + key).Click += self._make_click(key)
        try:
            self.tb_info.Text = info_text
        except Exception:
            pass

    def _make_click(self, key):
        def handler(sender, args):
            self.choice = key
            self.Close()
        return handler

    def _hide_preset_bar(self):
        """แถบ Preset เป็น StackPanel แรกที่ครอบ pk_preset_cmb"""
        try:
            from System.Windows import LogicalTreeHelper, Visibility
            from System.Windows.Controls import StackPanel
            node = self.pk_preset_cmb
            while node is not None:
                node = LogicalTreeHelper.GetParent(node)
                if isinstance(node, StackPanel):
                    node.Visibility = Visibility.Collapsed
                    return
        except Exception:
            pass

    def ask(self):
        """เปิดแบบ modal คืน key ที่เลือก (None = ยกเลิก)"""
        self.ShowDialog()
        return self.choice
