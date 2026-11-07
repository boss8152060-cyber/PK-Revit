# -*- coding: utf-8 -*-
"""หน่วย: Revit เก็บความยาวเป็นฟุต — ใช้ฟังก์ชันนี้ทุกครั้งที่ข้ามหน่วย"""

FT_PER_MM = 1.0 / 304.8


def mm_to_ft(v):
    return float(v) * FT_PER_MM


def ft_to_mm(v):
    return float(v) * 304.8


def m_to_ft(v):
    return mm_to_ft(float(v) * 1000.0)


def ft_to_m(v):
    return ft_to_mm(v) / 1000.0
