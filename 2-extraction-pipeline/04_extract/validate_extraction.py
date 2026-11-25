#!/usr/bin/env python3
"""Check extraction JSON files against extraction_schema.json (standard library only).

Supports the small subset of JSON Schema that the schema uses: type, required,
properties, items, minItems, enum, pattern and local $ref to #/$defs/.
Usage: python validate_extraction.py extraction_schema.json folder_or_file [...]
License: MIT.
"""
import json
import os
import re
import sys

TYPES = {"object": dict, "array": list, "string": str}


def validate(node, schema, root, path="$"):
    """Return a list of Chinese error messages; an empty list means valid."""
    errs = []
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return validate(node, target, root, path)
    t = schema.get("type")
    if t and not isinstance(node, TYPES[t]):
        return [f"{path}：型別應為 {t}"]
    if "enum" in schema and node not in schema["enum"]:
        errs.append(f"{path}：值 {node!r} 不在允許清單 {schema['enum']}")
    if "pattern" in schema and isinstance(node, str) and not re.search(schema["pattern"], node):
        errs.append(f"{path}：格式不符 {schema['pattern']}")
    if isinstance(node, dict):
        for k in schema.get("required", []):
            if k not in node:
                errs.append(f"{path}：缺少欄位 {k}")
        for k, sub in schema.get("properties", {}).items():
            if k in node:
                errs += validate(node[k], sub, root, f"{path}.{k}")
    if isinstance(node, list):
        if len(node) < schema.get("minItems", 0):
            errs.append(f"{path}：至少要有 {schema['minItems']} 項")
        for i, item in enumerate(node):
            if "items" in schema:
                errs += validate(item, schema["items"], root, f"{path}[{i}]")
    return errs


def main(argv):
    if len(argv) < 3:
        sys.exit("用法：python validate_extraction.py extraction_schema.json 資料夾或檔案 [...]")
    with open(argv[1], encoding="utf-8") as f:
        schema = json.load(f)
    files = []
    for p in argv[2:]:
        if os.path.isdir(p):
            files += [os.path.join(p, x) for x in sorted(os.listdir(p)) if x.endswith(".json")]
        else:
            files.append(p)
    bad = 0
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[壞檔] {fp}：{e}")
            bad += 1
            continue
        errs = validate(doc, schema, schema)
        if errs:
            bad += 1
            print(f"[不合格] {fp}")
            for e in errs:
                print("   -", e)
        else:
            print(f"[合格] {fp}")
    print(f"共 {len(files)} 檔，不合格 {bad} 檔。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
