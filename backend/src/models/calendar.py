from datetime import timedelta

from src.utils.calendar import month_bounds


def facilities(db):
    sites = db.execute('SELECT * FROM facilities ORDER BY code').fetchall()
    indexed = {site['code']: dict(site, windows=[]) for site in sites}
    windows = db.execute('''SELECT facility_code, weekday, start_min, end_min FROM opening_windows
                            ORDER BY facility_code, weekday, start_min, end_min''')
    for window in windows:
        indexed[window.pop('facility_code')]['windows'].append(window)
    return list(indexed.values())


def outages(db, period=None):
    query = 'SELECT * FROM outages'
    params = ()
    if period:
        query += ' WHERE starts_at < %s AND ends_at > %s'
        params = (period[1], period[0])
    return db.execute(query + ' ORDER BY starts_at DESC, code', params).fetchall()


def door_records(db, period=None):
    """Complete records overlapping the period, plus one-sided records whose single
    stamp is at most one day before it (their undecided span can reach inside)."""
    query = 'SELECT * FROM door_records'
    params = ()
    if period:
        start, end = period
        query += (' WHERE (closed_at IS NOT NULL AND reopened_at IS NOT NULL'
                  '        AND closed_at < %s AND reopened_at > %s)'
                  '    OR (closed_at IS NOT NULL AND reopened_at IS NULL'
                  '        AND closed_at >= %s AND closed_at < %s)'
                  '    OR (closed_at IS NULL AND reopened_at IS NOT NULL'
                  '        AND reopened_at >= %s AND reopened_at < %s)')
        params = (end, start, start - timedelta(days=1), end, start - timedelta(days=1), end)
    return db.execute(query + ' ORDER BY closed_at NULLS LAST, reopened_at NULLS LAST, code',
                      params).fetchall()


def door_imports(db, limit=20):
    return db.execute('''SELECT id, filename, checksum, row_count, incomplete_count,
                                imported_by, imported_at
                         FROM door_imports ORDER BY id DESC LIMIT %s''', (limit,)).fetchall()


def door_records_for_facility(db, facility_code):
    return db.execute('SELECT * FROM door_records WHERE facility_code = %s ORDER BY code',
                      (facility_code,)).fetchall()


def month_period(month):
    return month_bounds(month)
