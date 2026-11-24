import csv
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.config.runtime import ARTIFACT_DIR

COLUMNS = ('month', 'snapshot_id', 'revision', 'formula', 'evidence_policy', 'checksum',
           'code', 'name', 'district', 'evidence_status', 'promised_minutes', 'planned_minutes',
           'lost_minutes', 'available_minutes', 'availability_pct', 'pending_minutes',
           'deferred_minutes', 'both_minutes', 'door_only_minutes', 'outage_only_minutes',
           'undisturbed_minutes', 'door_closed_minutes', 'incomplete_codes')


def export_path(snapshot_id):
    return ARTIFACT_DIR / f'availability-{snapshot_id}.csv'


def safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def _cells(row, context):
    reconciliation = row.get('reconciliation', {})
    return {**reconciliation, **row, **context,
            'evidence_status': row.get('evidence_status') or reconciliation.get('status'),
            'incomplete_codes': ' '.join(row.get('incomplete_codes') or [])}


def write_export(snapshot_id, inputs, checksum, result):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    context = {'month': inputs['month'], 'snapshot_id': snapshot_id,
               'revision': inputs.get('revision', 1), 'formula': result['formula'],
               'evidence_policy': inputs.get('evidence_policy', 'partial'), 'checksum': checksum}
    path = None
    try:
        with NamedTemporaryFile(dir=ARTIFACT_DIR, encoding='utf-8-sig', newline='', mode='w', delete=False) as stream:
            path = Path(stream.name)
            writer = csv.writer(stream)
            writer.writerow(COLUMNS)
            summary = {**result['totals'], **result.get('reconciliation', {}),
                       'code': 'TOTAL', 'name': '全辖区', 'district': '',
                       'evidence_status': '合计', 'incomplete_codes': ''}
            for row in [*result['facilities'], summary]:
                cells = _cells(row, context)
                writer.writerow(safe_cell(cells.get(key)) for key in COLUMNS)
        path.replace(export_path(snapshot_id))
    finally:
        if path is not None:
            path.unlink(missing_ok=True)
