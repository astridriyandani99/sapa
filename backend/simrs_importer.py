import os
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database import SessionLocal, init_db, SimrsResep, UploadHistory, BASE_DIR
from backend.sanitizer import sanitize_date_str, clean_text_field, sanitize_float

def ingest_simrs_arv_file(filepath: str, db: Session) -> dict:
    if not os.path.exists(filepath):
        return {"status": "ERROR", "message": f"File tidak ditemukan: {filepath}"}

    xl = pd.ExcelFile(filepath)
    total_processed = 0
    total_inserted = 0

    # Process all monthly sheets (skip pivot or empty sheets)
    valid_sheets = [s for s in xl.sheet_names if not s.lower().startswith("pivot") and s.lower() != "sheet41"]

    for sheet in valid_sheets:
        try:
            df = pd.read_excel(filepath, sheet_name=sheet)
            if df.empty:
                continue

            # Detect columns dynamically
            col_mr = next((c for c in df.columns if "mr" in str(c).lower() or "rm" in str(c).lower() or "medik" in str(c).lower()), None)
            col_date = next((c for c in df.columns if "date" in str(c).lower() or "tgl" in str(c).lower() or "tanggal" in str(c).lower()), None)
            col_nama = next((c for c in df.columns if "nama_pasien" in str(c).lower() or "nama" in str(c).lower() or "pasien" in str(c).lower()), None)
            col_tgl_lhr = next((c for c in df.columns if "lahir" in str(c).lower()), None)
            col_desc = next((c for c in df.columns if "desc" in str(c).lower() or "obat" in str(c).lower() or "rejimen" in str(c).lower()), None)
            col_qty = next((c for c in df.columns if "qty" in str(c).lower() or "jumlah" in str(c).lower()), None)
            col_doc = next((c for c in df.columns if "dokter" in str(c).lower() or "penanggungjawab" in str(c).lower()), None)
            col_depo = next((c for c in df.columns if "outlet_name" in str(c).lower() or "depo" in str(c).lower() or "farmasi" in str(c).lower()), None)
            if not col_depo:
                col_depo = next((c for c in df.columns if "outlet" in str(c).lower()), None)
            col_bill = next((c for c in df.columns if "bill" in str(c).lower() or "faktur" in str(c).lower()), None)
            col_alamat = next((c for c in df.columns if "alamat" in str(c).lower()), None)

            if not col_mr:
                continue

            batch_objects = []
            for _, row in df.iterrows():
                rm_val = clean_text_field(row.get(col_mr)) if col_mr else None
                if not rm_val or len(rm_val) < 3 or rm_val.lower() in ["no rm", "rm", "mr_no"]:
                    continue

                tgl_val = sanitize_date_str(row.get(col_date)) if col_date else None
                nama_val = clean_text_field(row.get(col_nama)) if col_nama else None
                lhr_val = sanitize_date_str(row.get(col_tgl_lhr)) if col_tgl_lhr else None
                desc_val = clean_text_field(row.get(col_desc)) if col_desc else None
                qty_val = sanitize_float(row.get(col_qty)) if col_qty else None
                doc_val = clean_text_field(row.get(col_doc)) if col_doc else None
                depo_val = clean_text_field(row.get(col_depo)) if col_depo else None

                # Clean numeric outlet IDs
                if depo_val in ["15", "15.0"]:
                    depo_val = "DEPO RAWAT JALAN"
                elif depo_val in ["62", "62.0"]:
                    depo_val = "DEPO FARMASI GARUDA"

                bill_val = clean_text_field(row.get(col_bill)) if col_bill else None
                alamat_val = clean_text_field(row.get(col_alamat)) if col_alamat else None

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
                    periode_sheet=sheet
                )
                batch_objects.append(resep)
                total_processed += 1

            if batch_objects:
                db.bulk_save_objects(batch_objects)
                db.commit()
                total_inserted += len(batch_objects)

        except Exception as e:
            print(f"[SIMRS Ingest Warning] Error processing sheet {sheet}: {e}")

    # Record Upload History
    hist = UploadHistory(
        filename=os.path.basename(filepath),
        file_type="SIMRS_ARV",
        rows_processed=total_processed,
        rows_inserted=total_inserted,
        rows_updated=0,
        status="SUCCESS",
        details=f"Sukses memproses {len(valid_sheets)} sheet bulanan SIMRS ARV."
    )
    db.add(hist)
    db.commit()

    return {
        "status": "SUCCESS",
        "filename": os.path.basename(filepath),
        "total_processed": total_processed,
        "total_inserted": total_inserted,
        "sheets_count": len(valid_sheets)
    }

def auto_seed_simrs_arv():
    init_db()
    db = SessionLocal()
    try:
        count = db.query(SimrsResep).count()
        if count > 0:
            print(f"[SIMRS Auto-Seed] Database SIMRS Resep sudah terisi: {count:,} rekam penyerahan obat.")
            return

        target_file = os.path.join(BASE_DIR, "DAFTAR PASIEN PENERIMA ARV (1).xlsx")
        if os.path.exists(target_file):
            print(f"[SIMRS Auto-Seed] Mengimpor berkas resmi farmasi SIMRS: {target_file}")
            res = ingest_simrs_arv_file(target_file, db)
            print(" -> Result:", res)
    finally:
        db.close()
