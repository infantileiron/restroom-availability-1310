/** @typedef {{promised_minutes: number, planned_minutes: number, lost_minutes: number,
 * available_minutes: number, availability_pct: string|null}} Availability */
/** @typedef {{planned: [number, number][], lost: [number, number][], pending: [number, number][],
 * door: [number, number][], both: [number, number][], door_only: [number, number][],
 * outage_only: [number, number][], status: 'complete'|'partial'|'deferred',
 * promised_minutes: number, planned_minutes: number, lost_minutes: number,
 * pending_minutes: number, deferred_minutes: number, both_minutes: number,
 * door_only_minutes: number, outage_only_minutes: number}} DayTimeline */
/** @typedef {Availability & {code: string, name: string, district: string,
 * out_of_window_minutes: number, door_record_count: number, incomplete_codes: string[],
 * daily: Record<string, DayTimeline>, reconciliation: object}} FacilityResult */
