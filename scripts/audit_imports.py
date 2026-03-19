#!/usr/bin/env python3
"""Audit: find all city.* imports that reference non-existent modules."""
import ast
import os
import sys

city_dir = os.path.join(os.path.dirname(__file__), "..", "city")
root = os.path.join(os.path.dirname(__file__), "..")
broken = []

for dirpath, dirs, files in os.walk(city_dir):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fname in files:
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(dirpath, fname)
        try:
            tree = ast.parse(open(fpath).read())
        except SyntaxError:
            broken.append((fpath, 0, "SYNTAX_ERROR"))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("city."):
                mod_path = os.path.join(root, node.module.replace(".", "/") + ".py")
                pkg_path = os.path.join(root, node.module.replace(".", "/"), "__init__.py")
                if not os.path.exists(mod_path) and not os.path.exists(pkg_path):
                    rel = os.path.relpath(fpath, root)
                    broken.append((rel, node.lineno, node.module))

# Also scan tests/
tests_dir = os.path.join(root, "tests")
if os.path.isdir(tests_dir):
    for fname in os.listdir(tests_dir):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(tests_dir, fname)
        try:
            tree = ast.parse(open(fpath).read())
        except SyntaxError:
            broken.append((fpath, 0, "SYNTAX_ERROR"))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("city."):
                mod_path = os.path.join(root, node.module.replace(".", "/") + ".py")
                pkg_path = os.path.join(root, node.module.replace(".", "/"), "__init__.py")
                if not os.path.exists(mod_path) and not os.path.exists(pkg_path):
                    rel = os.path.relpath(fpath, root)
                    broken.append((rel, node.lineno, node.module))

if broken:
    print(f"BROKEN IMPORTS: {len(broken)}")
    for path, line, mod in sorted(set(broken)):
        print(f"  {path}:{line} -> {mod}")
    sys.exit(1)
else:
    print("ALL IMPORTS CLEAN")
