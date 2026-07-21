#!/usr/bin/env python3
from __future__ import annotations
"""LightGBM市场预测 — 替代Transformer，CPU秒级训练

预测未来N日市场下跌概率。
特点：不需要torch，lightgbm在CPU上秒级训练，无需GPU。
"""
import math, statistics
from typing import List, Dict, Tuple, Optional
from collections import deque

try:
    import lightgbm as lgb
    import numpy as np
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False


def _to_nav(values: List[float]) -> List[float]:
    return [(100 + v) / 100 for v in values]

def _compute_rsi(nav_values: List[float], period: int = 14) -> float:
    if len(nav_values) < period + 1:
        return 50.0
    deltas = [nav_values[i] - nav_values[i-1] for i in range(1, len(nav_values))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))

def _compute_macd_hist(nav_values: List[float]) -> float:
    if len(nav_values) < 35:
        return 0.0
    def ema_series(data, period):
        mult = 2 / (period + 1)
        result = [data[0]]
        for v in data[1:]:
            result.append(v * mult + result[-1] * (1 - mult))
        return result
    ema_fast = ema_series(nav_values, 12)
    ema_slow = ema_series(nav_values, 26)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    sig_mult = 2 / 10
    sig_line = [macd_line[0]]
    for v in macd_line[1:]:
        sig_line.append(v * sig_mult + sig_line[-1] * (1 - sig_mult))
    return macd_line[-1] - sig_line[-1]

def _compute_vol(nav_values: List[float], lookback: int = 20) -> float:
    if len(nav_values) < lookback + 1:
        return 0.01
    recent = nav_values[-(lookback+1):]
    rets = [(recent[i] / recent[i-1] - 1) for i in range(1, len(recent)) if recent[i-1] > 0]
    return statistics.stdev(rets) if len(rets) > 5 else 0.01


def build_features(nav_values: List[float], seq_len: int = 60) -> Optional[np.ndarray]:
    """构建特征向量（单时间步，聚合过去seq_len天的信息）"""
    if len(nav_values) < seq_len + 35:
        return None
    
    window = nav_values[-(seq_len+1):]
    rets = [(window[i] / window[i-1] - 1) if window[i-1] > 0 else 0 for i in range(1, len(window))]
    
    # 特征聚合
    ret_5 = sum(rets[-5:]) / 5 if len(rets) >= 5 else 0
    ret_10 = sum(rets[-10:]) / 10 if len(rets) >= 10 else 0
    ret_20 = sum(rets[-20:]) / 20 if len(rets) >= 20 else 0
    ret_60 = sum(rets[-60:]) / min(60, len(rets)) if rets else 0
    
    navs = _to_nav([float(v) for v in [0]])  # dummy
    rsi = _compute_rsi(window, 14)
    macd_h = _compute_macd_hist(window)
    vol = _compute_vol(window, 20)
    
    # 距MA20偏离度
    ma20 = statistics.mean(window[-20:]) if len(window) >= 20 else window[-1]
    dev = (window[-1] / ma20 - 1) if ma20 > 0 else 0
    
    # 最大回撤(20日内)
    recent_20 = window[-20:] if len(window) >= 20 else window
    peak = max(recent_20)
    dd = (window[-1] / peak - 1) if peak > 0 else 0
    
    # 布林带位置
    if len(window) >= 20:
        std = statistics.stdev(recent_20)
        bb_pct = (window[-1] - min(recent_20)) / (max(recent_20) - min(recent_20) + 1e-8)
    else:
        bb_pct = 0.5
    
    features = np.array([
        ret_5, ret_10, ret_20, ret_60,
        rsi / 100.0, macd_h, dev, vol, dd, bb_pct,
        # 交互特征
        rsi / 100.0 * vol, ret_5 * ret_20, dev * vol,
    ], dtype=np.float32)
    
    return features


class LGBMarketPredictor:
    """LightGBM市场预测器 — walk-forward训练"""
    
    def __init__(self, seq_len=60, fwd_days=10, retrain_interval=20, crash_threshold=0.0):
        self.seq_len = seq_len
        self.fwd_days = fwd_days
        self.retrain_interval = retrain_interval
        self.crash_threshold = crash_threshold
        self.model = None
        self.training_data_X = []
        self.training_data_y = []
        self._last_train_count = 0
        self._is_trained = False
    
    def collect_sample(self, nav_values: List[float], current_idx: int) -> Optional[Tuple]:
        if current_idx < self.seq_len + 35:
            return None
        if current_idx + self.fwd_days >= len(nav_values):
            return None
        
        window = nav_values[:current_idx + 1]
        feat = build_features(window, self.seq_len)
        if feat is None:
            return None
        
        future_ret = (nav_values[current_idx + self.fwd_days] / nav_values[current_idx] - 1)
        label = 1 if future_ret < self.crash_threshold else 0
        
        return (feat, label)
    
    def add_training_data(self, nav_values: List[float], cutoff_idx: int):
        step = 5
        for i in range(self.seq_len + 35, cutoff_idx - self.fwd_days, step):
            sample = self.collect_sample(nav_values, i)
            if sample is not None:
                self.training_data_X.append(sample[0])
                self.training_data_y.append(sample[1])
    
    def should_retrain(self, current_count: int) -> bool:
        return current_count - self._last_train_count >= self.retrain_interval
    
    def train(self) -> bool:
        if not LGB_AVAILABLE or len(self.training_data_X) < 50:
            return False
        
        X = np.array(self.training_data_X)
        y = np.array(self.training_data_y)
        
        if y.sum() < 5:  # 正样本太少
            return False
        
        self.model = lgb.LGBMClassifier(
            n_estimators=50, max_depth=4, num_leaves=15,
            learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
            min_child_samples=5, verbose=-1, n_jobs=1
        )
        self.model.fit(X, y)
        
        self._is_trained = True
        self._last_train_count = len(self.training_data_X)
        return True
    
    def predict(self, nav_values: List[float]) -> float:
        """返回 P(未来fwd_days收益 < crash_threshold)"""
        if not self._is_trained or not LGB_AVAILABLE:
            return 0.5
        
        feat = build_features(nav_values, self.seq_len)
        if feat is None:
            return 0.5
        
        try:
            prob = self.model.predict_proba(feat.reshape(1, -1))[0]
            return float(prob[1]) if len(prob) > 1 else 0.5
        except Exception:
            return 0.5
