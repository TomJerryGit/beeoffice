"""安全扫描器自测：确保只匹配真实动态执行，不误报 Qt .exec()。"""
import json
from pathlib import Path

from tools.security_scan import iter_python_files, scan_source


def write(tmp_path, rel, text):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_qt_exec_not_flagged(tmp_path):
    p = write(tmp_path, "beeoffice/ui.py", "def f(d):\n    d.exec()\n    d.exec_(1)\n")
    assert scan_source(p) == []


def test_bare_exec_eval_flagged(tmp_path):
    p = write(tmp_path, "beeoffice/bad.py", "exec('x=1')\neval('1+1')\n")
    kinds = [f.kind for f in scan_source(p)]
    assert kinds == ["exec", "eval"]
    assert all(f.severity == "high" for f in scan_source(p))


def test_guarded_eval_marked(tmp_path):
    text = '''
import ast
def safe(expr):
    tree = ast.parse(expr, mode="eval")
    allowed_nodes = (ast.Expression, ast.Constant)
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError
    return eval(compile(tree, "x", "eval"), {"__builtins__": {}}, {})
'''
    p = write(tmp_path, "beeoffice/safe.py", text)
    findings = scan_source(p)
    assert findings[0].kind == "eval" and findings[0].guarded is True


def test_pickle_and_shell_flagged(tmp_path):
    p = write(
        tmp_path,
        "beeoffice/bad.py",
        "import pickle, subprocess\n"
        "pickle.loads(b'x')\n"
        "subprocess.run('x', shell=True)\n",
    )
    kinds = [f.kind for f in scan_source(p)]
    assert "pickle.load" in kinds and "shell=True" in kinds


def test_excluded_dirs_and_json(tmp_path, capsys):
    write(tmp_path, "tests/test_bad.py", "exec('x')\n")
    write(tmp_path, "dist/bad.py", "exec('x')\n")
    write(tmp_path, "release-archive/bad.py", "exec('x')\n")
    write(tmp_path, "beeoffice/ok.py", "def f(d):\n    d.exec()\n")
    files = list(iter_python_files(tmp_path))
    assert [p.name for p in files] == ["ok.py"]

    import tools.security_scan as s
    rc = s.main(["--root", str(tmp_path), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data == []
