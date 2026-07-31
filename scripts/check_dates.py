"""Check date fields in trading data."""
import json

with open('backtest/data/trading_history.json') as f:
    th = json.load(f)

print(f"trading_history.json: {len(th)} records")
print()

# Sample entries
print("=== Sample records ===")
for r in th[:3]:
    print(f"  summary={r.get('summary')}")
    print(f"  _date_prefix={r.get('_date_prefix')}")
    print(f"  _user={r.get('_user')}")
    print()

# Unique prefixes
prefixes = sorted(set(r.get('_date_prefix', '') for r in th))
print(f"=== Unique _date_prefix values ({len(prefixes)} total) ===")
print("First 20:", prefixes[:20])
print()

# Check trading_by_date_fixed
with open('backtest/data/trading_by_date_fixed.json') as f:
    td = json.load(f)

print(f"trading_by_date_fixed.json: {len(td)} dates")
td_dates = sorted(td.keys())
print(f"Range: {td_dates[0]} to {td_dates[-1]}")

# Check if first date in trading_by_date has records from the corresponding trading_history
first_td_date = td_dates[0]
print(f"\n=== First TD date: {first_td_date} ===")
print(f"Records in td['{first_td_date}']: {len(td[first_td_date])}")
for r in td[first_td_date][:2]:
    print(f"  {r}")

# Cross-reference: find year info from summary
print("\n=== Year analysis from summary ===")
years = set()
for r in th:
    s = r.get('summary', '')
    if len(s) >= 10:
        # Try to find year
        parts = s.split(' ')
        if len(parts) >= 1:
            date_part = parts[0]
            year_part = date_part.split('-')[0] if '-' in date_part else None
            if year_part and year_part.isdigit() and len(year_part) == 4:
                years.add(year_part)

print(f"Years found in summary: {sorted(years)}")

# Alternative: look for year in other fields
print("\n=== Other date fields ===")
sample = th[0]
print("All keys in first record:", list(sample.keys()))
for k, v in sample.items():
    print(f"  {k}: {v}")
