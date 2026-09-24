import os

from flask import Flask, jsonify, request, send_from_directory

from app.dirpicker import choose_folder
from app.export import build_meta, export_task, load_master
from app.fields import FIELDS

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def create_app(controller, settings, token: str) -> Flask:
    app = Flask(__name__, static_folder=None)

    @app.before_request
    def check_token():
        # 令牌只保护数据与操作端点；静态资源无秘密，否则页面自己的
        # <script>/<link> 标签不带令牌会全部 401，界面变成空壳
        if not request.path.startswith("/api/"):
            return None
        # fail-closed：任一通道携带了错误令牌即拒绝，不允许错头+对 query 混搭通过
        provided = request.headers.get("X-Token") or request.args.get("t") or ""
        if provided != token:
            return jsonify({"error": "未授权"}), 401

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename):
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/api/state")
    def api_state():
        return jsonify(controller.state())

    @app.get("/api/fields")
    def api_fields():
        return jsonify(FIELDS)

    @app.get("/api/cities")
    def api_cities():
        from app.engine import _engine_module
        eng = _engine_module()
        name_to_code, _ = eng.load_local_city_map()
        hot = [c for c in ("北京", "上海", "广州", "深圳", "杭州",
                           "成都", "武汉", "南京", "西安", "重庆")
               if c in name_to_code]
        return jsonify({"cities": sorted(name_to_code.keys()), "hot": hot})

    @app.route("/api/settings", methods=["GET", "POST"])
    def api_settings():
        if request.method == "GET":
            return jsonify(settings.load())
        return jsonify(settings.save(request.get_json(silent=True) or {}))

    @app.post("/api/choose-dir")
    def api_choose_dir():
        try:
            return jsonify({"path": choose_folder()})
        except Exception:
            return jsonify({"path": None, "error": "选择文件夹窗口打开失败，可直接手动输入路径"})

    @app.post("/api/start")
    def api_start():
        return jsonify(controller.start(request.get_json(silent=True) or {}))

    @app.post("/api/login/start-browser")
    def api_login_browser():
        controller.login_start_browser()
        return jsonify({"ok": True})

    @app.post("/api/login/verify")
    def api_login_verify():
        return jsonify({"ok": controller.login_verify()})

    @app.post("/api/browser/cleanup")
    def api_browser_cleanup():
        controller.cleanup_stale_browser()
        return jsonify({"ok": True})

    @app.post("/api/stop")
    def api_stop():
        controller.stop()
        return jsonify({"ok": True})

    @app.post("/api/export")
    def api_export():
        body = request.get_json(silent=True) or {}
        task_dir_path = body.get("task_dir") or ""
        if not task_dir_path or not os.path.isdir(task_dir_path):
            return jsonify({"error": "任务不存在"}), 404
        st = controller.state()
        master = load_master(task_dir_path)
        export_task(task_dir_path, body.get("fields") or [],
                    build_meta(st.get("task", ""), {}, st.get("rounds", []), master))
        return jsonify({"ok": True})

    return app
