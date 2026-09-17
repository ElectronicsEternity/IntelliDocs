from datetime import datetime

from pydantic import BaseModel


class UsageMetric(BaseModel):
    used: int
    limit: int


class UsageSummaryResponse(BaseModel):
    plan_code: str
    plan_name: str
    period_start: datetime
    period_end: datetime
    documents: UsageMetric
    storage_bytes: UsageMetric
    pages_processed: UsageMetric
    questions: UsageMetric
