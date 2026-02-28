"""ORM model package. Import all models here so Alembic can discover them."""
from app.models.exchange import Exchange  # noqa: F401
from app.models.price import PriceSnapshot  # noqa: F401
from app.models.spread import SpreadRecord  # noqa: F401
from app.models.alert import AlertConfig, AlertHistory  # noqa: F401
from app.models.user import UserPreference, ExchangeStatusLog, FxRateHistory, TrackedSymbol  # noqa: F401
