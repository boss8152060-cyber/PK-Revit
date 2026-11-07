# -*- coding: utf-8 -*-
"""os จิ๋วสำหรับ IronPython เปล่าๆ (ไม่มี stdlib) — เฉพาะที่เดโม/ทดสอบ preview ใช้"""
import nt
import System
from System.IO import Path as _P, Directory as _D, File as _F

environ = dict((str(k), str(v)) for k, v in
               [(e.Key, e.Value) for e in System.Environment.GetEnvironmentVariables()])
sep = "\\"


class _Path(object):
    @staticmethod
    def join(*a):
        r = a[0]
        for p in a[1:]:
            r = _P.Combine(r, p)
        return r

    @staticmethod
    def dirname(p):
        return _P.GetDirectoryName(p) or ""

    @staticmethod
    def basename(p):
        return _P.GetFileName(p)

    @staticmethod
    def abspath(p):
        return _P.GetFullPath(p)

    @staticmethod
    def isdir(p):
        return _D.Exists(p)

    @staticmethod
    def isfile(p):
        return _F.Exists(p)

    @staticmethod
    def exists(p):
        return _D.Exists(p) or _F.Exists(p)

    @staticmethod
    def expanduser(p):
        return p.replace("~", environ.get("USERPROFILE", "~"), 1)


path = _Path()


def makedirs(p):
    _D.CreateDirectory(p)


def listdir(p):
    return [_P.GetFileName(x) for x in _D.GetFileSystemEntries(p)]


def walk(top):
    files = [_P.GetFileName(x) for x in _D.GetFiles(top)]
    dirs = [_P.GetFileName(x) for x in _D.GetDirectories(top)]
    yield top, dirs, files
    for d in dirs:
        for t in walk(_P.Combine(top, d)):
            yield t
