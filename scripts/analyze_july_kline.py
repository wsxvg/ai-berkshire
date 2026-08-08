#!/usr/bin/env python3
"""Analyze July 2026 crash from K-line perspective to find predictive signals."""
import json, os, sys
sys.path.insert(0, '.')

DATA_DIR = 'C:/fund/data'

# Load user trades
trades = json.load(open(os.path.join(DATA_DIR, 'expanded_user_trades.json')))
print('=== TRADES TYPE:', type(trades))
if isinstance(trades, dict):
    keys = list(trades.keys())[:10]
    print('Keys sample:', keys)
    first_key = keys[0]
    print('First value sample:', trades[first_key])
elif isinstance(trades, list):
    print('First entry:', trades[0] if trades else 'EMPTY')

# Load a sample chart (000001 - 华夏成长?)
chart = json.load(open(os.path.join(DATA_DIR, 'fund_charts/000001.json')))
total_entries = len(chart)
print('\n=== CHART 000001 ===')
print('Total entries:', total_entries)
print('Last 10 entries:')
for entry in chart[-10:]:
    print('  %s  %.2f' % (entry['xAxis'], entry['yAxis']))

# Find June-July 2026 entries
june_july = [e for e in chart if e['xAxis'] >= '2026-06-01']
print('\n=== June-July 2026 for 000001 ===')
print('Entries in June-July:', len(june_july))
for e in june_july[-20:]:
    print('  %s  %.2f' % (e['xAxis'], e['yAxis']))

# Load fund_name_map to find CSI300 proxy
name_map = json.load(open(os.path.join(DATA_DIR, 'fund_name_map.json')))
print('\n=== NAME MAP TYPE:', type(name_map))
if isinstance(name_map, dict):
    # Find CSI300 or index funds
    for k, v in list(name_map.items())[:5]:
        print('  %s: %s' % (k, str(v)[:60]))
elif isinstance(name_map, list):
    for item in name_map[:5]:
        print(' ', str(item)[:100])

# Check for CSI300 or 沪深300 in fund charts
charts_dir = os.path.join(DATA_DIR, 'fund_charts')
csi_codes = []
print('\n=== CSI300/INDEX funds in charts ===')
for f in os.listdir(charts_dir)[:5]:
    code = f.replace('.json', '')
    name = name_map.get(code, '') if isinstance(name_map, dict) else ''
    if '沪深300' in str(name) or 'CSI' in str(name) or '300' in str(name)[:20]:
        csi_codes.append(code)
        print('  FOUND: %s %s' % (code, name))

# Also look in fund_charts_index.json
idx_data = json.load(open(os.path.join(DATA_DIR, 'fund_charts_index.json')))
print('\n=== CHARTS INDEX TYPE:', type(idx_data))
if isinstance(idx_data, list):
    print('Total index entries:', len(idx_data))
    for item in idx_data[:3]:
        print('  ', str(item)[:200])
