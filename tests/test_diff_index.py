from code_review_app.review.diff import DiffIndex


def test_diff_index_tracks_right_side_added_and_context_lines() -> None:
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,4 +1,5 @@
 import os
+print("new")
 unchanged
-old_call()
+new_call()
 final
"""

    index = DiffIndex.from_unified_diff(diff)

    assert index.has_right_line("app.py", 1)
    assert index.has_right_line("app.py", 2)
    assert index.has_right_line("app.py", 3)
    assert index.has_right_line("app.py", 4)
    assert index.has_right_line("app.py", 5)
    assert not index.has_right_line("app.py", 6)
    assert not index.has_added_line("app.py", 1)
    assert index.has_added_line("app.py", 2)
    assert not index.has_added_line("app.py", 3)
    assert index.has_added_line("app.py", 4)
    assert not index.has_added_line("app.py", 5)
    assert index.right_line_count == 5
    assert index.added_line_count == 2


def test_diff_index_uses_new_path_for_renamed_file() -> None:
    diff = """diff --git a/old.py b/new.py
similarity index 90%
rename from old.py
rename to new.py
--- a/old.py
+++ b/new.py
@@ -10,2 +10,3 @@
 keep()
+added()
 next()
"""

    index = DiffIndex.from_unified_diff(diff)

    assert index.has_right_line("new.py", 10)
    assert index.has_right_line("new.py", 11)
    assert index.has_right_line("new.py", 12)
    assert index.has_added_line("new.py", 11)
    assert not index.has_right_line("old.py", 11)


def test_diff_index_resets_between_files() -> None:
    diff = """diff --git a/one.py b/one.py
--- a/one.py
+++ b/one.py
@@ -1 +1 @@
+first()
diff --git a/two.py b/two.py
--- a/two.py
+++ b/two.py
@@ -5 +5 @@
+second()
"""

    index = DiffIndex.from_unified_diff(diff)

    assert index.has_right_line("one.py", 1)
    assert not index.has_right_line("one.py", 2)
    assert index.has_right_line("two.py", 5)
    assert index.added_line_count == 2
