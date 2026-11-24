from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from src.constants.business import Role
from src.controllers.identity import current_user, require
from src.models import calendar
from src.models.database import connect
from src.schemas.calendar import FacilityInput, OutageInput, WindowInput
from src.services import calendar as operations
from src.services import door_csv
from src.utils.calendar import month_bounds

router = APIRouter(tags=['calendar'])
analyst = require(Role.ANALYST)


@router.get('/facilities')
def facilities(user=Depends(current_user)):
    with connect() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        return calendar.facilities(db)


@router.post('/facilities', status_code=201)
def add_facility(payload: FacilityInput, user=Depends(analyst)):
    return operations.create_facility(payload, user['username'])


@router.post('/facilities/{code}/windows', status_code=201)
def add_opening(code: str, payload: WindowInput, user=Depends(analyst)):
    return operations.save_windows(code, payload, user['username'])


@router.get('/outages')
def outages(user=Depends(current_user)):
    with connect() as db:
        return calendar.outages(db)


@router.post('/outages', status_code=201)
def add_outage(payload: OutageInput, user=Depends(analyst)):
    return operations.create_outage(payload, user['username'])


@router.get('/door-imports')
def door_imports(user=Depends(current_user)):
    with connect() as db:
        return calendar.door_imports(db)


@router.get('/door-records')
def door_records(month: str | None = Query(default=None, pattern=r'^20[0-9]{2}-(0[1-9]|1[0-2])$'),
                 user=Depends(current_user)):
    with connect() as db:
        return calendar.door_records(db, month_bounds(month) if month else None)


@router.post('/door-records/import', status_code=201)
async def import_door_records(file: UploadFile = File(...), user=Depends(analyst)):
    payload = await file.read()
    if not payload:
        raise HTTPException(422, '门磁记录文件是空的')
    if len(payload) > 2 * 1024 * 1024:
        raise HTTPException(413, '门磁记录文件超过 2 MB，请分批导入')
    parsed = door_csv.parse(file.filename or 'door-records.csv', payload)
    return operations.import_door_records(parsed, user['username'], door_csv.digest(payload))
