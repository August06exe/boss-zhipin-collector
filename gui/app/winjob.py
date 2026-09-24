import os

_job_handle = None


def _create_job():
    import ctypes

    k32 = ctypes.windll.kernel32
    job = k32.CreateJobObjectW(None, None)

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [("ReadOperationCount", ctypes.c_uint64),
                    ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64),
                    ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64),
                    ("OtherTransferCount", ctypes.c_uint64)]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", ctypes.c_uint32),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", ctypes.c_uint32),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", ctypes.c_uint32),
                    ("SchedulingClass", ctypes.c_uint32)]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("BasicLimitInformation",
                     JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = k32.SetInformationJobObject(
        job, 9,  # JobObjectExtendedLimitInformation
        ctypes.byref(info), ctypes.sizeof(info))
    if not ok:
        k32.CloseHandle(job)
        return None, False
    return k32, job


def assign_child(pid: int):
    """子进程加入 Job；本进程退出时句柄关闭，KILL_ON_JOB_CLOSE 兜底回收子进程。"""
    global _job_handle
    if os.name != "nt":
        return None
    import ctypes
    if _job_handle is None:
        k32, job = _create_job()
        if job is None:
            return None
        _job_handle = job
    else:
        k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
    if not h:
        return None
    try:
        if not k32.AssignProcessToJobObject(_job_handle, h):
            return None
    finally:
        k32.CloseHandle(h)
    return _job_handle


def terminate_children() -> None:
    global _job_handle
    if os.name != "nt" or _job_handle is None:
        return
    import ctypes
    ctypes.windll.kernel32.TerminateJobObject(_job_handle, 1)
