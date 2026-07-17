#!/usr/bin/env python3
"""ML Signal Enhancement Module — LightGBM-based fund buy signal classifier.

Features (all computed from data available up to date T, no look-ahead):
  - Five dimension scores (quality, cost, manager, momentum, smart_money)
  - Recent returns: 1m, 3m, 6m
  - Max drawdown, volatility
  - Fund scale, management fee
  - Buy count (consensus), market state
  - Fund age (days since first chart point)

Label: 1 if 30-day forward return > threshold (default 3%), else 0

Usage in backtest:
  from tools.ml_signal import MLSignalEnhancer
  enhancer = MLSignalEnhancer(fund_charts, trading_by_date, ...)
  enhancer.pretrain(cutoff_date)  # train on data up to cutoff_date
  prob = enhancer.predict(code, features_dict)  # returns P(profitable)
"""
import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from collections import defaultdict

try:
    import lightgbm as lgb
    import numpy as np
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False


def _float(v, default=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


class MLSignalEnhancer:
    """Walk-forward LightGBM signal enhancer for fund backtesting."""

    FEATURE_NAMES = [
        "quality_score", "cost_score", "manager_score",
        "momentum_score", "smart_money_score",
        "ret_1m", "ret_3m", "ret_6m",
        "max_drawdown", "volatility",
        "fund_scale", "manage_fee",
        "buy_count", "market_state_num",
        "fund_age_days", "total_score",
    ]

    def __init__(self, fund_charts, fund_profiles=None, fund_rules=None,
                 fwd_days=30, label_threshold=3.0):
        self.fund_charts = fund_charts
        self.fund_profiles = fund_profiles or {}
        self.fund_rules = fund_rules or {}
        self.fwd_days = fwd_days
        self.label_threshold = label_threshold
        self.model = None
        self._feature_cache = {}  # (code, date_str) -> feature vector

    def _compute_features(self, code, cutoff_date, scores=None, buy_count=0,
                          market_state="neutral"):
        """Compute feature vector for a fund on a given date."""
        pts = self.fund_charts.get(code, [])
        valid = [p for p in pts if p.get("xAxis", "") <= cutoff_date]
        if len(valid) < 20:
            return None

        values = [_float(p.get("yAxis", 0)) for p in valid]
        cur_return = values[-1]

        # Recent returns
        ret_1m = cur_return - values[-20] if len(values) >= 20 else 0
        ret_3m = cur_return - values[-60] if len(values) >= 60 else 0
        ret_6m = cur_return - values[-120] if len(values) >= 120 else 0

        # Max drawdown
        nav_values = [(100 + v) / 100 for v in values]
        peak = nav_values[0]
        max_dd = 0
        for v in nav_values:
            if v > peak:
                peak = v
            if peak > 0:
                dd = (peak - v) / peak * 100
                if dd > max_dd:
                    max_dd = dd

        # Volatility (std of last 60 daily returns)
        recent_navs = nav_values[-60:] if len(nav_values) >= 60 else nav_values
        daily_rets = [(recent_navs[i] / recent_navs[i-1] - 1) * 100
                      for i in range(1, len(recent_navs)) if recent_navs[i-1] > 0]
        vol = statistics.stdev(daily_rets) if len(daily_rets) > 5 else 0

        # Fund scale
        profile = self.fund_profiles.get(code, {})
        scale_str = profile.get("scale", "")
        fund_scale = 0.0
        if "亿" in scale_str:
            import re
            nums = re.findall(r'[\d.]+', scale_str.replace("亿元", "").replace("亿", ""))
            if nums:
                fund_scale = float(nums[0])

        # Management fee
        rules = self.fund_rules.get(code, {})
        manage_fee = _float(rules.get("manage_fee", 0))

        # Market state to number
        ms_num = {"bull": 2, "neutral": 1, "bear": 0}.get(market_state, 1)

        # Fund age
        first_date = valid[0].get("xAxis", "")[:10]
        fund_age_days = 0
        try:
            first_dt = datetime.strptime(first_date, "%Y-%m-%d")
            cur_dt = datetime.strptime(cutoff_date[:10], "%Y-%m-%d")
            fund_age_days = (cur_dt - first_dt).days
        except (ValueError, TypeError):
            pass

        # Scores (from the five-dimension scoring)
        q_score = scores.get("quality", 2.5) if scores else 2.5
        c_score = scores.get("cost", 3.0) if scores else 3.0
        m_score = scores.get("manager", 2.5) if scores else 2.5
        mo_score = scores.get("momentum", 2.5) if scores else 2.5
        sm_score = scores.get("smart_money", 2.5) if scores else 2.5
        total_score = scores.get("total", 3.0) if scores else 3.0

        return [
            q_score, c_score, m_score, mo_score, sm_score,
            ret_1m, ret_3m, ret_6m,
            max_dd, vol,
            fund_scale, manage_fee,
            buy_count, ms_num,
            fund_age_days, total_score,
        ]

    def _compute_label(self, code, date_str, cutoff_date=None):
        """Compute label: 1 if fwd_days forward return > threshold, else 0.
        如果提供了cutoff_date，则检查前瞻数据是否在截止日之前（防前视偏差）。
        """
        pts = self.fund_charts.get(code, [])
        # Find the index for date_str
        buy_idx = None
        for i, p in enumerate(pts):
            if p.get("xAxis", "") >= date_str:
                buy_idx = i
                break
        if buy_idx is None or buy_idx + self.fwd_days >= len(pts):
            return None
        # 防前视偏差：前瞻日期不能超过截止日
        fwd_point = pts[buy_idx + self.fwd_days]
        if cutoff_date and fwd_point.get("xAxis", "9999") > cutoff_date[:10]:
            return None  # 前瞻数据在截止日之后，不可用
        bv = _float(pts[buy_idx].get("yAxis", 0))
        sv = _float(fwd_point.get("yAxis", 0))
        fwd_return = sv - bv
        return 1 if fwd_return > self.label_threshold else 0

    def pretrain(self, cutoff_date, training_data=None):
        """Train the model on all available data up to cutoff_date.
        training_data: list of (code, date_str, scores_dict, buy_count, market_state)
        """
        if not ML_AVAILABLE:
            return False

        X, y = [], []
        for item in (training_data or []):
            code, date_str, scores, buy_count, ms = item
            if date_str >= cutoff_date:
                continue
            label = self._compute_label(code, date_str, cutoff_date)
            if label is None:
                continue
            features = self._compute_features(code, date_str, scores, buy_count, ms)
            if features is None:
                continue
            X.append(features)
            y.append(label)

        if len(X) < 50 or len(set(y)) < 2:
            print(f"  ML: insufficient training data ({len(X)} samples, {len(set(y))} classes)")
            return False

        X = np.array(X)
        y = np.array(y)

        self.model = lgb.LGBMClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            min_child_samples=10,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1,
        )
        self.model.fit(X, y)
        pos_ratio = sum(y) / len(y)
        print(f"  ML: trained on {len(X)} samples, positive ratio={pos_ratio:.1%}")
        return True

    def predict(self, code, cutoff_date, scores=None, buy_count=0, market_state="neutral"):
        """Predict probability of profitable trade. Returns 0.5 if model unavailable."""
        if not self.model or not ML_AVAILABLE:
            return 0.5
        features = self._compute_features(code, cutoff_date, scores, buy_count, market_state)
        if features is None:
            return 0.5
        prob = self.model.predict_proba([features])[0][1]
        return float(prob)
