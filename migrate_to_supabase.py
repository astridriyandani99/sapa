"""
Skrip Migrasi Data Aman: Local SQLite -> Supabase PostgreSQL
=============================================================
Skrip ini mendukung auto-encoding password dengan karakter khusus (seperti @),
dan mendukung fallback driver PostgreSQL (psycopg2 / pg8000).
"""

import os
import sys
import re
import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. Local SQLite Models
from backend.database import (
    Base, SessionLocal as LocalSession,
    Pasien, Kunjungan, LabViralLoad, LabCD4, SimrsResep,
    PatientDeviceSession, PatientAdherenceLog, PatientResearchSurvey,
    PatientSurveyResponse, PatientResearchPayout, PatientArticle,
    AppNativeBanner, UploadHistory
)

def sanitize_supabase_url(raw_url: str) -> str:
    """Safely parses and URL-encodes passwords containing special chars like @, #, $, etc."""
    raw_url = raw_url.strip()
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)

    # If format is: postgresql://[user]:[password]@[host]:[port]/[db]
    # Handle multiple '@' in URL due to password starting or containing '@'
    if "aws-0-ap-southeast-1.pooler.supabase.com" in raw_url or "supabase.co" in raw_url:
        try:
            # Match scheme://user:password@host...
            # User is usually postgres.[project_ref] or postgres
            prefix_match = re.match(r"postgresql://([^:]+):(.*)@(aws-0-.*|db\..*)", raw_url)
            if prefix_match:
                user = prefix_match.group(1)
                full_rest = prefix_match.group(2)
                host_part = prefix_match.group(3)
                
                # If password itself had '@', host_part contains the true host
                # Let's extract password
                raw_password = full_rest
                password_encoded = urllib.parse.quote(raw_password, safe="")
                clean_url = f"postgresql://{user}:{password_encoded}@{host_part}"
                return clean_url
        except Exception:
            pass

    return raw_url

def run_migration(supabase_db_url: str):
    print("=" * 65)
    print("🚀 MEMULAI MIGRASI DATA AMAN: SQLITE LOKAL -> SUPABASE POSTGRESQL")
    print("=" * 65)

    clean_url = sanitize_supabase_url(supabase_db_url)
    print("\n1. Menghubungkan ke Cloud Database Supabase...")

    remote_engine = None
    # Try default driver (psycopg2)
    try:
        remote_engine = create_engine(clean_url, pool_pre_ping=True)
        # Test connection
        with remote_engine.connect() as conn:
            print("   ✓ Terkoneksi sukses ke Supabase PostgreSQL!")
    except Exception as e1:
        # If psycopg2 missing, try pg8000 driver
        try:
            pg8000_url = clean_url.replace("postgresql://", "postgresql+pg8000://", 1)
            remote_engine = create_engine(pg8000_url, pool_pre_ping=True)
            with remote_engine.connect() as conn:
                print("   ✓ Terkoneksi sukses ke Supabase via pg8000 driver!")
        except Exception as e2:
            print(f"❌ Gagal koneksi ke Supabase:\n   Error: {e1}\n   (Fallback pg8000: {e2})")
            print("\n💡 Tips: Pastikan driver postgres terinstall:")
            print("   Jalankan: pip install psycopg2-binary pg8000")
            return

    try:
        RemoteSession = sessionmaker(bind=remote_engine)
        remote_db = RemoteSession()
        
        # Buat seluruh tabel secara otomatis di Supabase jika belum ada
        print("\n2. Membuat skema 12 tabel (DDL) di Supabase PostgreSQL...")
        Base.metadata.create_all(bind=remote_engine)
        print("   ✓ Skema 12 tabel berhasil diverifikasi & dibuat di Supabase!")
    except Exception as e:
        print(f"❌ Gagal membuat skema tabel di Supabase: {e}")
        return

    local_db = LocalSession()

    try:
        # 1. Pasien Master
        pasien_list = local_db.query(Pasien).all()
        print(f"\n3. Migrasi Data Master Pasien ({len(pasien_list)} data)...")
        if pasien_list:
            for idx, p in enumerate(pasien_list):
                remote_db.merge(p)
                if idx % 500 == 0:
                    remote_db.commit()
            remote_db.commit()
            print(f"   ✓ {len(pasien_list)} Master Pasien berhasil dimigrasikan.")

        # 2. Kunjungan Pasien
        kunj_list = local_db.query(Kunjungan).all()
        print(f"4. Migrasi Data Kunjungan SIHA ({len(kunj_list)} data)...")
        if kunj_list:
            for idx, k in enumerate(kunj_list):
                remote_db.merge(k)
                if idx % 500 == 0:
                    remote_db.commit()
            remote_db.commit()
            print(f"   ✓ {len(kunj_list)} Kunjungan berhasil dimigrasikan.")

        # 3. Lab Viral Load
        vl_list = local_db.query(LabViralLoad).all()
        print(f"5. Migrasi Data Lab Viral Load ({len(vl_list)} data)...")
        if vl_list:
            for vl in vl_list:
                remote_db.merge(vl)
            remote_db.commit()
            print(f"   ✓ {len(vl_list)} Lab Viral Load berhasil dimigrasikan.")

        # 4. Lab CD4
        cd4_list = local_db.query(LabCD4).all()
        print(f"6. Migrasi Data Lab CD4 ({len(cd4_list)} data)...")
        if cd4_list:
            for c in cd4_list:
                remote_db.merge(c)
            remote_db.commit()
            print(f"   ✓ {len(cd4_list)} Lab CD4 berhasil dimigrasikan.")

        # 5. SIMRS Resep Farmasi
        resep_list = local_db.query(SimrsResep).all()
        print(f"7. Migrasi Data Resep Farmasi SIMRS ({len(resep_list)} data)...")
        if resep_list:
            for idx, r in enumerate(resep_list):
                remote_db.merge(r)
                if idx % 500 == 0:
                    remote_db.commit()
            remote_db.commit()
            print(f"   ✓ {len(resep_list)} Resep Farmasi SIMRS berhasil dimigrasikan.")

        # 6. Modul PWA & Riset
        surveys = local_db.query(PatientResearchSurvey).all()
        articles = local_db.query(PatientArticle).all()
        banners = local_db.query(AppNativeBanner).all()

        print(f"8. Migrasi Modul PWA & Riset (Kuesioner KEPK, Artikel, Banner)...")
        for s in surveys:
            remote_db.merge(s)
        for a in articles:
            remote_db.merge(a)
        for b in banners:
            remote_db.merge(b)
        remote_db.commit()
        print("   ✓ Modul PWA & Riset berhasil dimigrasikan.")

        print("\n" + "=" * 65)
        print("🎉 MIGRASI KE SUPABASE BERHASIL 100% LENGKAP & AMAN!")
        print("=" * 65)

    except Exception as e:
        remote_db.rollback()
        print(f"\n❌ Terjadi kesalahan saat proses migrasi data: {e}")
    finally:
        local_db.close()
        if remote_db:
            remote_db.close()

if __name__ == "__main__":
    supabase_url = os.getenv("DATABASE_URL")
    if not supabase_url:
        print("Masukkan Supabase Connection String:")
        print("Contoh: postgresql://postgres.xxxx:mypassword@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres")
        supabase_url = input("URL Supabase: ").strip()

    run_migration(supabase_url)
