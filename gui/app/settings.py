import copy
import json
import os

DEFAULT_SETTINGS = {
    "keyword": "",
    "city": "",
    "salary": "不限",
    "experience": "不限",
    "degree": "不限",
    "scale": "不限",
    "target_count": 300,
    "max_minutes": 300,
    "fields": [],
    "data_dir": "",
}


def default_data_dir() -> str:
    """默认数据目录 = 系统真实的下载文件夹。

    Windows 允许用户把下载文件夹挪到别的盘，直接拼 ~/Downloads 会拼出
    一个不存在的 C 盘路径，数据落进去用户根本找不到。用
    SHGetKnownFolderPath 问系统要真实位置，问不到再退回 ~/Downloads。
    """
    if os.name == "nt":
        try:
            import ctypes
            guid = (ctypes.c_ubyte * 16)()
            # FOLDERID_Downloads 的 GUID，字符串形式让系统解析，避免手填错误
            if ctypes.windll.ole32.CLSIDFromString(
                    "{374DE290-123F-4565-9164-39C4925E467B}", guid) == 0:
                path_ptr = ctypes.c_void_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.cast(guid, ctypes.c_void_p), 0, None,
                        ctypes.byref(path_ptr)) == 0 and path_ptr.value:
                    out = ctypes.wstring_at(path_ptr)
                    ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                    if out:
                        os.makedirs(out, exist_ok=True)
                        return out
                if path_ptr.value:
                    ctypes.windll.ole32.CoTaskMemFree(path_ptr)
        except Exception:
            pass
    fallback = os.path.join(os.path.expanduser("~"), "Downloads")
    try:
        os.makedirs(fallback, exist_ok=True)
    except OSError:
        pass
    return fallback


def atomic_write_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class SettingsStore:
    def __init__(self, data_dir: str = ""):
        self.set_data_dir(data_dir or default_data_dir())

    def set_data_dir(self, data_dir: str) -> None:
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "settings.json")

    def load(self) -> dict:
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                merged.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        if not merged.get("data_dir"):
            merged["data_dir"] = self.data_dir
        return merged

    def save(self, patch: dict) -> dict:
        merged = self.load()
        merged.update({k: v for k, v in patch.items() if k in DEFAULT_SETTINGS})
        os.makedirs(self.data_dir, exist_ok=True)
        atomic_write_json(self.path, merged)
        return merged
