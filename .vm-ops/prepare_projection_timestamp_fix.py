"""Patch only the inspected timestamp parser; preserve all readiness checks."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'backend/db/services/price_storage_v2_projection_gate.py'
s=p.read_text()
old='''    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None'''
new='''    # PostgreSQL omits trailing fractional zeros. Python 3.10 accepts only
    # three or six fractional digits; normalize precision without changing the
    # represented instant before parsing (e.g. .13337 -> .133370).
    import re
    text = re.sub(r"\\.(\\d{1,6})(?=Z$|[+-]\\d{2}:\\d{2}$|$)",
                  lambda match: "." + match.group(1).ljust(6, "0"), text)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None'''
if 'PostgreSQL omits trailing fractional zeros' not in s:
    if s.count(old)!=1:raise RuntimeError('timestamp parser changed; refusing patch')
    p.write_text(s.replace(old,new,1))
print('POSTGRES_TIMESTAMP_PRECISION_NORMALIZED=true')
