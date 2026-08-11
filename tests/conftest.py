import os
import warnings

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")

warnings.filterwarnings(
    "ignore",
    message=r"datetime\.datetime\.utcnow\(\) is deprecated and scheduled for removal in a future version\. Use timezone-aware objects to represent datetimes in UTC: datetime\.datetime\.now\(datetime\.UTC\)\.",
    category=DeprecationWarning,
    module=r"sqlalchemy.*",
)