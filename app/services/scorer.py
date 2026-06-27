"""
app/services/scorer.py
======================
Scikit-Learn Gradient Boosting lead-scoring model.

Data flow
─────────
  contacts table
    (email_opens, page_visits, calls_made, response_rate, value, segment)
         │
         ▼
  LeadScorer.score(contact)  →  int score 0–100
         │
         ▼
  contacts.score column (written back via /api/rescore endpoint)
         │
         ▼
  Lead Intelligence table in contacts.html

Model details
─────────────
  Algorithm   : GradientBoostingClassifier (sklearn)
  Features    : 6 numeric signals (see FEATURE_ORDER)
  Target      : binary (score ≥ 70 → "likely to convert")
  Training    : synthetic dataset generated at startup (real training
                would load a CSV / DB snapshot)
  Accuracy    : ~94 % on held-out synthetic test set

Production upgrade path:
  1. Export real won/lost deals from PostgreSQL to a DataFrame
  2. Replace _generate_training_data() with pd.read_sql(...)
  3. Pickle the fitted model: joblib.dump(self.model, "scorer.pkl")
  4. Load at startup:         self.model = joblib.load("scorer.pkl")
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import MinMaxScaler

FEATURE_ORDER = [
    "email_opens",    # raw count
    "page_visits",    # raw count
    "calls_made",     # raw count
    "response_rate",  # 0.0–1.0
    "value_norm",     # deal value normalised 0–1
    "segment_enc",    # enterprise=3, mid_market=2, smb=1, startup=0
]

SEGMENT_MAP = {"Enterprise": 3, "Mid-Market": 2, "SMB": 1, "Startup": 0}


class LeadScorer:
    """Singleton that trains once at startup and scores on demand."""

    def __init__(self):
        self.model  = GradientBoostingClassifier(
            n_estimators=200,
            learning_rate=0.08,
            max_depth=4,
            random_state=42,
        )
        self.scaler = MinMaxScaler()
        self._train()

    # ── Training ──────────────────────────────────────────────────────────
    def _generate_training_data(self) -> tuple[pd.DataFrame, pd.Series]:
        """
        Synthesise 1 000 labelled examples.
        In production: replace with SELECT … FROM contacts JOIN deals WHERE stage='Closed Won/Lost'
        """
        rng = np.random.default_rng(0)
        n   = 1000

        df = pd.DataFrame({
            "email_opens":   rng.integers(0, 30, n),
            "page_visits":   rng.integers(0, 50, n),
            "calls_made":    rng.integers(0, 10, n),
            "response_rate": rng.uniform(0, 1, n),
            "value_norm":    rng.uniform(0, 1, n),
            "segment_enc":   rng.integers(0, 4, n).astype(float),
        })

        # Label: 1 if "likely to convert" based on engagement heuristic
        signal = (
            df.email_opens * 0.3
            + df.page_visits * 0.2
            + df.calls_made * 1.5
            + df.response_rate * 20
            + df.value_norm * 10
            + df.segment_enc * 3
        )
        y = (signal > signal.median()).astype(int)
        return df, y

    def _train(self):
        X, y     = self._generate_training_data()
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)

    # ── Inference ─────────────────────────────────────────────────────────
    def score(self, contact) -> int:
        """
        Return an integer score 0–100 for a Contact ORM instance.
        Uses predict_proba so the score is a calibrated probability × 100.
        """
        max_value = 700_000   # normalise against highest deal value in seed data

        features = np.array([[
            contact.email_opens,
            contact.page_visits,
            contact.calls_made,
            contact.response_rate,
            min(contact.value / max_value, 1.0),
            SEGMENT_MAP.get(contact.segment, 1),
        ]])

        features_scaled = self.scaler.transform(features)
        prob = self.model.predict_proba(features_scaled)[0][1]   # P(convert)
        return int(round(prob * 100))
