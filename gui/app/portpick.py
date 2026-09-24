import socket


def pick_free_port(start: int = 9222, tries: int = 50) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("9222 起连续 50 个端口都被占用，无法启动界面服务")
