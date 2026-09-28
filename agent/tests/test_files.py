import io
import zipfile

from tide_agent.exam_folder import ExamFolder
from tide_agent.inventory import build_inventory

OLD = "\n".join(["#include <stdio.h>", "int main() {", "  int a[100], n, best = 0;", '  scanf("%d", &n);',
                 "  for (int i = 0; i < n; i++) {", '    scanf("%d", &a[i]);', "    if (a[i] > best) best = a[i];",
                 "  }", '  printf("%d\\n", best);', "  return 0;", "}"])


def make_tree(tmp_path):
    old = tmp_path / "D" / "old"
    old.mkdir(parents=True)
    (old / "dsa_lab5.cpp").write_text(OLD)
    (old / "notes.pdf").write_bytes(b"%PDF")
    skipped = tmp_path / "D" / "node_modules"
    skipped.mkdir()
    (skipped / "x.js").write_text("ignored")
    exam = tmp_path / "Exam" / "22BCS107"
    exam.mkdir(parents=True)
    (exam / "main.c").write_text("int main(){}")
    return tmp_path / "D", tmp_path / "Exam"


def test_inventory_indexes_and_skips(tmp_path):
    root, exam = make_tree(tmp_path)
    inv = build_inventory([root, exam], exclude=exam)
    names = sorted(f.name for f in inv.files)
    assert names == ["dsa_lab5.cpp", "notes.pdf"]


def test_match_title_finds_old_file(tmp_path):
    root, exam = make_tree(tmp_path)
    inv = build_inventory([root], exclude=exam)
    assert inv.match_title("dsa_lab5.cpp - old - Visual Studio Code").endswith("dsa_lab5.cpp")
    assert inv.match_title("main.c - 22BCS107 - Visual Studio Code") is None


def test_best_match_survives_renaming(tmp_path):
    root, exam = make_tree(tmp_path)
    inv = build_inventory([root], exclude=exam)
    path, pct = inv.best_match(OLD.replace("best", "mx").replace("a[", "arr["))
    assert path.endswith("dsa_lab5.cpp") and pct >= 80
    assert inv.best_match("print('hello world')\n" * 3) is None


def test_exam_folder_never_overwrites_and_skips_starters(tmp_path):
    """Review focus #1: re-delivery after an agent restart must not wipe the student's work."""
    f = ExamFolder(tmp_path / "Exam" / "22BCS107")
    assert f.write_files([("questions.txt", b"Q1"), ("../evil.c", b"x")]) == 2
    assert (f.root / "evil.c").exists() and not (tmp_path / "Exam" / "evil.c").exists()
    assert f.changed_files() == []                      # starters unchanged -> nothing to send
    (f.root / "evil.c").write_text("int main(){ return 1; }")
    assert f.write_files([("evil.c", b"x")]) == 0      # re-delivery keeps the edit
    changed = f.changed_files()
    assert [c["path"] for c in changed] == ["evil.c"] and "return 1" in changed[0]["text"]
    assert f.changed_files() == []                      # nothing new since last call
    names = zipfile.ZipFile(io.BytesIO(f.zip_bytes())).namelist()
    assert sorted(names) == ["evil.c", "questions.txt"]
