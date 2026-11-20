"""Phase 12.2: GTA / gaming intelligence (categories, audio signal, multi-signal scoring, rules)."""
from .categories import GAMING_CATEGORIES, get_categories, category_ids
from .signals import audio_energy_profile, summarize_audio
from .scoring import classify_unit, best_categories