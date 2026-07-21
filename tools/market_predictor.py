#!/usr/bin/env python3
from __future__ import annotations
"""市场方向预测 — Transformer + LSTM 混合模型预测未来N日市场下跌概率。

输入特征序列（过去60个交易日）：
  1. 日收益率
  2. 14日RSI
  3. MACD柱状图
  4. 距MA20偏离度
  5. 20日波动率
  6. 成交量代理（日收益率绝对值的MA）

输出：P(未来10日累计收益 < 0) — 下跌概率

训练方式：Walk-forward，在回测中每个N天重新训练
  - 用截止到T的所有历史数据训练
  - 预测T+1到T+10的市场方向
  - 在T+10后评估并更新模型

轻量级实现：单层Transformer encoder + MLP分类头
"""
import math
import statistics
from typing import List, Dict, Tuple, Optional
from collections import deque

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


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


def build_feature_sequence(nav_values: List[float], seq_len: int = 60) -> Optional[np.ndarray]:
    """构建长度为seq_len的特征序列，每个时间步6个特征。

    Returns: shape (seq_len, 6) or None if insufficient data
    """
    if len(nav_values) < seq_len + 35:  # 需要足够数据计算MACD
        return None

    features = []
    for i in range(len(nav_values) - seq_len, len(nav_values)):
        window = nav_values[:i+1]
        # 特征1: 日收益率
        if i > 0 and nav_values[i-1] > 0:
            ret = (nav_values[i] / nav_values[i-1] - 1)
        else:
            ret = 0.0
        # 特征2: RSI
        rsi = _compute_rsi(window, 14) / 100.0  # 归一化到0-1
        # 特征3: MACD柱状图
        macd_h = _compute_macd_hist(window)
        # 特征4: 距MA20偏离度
        if len(window) >= 20:
            ma20 = statistics.mean(window[-20:])
            dev = (nav_values[i] / ma20 - 1) if ma20 > 0 else 0
        else:
            dev = 0
        # 特征5: 20日波动率
        vol = _compute_vol(window, 20)
        # 特征6: 日收益率绝对值的5日MA（成交量代理）
        if len(window) >= 6:
            recent_rets = []
            for j in range(max(1, len(window)-5), len(window)):
                if window[j-1] > 0:
                    recent_rets.append(abs(window[j] / window[j-1] - 1))
            vol_proxy = statistics.mean(recent_rets) if recent_rets else 0
        else:
            vol_proxy = 0

        features.append([ret, rsi, macd_h, dev, vol, vol_proxy])

    arr = np.array(features, dtype=np.float32)
    # 归一化：每个特征列z-score
    for col in range(arr.shape[1]):
        mean = arr[:, col].mean()
        std = arr[:, col].std()
        if std > 1e-8:
            arr[:, col] = (arr[:, col] - mean) / std

    return arr


if TORCH_AVAILABLE:

    class MarketTransformer(nn.Module):
        """轻量级Transformer预测市场下跌概率。"""

        def __init__(self, seq_len=60, n_features=6, d_model=64, nhead=4, num_layers=2):
            super().__init__()
            self.input_proj = nn.Linear(n_features, d_model)
            self.pos_encoding = nn.Parameter(torch.randn(1, seq_len, d_model) * 0.02)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model, nhead=nhead, dim_feedforward=128,
                dropout=0.1, batch_first=True
            )
            self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.classifier = nn.Sequential(
                nn.Linear(d_model, 32),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(32, 1),
                nn.Sigmoid()
            )

        def forward(self, x):
            # x: (batch, seq_len, n_features)
            x = self.input_proj(x) + self.pos_encoding
            x = self.transformer(x)
            # 用最后一个时间步的输出做分类
            return self.classifier(x[:, -1, :]).squeeze(-1)


class MarketPredictor:
    """Walk-forward市场预测器，在回测中逐步训练和预测。"""

    def __init__(self, seq_len=60, fwd_days=10, retrain_interval=20):
        self.seq_len = seq_len
        self.fwd_days = fwd_days
        self.retrain_interval = retrain_interval
        self.model = None
        self.training_data = []  # [(feature_seq, label)]
        self._last_train_count = 0
        self._is_trained = False

        if TORCH_AVAILABLE:
            self.model = MarketTransformer(seq_len=seq_len)
            self.optimizer = None

    def collect_sample(self, nav_values: List[float], current_idx: int) -> Optional[Tuple]:
        """收集一个训练样本：在current_idx处构建特征，用fwd_days后的收益做标签。"""
        if current_idx < self.seq_len + 35:
            return None
        if current_idx + self.fwd_days >= len(nav_values):
            return None  # 没有前瞻数据

        # 构建特征序列
        window = nav_values[:current_idx+1]
        feat = build_feature_sequence(window, self.seq_len)
        if feat is None:
            return None

        # 标签：未来fwd_days的累计收益是否为负
        future_ret = (nav_values[current_idx + self.fwd_days] / nav_values[current_idx] - 1)
        label = 1 if future_ret < 0 else 0

        return (feat, label)

    def add_training_data(self, nav_values: List[float], cutoff_idx: int):
        """从历史数据中提取训练样本，截止到cutoff_idx。"""
        # 每隔5天采样一个，避免过密
        step = 5
        for i in range(self.seq_len + 35, cutoff_idx - self.fwd_days, step):
            sample = self.collect_sample(nav_values, i)
            if sample is not None:
                self.training_data.append(sample)

    def train(self):
        """训练模型。"""
        if not TORCH_AVAILABLE or len(self.training_data) < 50:
            return False

        # 准备数据
        X = torch.FloatTensor(np.array([s[0] for s in self.training_data]))
        y = torch.FloatTensor([s[1] for s in self.training_data])

        # 类别平衡
        pos_weight = (len(y) - y.sum()) / max(y.sum(), 1)

        self.model.train()
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-3, weight_decay=1e-4)
        criterion = nn.BCELoss()

        # 训练50个epoch
        for epoch in range(50):
            self.optimizer.zero_grad()
            pred = self.model(X)
            loss = criterion(pred, y)
            loss.backward()
            self.optimizer.step()

        self._is_trained = True
        self._last_train_count = len(self.training_data)
        return True

    def predict(self, nav_values: List[float]) -> float:
        """预测当前时点的下跌概率。

        Returns: P(未来fwd_days收益为负) — 0到1之间的概率
        """
        if not self._is_trained or not TORCH_AVAILABLE:
            return 0.5  # 未训练，返回中性概率

        feat = build_feature_sequence(nav_values, self.seq_len)
        if feat is None:
            return 0.5

        self.model.eval()
        with torch.no_grad():
            x = torch.FloatTensor(feat).unsqueeze(0)  # (1, seq_len, n_features)
            prob = self.model(x).item()

        return prob

    def should_retrain(self, new_sample_count: int) -> bool:
        """判断是否需要重新训练。"""
        if not self._is_trained:
            return new_sample_count >= 50
        return new_sample_count - self._last_train_count >= self.retrain_interval
