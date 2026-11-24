from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints


class SnapshotInput(BaseModel):
    month: Annotated[str, StringConstraints(pattern=r'^20[0-9]{2}-(0[1-9]|1[0-2])$')]
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
    evidence_policy: Literal['partial', 'defer'] = 'partial'
    revises: int | None = None
