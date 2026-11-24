import json

from src.models.database import connect
from src.utils.identity import hash_password

USERS = [('analyst', '林清', 'analyst'), ('reviewer', '陈亭', 'reviewer'), ('viewer', '周桐', 'viewer')]
SITES = [('FJ-01', '桥西便民公厕', '桥西片区'), ('FJ-02', '站前夜间公厕', '站前片区'),
         ('FJ-03', '河畔绿道公厕', '河畔片区'), ('FJ-04', '北坊整修公厕', '北坊片区')]
RULES = [('FJ-01', 0, 1440), ('FJ-02', 1200, 1560), ('FJ-02', 1290, 1380), ('FJ-03', 420, 1140)]
OUTAGES = [
    ('WX-1101', 'FJ-02', 'fault', '2026-10-31 23:20', '2026-11-01 00:30', '门锁复位，跨月交班'),
    ('WX-1102', 'FJ-01', 'water', '2026-11-12 06:10', '2026-11-12 07:00', '管线检修停水'),
    ('WX-1103', 'FJ-01', 'fault', '2026-11-12 06:40', '2026-11-12 07:25', '冲洗阀故障，和停水交叠'),
    ('WX-1104', 'FJ-02', 'water', '2026-11-12 23:30', '2026-11-13 00:45', '夜班支线停水'),
    ('WX-1105', 'FJ-02', 'fault', '2026-11-13 00:15', '2026-11-13 03:10', '设备恢复时间晚于闭馆'),
    ('WX-1106', 'FJ-03', 'fault', '2026-11-12 05:45', '2026-11-12 06:25', '晨巡故障，开放前已恢复'),
    ('WX-1107', 'FJ-03', 'water', '2026-11-12 18:30', '2026-11-12 19:30', '晚班停水跨过闭馆线'),
    ('WX-1108', 'FJ-04', 'fault', '2026-11-12 08:00', '2026-11-12 09:10', '整修期测试发现照明故障'),
]
# 门磁开关记录：成对记录可证明停用；单端记录只把当天余下时段标为待核。
DOOR_IMPORT = ('巡维门磁_2026-11.csv', '1fa3c60f9ecaffae89f60d4109fdda8e659fc2132619450f5bfd187e29974188', 9, 2)
DOOR_RECORDS = [
    ('MC-1101', 'FJ-01', '2026-11-12 06:12', '2026-11-12 07:02', '停水期间闭门，与登记基本吻合'),
    ('MC-1102', 'FJ-01', '2026-11-12 06:42', '2026-11-12 07:20', '冲洗阀故障闭门，与停水重合'),
    ('MC-1103', 'FJ-02', '2026-11-12 23:31', '2026-11-13 00:44', '夜间停水闭门'),
    ('MC-1104', 'FJ-03', '2026-11-12 05:50', '2026-11-12 06:20', '开放前故障闭门'),
    ('MC-1105', 'FJ-03', '2026-11-12 09:00', '2026-11-12 09:40', '设备故障，入口指示灯更换'),
    ('MC-1106', 'FJ-03', '2026-11-12 18:32', '2026-11-12 19:20', '晚班停水闭门'),
    ('MC-1107', 'FJ-02', '2026-11-18 21:40', '2026-11-18 22:05', '只有门磁记录，无停用登记'),
    ('MC-1108', 'FJ-01', None, '2026-11-20 10:15', '交接表缺关门时间，从开门前起待核'),
    ('MC-1109', 'FJ-02', '2026-11-24 22:10', None, '交接表未记恢复时间，待核'),
]


def seed():
    with connect() as db, db.cursor() as cursor:
        cursor.executemany('INSERT INTO users VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING',
                           [(*user, hash_password('Fangjie2026!')) for user in USERS])
        cursor.executemany('INSERT INTO facilities VALUES (%s, %s, %s) ON CONFLICT DO NOTHING', SITES)
        cursor.executemany('''INSERT INTO opening_windows (facility_code, weekday, start_min, end_min)
                              VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING''',
                           [(code, day, start, end) for code, start, end in RULES for day in range(7)])
        cursor.executemany('INSERT INTO outages VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING', OUTAGES)
        filename, checksum, row_count, incomplete = DOOR_IMPORT
        cursor.execute('''INSERT INTO door_imports (filename, checksum, row_count, incomplete_count,
                                                   created_count, imported_by)
                          VALUES (%s, %s, %s, %s, %s, 'analyst') ON CONFLICT (checksum) DO NOTHING
                          RETURNING id''', (filename, checksum, row_count, incomplete, row_count))
        batch = cursor.fetchone()
        if batch:
            cursor.executemany('''INSERT INTO door_records (import_id, code, facility_code, closed_at,
                                                            reopened_at, note)
                                  VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING''',
                               [(batch['id'], code, site, closed, reopened, note or '')
                                for code, site, closed, reopened, note in DOOR_RECORDS])
        keys = {
            'facilities': sorted(site[0] for site in SITES),
            'outages': sorted(row[0] for row in OUTAGES),
            'door_records': sorted(row[0] for row in DOOR_RECORDS),
            'opening_windows': len(RULES) * 7,
            'users': sorted(user[0] for user in USERS),
        }
    return keys


if __name__ == '__main__':
    print(json.dumps(seed(), ensure_ascii=False, sort_keys=True))
