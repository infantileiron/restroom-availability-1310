from enum import StrEnum


class Role(StrEnum):
    ANALYST = 'analyst'
    REVIEWER = 'reviewer'
    VIEWER = 'viewer'


class Reason(StrEnum):
    WATER = 'water'
    FAULT = 'fault'


class Status(StrEnum):
    DRAFT = 'draft'
    QUEUED = 'queued'
    READY = 'ready'
    PUBLISHED = 'published'
    FAILED = 'failed'


class EvidencePolicy(StrEnum):
    PARTIAL = 'partial'
    DEFER = 'defer'


FORMULA_VERSION = 'facility-minute-v2'
