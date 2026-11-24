from fastapi import HTTPException

from src.models.audit import audit
from src.models.database import connect


def create_facility(payload, user):
    with connect() as db:
        row = db.execute('INSERT INTO facilities (code, name, district) VALUES (%s, %s, %s) RETURNING *',
                         (payload.code, payload.name, payload.district)).fetchone()
        audit(db, user, 'facility.create', payload.code)
        return row


def save_windows(code, payload, user):
    with connect() as db:
        if not db.execute('SELECT 1 FROM facilities WHERE code = %s FOR UPDATE', (code,)).fetchone():
            raise HTTPException(404, '设施不存在')
        added = []
        for day in sorted(payload.weekdays):
            row = db.execute('''INSERT INTO opening_windows (facility_code, weekday, start_min, end_min)
                                VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
                                RETURNING weekday, start_min, end_min''',
                             (code, day, payload.start_min, payload.end_min)).fetchone()
            if row:
                added.append(row)
        if added:
            audit(db, user, 'opening.add', code)
        return {'added': added}


def create_outage(payload, user):
    with connect() as db:
        if not db.execute('SELECT 1 FROM facilities WHERE code = %s', (payload.facility_code,)).fetchone():
            raise HTTPException(404, '设施不存在')
        row = db.execute('''INSERT INTO outages (code, facility_code, reason, starts_at, ends_at, note)
                            VALUES (%(code)s, %(facility_code)s, %(reason)s, %(starts_at)s, %(ends_at)s, %(note)s)
                            RETURNING *''', payload.model_dump(mode='json')).fetchone()
        audit(db, user, 'outage.create', payload.code)
        return row


def _door_values(record):
    return {'code': record.code, 'facility_code': record.facility_code,
            'closed_at': record.closed_at, 'reopened_at': record.reopened_at, 'note': record.note}


def _same(existing, record):
    def stamp(value):
        if value is None:
            return None
        if hasattr(value, 'isoformat'):
            return value.strftime('%Y-%m-%d %H:%M')
        return str(value).replace('T', ' ')[:16]
    return (stamp(existing['closed_at']) == stamp(record.closed_at)
            and stamp(existing['reopened_at']) == stamp(record.reopened_at)
            and existing['note'] == record.note)


def import_door_records(payload, user, checksum):
    with connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('door-import',))
        duplicate = db.execute('SELECT id FROM door_imports WHERE checksum = %s', (checksum,)).fetchone()
        if duplicate:
            raise HTTPException(409, '这批门磁记录已经导入过，未重复写入')
        codes = {record.code for record in payload.rows}
        if len(codes) != len(payload.rows):
            raise HTTPException(422, '同一批门磁记录里出现重复记录编号')
        sites = {row['code'] for row in db.execute('SELECT code FROM facilities').fetchall()}
        unknown = sorted({record.facility_code for record in payload.rows} - sites)
        if unknown:
            raise HTTPException(422, f'设施未登记：{", ".join(unknown)}')
        incomplete = sum(1 for record in payload.rows
                         if record.closed_at is None or record.reopened_at is None)
        batch = db.execute('''INSERT INTO door_imports (filename, checksum, row_count, incomplete_count,
                                                        created_count, imported_by)
                              VALUES (%s, %s, %s, %s, 0, %s) RETURNING id''',
                           (payload.filename, checksum, len(payload.rows), incomplete, user)).fetchone()
        created = updated = 0
        for record in payload.rows:
            existing = db.execute('SELECT id, closed_at, reopened_at, note FROM door_records WHERE code = %s',
                                  (record.code,)).fetchone()
            if existing and _same(existing, record):
                continue
            db.execute('''INSERT INTO door_records (import_id, code, facility_code, closed_at, reopened_at, note)
                          VALUES (%(import_id)s, %(code)s, %(facility_code)s, %(closed_at)s,
                                  %(reopened_at)s, %(note)s)
                          ON CONFLICT (code) DO UPDATE
                          SET import_id = EXCLUDED.import_id, facility_code = EXCLUDED.facility_code,
                              closed_at = EXCLUDED.closed_at, reopened_at = EXCLUDED.reopened_at,
                              note = EXCLUDED.note''',
                       {**_door_values(record), 'import_id': batch['id']})
            if existing:
                updated += 1
            else:
                created += 1
        db.execute('UPDATE door_imports SET created_count = %s, updated_count = %s WHERE id = %s',
                   (created, updated, batch['id']))
        audit(db, user, 'door.import', f'{payload.filename}:{created}+{updated}')
        return {'id': batch['id'], 'row_count': len(payload.rows), 'created': created, 'updated': updated,
                'incomplete': incomplete, 'checksum': checksum}
