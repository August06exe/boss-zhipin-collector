import ctypes
import os
import threading
import time
from ctypes import wintypes


def _force_dialog_topmost(stop_event):
    """看门狗：把本进程新弹出的文件夹选择框提到最前。

    选择框没有属主窗口时默认排在浏览器后面，用户根本看不到。这里
    在对话框创建后的几秒内持续扫描本进程的窗口（对话框类名固定为
    #32770），找到就置顶并拉到前台。
    """
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    # 64 位下不声明参数类型，HWND_TOPMOST(-1) 会被截断成 32 位导致
    # SetWindowPos 静默失败
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    my_pid = kernel32.GetCurrentProcessId()

    enum_proc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    found = []

    def _on_window(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value != "#32770":
            return True
        owner_pid = ctypes.c_uint()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value != my_pid:
            return True
        # HWND_TOPMOST + NOSIZE|NOMOVE|SHOWWINDOW
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
        found.append(hwnd)
        return True

    cb = enum_proc(_on_window)
    # 两个阶段：先在 10 秒内等对话框出现；找到后持续重新置顶直到选择
    # 结束——对话框初始化完成时会自行重设层级，置一次顶会被打回去
    deadline = time.time() + 10
    while time.time() < deadline and not stop_event.is_set() and not found:
        user32.EnumWindows(cb, None)
        time.sleep(0.05)
    if not found:
        return
    user32.SetForegroundWindow(found[0])
    while not stop_event.is_set():
        for hwnd in found:
            if user32.IsWindow(hwnd):
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0,
                                    0x0001 | 0x0002 | 0x0040)
        time.sleep(0.3)


def choose_folder() -> "str | None":
    """Windows 原生文件夹选择框；其他环境或用户取消返回 None。

    弹窗会被看门狗线程提到最前，保证盖在浏览器页面之上。
    """
    if os.name != "nt":
        return None
    from ctypes import wintypes

    try:
        # 对话框需要 COM；工作线程里默认没初始化
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # APARTMENTTHREADED
    except Exception:
        pass

    BIF_RETURNONLYFSDIRS = 0x1
    BIF_NEWDIALOGSTYLE = 0x40

    class BROWSEINFO(ctypes.Structure):
        _fields_ = [("hwndOwner", wintypes.HWND),
                    ("pidlRoot", ctypes.c_void_p),
                    ("pszDisplayName", ctypes.c_wchar_p),
                    ("lpszTitle", ctypes.c_wchar_p),
                    ("ulFlags", ctypes.c_uint),
                    ("lpfn", ctypes.c_void_p),
                    ("lParam", ctypes.c_void_p),
                    ("iImage", ctypes.c_int)]

    # 64 位指针必须声明类型：SHBrowseForFolderW 返回的 PIDL 不声明
    # restype 会被截成 32 位，SHGetPathFromIDListW 拿着残缺指针必然
    # 失败——表现为「选完了路径不变」
    shell32 = ctypes.windll.shell32
    shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFO)]
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p,
                                             wintypes.LPWSTR]
    shell32.SHGetPathFromIDListW.restype = wintypes.BOOL
    ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]

    buf = ctypes.create_unicode_buffer(260)
    bi = BROWSEINFO()
    bi.lpszTitle = "选择数据保存位置（抓到的数据会存在这个文件夹里）"
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE
    bi.pszDisplayName = ctypes.cast(buf, ctypes.c_wchar_p)

    stop = threading.Event()
    watchdog = threading.Thread(target=_force_dialog_topmost, args=(stop,),
                                daemon=True)
    watchdog.start()
    try:
        pidl = ctypes.windll.shell32.SHBrowseForFolderW(ctypes.byref(bi))
    finally:
        stop.set()
    if not pidl:
        return None
    if not ctypes.windll.shell32.SHGetPathFromIDListW(pidl, buf):
        ctypes.windll.ole32.CoTaskMemFree(pidl)
        return None
    ctypes.windll.ole32.CoTaskMemFree(pidl)
    return buf.value
