import ast
import importlib.util
import os
import sys


def collect_imports(root):
    found = set()
    for base, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            try:
                with open(path, encoding="utf-8") as f:
                    tree = ast.parse(f.read())
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    found.add(node.module.split(".")[0])
    return found


def main():
    roots = sys.argv[1:]
    all_modules = set()
    local = set()
    for root in roots:
        all_modules |= collect_imports(root)
        for base, _dirs, files in os.walk(root):
            for name in files:
                if name.endswith(".py"):
                    local.add(name[:-3])
    missing = sorted(
        m for m in all_modules
        if m not in sys.stdlib_module_names
        and m not in local
        and m not in {"app"}
        and importlib.util.find_spec(m) is None)
    if missing:
        print("缺失依赖:", ", ".join(missing))
        return 1
    print("依赖审计通过，共检查", len(all_modules), "个导入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
