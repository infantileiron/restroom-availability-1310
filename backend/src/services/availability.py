from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from src.constants.business import FORMULA_VERSION
from src.utils.calendar import month_bounds
from src.utils.intervals import MINUTE, union, intersections, duration, subtract

DAY = timedelta(days=1)
POLICIES = ('partial', 'defer')
RECON_KEYS = ('promised_minutes', 'planned_minutes', 'lost_minutes', 'pending_minutes',
              'both_minutes', 'door_only_minutes', 'outage_only_minutes', 'undisturbed_minutes',
              'door_closed_minutes', 'deferred_minutes', 'complete_days', 'partial_days',
              'deferred_days')
STATUSES = ('complete', 'partial', 'deferred', 'none')


def opening_intervals(windows, start, end):
    by_weekday = defaultdict(list)
    for rule in windows:
        by_weekday[rule['weekday']].append(rule)
    intervals = []
    day = start - DAY
    while day < end:
        for rule in by_weekday[day.weekday()]:
            open_at = max(start, day + rule['start_min'] * MINUTE)
            close_at = min(end, day + rule['end_min'] * MINUTE)
            if open_at < close_at:
                intervals.append((open_at, close_at))
        day += DAY
    return union(intervals)


def metrics(planned, lost):
    available = planned - lost
    rate = None
    if planned:
        rate = str((Decimal(available * 100) / planned).quantize(Decimal('0.01'), ROUND_HALF_UP))
    return {'planned_minutes': planned, 'lost_minutes': lost, 'available_minutes': available,
            'availability_pct': rate}


def _stamp(record, field):
    value = record.get(field)
    return datetime.fromisoformat(value) if value else None


def _clip(interval, start, end):
    return max(interval[0], start), min(interval[1], end)


def _offset(intervals, day):
    return [[(begin - day) // MINUTE, (finish - day) // MINUTE] for begin, finish in intervals]


def door_evidence(records, start, end):
    """Split door input into proven closures and same-day spans still unresolved.

    Only a record carrying both endpoints proves the door was closed for that
    span, and only that can subtract promised-open minutes. A record with one
    endpoint proves neither an open nor a closed state, so the undecided part of
    its own calendar day — from a close stamp onward, or up to an open stamp —
    stays pending instead of counting as open or closed.
    """
    complete, close_only, open_only = [], [], []
    for record in records:
        closed, reopened = _stamp(record, 'closed_at'), _stamp(record, 'reopened_at')
        if closed and reopened:
            if closed < end and reopened > start:
                complete.append(_clip((closed, reopened), start, end))
        elif closed:
            close_only.append(closed)
        elif reopened:
            open_only.append(reopened)
    complete = union(complete)
    events = sorted({stamp for span in complete for stamp in span} | set(close_only) | set(open_only))
    uncertain = []
    for closed in close_only:
        day_end = datetime(closed.year, closed.month, closed.day) + DAY
        bound = [stamp for stamp in events if closed < stamp <= day_end]
        uncertain.append((closed, bound[0] if bound else day_end))
    for reopened in open_only:
        day_start = datetime(reopened.year, reopened.month, reopened.day)
        bound = [stamp for stamp in events if day_start <= stamp < reopened]
        uncertain.append((bound[-1] if bound else day_start, reopened))
    clipped = [_clip(span, start, end) for span in uncertain]
    pending = subtract(union(span for span in clipped if span[0] < span[1]), complete)
    return complete, pending


def incomplete_codes(records, start, end):
    """One-sided codes whose unresolved window can reach into the month."""
    codes = []
    for record in records:
        closed, reopened = _stamp(record, 'closed_at'), _stamp(record, 'reopened_at')
        if closed and reopened:
            continue
        stamp = closed or reopened
        if stamp and start <= stamp < end:
            codes.append(record['code'])
    return sorted(codes)


def _entry(day, end, plans, outages, closed, pending_door, policy):
    clip = [(day, min(day + DAY, end))]
    promised = list(intersections(plans, clip))
    pending = list(intersections(promised, pending_door))
    entry = {'status': 'complete', 'promised_minutes': duration(promised),
             'planned_minutes': 0, 'lost_minutes': 0, 'pending_minutes': 0,
             'both_minutes': 0, 'door_only_minutes': 0, 'outage_only_minutes': 0,
             'undisturbed_minutes': 0, 'door_closed_minutes': 0, 'deferred_minutes': 0,
             'complete_days': 0, 'partial_days': 0, 'deferred_days': 0,
             'promised': _offset(promised, day), 'planned': _offset(promised, day),
             'lost': [], 'pending': _offset(pending, day),
             'door': [], 'both': [], 'door_only': [], 'outage_only': []}
    if pending and policy == 'defer':
        entry.update(status='deferred', deferred_days=1, deferred_minutes=duration(promised),
                     planned=[], planned_minutes=0, pending_minutes=0,
                     pending=_offset(promised, day))
        return entry
    determined = subtract(promised, pending_door)
    door = list(intersections(closed, determined))
    outage = list(intersections(outages, determined))
    both = list(intersections(door, outage))
    door_only = subtract(door, outage)
    outage_only = subtract(outage, door)
    undisturbed = subtract(determined, union(door + outage))
    lost = union(door + outage)
    entry.update({'status': 'partial' if pending else 'complete',
                  'planned_minutes': duration(determined), 'lost_minutes': duration(lost),
                  'pending_minutes': duration(pending),
                  'both_minutes': duration(both), 'door_only_minutes': duration(door_only),
                  'outage_only_minutes': duration(outage_only),
                  'undisturbed_minutes': duration(undisturbed),
                  'door_closed_minutes': duration(door),
                  'complete_days': 0 if pending else 1, 'partial_days': 1 if pending else 0,
                  'planned': _offset(determined, day), 'lost': _offset(lost, day),
                  'pending': _offset(pending, day),
                  'door': _offset(door, day), 'both': _offset(both, day),
                  'door_only': _offset(door_only, day), 'outage_only': _offset(outage_only, day)})
    return entry


def _prepare(inputs):
    raw = defaultdict(list)
    outage_events = defaultdict(list)
    for event in inputs.get('outages', []):
        interval = (datetime.fromisoformat(event['starts_at']), datetime.fromisoformat(event['ends_at']))
        raw[event['facility_code']].append(interval)
        outage_events[event['facility_code']].append((event['code'], interval))
    outages = defaultdict(list, {code: union(intervals) for code, intervals in raw.items()})
    records = defaultdict(list)
    for record in inputs.get('door_records', []):
        records[record['facility_code']].append(record)
    return outages, outage_events, records


def _aggregate(daily):
    totals = {key: 0 for key in RECON_KEYS}
    for entry in daily.values():
        for key in totals:
            totals[key] += entry.get(key, 0)
    return totals


def policy_of(inputs):
    policy = inputs.get('evidence_policy', 'partial')
    return policy if policy in POLICIES else 'partial'


def calculate(inputs, previous=None, affected=None):
    """Facility-minute result with door/registration reconciliation.

    With a previous result plus the facility-days whose frozen inputs changed,
    only those days are recalculated; every other day entry is copied verbatim,
    so a supplementary run never counts the same minutes twice.
    """
    start, end = month_bounds(inputs['month'])
    policy = policy_of(inputs)
    outages, outage_events, records = _prepare(inputs)
    previous_sites = {row['code']: row for row in (previous or {}).get('facilities', [])}
    affected_set = {tuple(item) for item in (affected or [])}
    incremental = previous is not None and affected is not None

    rows, event_checks = [], []
    reused, recomputed = 0, []
    grand = {key: 0 for key in RECON_KEYS}
    facility_status = {status: 0 for status in STATUSES}

    for site in inputs['facilities']:
        code = site['code']
        plans = opening_intervals(site['windows'], start, end)
        closed, pending_door = door_evidence(records[code], start, end)
        missing = incomplete_codes(records[code], start, end)
        prior_daily = previous_sites.get(code, {}).get('daily', {})

        daily = {}
        day = start
        while day < end:
            key = day.date().isoformat()
            carried = (incremental and (code, key) not in affected_set
                       and isinstance(prior_daily.get(key), dict)
                       and 'promised_minutes' in prior_daily[key] and 'pending_minutes' in prior_daily[key])
            if carried:
                daily[key] = prior_daily[key]
                reused += 1
            else:
                daily[key] = _entry(day, end, plans, outages[code], closed, pending_door, policy)
                if incremental:
                    recomputed.append({'code': code, 'day': key})
            day += DAY

        aggregate = _aggregate(daily)
        for key in RECON_KEYS:
            grand[key] += aggregate[key]
        status = ('deferred' if aggregate['deferred_days'] else
                  'partial' if aggregate['pending_minutes'] else
                  'complete' if records[code] else 'none')
        facility_status[status] += 1

        for event_code, interval in outage_events[code]:
            in_month = list(intersections([_clip(interval, start, end)], [(start, end)]))
            event_checks.append({'code': event_code, 'facility_code': code,
                                 'in_month_minutes': duration(in_month),
                                 'inside_opening_minutes': duration(intersections(plans, in_month))})

        door_closed = list(intersections(closed, [(start, end)]))
        in_plan = duration(intersections(door_closed, plans))
        rows.append({'code': code, 'name': site['name'], 'district': site['district'],
                     **metrics(aggregate['planned_minutes'], aggregate['lost_minutes']),
                     'out_of_window_minutes': duration(door_closed) - in_plan,
                     'door_record_count': len(records[code]),
                     'incomplete_codes': missing,
                     'daily': daily,
                     'reconciliation': {**aggregate, 'status': status,
                                        'evidence': 'complete' if records[code] else 'none'}})

    totals = metrics(sum(row['planned_minutes'] for row in rows), sum(row['lost_minutes'] for row in rows))
    totals['excluded_facilities'] = sum(row['planned_minutes'] == 0 for row in rows)
    totals['facility_count'] = len(rows)

    reconciliation = {**grand, 'policy': policy, 'facility_status': facility_status,
                      'incomplete_record_count': sum(len(row['incomplete_codes']) for row in rows),
                      'pending_days': sum(1 for row in rows for entry in row['daily'].values()
                                          if entry.get('status') == 'partial')}
    computed = {'revision': inputs.get('revision', 1), 'incremental': incremental,
                'reused_days': reused, 'recomputed_day_count': len(recomputed),
                'affected_days': sorted([list(item) for item in affected_set])[:400] if incremental else None}
    return {'totals': totals, 'facilities': rows, 'event_checks': event_checks,
            'reconciliation': reconciliation, 'computed': computed, 'formula': FORMULA_VERSION}


def _spanned_days(interval, start, end):
    first, last = max(interval[0], start), min(interval[1], end)
    days, cursor = set(), datetime(first.year, first.month, first.day)
    while cursor < last:
        days.add(cursor.date().isoformat())
        cursor += DAY
    return days


def _group_records(rows):
    grouped = defaultdict(dict)
    for row in rows:
        grouped[row['facility_code']][row['code']] = row
    return grouped


def affected_facility_days(previous_inputs, current_inputs):
    """Facility-days whose frozen inputs differ between two snapshots."""
    start, end = month_bounds(current_inputs['month'])
    all_days = set()
    cursor = start
    while cursor < end:
        all_days.add(cursor.date().isoformat())
        cursor += DAY

    affected = set()

    def mark(code, interval):
        affected.update((code, key) for key in _spanned_days(interval, start, end))

    wholesale = (previous_inputs.get('month') != current_inputs['month']
                 or policy_of(previous_inputs) != policy_of(current_inputs))
    previous_sites = {site['code']: site for site in previous_inputs.get('facilities', [])}
    current_codes = {site['code'] for site in current_inputs['facilities']}
    for site in current_inputs['facilities']:
        prior = previous_sites.get(site['code'])
        if wholesale or prior is None or prior.get('windows') != site.get('windows'):
            affected.update((site['code'], key) for key in all_days)
    for code in set(previous_sites) - current_codes:
        affected.update((code, key) for key in all_days)

    previous_doors = _group_records(previous_inputs.get('door_records', []))
    current_doors = _group_records(current_inputs.get('door_records', []))
    for code in set(previous_doors) | set(current_doors):
        old, new = previous_doors.get(code, {}), current_doors.get(code, {})
        if bool(old) != bool(new):
            affected.update((code, key) for key in all_days)
            continue
        changed = False
        for record_code in set(old) | set(new):
            before, after = old.get(record_code, {}), new.get(record_code, {})
            if (before.get('facility_code'), before.get('closed_at'), before.get('reopened_at')) == \
                    (after.get('facility_code'), after.get('closed_at'), after.get('reopened_at')):
                continue
            changed = True
            for record in (before, after):
                if record and record.get('closed_at') and record.get('reopened_at'):
                    mark(code, (datetime.fromisoformat(record['closed_at']),
                                datetime.fromisoformat(record['reopened_at'])))
        if changed:
            # A one-sided record leaves the rest of its own calendar day pending,
            # so mark whichever of those days either version leaves undecided.
            for version in (old, new):
                _, pending = door_evidence(list(version.values()), start, end)
                for span in pending:
                    mark(code, span)

    previous_outages = _group_records(previous_inputs.get('outages', []))
    current_outages = _group_records(current_inputs.get('outages', []))
    for code in set(previous_outages) | set(current_outages):
        old, new = previous_outages.get(code, {}), current_outages.get(code, {})
        if bool(old) != bool(new):
            affected.update((code, key) for key in all_days)
            continue
        for event_code in set(old) | set(new):
            before, after = old.get(event_code), new.get(event_code)
            if before == after:
                continue
            for event in (before, after):
                if event:
                    mark(code, (datetime.fromisoformat(event['starts_at']),
                                datetime.fromisoformat(event['ends_at'])))

    return sorted([list(item) for item in affected])
