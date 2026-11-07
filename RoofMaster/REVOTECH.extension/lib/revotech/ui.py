# -*- coding: utf-8 -*-
"""UI/ผลลัพธ์ที่ใช้ร่วมกันทุกโมดูล: ฟอร์มธีมมืด-ส้ม, popup สรุป, log, parse ตัวเลข"""

import os
import io
import datetime
from pyrevit import forms

LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                       "REVOTECH")


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
            BorderBrush="#2B2E36" BorderThickness="1" Padding="0">
        <StackPanel>
            <Grid x:Name="title_bar" Background="Transparent" Margin="24,18,16,0">
                <StackPanel>
                    <TextBlock FontSize="20" FontWeight="Bold">
                        <Run Text="{t1}" Foreground="#F2F2F2"/><Run Text="{t2}" Foreground="#FF6B2C"/>
                    </TextBlock>
                    <TextBlock Text="{subtitle}" FontSize="11.5"
                               Foreground="{{StaticResource TxtDim}}" Margin="0,2,0,0"/>
                </StackPanel>
                <Button x:Name="close_btn" Content="&#x2715;" HorizontalAlignment="Right"
                        VerticalAlignment="Top" Width="28" Height="28"
                        Background="Transparent" Foreground="#9A9DA6"
                        BorderThickness="0" FontSize="13" Cursor="Hand"/>
            </Grid>
            <Border Height="1" Background="{{StaticResource Line}}" Margin="24,14,24,0"/>
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
                                <Setter TargetName="bg" Property="Background" Value="#FF8449"/>
                            </Trigger>
                            <Trigger Property="IsPressed" Value="True">
                                <Setter TargetName="bg" Property="Background" Value="#E55A1E"/>
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


class RevoWindow(forms.WPFWindow):
    """หน้าต่างธีมเดียวกับ Roof Master (มืด-ส้ม) — โมดูลส่ง "เนื้อใน" (body.xaml) มา

    ชื่อควบคุมที่ได้เสมอ: title_bar, close_btn, run_btn
    การใช้: คลาสลูก override __init__ แล้วต่อ event ของช่องที่ตัวเองประกาศใน body
    ผู้ใช้กดปุ่มรัน → self.values ถูกตั้งโดยลูก (override collect()) แล้วปิดหน้าต่าง
    """

    def __init__(self, body_path, title_white, title_accent, subtitle,
                 run_text, width=470, max_height=640):
        with io.open(os.path.join(_HERE, "theme.xaml"), encoding="utf-8") as f:
            theme = f.read()
        with io.open(body_path, encoding="utf-8") as f:
            body = f.read()
        xaml = _WINDOW_XAML.format(
            title=title_white + title_accent, width=width, theme=theme,
            body=body, t1=title_white, t2=title_accent, subtitle=subtitle,
            run_text=run_text, maxh=max_height)
        forms.WPFWindow.__init__(self, xaml, literal_string=True)
        self.values = None
        self.run_btn.Click += self._on_run
        self.close_btn.Click += self._on_close
        self.title_bar.MouseLeftButtonDown += self._on_drag

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
    """เขียนรายละเอียดเต็มลงไฟล์ %LOCALAPPDATA%\\REVOTECH\\<name> และคืน path"""
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
                title=u"REVOTECH", exitscript=True)
