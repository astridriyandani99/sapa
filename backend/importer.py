import os
import re
import uuid
import datetime
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from backend.database import (
    SessionLocal, init_db, Pasien, Kunjungan, LabViralLoad, LabCD4, SimrsResep, UploadHistory, BASE_DIR
)

from backend.sanitizer import sanitize_date_str, clean_text_field, sanitize_integer, sanitize_float, calculate_fallback_afu
from backend.schemas import PasienIngestSchema, KunjunganIngestSchema, LabViralLoadIngestSchema, LabCD4IngestSchema

def clean_val(val):
    return clean_text_field(val)

def parse_date_str(val):
    return sanitize_date_str(val)

def parse_float(val):
    if pd.isna(val) or val is None:
        return None
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None

def parse_int(val):
    if pd.isna(val) or val is None:
        return None
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None

def calculate_imt(bb, tb):
    if bb and tb and tb > 50 and bb > 10:
        tb_m = tb / 100.0
        imt = round(bb / (tb_m ** 2), 2)
        if imt < 18.5:
            cat = "Underweight (< 18.5)"
        elif imt <= 22.9:
            cat = "Normal (18.5 - 22.9)"
        elif imt <= 24.9:
            cat = "Overweight (23.0 - 24.9)"
        else:
            cat = "Obesitas (>= 25.0)"
        return imt, cat
    return None, None

def classify_regimen(rejimen_name):
    if not rejimen_name:
        return "Tanpa ARV / Belum Ada"
    s = str(rejimen_name).upper()
    if "TDF" in s and "DTG" in s:
        return "TLD (Lini 1 Utama)"
    elif "TDF" in s and "EFV" in s:
        return "TLE (Lini 1 Alternatif)"
    elif "ZDV" in s or "AZT" in s:
        return "ZDV-based (Lini Alternatif/2)"
    elif "LPV" in s or "ATV" in s:
        return "PI-based (Lini 2)"
    elif "ABC" in s:
        return "ABC-based (Pediatrik/Khusus)"
    else:
        return "Rejimen Lainnya"

def classify_viral_load(val):
    if pd.isna(val) or val is None or str(val).strip() == "":
        return None, "Pending / Belum Ada", False, False
    
    s = str(val).strip()
    s_lower = s.lower()
    
    if any(k in s_lower for k in ["tidak terdeteksi", "target not detected", "tnd", "undetected", "undetectable"]):
        return 0.0, "Undetectable (< TND)", True, True
    
    if "<" in s_lower:
        num = parse_float(re.sub(r"[^\d.]", "", s))
        val_num = num if num is not None else 20.0
        return val_num, "Tersupresi (< 40 - 200 copies/mL)", True, True
    
    if "error" in s_lower or "invalid" in s_lower:
        return None, "Error / Invalid", False, False
        
    num = parse_float(s)
    if num is not None:
        if num < 200:
            return num, "Tersupresi (< 200 copies/mL)", True, True
        elif num < 1000:
            return num, "Viremia Rendah (200 - 999 copies/mL)", True, False
        else:
            return num, "Gagal Virologis / Tidak Tersupresi (>= 1,000 copies/mL)", False, False
            
    return None, f"Lainnya ({s})", False, False

def classify_cd4(val):
    num = parse_float(val)
    if num is None:
        return None, None
    if num < 200:
        return num, "Imunodefisiensi Berat (< 200)"
    elif num < 350:
        return num, "Imunodefisiensi Sedang (200 - 349)"
    elif num < 500:
        return num, "Imunodefisiensi Ringan (350 - 499)"
    else:
        return num, "Normal / Tersupresi Baik (>= 500)"

def detect_file_type(df, filename: str = ""):
    fn_lower = filename.lower() if filename else ""
    cols_joined = " ".join([str(c).lower() for c in df.columns])
    
    # 1. Filename-based explicit keywords
    if any(k in fn_lower for k in ["kunjunganfarmasi", "kunjungan_farmasi", "farmasi", "simrs", "resep_arv"]):
        return "SIMRS_ARV"
    if any(k in fn_lower for k in ["data pasien", "data_pasien", "datapasien"]):
        return "PASIEN"
    if any(k in fn_lower for k in ["kunjungan pasien", "kunjungan_pasien"]):
        return "KUNJUNGAN"
    if any(k in fn_lower for k in ["viral load", "viral_load", "pemeriksaan viral load"]):
        return "VIRAL_LOAD"
    if any(k in fn_lower for k in ["cd4"]):
        return "CD4"

    # 2. Check column patterns for SIMRS / Kunjungan Farmasi
    if any(k in cols_joined for k in ["item_code_desc", "outlet_name", "bill_number", "bill_date", "nama_dokter"]) or \
       ("qty" in cols_joined and any(k in cols_joined for k in ["obat", "desc", "resep", "mr_no", "no_rm", "depo"])):
        return "SIMRS_ARV"
        
    # 3. Check SIHA standard entity formats by specific unique column combinations
    if "tanggal pemeriksaan" in cols_joined or "viral load" in cols_joined or "no order" in cols_joined or ("hasil" in cols_joined and "pemeriksa" in cols_joined):
        return "VIRAL_LOAD"
    elif "nilai cd4" in cols_joined or "hasil cd4" in cols_joined:
        return "CD4"
    elif "tanggal register" in cols_joined or "status nik" in cols_joined or "domisili" in cols_joined or "kunjungan terakhir" in cols_joined or ("pasien id" in cols_joined and "nik" in cols_joined):
        return "PASIEN"
    elif "tanggal kunjungan" in cols_joined or "alasan kunjungan" in cols_joined or "nama rejimen" in cols_joined or "jumlah hari arv" in cols_joined:
        return "KUNJUNGAN"
    elif "kunjungan" in cols_joined:
        return "KUNJUNGAN"
        
    return "UNKNOWN"

def read_excel_smart(file_path_or_bytes):
    # Try reading directly or skip row 1 if row 0 was title
    df = pd.read_excel(file_path_or_bytes, nrows=5)
    first_cell = str(df.columns[0]).lower() if len(df.columns) > 0 else ""
    if "data pasien" in first_cell or "kunjungan pasien" in first_cell or "hasil pemeriksaan" in first_cell or "unnamed" in first_cell:
        df_full = pd.read_excel(file_path_or_bytes, skiprows=1)
    else:
        df_full = pd.read_excel(file_path_or_bytes)
    
    # Strip whitespace from column names
    df_full.columns = [str(c).strip() for c in df_full.columns]
    return df_full

def import_pasien_data(df: pd.DataFrame, db: Session, batch_id: str):
    processed = 0
    inserted = 0
    updated = 0

    col_map = {
        "pasien_id": ["Pasien ID", "ID Pasien", "PasienID", "No Pasien"],
        "no_rekam_medik": ["No Rekam Medik", "No. Rekam Medik", "No RM", "No Rekam Medis", "Nomor RM"],
        "no_reg_nas": ["No Reg Nas", "No. Reg Nas", "No Regnas"],
        "nama_pasien": ["Nama Pasien", "Nama"],
        "nik": ["NIK/No. Identitas", "NIK", "No. Identitas"],
        "status_nik": ["Status NIK"],
        "tanggal_lahir": ["Tanggal Lahir", "Tgl Lahir"],
        "umur": ["Umur", "Usia"],
        "kategori_umur": ["Kategori Umur"],
        "jenis_kelamin": ["Jenis Kelamin", "Gender", "JK"],
        "pekerjaan": ["Pekerjaan"],
        "suku": ["Suku"],
        "warga_negara": ["Warga Negara", "Kewarganegaraan"],
        "alamat_provinsi": ["Alamat Provinsi"],
        "alamat_kabupaten": ["Alamat Kabupaten", "Alamat Kota"],
        "alamat_kecamatan": ["Alamat Kecamatan"],
        "alamat_kelurahan": ["Alamat Kelurahan", "Alamat Desa"],
        "alamat": ["Alamat"],
        "domisili_provinsi": ["Domisili Provinsi"],
        "domisili_kabupaten": ["Domisili Kabupaten", "Domisili Kota"],
        "domisili_kecamatan": ["Domisili Kecamatan"],
        "domisili_kelurahan": ["Domisili Kelurahan", "Domisili Desa"],
        "alamat_domisili": ["Alamat Domisili"],
        "tanggal_register": ["Tanggal Register", "Tgl Register"],
        "kunjungan_terakhir": ["Kunjungan Terakhir"],
        "asal_rujukan": ["Asal Rujukan"],
        "kelompok_populasi": ["Kelompok Populasi", "Populasi Kunci"],
        "stadium_klinis_awal": ["Stadium Klinis"],
        "status_odhiv": ["Status ODHIV"],
        "status_odhiv_pdp": ["Status ODHIV dalam PDP", "Status PDP"],
        "tanggal_konfirmasi_hiv": ["Tanggal Konfirmasi HIV"],
        "tanggal_masuk_perawatan": ["Tanggal Masuk Perawatan"],
        "tanggal_mulai_art": ["Tanggal Mulai ART"],
        "tanggal_lost_to_follow_up": ["Tanggal Lost To Follow Up", "Tanggal LTFU"],
        "rujuk_masuk": ["Rujuk Masuk"],
        "rujuk_masuk_dari_upk": ["Rujuk Masuk dari UPK"],
        "rujuk_keluar": ["Rujuk Keluar"],
        "rujuk_keluar_ke_upk": ["Rujuk Keluar ke UPK"],
        "tanggal_rujuk_keluar": ["Tanggal Rujuk Keluar"],
        "tanggal_meninggal": ["Tanggal diketahui meninggal", "Tanggal Meninggal"],
    }

    def get_first_val(row, aliases):
        for a in aliases:
            if a in row and pd.notna(row[a]):
                return row[a]
        return None

    # Preload existing patients into a dictionary for instant in-memory lookup
    existing_pasien_dict = {p.pasien_id: p for p in db.query(Pasien).all()}
    new_pasien_objects = []

    for _, row in df.iterrows():
        p_id_raw = get_first_val(row, col_map["pasien_id"])
        if not p_id_raw:
            continue
        p_id = str(p_id_raw).strip()
        processed += 1

        is_new = False
        if p_id in existing_pasien_dict:
            pasien = existing_pasien_dict[p_id]
            updated += 1
        else:
            is_new = True
            pasien = Pasien(pasien_id=p_id)
            existing_pasien_dict[p_id] = pasien
            new_pasien_objects.append(pasien)
            inserted += 1

        # Populate / Update fields
        no_rm = clean_val(get_first_val(row, col_map["no_rekam_medik"]))
        if no_rm:
            pasien.no_rekam_medik = no_rm
        no_reg = clean_val(get_first_val(row, col_map["no_reg_nas"]))
        if no_reg:
            pasien.no_reg_nas = no_reg
        nama = clean_val(get_first_val(row, col_map["nama_pasien"]))
        if nama:
            pasien.nama_pasien = nama
        nik = clean_val(get_first_val(row, col_map["nik"]))
        if nik:
            pasien.nik = nik
        status_nik = clean_val(get_first_val(row, col_map["status_nik"]))
        if status_nik:
            pasien.status_nik = status_nik
        
        tgl_lahir = parse_date_str(get_first_val(row, col_map["tanggal_lahir"]))
        if tgl_lahir:
            pasien.tanggal_lahir = tgl_lahir
        umur = parse_int(get_first_val(row, col_map["umur"]))
        if umur is not None:
            pasien.umur = umur
        kat_umur = clean_val(get_first_val(row, col_map["kategori_umur"]))
        if kat_umur:
            pasien.kategori_umur = kat_umur
        jk = clean_val(get_first_val(row, col_map["jenis_kelamin"]))
        if jk:
            pasien.jenis_kelamin = jk
        pekerjaan = clean_val(get_first_val(row, col_map["pekerjaan"]))
        if pekerjaan:
            pasien.pekerjaan = pekerjaan
        suku = clean_val(get_first_val(row, col_map["suku"]))
        if suku:
            pasien.suku = suku
        wn = clean_val(get_first_val(row, col_map["warga_negara"]))
        if wn:
            pasien.warga_negara = wn
        
        # Alamat & Domisili
        for col_name in ["alamat_provinsi", "alamat_kabupaten", "alamat_kecamatan", "alamat_kelurahan", "alamat",
                         "domisili_provinsi", "domisili_kabupaten", "domisili_kecamatan", "domisili_kelurahan", "alamat_domisili"]:
            val = clean_val(get_first_val(row, col_map[col_name]))
            if val:
                setattr(pasien, col_name, val)
        
        # Registrasi & Rujukan
        tgl_reg = parse_date_str(get_first_val(row, col_map["tanggal_register"]))
        if tgl_reg:
            pasien.tanggal_register = tgl_reg
        tgl_kt = parse_date_str(get_first_val(row, col_map["kunjungan_terakhir"]))
        if tgl_kt:
            pasien.kunjungan_terakhir = tgl_kt
        asal_ruj = clean_val(get_first_val(row, col_map["asal_rujukan"]))
        if asal_ruj:
            pasien.asal_rujukan = asal_ruj
        pop = clean_val(get_first_val(row, col_map["kelompok_populasi"]))
        if pop:
            pasien.kelompok_populasi = pop
        stadium = clean_val(get_first_val(row, col_map["stadium_klinis_awal"]))
        if stadium:
            pasien.stadium_klinis_awal = stadium
        st_odh = clean_val(get_first_val(row, col_map["status_odhiv"]))
        if st_odh:
            pasien.status_odhiv = st_odh
        st_pdp = clean_val(get_first_val(row, col_map["status_odhiv_pdp"]))
        if st_pdp:
            pasien.status_odhiv_pdp = st_pdp
        
        for date_fld in ["tanggal_konfirmasi_hiv", "tanggal_masuk_perawatan", "tanggal_mulai_art", 
                         "tanggal_lost_to_follow_up", "tanggal_rujuk_keluar", "tanggal_meninggal"]:
            d_val = parse_date_str(get_first_val(row, col_map[date_fld]))
            if d_val:
                setattr(pasien, date_fld, d_val)
                
        for str_fld in ["rujuk_masuk", "rujuk_masuk_dari_upk", "rujuk_keluar", "rujuk_keluar_ke_upk"]:
            s_val = clean_val(get_first_val(row, col_map[str_fld]))
            if s_val:
                setattr(pasien, str_fld, s_val)

    if new_pasien_objects:
        db.bulk_save_objects(new_pasien_objects)
    db.commit()
    return processed, inserted, updated

def import_kunjungan_data(df: pd.DataFrame, db: Session, batch_id: str):
    processed = 0
    inserted = 0
    updated = 0

    # Preload existing patients in 1 query
    existing_pasien_ids = set(r[0] for r in db.query(Pasien.pasien_id).all())
    missing_pasien_map = {}
    kunjungan_objects = []

    for _, row in df.iterrows():
        p_id_raw = row.get("Pasien ID") or row.get("ID Pasien")
        if pd.isna(p_id_raw):
            continue
        p_id = str(p_id_raw).strip()
        tgl_kunj = parse_date_str(row.get("Tanggal Kunjungan"))
        if not tgl_kunj:
            continue

        processed += 1

        # Check / Create placeholder master patient
        if p_id not in existing_pasien_ids and p_id not in missing_pasien_map:
            missing_pasien_map[p_id] = Pasien(
                pasien_id=p_id,
                no_rekam_medik=clean_val(row.get("No Rekam Medik")),
                no_reg_nas=clean_val(row.get("No Reg Nas")),
                nama_pasien=clean_val(row.get("Nama Pasien")),
                nik=clean_val(row.get("NIK/No. Identitas")),
                jenis_kelamin=clean_val(row.get("Jenis Kelamin")),
                tanggal_lahir=parse_date_str(row.get("Tanggal Lahir")),
                kelompok_populasi=clean_val(row.get("Kelompok Populasi")),
                status_odhiv=clean_val(row.get("Status ODHIV")),
                status_odhiv_pdp=clean_val(row.get("Status ODHIV dalam PDP")),
                tanggal_mulai_art=parse_date_str(row.get("Tanggal Mulai ART")),
                tanggal_konfirmasi_hiv=parse_date_str(row.get("Tanggal Konfirmasi HIV")),
                tanggal_masuk_perawatan=parse_date_str(row.get("Tanggal Masuk Perawatan")),
                kunjungan_terakhir=tgl_kunj
            )

        alasan = clean_val(row.get("Alasan Kunjungan"))
        bb = parse_float(row.get("Berat Badan (kg)"))
        tb = parse_float(row.get("Tinggi Badan (cm)"))
        imt, kat_imt = calculate_imt(bb, tb)

        rejimen = clean_val(row.get("Nama Rejimen"))
        kat_rejimen = classify_regimen(rejimen)
        jml_arv = parse_int(row.get("Jumlah hari ARV"))

        akhir_fu = parse_date_str(row.get("Akhir Follow Up"))
        if not akhir_fu:
            akhir_fu = calculate_fallback_afu(tgl_kunj, jml_arv)

        kunj = Kunjungan(
            pasien_id=p_id,
            no_rekam_medik=clean_val(row.get("No Rekam Medik")),
            no_reg_nas=clean_val(row.get("No Reg Nas")),
            tanggal_kunjungan=tgl_kunj,
            nama_upk=clean_val(row.get("Nama UPK")),
            upk_asal=clean_val(row.get("UPK Asal")),
            alasan_kunjungan=alasan,
            jenis_layanan=clean_val(row.get("Jenis Layanan")),
            berat_badan=bb,
            tinggi_badan=tb,
            imt=imt,
            kategori_imt=kat_imt,
            status_kawin=clean_val(row.get("Status Kawin")),
            status_hamil=clean_val(row.get("Status Hamil")),
            status_odhiv=clean_val(row.get("Status ODHIV")),
            status_odhiv_pdp=clean_val(row.get("Status ODHIV dalam PDP")),
            stadium_klinis=clean_val(row.get("Stadium Klinis")),
            nama_rejimen=rejimen,
            kategori_rejimen=kat_rejimen,
            jumlah_hari_arv=jml_arv,
            akhir_follow_up=akhir_fu,
            tanggal_dirujuk=parse_date_str(row.get("Tanggal Dirujuk")),
            lembaga_pendamping=clean_val(row.get("Lembaga Pendamping")),
            batch_id=batch_id
        )
        kunjungan_objects.append(kunj)
        inserted += 1

    # Save missing master patients first
    if missing_pasien_map:
        db.bulk_save_objects(list(missing_pasien_map.values()))
        db.commit()

    # Bulk save kunjungan in chunks of 2000
    if kunjungan_objects:
        for i in range(0, len(kunjungan_objects), 2000):
            db.bulk_save_objects(kunjungan_objects[i:i+2000])
            db.commit()

    return processed, inserted, updated

def import_viral_load_data(df: pd.DataFrame, db: Session, batch_id: str):
    processed = 0
    inserted = 0
    updated = 0

    existing_pasien_ids = set(r[0] for r in db.query(Pasien.pasien_id).all())
    missing_pasien_map = {}
    vl_objects = []

    for _, row in df.iterrows():
        p_id_raw = row.get("Pasien ID") or row.get("ID Pasien")
        if pd.isna(p_id_raw):
            continue
        p_id = str(p_id_raw).strip()
        tgl_periksa = parse_date_str(row.get("Tanggal Pemeriksaan"))
        if not tgl_periksa:
            continue

        processed += 1

        if p_id not in existing_pasien_ids and p_id not in missing_pasien_map:
            missing_pasien_map[p_id] = Pasien(
                pasien_id=p_id,
                no_rekam_medik=clean_val(row.get("No Rekam Medik")),
                no_reg_nas=clean_val(row.get("No Reg Nas")),
                nama_pasien=clean_val(row.get("Nama Pasien")),
                nik=clean_val(row.get("NIK/No. Identitas")),
                jenis_kelamin=clean_val(row.get("Jenis Kelamin")),
                tanggal_lahir=parse_date_str(row.get("Tanggal Lahir"))
            )

        hasil_raw = clean_val(row.get("Hasil"))
        num_val, kat_vl, is_supp, is_undet = classify_viral_load(hasil_raw)

        vl = LabViralLoad(
            pasien_id=p_id,
            no_order=clean_val(row.get("No Order")),
            tanggal_pemeriksaan=tgl_periksa,
            upk_asal=clean_val(row.get("UPK Asal")),
            hasil_raw=hasil_raw,
            hasil_numerik=num_val,
            kategori_vl=kat_vl,
            is_suppressed=is_supp,
            is_undetectable=is_undet,
            tanggal_hasil_keluar=parse_date_str(row.get("Tanggal Hasil Keluar")),
            pemeriksa=clean_val(row.get("Pemeriksa")),
            penanggung_jawab=clean_val(row.get("Penanggung Jawab")),
            status_pemeriksaan=clean_val(row.get("Status Pemeriksaan")),
            diulang=clean_val(row.get("Diulang")),
            batch_id=batch_id
        )
        vl_objects.append(vl)
        inserted += 1

    if missing_pasien_map:
        db.bulk_save_objects(list(missing_pasien_map.values()))
        db.commit()

    if vl_objects:
        for i in range(0, len(vl_objects), 2000):
            db.bulk_save_objects(vl_objects[i:i+2000])
            db.commit()

    return processed, inserted, updated

def import_cd4_data(df: pd.DataFrame, db: Session, batch_id: str):
    processed = 0
    inserted = 0
    updated = 0

    col_id = next((c for c in df.columns if "pasien id" in c.lower() or "id pasien" in c.lower()), None)
    col_tgl = next((c for c in df.columns if "tanggal" in c.lower() or "tgl" in c.lower()), None)
    col_val = next((c for c in df.columns if "cd4" in c.lower() or "nilai" in c.lower() or "hasil" in c.lower()), None)
    col_rm = next((c for c in df.columns if "rekam" in c.lower() or "rm" in c.lower()), None)

    if not col_id or not col_val:
        raise ValueError("Kolom Pasien ID dan Nilai CD4 tidak ditemukan.")

    existing_pasien_ids = set(r[0] for r in db.query(Pasien.pasien_id).all())
    missing_pasien_map = {}
    cd4_objects = []

    for _, row in df.iterrows():
        p_id_raw = row.get(col_id)
        if pd.isna(p_id_raw):
            continue
        p_id = str(p_id_raw).strip()
        tgl = parse_date_str(row.get(col_tgl)) if col_tgl else datetime.date.today().strftime("%Y-%m-%d")

        processed += 1
        if p_id not in existing_pasien_ids and p_id not in missing_pasien_map:
            missing_pasien_map[p_id] = Pasien(
                pasien_id=p_id,
                no_rekam_medik=clean_val(row.get(col_rm)) if col_rm else None
            )

        num_cd4, kat_cd4 = classify_cd4(row.get(col_val))
        if num_cd4 is None:
            continue

        cd4 = LabCD4(
            pasien_id=p_id,
            no_rekam_medik=clean_val(row.get(col_rm)) if col_rm else None,
            tanggal_pemeriksaan=tgl,
            nilai_cd4=num_cd4,
            kategori_cd4=kat_cd4,
            batch_id=batch_id
        )
        cd4_objects.append(cd4)
        inserted += 1

    if missing_pasien_map:
        db.bulk_save_objects(list(missing_pasien_map.values()))
        db.commit()

    if cd4_objects:
        for i in range(0, len(cd4_objects), 2000):
            db.bulk_save_objects(cd4_objects[i:i+2000])
            db.commit()

    return processed, inserted, updated

def import_simrs_resep_data(df: pd.DataFrame, db: Session, batch_id: str, filename: str = "kunjunganfarmasi.xlsx"):
    processed = 0
    inserted = 0
    updated = 0

    # Clean header names
    df.columns = [str(c).strip() for c in df.columns]

    col_mr = next((c for c in df.columns if any(k in str(c).lower() for k in ["mr_no", "no_rm", "no rekam medik", "no. rm", "norm", "rekam medik", "rm"])), None)
    col_date = next((c for c in df.columns if any(k in str(c).lower() for k in ["bill_date", "tgl_bill", "tanggal", "tgl", "date", "tgl resep"])), None)
    col_nama = next((c for c in df.columns if any(k in str(c).lower() for k in ["nama_pasien", "nama", "pasien"])), None)
    col_tgl_lhr = next((c for c in df.columns if any(k in str(c).lower() for k in ["tanggal_lahir", "tgl_lahir", "lahir", "dob"])), None)
    col_desc = next((c for c in df.columns if any(k in str(c).lower() for k in ["item_code_desc", "desc", "nama_obat", "obat", "rejimen", "item_desc", "item"])), None)
    col_qty = next((c for c in df.columns if any(k in str(c).lower() for k in ["qty", "jumlah", "kuantitas"])), None)
    col_doc = next((c for c in df.columns if any(k in str(c).lower() for k in ["nama_dokter", "dokter", "dpjp", "penanggungjawab"])), None)
    col_depo = next((c for c in df.columns if any(k in str(c).lower() for k in ["outlet_name", "depo_name", "depo", "farmasi", "outlet"])), None)
    col_bill = next((c for c in df.columns if any(k in str(c).lower() for k in ["bill_number", "no_faktur", "faktur", "bill_no", "bill", "no resep"])), None)
    col_alamat = next((c for c in df.columns if any(k in str(c).lower() for k in ["alamat", "address"])), None)

    if not col_mr:
        raise ValueError("Kolom Nomor Rekam Medik (No. RM / MR_NO) tidak ditemukan pada berkas Farmasi SIMRS.")

    # Determine sheet/periode label from filename
    sheet_label = os.path.splitext(os.path.basename(filename))[0] if filename else "Kunjungan Farmasi"

    batch_objects = []
    for _, row in df.iterrows():
        rm_val = clean_text_field(row.get(col_mr)) if col_mr else None
        if not rm_val or len(rm_val) < 3 or rm_val.lower() in ["no rm", "rm", "mr_no", "rekam medik"]:
            continue

        processed += 1
        tgl_val = sanitize_date_str(row.get(col_date)) if col_date else None
        nama_val = clean_text_field(row.get(col_nama)) if col_nama else None
        lhr_val = sanitize_date_str(row.get(col_tgl_lhr)) if col_tgl_lhr else None
        desc_val = clean_text_field(row.get(col_desc)) if col_desc else None
        qty_val = sanitize_float(row.get(col_qty)) if col_qty else 30.0
        doc_val = clean_text_field(row.get(col_doc)) if col_doc else None
        depo_val = clean_text_field(row.get(col_depo)) if col_depo else "DEPO FARMASI"
        bill_val = clean_text_field(row.get(col_bill)) if col_bill else None
        alamat_val = clean_text_field(row.get(col_alamat)) if col_alamat else None

        # Clean numeric outlet IDs
        if depo_val in ["15", "15.0"]:
            depo_val = "DEPO RAWAT JALAN"
        elif depo_val in ["62", "62.0"]:
            depo_val = "DEPO FARMASI GARUDA"

        resep = SimrsResep(
            bill_number=bill_val,
            bill_date=tgl_val,
            no_rekam_medik=rm_val,
            nama_pasien=nama_val,
            tanggal_lahir=lhr_val,
            item_code_desc=desc_val,
            qty=qty_val,
            nama_dokter=doc_val,
            depo_name=depo_val,
            alamat=alamat_val,
            periode_sheet=sheet_label
        )
        batch_objects.append(resep)

    if batch_objects:
        db.bulk_save_objects(batch_objects)
        db.commit()
        inserted = len(batch_objects)

    return processed, inserted, updated

def process_file_upload(file_path_or_buffer, filename: str, forced_type: str = None) -> dict:
    db = SessionLocal()
    batch_id = str(uuid.uuid4())[:8]
    try:
        before_stats = {
            "total_pasien": db.query(Pasien).count(),
            "total_kunjungan": db.query(Kunjungan).count(),
            "total_vl": db.query(LabViralLoad).count(),
            "total_cd4": db.query(LabCD4).count(),
            "total_simrs": db.query(SimrsResep).count()
        }

        df = read_excel_smart(file_path_or_buffer)
        file_type = forced_type or detect_file_type(df, filename=filename)
        
        if file_type == "PASIEN":
            proc, ins, upd = import_pasien_data(df, db, batch_id)
        elif file_type == "KUNJUNGAN":
            proc, ins, upd = import_kunjungan_data(df, db, batch_id)
        elif file_type == "VIRAL_LOAD":
            proc, ins, upd = import_viral_load_data(df, db, batch_id)
        elif file_type == "CD4":
            proc, ins, upd = import_cd4_data(df, db, batch_id)
        elif file_type in ["SIMRS_ARV", "KUNJUNGAN_FARMASI", "SIMRS_RESEP"]:
            proc, ins, upd = import_simrs_resep_data(df, db, batch_id, filename=filename)
        else:
            raise ValueError(f"Format file tidak dikenali untuk '{filename}'. Pastikan format sesuai ekspor SIHA/SIMRS.")

        after_stats = {
            "total_pasien": db.query(Pasien).count(),
            "total_kunjungan": db.query(Kunjungan).count(),
            "total_vl": db.query(LabViralLoad).count(),
            "total_cd4": db.query(LabCD4).count(),
            "total_simrs": db.query(SimrsResep).count()
        }

        history = UploadHistory(
            filename=filename,
            file_type=file_type,
            rows_processed=proc,
            rows_inserted=ins,
            rows_updated=upd,
            status="SUCCESS",
            details=f"Batch {batch_id}: {proc} baris dibaca, {ins} baru, {upd} diupdate."
        )
        db.add(history)
        db.commit()

        return {
            "success": True,
            "filename": filename,
            "file_type": file_type,
            "processed": proc,
            "inserted": ins,
            "updated": upd,
            "batch_id": batch_id,
            "before": before_stats,
            "after": after_stats
        }
    except Exception as e:
        db.rollback()
        history = UploadHistory(
            filename=filename,
            file_type=forced_type or "UNKNOWN",
            rows_processed=0,
            rows_inserted=0,
            rows_updated=0,
            status="FAILED",
            details=str(e)
        )
        db.add(history)
        db.commit()
        return {
            "success": False,
            "filename": filename,
            "error": str(e)
        }
    finally:
        db.close()

def auto_seed_local_files():
    init_db()
    db = SessionLocal()
    try:
        pasien_count = db.query(Pasien).count()
        kunj_count = db.query(Kunjungan).count()
        vl_count = db.query(LabViralLoad).count()

        if pasien_count > 0 or kunj_count > 0 or vl_count > 0:
            print(f"[Auto-Seed] Database sudah terisi: {pasien_count} Pasien, {kunj_count} Kunjungan, {vl_count} VL.")
            return

        print("[Auto-Seed] Database masih kosong. Memindai file lokal awal...")
        # Order of import: Pasien first, then Kunjungan, then Viral Load
        files = os.listdir(BASE_DIR)
        
        # 1. Pasien
        for f in sorted(files):
            if f.lower().endswith((".xlsx", ".xls")) and "pasien" in f.lower() and "kunjungan" not in f.lower():
                path = os.path.join(BASE_DIR, f)
                print(f"Mengimpor master: {f}")
                res = process_file_upload(path, f, forced_type="PASIEN")
                print(" ->", res)
                
        # 2. Kunjungan
        for f in sorted(files):
            if f.lower().endswith((".xlsx", ".xls")) and "kunjungan" in f.lower():
                path = os.path.join(BASE_DIR, f)
                print(f"Mengimpor kunjungan: {f}")
                res = process_file_upload(path, f, forced_type="KUNJUNGAN")
                print(" ->", res)

        # 3. Viral Load
        for f in sorted(files):
            if f.lower().endswith((".xlsx", ".xls")) and "viral load" in f.lower():
                path = os.path.join(BASE_DIR, f)
                print(f"Mengimpor viral load: {f}")
                res = process_file_upload(path, f, forced_type="VIRAL_LOAD")
                print(" ->", res)

        print("[Auto-Seed] Selesai seeding awal.")
    finally:
        db.close()
