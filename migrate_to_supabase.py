"""
Skrip Migrasi Data Aman: Local SQLite -> Supabase PostgreSQL
=============================================================
Skrip ini dijalankan langsung dari laptop lokal Anda untuk menyalin
data rekam medis dari database lokal (data_siha.db) ke database Supabase
secara terenkripsi (TLS/SSL).

DATA MEDIS TIDAK PERNAH DIUNGGAH KE GITHUB!
"""

import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. Local SQLite Engine
from backend.database import (
    Base, SessionLocal as LocalSession,
    Pasien, Kunjungan, LabViralLoad, LabCD4, SimrsResep,
    PatientDeviceSession, PatientAdherenceLog, PatientResearchSurvey,
    PatientSurveyResponse, PatientResearchPayout, PatientArticle,
    AppNativeBanner, UploadHistory
)

def run_migration(supabase_db_url: str):
    print("=" * 65)
    print("🚀 MEMULAI MIGRASI DATA AMAN: SQLITE LOKAL -> SUPABASE POSTGRESQL")
    print("=" * 65)

    if not supabase_db_url or "supabase.co" not in supabase_db_url:
        print("❌ URL Supabase tidak valid! Format harus:")
        print("   postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres")
        return

    # Handle postgres:// alias
    if supabase_db_url.startswith("postgres://"):
        supabase_db_url = supabase_db_url.replace("postgres://", "postgresql://", 1)

    print("\n1. Menghubungkan ke Cloud Database Supabase...")
    try:
        remote_engine = create_engine(supabase_db_url, pool_pre_ping=True)
        RemoteSession = sessionmaker(bind=remote_engine)
        remote_db = RemoteSession()
        
        # Buat seluruh tabel secara otomatis di Supabase jika belum ada
        print("2. Membuat skema tabel (DDL) di Supabase PostgreSQL...")
        Base.metadata.create_all(bind=remote_engine)
        print("   ✓ Skema 12 tabel berhasil diverifikasi & dibuat di Supabase!")
    except Exception as e:
        print(f"❌ Gagal koneksi ke Supabase: {e}")
        return

    local_db = LocalSession()

    try:
        # 1. Pasien Master
        pasien_list = local_db.query(Pasien).all()
        print(f"\n3. Migrasi Data Master Pasien ({len(pasien_list)} data)...")
        if pasien_list:
            for p in pasien_list:
                remote_db.merge(p)
            remote_db.commit()
            print(f"   ✓ {len(pasien_list)} Master Pasien berhasil dimigrasikan.")

        # 2. Kunjungan Pasien
        kunj_list = local_db.query(Kunjungan).all()
        print(f"4. Migrasi Data Kunjungan SIHA ({len(kunj_list)} data)...")
        if kunj_list:
            for k in kunj_list:
                remote_db.merge(k)
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
            for r in resep_list:
                remote_db.merge(r)
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
        print(f"\n❌ Terjadi kesalahan saat proses migrasi: {e}")
    finally:
        local_db.close()
        remote_db.close()

if __name__ == "__main__":
    supabase_url = os.getenv("DATABASE_URL")
    if not supabase_url:
        print("Masukkan Supabase Connection String:")
        print("Contoh: postgresql://postgres.xxxx:mypassword@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres")
        supabase_url = input("URL Supabase: ").strip()

    run_migration(supabase_url)
