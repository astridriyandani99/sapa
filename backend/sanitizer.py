import re
from datetime import datetime, date, timedelta
import pandas as pd

def clean_text_field(val) -> str | None:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if s == "" or s.lower() in ["nan", "none", "null", "-"]:
        return None
    return s

def sanitize_date_str(val) -> str | None:
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if s == "" or s.lower() in ["nan", "none", "null", "-"]:
        return None
    
    # Try standard ISO or common Indonesian date formats
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y", "%Y-%m-%d %H:%M:%S"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
            
    # Try pandas to_datetime coerce
    try:
        dt = pd.to_datetime(s, errors="coerce")
        if pd.notna(dt):
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
        
    return None

def sanitize_integer(val) -> int | None:
    if val is None or pd.isna(val):
        return None
    try:
        # Extract digits if string has text like "30 hari"
        s = str(val).replace(",", ".").strip()
        nums = re.findall(r"\d+", s)
        if nums:
            return int(nums[0])
    except Exception:
        pass
    return None

def sanitize_float(val) -> float | None:
    if val is None or pd.isna(val):
        return None
    try:
        s = str(val).replace(",", ".").strip()
        nums = re.findall(r"\d+\.?\d*", s)
        if nums:
            return float(nums[0])
    except Exception:
        pass
    return None

def calculate_fallback_afu(tanggal_kunjungan_str: str | None, jumlah_hari_arv: int | None) -> str | None:
    if not tanggal_kunjungan_str:
        return None
    try:
        dt_kunj = datetime.strptime(tanggal_kunjungan_str, "%Y-%m-%d").date()
        days = jumlah_hari_arv if jumlah_hari_arv and jumlah_hari_arv > 0 else 30
        return (dt_kunj + timedelta(days=days)).strftime("%Y-%m-%d")
    except Exception:
        return None
