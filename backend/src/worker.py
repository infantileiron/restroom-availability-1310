import logging
import time
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from redis.exceptions import RedisError

from src.config.runtime import REDIS, WAKE_QUEUE
from src.constants.business import FORMULA_VERSION
from src.models.audit import audit
from src.models.database import connect
from src.services.availability import calculate
from src.services.exports import write_export

HEARTBEAT = Path('/tmp/heartbeat')
log = logging.getLogger(__name__)


def previous_result(db, job):
    """Result this job may reuse for unaffected days.

    Only the version being revised, or this same job's earlier result after a
    retry, is a valid base, and only when it was produced by the current formula;
    anything else would mix incompatible frozen inputs.
    """
    if job['affected'] is None:
        return None
    for candidate in (job['revises'], job['id']):
        if candidate is None:
            continue
        parent = db.execute('SELECT result FROM snapshots WHERE id = %s', (candidate,)).fetchone()
        if parent and parent['result'] and parent['result'].get('formula') == FORMULA_VERSION:
            return parent['result']
    return None


def work_once():
    with connect() as db:
        job = db.execute("""SELECT id, month, revises, affected, inputs, checksum FROM snapshots
                            WHERE status = 'queued' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
        if job is None:
            return False
        try:
            previous = previous_result(db, job)
            result = calculate(job['inputs'], previous=previous,
                               affected=job['affected'] if previous is not None else None)
            write_export(job['id'], job['inputs'], job['checksum'], result)
        except Exception:
            log.exception('Snapshot %s failed', job['id'])
            db.execute("""UPDATE snapshots SET status = 'failed', error = %s, finished_at = now() WHERE id = %s""",
                       ('核算或导出失败，可重试当前版本', job['id']))
            audit(db, 'worker', 'snapshot.fail', job['id'])
        else:
            db.execute("UPDATE snapshots SET status = 'ready', result = %s, finished_at = now() WHERE id = %s",
                       (Jsonb(result), job['id']))
            audit(db, 'worker', 'snapshot.finish', job['id'])
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            worked = work_once()
        except psycopg.Error:
            log.warning('Waiting for the database and schema')
            time.sleep(2)
            continue
        HEARTBEAT.touch()
        if not worked:
            try:
                REDIS.blpop(WAKE_QUEUE, timeout=2)
            except RedisError:
                time.sleep(2)


if __name__ == '__main__':
    main()
