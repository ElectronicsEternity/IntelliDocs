# Import dataclass decorator
from dataclasses import dataclass

# Import datetime
from datetime import datetime


# Represents a registered IntelliDocs user
@dataclass
class User:

    # Unique user identifier
    user_id: str

    # Full name
    full_name: str

    # Email address
    email: str

    # Subscription plan
    subscription_plan: str

    # Trial expiration date
    trial_expiry: datetime | None

    # Account creation date
    created_at: datetime

    # Whether the account is active
    is_active: bool