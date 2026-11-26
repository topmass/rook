#!/usr/bin/env python3
"""Static AST import-boundary check for Rook modules (no Rook imports).

Reads module classes and today's explicit exceptions from scripts/module_boundaries.json.
Fails if:
  - any tracked .py module is unclassified;
  - any core module imports an extension, presence, phone, or platform-specific module at import time
    without an explicit entry in known_exceptions (the strict import-time rule);
  - any core module imports one lazily inside a function without an explicit entry in lazy_exceptions; or
  - any import-time or lazy exception is stale (remove it so the exception lists only shrink).
"""
import argparse
import ast
import json
from pathlib import Path
import sys

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = Path(__file__).resolve().with_name("module_boundaries.json")
FORBIDDEN_CLASSES = frozenset({"extension", "presence", "phone", "platform"})


def _is_main_guard(node):
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    if len(test.comparators) != 1:
        return False
    left, right = test.left, test.comparators[0]
    pair = (left, right)
    for a, b in (pair, pair[::-1]):
        if isinstance(a, ast.Name) and a.id == "__name__" and isinstance(b, ast.Constant) and b.value == "__main__":
            return True
    return False


def _top_level_imports(tree):
    """Return [(lineno, module_name)] imported at module import time (excluding def/class and __main__ guards)."""
    found = []

    def walk(stmts):
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if _is_main_guard(stmt):
                continue
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    found.append((stmt.lineno, alias.name))
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.module:
                    found.append((stmt.lineno, stmt.module))
                elif stmt.level:
                    for alias in stmt.names:
                        found.append((stmt.lineno, "." * stmt.level + alias.name))
            elif isinstance(stmt, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                for attr in ("body", "orelse", "finalbody"):
                    sub = getattr(stmt, attr, None)
                    if isinstance(sub, list):
                        walk(sub)
                for handler in getattr(stmt, "handlers", ()) or ():
                    walk(handler.body)
            elif hasattr(ast, "TryStar") and isinstance(stmt, ast.TryStar):
                walk(stmt.body)
                walk(stmt.orelse)
                walk(stmt.finalbody)
                for handler in stmt.handlers:
                    walk(handler.body)

    walk(tree.body)
    return found


def _lazy_imports(tree):
    """Return [(lineno, qualname, module_name)] imported inside functions or methods."""
    found = []

    def scan_body(node, scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope = scope + (node.name,)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, ".".join(scope), alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append((node.lineno, ".".join(scope), node.module))
            elif node.level:
                for alias in node.names:
                    found.append((node.lineno, ".".join(scope), "." * node.level + alias.name))
        for child in ast.iter_child_nodes(node):
            scan_body(child, scope)

    def walk_top(stmts, scope):
        for stmt in stmts:
            if isinstance(stmt, ast.ClassDef):
                walk_top(stmt.body, scope + (stmt.name,))
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_scope = scope + (stmt.name,)
                for child in stmt.body:
                    scan_body(child, fn_scope)
            elif not _is_main_guard(stmt):
                for attr in ("body", "orelse", "finalbody"):
                    sub = getattr(stmt, attr, None)
                    if isinstance(sub, list):
                        walk_top(sub, scope)
                for handler in getattr(stmt, "handlers", ()) or ():
                    walk_top(handler.body, scope)

    walk_top(tree.body, ())
    return found


def _build_resolvers(classified):
    by_dotted = {}
    by_dir_stem = {}
    stem_counts = {}
    for rel in classified:
        p = Path(rel)
        by_dotted[rel[:-3].replace("/", ".")] = rel
        by_dir_stem.setdefault((p.parent.as_posix(), p.stem), rel)
        stem_counts.setdefault(p.stem, []).append(rel)
    by_unique_stem = {stem: rels[0] for stem, rels in stem_counts.items() if len(rels) == 1}
    return by_dotted, by_dir_stem, by_unique_stem


def _resolve_import(importer_rel, mod_name, by_dotted, by_dir_stem, by_unique_stem,
                    module_class, platform_specific):
    root_pkg = mod_name.split(".")[0]
    if root_pkg in platform_specific:
        return root_pkg, "platform-specific"
    if mod_name in by_dotted:
        return by_dotted[mod_name], None
    # Sibling import (e.g. `import watch` from `desktop/rook.py` -> `desktop/watch.py`).
    importer_dir = Path(importer_rel).parent.as_posix()
    if (importer_dir, root_pkg) in by_dir_stem:
        return by_dir_stem[(importer_dir, root_pkg)], None
    if ("desktop", root_pkg) in by_dir_stem:
        return by_dir_stem[("desktop", root_pkg)], None
    if root_pkg in by_unique_stem and module_class.get(by_unique_stem[root_pkg]) in FORBIDDEN_CLASSES:
        return by_unique_stem[root_pkg], None
    return None, None


def check_boundaries(root, config_path):
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    tracked_dirs = cfg["tracked_dirs"]
    classes = cfg["classes"]
    seam = set(cfg.get("platform_seam", ()))
    platform_specific = set(cfg.get("platform_specific_imports", ()))

    module_class = {}
    errors = []
    for cls_name, files in classes.items():
        for rel in files:
            if rel in module_class:
                errors.append(f"duplicate classification for {rel}: {module_class[rel]} and {cls_name}")
            module_class[rel] = cls_name

    # Verify every tracked .py file on disk is classified.
    on_disk = set()
    for d in tracked_dirs:
        base = Path(root) / d
        if base.is_dir():
            for py in sorted(base.rglob("*.py")):
                if "__pycache__" in py.parts:
                    continue
                on_disk.add(py.relative_to(root).as_posix())

    unclassified = sorted(on_disk - set(module_class))
    for rel in unclassified:
        errors.append(f"unclassified module: {rel} (add it to {Path(config_path).name})")

    # A whole folder may be left out, as the public snapshot leaves out wow/ and stage/. One missing file is an error.
    missing_files = sorted(rel for rel in set(module_class) - on_disk if (Path(root) / rel.split("/")[0]).is_dir())
    for rel in missing_files:
        errors.append(f"classified module not found on disk: {rel}")

    exceptions = {}
    for entry in cfg.get("known_exceptions", ()):
        if not entry.get("reason", "").strip():
            errors.append(f"exception missing reason: {entry}")
        key = (entry["from"], entry["to"])
        if key in exceptions:
            errors.append(f"duplicate exception: {key[0]} -> {key[1]}")
        exceptions[key] = entry

    lazy_exceptions = {}
    for entry in cfg.get("lazy_exceptions", ()):
        if not entry.get("reason", "").strip():
            errors.append(f"lazy exception missing reason: {entry}")
        key = (entry["from"], entry["function"], entry["to"])
        if key in lazy_exceptions:
            errors.append(f"duplicate lazy exception: {key[0]} ({key[1]}) -> {key[2]}")
        lazy_exceptions[key] = entry

    by_dotted, by_dir_stem, by_unique_stem = _build_resolvers(module_class)
    seen_exceptions = set()
    seen_lazy = set()

    def _classify_target(importer_rel, mod_name):
        target, special_kind = _resolve_import(
            importer_rel, mod_name, by_dotted, by_dir_stem, by_unique_stem, module_class, platform_specific
        )
        if target is None:
            return None, None
        if special_kind is not None:
            return target, special_kind
        target_cls = module_class.get(target)
        if target_cls not in FORBIDDEN_CLASSES or target in seam:
            return None, None
        return target, target_cls

    for rel in sorted(classes.get("core", ())):
        path = Path(root) / rel
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for lineno, mod_name in _top_level_imports(tree):
            target, kind = _classify_target(rel, mod_name)
            if target is None:
                continue
            key = (rel, target)
            if key in exceptions:
                seen_exceptions.add(key)
            else:
                errors.append(f"forbidden import-time crossing: {rel}:{lineno} (core) imports {target} ({kind})")

        for lineno, qualname, mod_name in _lazy_imports(tree):
            target, kind = _classify_target(rel, mod_name)
            if target is None:
                continue
            key = (rel, qualname, target)
            if key in lazy_exceptions:
                seen_lazy.add(key)
            else:
                errors.append(
                    f"forbidden lazy crossing: {rel}:{lineno} ({qualname}) imports {target} ({kind})"
                )

    for src, dst in sorted(set(exceptions) - seen_exceptions):
        errors.append(f"stale exception (crossing removed; delete from {Path(config_path).name}): {src} -> {dst}")
    for src, fn, dst in sorted(set(lazy_exceptions) - seen_lazy):
        errors.append(
            f"stale lazy exception (crossing removed; delete from {Path(config_path).name}): {src} ({fn}) -> {dst}"
        )

    return errors, len(on_disk), len(seen_exceptions), len(seen_lazy)


def main():
    parser = argparse.ArgumentParser(description="Check static module import boundaries.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Repository root to inspect.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Boundary JSON config file.")
    args = parser.parse_args()
    errors, total, exc_count, lazy_count = check_boundaries(args.root, args.config)
    if errors:
        for err in errors:
            print(f"boundary check FAILED: {err}", file=sys.stderr)
        return 1
    print(
        f"Import boundaries: {total} modules checked, {exc_count} import-time exceptions, "
        f"{lazy_count} lazy exceptions, 0 new crossings."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
