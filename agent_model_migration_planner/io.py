import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .exceptions import InputDataError


def load_json_object(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputDataError(f"JSON 文件格式错误: {path}: {exc}") from exc
    if not isinstance(data, Mapping):
        raise InputDataError(f"JSON 文件根节点必须是 object: {path}")
    return data


def load_json_or_csv_rows(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    if suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InputDataError(f"JSON 文件格式错误: {path}: {exc}") from exc
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, Mapping)]
        if isinstance(data, Mapping):
            rows = data.get("results", data.get("rows", []))
            if not isinstance(rows, list):
                raise InputDataError(f"JSON rows/results 必须是数组: {path}")
            return [dict(item) for item in rows if isinstance(item, Mapping)]
    raise InputDataError(f"不支持的输入格式: {path}")
