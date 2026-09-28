from dataclasses import dataclass
from decimal import Decimal

from app.config import settings


@dataclass(frozen=True)
class PlanLimits:
    code: str
    name: str
    documents: int
    storage_bytes: int
    pages_per_month: int
    ai_budget_usd: Decimal


def get_plan_limits(code: str) -> PlanLimits:
    if code == "pro":
        return PlanLimits(
            code="pro",
            name="Pro",
            documents=settings.PRO_MAX_DOCUMENTS,
            storage_bytes=settings.PRO_MAX_STORAGE_BYTES,
            pages_per_month=settings.PRO_MAX_PAGES_PER_MONTH,
            ai_budget_usd=Decimal(str(settings.PRO_AI_BUDGET_USD)),
        )
    return PlanLimits(
        code="trial",
        name="Trial",
        documents=settings.TRIAL_MAX_DOCUMENTS,
        storage_bytes=settings.TRIAL_MAX_STORAGE_BYTES,
        pages_per_month=settings.TRIAL_MAX_PAGES_PER_MONTH,
        ai_budget_usd=Decimal(str(settings.TRIAL_AI_BUDGET_USD)),
    )
