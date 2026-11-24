import csv
import hashlib
import io

from fastapi import HTTPException
from pydantic import ValidationError

from src.schemas.calendar import DoorImportInput, DoorRecordInput

HEADERS = {
    '记录编号': 'code', '编号': 'code', 'code': 'code',
    '设施编号': 'facility_code', '设施': 'facility_code', 'facility': 'facility_code',
    'facility_code': 'facility_code',
    '关门时间': 'closed_at', '关闭时间': 'closed_at', 'closed_at': 'closed_at',
    '开门时间': 'reopened_at', '恢复时间': 'reopened_at', 'reopened_at': 'reopened_at',
    '备注': 'note', 'note': 'note',
}
REQUIRED = ('code', 'facility_code')


def _clean(value):
    text = (value or '').strip()
    return text or None


def parse(filename, payload):
    try:
        text = payload.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise HTTPException(422, '门磁记录文件需为 UTF-8 编码的 CSV') from None
    reader = csv.reader(io.StringIO(text))
    try:
        header_row = next(reader)
    except StopIteration:
        raise HTTPException(422, '门磁记录文件是空的') from None
    mapping = {}
    for index, name in enumerate(header_row):
        key = HEADERS.get(name.strip())
        if key and key not in mapping:
            mapping[key] = index
    missing = [name for name in REQUIRED if name not in mapping]
    if missing:
        raise HTTPException(422, f'门磁记录缺少必需列：{"、".join(missing)}')
    if 'closed_at' not in mapping and 'reopened_at' not in mapping:
        raise HTTPException(422, '门磁记录至少要有关门时间或开门时间一列')
    rows = []
    for line, values in enumerate(reader, start=2):
        if not any(value.strip() for value in values):
            continue
        picked = {key: _clean(values[index]) if index < len(values) else None
                  for key, index in mapping.items()}
        if picked.get('note') is None:
            picked.pop('note', None)
        if not picked.get('code') or not picked.get('facility_code'):
            raise HTTPException(422, f'第 {line} 行缺少记录编号或设施编号')
        try:
            rows.append(DoorRecordInput(**picked))
        except ValidationError as error:
            issue = error.errors()[0]
            message = issue.get('ctx', {}).get('error') or issue.get('msg') or '请核对开关门时间'
            raise HTTPException(422, f'第 {line} 行：{message}') from None
    if not rows:
        raise HTTPException(422, '门磁记录文件没有数据行')
    return DoorImportInput(filename=filename, rows=rows)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()
