# -*- coding: utf-8 -*-
"""io.open จิ๋ว (อ่าน/เขียนข้อความ UTF-8 ผ่าน System.IO)"""
import System
from System.IO import File
from System.Text import UTF8Encoding


class _F(object):
    def __init__(self, path, mode):
        self.path, self.mode = path, mode
        self.buf = []
        self.text = File.ReadAllText(path, UTF8Encoding(False)) if "r" in mode else None

    def read(self):
        return self.text

    def write(self, s):
        self.buf.append(s)

    def close(self):
        if "w" in self.mode:
            File.WriteAllText(self.path, u"".join(self.buf), UTF8Encoding(False))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def open(path, mode="r", encoding=None):
    return _F(path, mode)
