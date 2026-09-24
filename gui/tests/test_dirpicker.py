import ctypes
import os
from ctypes import wintypes

import pytest

from app import dirpicker


@pytest.mark.skipif(os.name != "nt", reason="Windows 专属")
def test_pidl_to_path_roundtrip(tmp_path):
    """SHBrowseForFolder 返回的 PIDL 换取完整路径的能力。

    64 位下若不声明指针类型，PIDL 被截断成 32 位，换路径必然失败，
    表现为「选完文件夹路径不变」。这里用 SHParseDisplayName 造一个
    真实 PIDL，验证同一条转换链路可用。
    """
    target = tmp_path / "下载位置"
    target.mkdir()
    shell32 = ctypes.windll.shell32
    pidl = ctypes.c_void_p()
    src = ctypes.c_wchar_p(str(target))
    assert shell32.SHParseDisplayName(src, None, ctypes.byref(pidl),
                                      0, None) == 0
    assert pidl.value

    buf = ctypes.create_unicode_buffer(260)
    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p,
                                             wintypes.LPWSTR]
    shell32.SHGetPathFromIDListW.restype = wintypes.BOOL
    assert shell32.SHGetPathFromIDListW(pidl, buf)
    assert buf.value == str(target)
    ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ctypes.windll.ole32.CoTaskMemFree(pidl)


@pytest.mark.skipif(os.name != "nt", reason="Windows 专属")
def test_choose_folder_module_importable():
    assert callable(dirpicker.choose_folder)
