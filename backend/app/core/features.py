"""Feature flag system. Simple JSON-based flags with dependency checking."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_features: dict | None = None


def get_features() -> dict:
    """Load feature flags from configs/features.json."""
    global _features
    if _features is None:
        path = Path(__file__).parent.parent.parent / "configs" / "features.json"
        _features = json.loads(path.read_text())
        logger.info("[FEATURES] Loaded %d feature flags", len(_features))
    return _features


def is_enabled(feature_id: str) -> bool:
    """Check if a feature is enabled. Respects dependency chains."""
    features = get_features()
    feat = features.get(feature_id, {})
    if not feat.get("enabled", False):
        return False
    for req in feat.get("requires", []):
        if not is_enabled(req):
            return False
    return True


def reload_features() -> None:
    """Force reload from disk. Call after updating features.json."""
    global _features
    _features = None
