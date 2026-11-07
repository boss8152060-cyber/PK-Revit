# -*- coding: utf-8 -*-
"""UI/ผลลัพธ์ที่ใช้ร่วมกันทุกโมดูล: ฟอร์มธีมขาว-ดำ (PK), popup สรุป, log, parse ตัวเลข"""

import os
import io
import datetime
import System
from pyrevit import forms, DB

from revotech import presetlogic, presetstore

LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                       "PKRevit")


_HERE = os.path.dirname(os.path.abspath(__file__))

_WINDOW_XAML = u"""<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="{title}" SizeToContent="Height" Width="{width}"
        WindowStartupLocation="CenterScreen" WindowStyle="None"
        AllowsTransparency="True" Background="Transparent"
        ShowInTaskbar="False" FontFamily="Segoe UI">
    <Window.Resources>
{theme}
    </Window.Resources>
    <Border Background="{{StaticResource Card}}" CornerRadius="14"
            BorderBrush="#BDBDBD" BorderThickness="1" Padding="0">
        <StackPanel>
            <Grid x:Name="title_bar" Background="Transparent" Margin="24,18,16,0">
                <StackPanel Orientation="Horizontal">
                    <Border Width="38" Height="38" Background="#FFFFFF" BorderBrush="#111111"
                            BorderThickness="2" CornerRadius="3" Margin="0,0,12,0" VerticalAlignment="Top">
                        <TextBlock Text="PK" FontSize="17" FontWeight="Black" Foreground="#111111"
                                   HorizontalAlignment="Center" VerticalAlignment="Center"/>
                    </Border>
                    <StackPanel>
                        <TextBlock FontSize="20" FontWeight="Bold">
                            <Run Text="{t1}" Foreground="#111111"/><Run Text="{t2}" Foreground="#666666"/>
                        </TextBlock>
                        <TextBlock Text="{subtitle}" FontSize="11.5"
                                   Foreground="{{StaticResource TxtDim}}" Margin="0,2,0,0"/>
                    </StackPanel>
                </StackPanel>
                <Button x:Name="close_btn" Content="&#x2715;" HorizontalAlignment="Right"
                        VerticalAlignment="Top" Width="28" Height="28"
                        Background="Transparent" Foreground="#666666"
                        BorderThickness="0" FontSize="13" Cursor="Hand"/>
            </Grid>
            <Border Height="1" Background="{{StaticResource Line}}" Margin="24,14,24,0"/>
{presetbar}
            <ScrollViewer VerticalScrollBarVisibility="Auto" MaxHeight="{maxh}">
                <StackPanel Margin="24,12,24,0">
{body}
                </StackPanel>
            </ScrollViewer>
            <Button x:Name="run_btn" Margin="24,16,24,22" Height="42"
                    Cursor="Hand" FontSize="14.5" FontWeight="Bold"
                    Foreground="White" BorderThickness="0">
                <Button.Template>
                    <ControlTemplate TargetType="Button">
                        <Border x:Name="bg" Background="{{StaticResource Accent}}"
                                CornerRadius="9">
                            <ContentPresenter HorizontalAlignment="Center"
                                              VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bg" Property="Background" Value="#333333"/>
                            </Trigger>
                            <Trigger Property="IsPressed" Value="True">
                                <Setter TargetName="bg" Property="Background" Value="#000000"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Button.Template>
                <TextBlock Text="{run_text}" Foreground="White"/>
            </Button>
        </StackPanel>
    </Border>
</Window>
"""


_PRESET_BAR = u"""            <StackPanel Margin="24,10,24,0">
                <Grid>
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="Auto"/><ColumnDefinition Width="104"/>
                        <ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/>
                        <ColumnDefinition Width="Auto"/><ColumnDefinition Width="Auto"/>
                    </Grid.ColumnDefinitions>
                    <TextBlock Text="Preset" FontSize="12" FontWeight="SemiBold"
                               VerticalAlignment="Center" Margin="0,0,8,0"/>
                    <ComboBox x:Name="pk_preset_scope" Grid.Column="1" Height="26" Margin="0,0,6,0"/>
                    <ComboBox x:Name="pk_preset_cmb" Grid.Column="2" Height="26" IsEditable="True"
                              ToolTip="เลือก preset ที่มี หรือพิมพ์ชื่อใหม่เพื่อบันทึก"/>
                    <Button x:Name="pk_preset_load" Grid.Column="3" Content="โหลด" Height="26"
                            Padding="9,0" Margin="6,0,0,0" Cursor="Hand"/>
                    <Button x:Name="pk_preset_save" Grid.Column="4" Content="บันทึก" Height="26"
                            Padding="9,0" Margin="4,0,0,0" Cursor="Hand"/>
                    <Button x:Name="pk_preset_del" Grid.Column="5" Content="ลบ" Height="26"
                            Padding="9,0" Margin="4,0,0,0" Cursor="Hand"/>
                </Grid>
                <TextBlock x:Name="pk_preset_msg" FontSize="10.5" TextWrapping="Wrap"
                           Foreground="{StaticResource TxtDim}" Margin="0,4,0,0"
                           Visibility="Collapsed"/>
            </StackPanel>"""

# ฟอร์มที่ไม่ควรมีแถบ Preset (เช่น มีรหัสลิขสิทธิ์ในช่องกรอก)
_NO_PRESET = ("License",)

SCOPE_LOCAL = u"เครื่องนี้ (Local)"
SCOPE_PROJECT = u"โปรเจกต์ (Project)"


def _control_kind(c):
    """ชนิดที่เก็บค่าได้ของ control (None = ไม่เก็บ)"""
    from System.Windows.Controls import TextBox, ComboBox
    from System.Windows.Controls.Primitives import ToggleButton
    if isinstance(c, TextBox):
        return None if c.IsReadOnly else "text"
    if isinstance(c, ComboBox):
        return "combo"
    if isinstance(c, ToggleButton):
        return "check"
    return None


class RevoWindow(forms.WPFWindow):
    """หน้าต่างธีมเดียวกับ Roof Master (ขาว-ดำ (PK)) — โมดูลส่ง "เนื้อใน" (body.xaml) มา

    ชื่อควบคุมที่ได้เสมอ: title_bar, close_btn, run_btn
    การใช้: คลาสลูก override __init__ แล้วต่อ event ของช่องที่ตัวเองประกาศใน body
    ผู้ใช้กดปุ่มรัน → self.values ถูกตั้งโดยลูก (override collect()) แล้วปิดหน้าต่าง
    """

    def __init__(self, body_path, title_white, title_accent, subtitle,
                 run_text, width=470, max_height=640):
        module = os.path.basename(
            os.path.dirname(os.path.abspath(body_path))).replace(".pushbutton", "")
        presetbar = u"" if module in _NO_PRESET else _PRESET_BAR
        with io.open(os.path.join(_HERE, "theme.xaml"), encoding="utf-8") as f:
            theme = f.read()
        with io.open(body_path, encoding="utf-8") as f:
            body = f.read()
        xaml = _WINDOW_XAML.format(
            title=title_white + title_accent, width=width, theme=theme,
            body=body, t1=title_white, t2=title_accent, subtitle=subtitle,
            run_text=run_text, maxh=max_height, presetbar=presetbar)
        forms.WPFWindow.__init__(self, xaml, literal_string=True)
        self.values = None
        self.preset_module = module
        self.run_btn.Click += self._on_run
        self.close_btn.Click += self._on_close
        self.title_bar.MouseLeftButtonDown += self._on_drag
        if presetbar:
            try:
                self._preset_init()
            except Exception:
                pass    # แถบ Preset พังต้องไม่ทำให้ฟอร์มหลักเปิดไม่ได้

    # ------------------------------------------------------------ Preset
    # เก็บ/คืนค่าของ control ที่มี x:Name ทั้งหมด (ยกเว้นชื่อขึ้นต้น pk_) แบบทั่วไป
    # ไม่ต้องแก้ XAML ของโมดูล — ตรรกะล้วนอยู่ใน revotech.presetlogic

    def _preset_init(self):
        self.pk_preset_scope.Items.Add(SCOPE_LOCAL)
        self.pk_preset_scope.Items.Add(SCOPE_PROJECT)
        self.pk_preset_scope.SelectedIndex = 0
        self.pk_preset_scope.SelectionChanged += lambda s, a: self._preset_refresh()
        self.pk_preset_load.Click += self._preset_load
        self.pk_preset_save.Click += self._preset_save
        self.pk_preset_del.Click += self._preset_delete
        self._preset_refresh()

    def _preset_say(self, text):
        self.pk_preset_msg.Text = text
        self.pk_preset_msg.Visibility = (
            System.Windows.Visibility.Visible if text
            else System.Windows.Visibility.Collapsed)

    def _preset_controls(self):
        """control ที่เก็บค่าได้: {ชื่อ: control}"""
        from System.Windows import LogicalTreeHelper
        out = {}

        def walk(obj):
            for ch in LogicalTreeHelper.GetChildren(obj):
                name = getattr(ch, "Name", None)
                if name and not name.startswith("pk_") and \
                        _control_kind(ch) is not None:
                    out[name] = ch
                if hasattr(ch, "Name"):
                    walk(ch)
        walk(self)
        return out

    def _preset_capture(self):
        ctrls = {}
        for name, c in self._preset_controls().items():
            k = _control_kind(c)
            if k == "text":
                v = c.Text
            elif k == "combo":
                v = c.SelectedItem
                if v is None:
                    continue
            else:
                v = bool(c.IsChecked)
            ctrls[name] = {"k": k, "v": v}
        return presetlogic.make_preset(self.preset_module, ctrls)

    def _preset_apply(self, preset):
        """คืนค่า 2 รอบ (combo บางตัวเปลี่ยนรายการของตัวอื่น) แล้วคืนรายการที่ข้าม"""
        skipped = []
        for _pass in (1, 2):
            ctrls = self._preset_controls()
            current = {}
            for name, c in ctrls.items():
                k = _control_kind(c)
                current[name] = {"k": k}
                if k == "combo":
                    current[name]["items"] = list(c.Items)
            actions, skipped = presetlogic.plan_restore(preset["controls"], current)
            for name, k, val in actions:
                try:
                    c = ctrls[name]
                    if k == "combo":
                        c.SelectedIndex = val
                    elif k == "check":
                        c.IsChecked = val
                    else:
                        c.Text = val
                except Exception:
                    skipped.append(u"ตั้งค่าช่อง “{}” ไม่สำเร็จ".format(name))
        return skipped

    def _preset_is_project(self):
        return self.pk_preset_scope.SelectedItem == SCOPE_PROJECT

    def _preset_doc(self):
        from pyrevit import revit
        return revit.doc

    def _preset_refresh(self, select=None):
        cmb = self.pk_preset_cmb
        cmb.Items.Clear()
        try:
            if self._preset_is_project():
                names = presetstore.project_names(
                    presetstore.project_read(self._preset_doc()), self.preset_module)
            else:
                names = presetstore.local_list(self.preset_module)
        except Exception:
            names = []
        for n in names:
            cmb.Items.Add(n)
        cmb.Text = select or u""

    def _preset_name(self):
        return presetlogic.safe_name(self.pk_preset_cmb.Text)

    def _project_write(self, allp):
        doc = self._preset_doc()
        t = DB.Transaction(doc, u"PK Revit - Preset")
        t.Start()
        try:
            presetstore.project_write(doc, allp)
            t.Commit()
        except Exception:
            t.RollBack()
            raise

    def _preset_load(self, sender, args):
        name = self._preset_name()
        if name is None:
            self._preset_say(u"เลือกหรือพิมพ์ชื่อ preset ที่จะโหลดก่อน")
            return
        try:
            if self._preset_is_project():
                preset = presetstore.project_read(self._preset_doc()) \
                    .get(self.preset_module, {}).get(name)
            else:
                preset = presetstore.local_load(self.preset_module, name)
        except Exception:
            preset = None
        if preset is None:
            self._preset_say(u"ไม่พบ preset “{}” ในขอบเขตนี้".format(name))
            return
        skipped = self._preset_apply(preset)
        msg = u"โหลด preset “{}” แล้ว".format(name)
        if skipped:
            msg += u" — " + presetlogic.skipped_text(skipped)
        self._preset_say(msg)

    def _preset_save(self, sender, args):
        name = self._preset_name()
        if name is None:
            self._preset_say(u"พิมพ์ชื่อ preset ก่อนกดบันทึก")
            return
        preset = self._preset_capture()
        try:
            if self._preset_is_project():
                allp = presetstore.project_read(self._preset_doc())
                if name in allp.get(self.preset_module, {}) and not forms.alert(
                        u"มี preset ชื่อ “{}” ในโปรเจกต์นี้แล้ว — เขียนทับ?".format(name),
                        title=u"PK Revit", yes=True, no=True):
                    return
                presetstore.project_put(allp, self.preset_module, name, preset)
                self._project_write(allp)
            else:
                if name in presetstore.local_list(self.preset_module) and \
                        not forms.alert(
                            u"มี preset ชื่อ “{}” ในเครื่องนี้แล้ว — เขียนทับ?".format(name),
                            title=u"PK Revit", yes=True, no=True):
                    return
                presetstore.local_save(self.preset_module, name, preset)
        except Exception as ex:
            self._preset_say(u"บันทึก preset ไม่สำเร็จ: {}".format(ex))
            return
        self._preset_refresh(select=name)
        self._preset_say(u"บันทึก preset “{}” แล้ว".format(name))

    def _preset_delete(self, sender, args):
        name = self._preset_name()
        if name is None:
            self._preset_say(u"เลือก preset ที่จะลบก่อน")
            return
        if not forms.alert(u"ลบ preset “{}” ?".format(name), title=u"PK Revit",
                           yes=True, no=True):
            return
        try:
            if self._preset_is_project():
                allp = presetstore.project_read(self._preset_doc())
                ok = presetstore.project_remove(allp, self.preset_module, name)
                if ok:
                    self._project_write(allp)
            else:
                ok = presetstore.local_delete(self.preset_module, name)
        except Exception as ex:
            self._preset_say(u"ลบ preset ไม่สำเร็จ: {}".format(ex))
            return
        self._preset_refresh()
        self._preset_say(u"ลบ preset “{}” แล้ว".format(name) if ok
                         else u"ไม่พบ preset “{}”".format(name))

    def collect(self):
        """override: คืน dict ค่าจากฟอร์ม (หรือ None ถ้าข้อมูลไม่ครบ)"""
        return {}

    def _on_run(self, sender, args):
        self.values = self.collect()
        if self.values is not None:
            self.Close()

    def _on_close(self, sender, args):
        self.values = None
        self.Close()

    def _on_drag(self, sender, args):
        try:
            self.DragMove()
        except Exception:
            pass

    def show(self):
        """เปิดแบบ modal แล้วคืน dict ค่า (None = ยกเลิก)"""
        self.ShowDialog()
        return self.values


def combo_fill(cmb, items, select=None):
    """เติมรายการให้ ComboBox และเลือก select (ถ้ามีในรายการ) ไม่งั้นตัวแรก"""
    cmb.Items.Clear()
    for it in items:
        cmb.Items.Add(it)
    idx = 0
    if select is not None:
        for i, it in enumerate(items):
            if it == select:
                idx = i
                break
    if items:
        cmb.SelectedIndex = idx


def num(text, default):
    """แปลงข้อความจากช่องกรอกเป็นตัวเลข — ผิดรูปแบบใช้ค่า default"""
    try:
        return float(str(text).strip().replace(",", ""))
    except Exception:
        return float(default)


def intval(text, default):
    try:
        return int(float(str(text).strip()))
    except Exception:
        return int(default)


def write_log(name, lines):
    """เขียนรายละเอียดเต็มลงไฟล์ %LOCALAPPDATA%\\PK Revit\\<name> และคืน path"""
    try:
        if not os.path.isdir(LOG_DIR):
            os.makedirs(LOG_DIR)
        path = os.path.join(LOG_DIR, name)
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(u"# {}\n".format(datetime.datetime.now().isoformat()))
            for ln in lines:
                f.write(ln + u"\n")
        return path
    except Exception:
        return None


def summary(title, head, lines, log_path=None):
    """popup สรุปผลสั้นๆ (ผลละเอียดอยู่ใน log)"""
    body = head + u"\n\n" + u"\n".join(lines)
    if log_path:
        body += u"\n\nรายละเอียด: " + log_path
    forms.alert(body, title=title)


def need_selection(what, hint=u""):
    """แจ้งให้เลือก element ก่อน แล้วจบสคริปต์"""
    forms.alert(u"กรุณาเลือก{}ก่อน {}".format(what, hint).strip(),
                title=u"PK Revit", exitscript=True)
