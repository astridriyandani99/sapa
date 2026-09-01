from typing import Optional
from pydantic import BaseModel, Field
from datetime import date

class PasienIngestSchema(BaseModel):
    pasien_id: str
    no_rekam_medik: Optional[str] = None
    no_reg_nas: Optional[str] = None
    nama_pasien: Optional[str] = None
    nik: Optional[str] = None
    status_nik: Optional[str] = None
    tanggal_lahir: Optional[str] = None
    umur: Optional[int] = None
    kategori_umur: Optional[str] = None
    jenis_kelamin: Optional[str] = None
    pekerjaan: Optional[str] = None
    suku: Optional[str] = None
    warga_negara: Optional[str] = "WNI"
    alamat_provinsi: Optional[str] = None
    alamat_kabupaten: Optional[str] = None
    alamat_kecamatan: Optional[str] = None
    alamat_kelurahan: Optional[str] = None
    domisili_provinsi: Optional[str] = None
    domisili_kabupaten: Optional[str] = None
    tanggal_register: Optional[str] = None
    asal_rujukan: Optional[str] = None
    kelompok_populasi: Optional[str] = None
    stadium_klinis_awal: Optional[str] = None
    status_odhiv: Optional[str] = None
    status_odhiv_pdp: Optional[str] = None
    tanggal_konfirmasi_hiv: Optional[str] = None
    tanggal_masuk_perawatan: Optional[str] = None
    tanggal_mulai_art: Optional[str] = None
    tanggal_lost_to_follow_up: Optional[str] = None
    rujuk_masuk: Optional[str] = None
    rujuk_keluar: Optional[str] = None
    tanggal_meninggal: Optional[str] = None

class KunjunganIngestSchema(BaseModel):
    pasien_id: str
    no_rekam_medik: Optional[str] = None
    tanggal_kunjungan: str
    alasan_kunjungan: Optional[str] = None
    stadium_klinis: Optional[str] = None
    nama_rejimen: Optional[str] = None
    kategori_rejimen: Optional[str] = None
    jumlah_hari_arv: Optional[int] = None
    berat_badan: Optional[float] = None
    tinggi_badan: Optional[float] = None
    imt: Optional[float] = None
    kategori_imt: Optional[str] = None
    akhir_follow_up: Optional[str] = None
    is_estimated_afu: bool = False
    status_keterlambatan: Optional[str] = None
    status_hamil: Optional[str] = None
    status_odhiv: Optional[str] = None
    status_odhiv_pdp: Optional[str] = None

class LabViralLoadIngestSchema(BaseModel):
    pasien_id: str
    no_rekam_medik: Optional[str] = None
    tanggal_pemeriksaan: str
    hasil_raw: Optional[str] = None
    hasil_numerik: Optional[float] = None
    kategori_vl: Optional[str] = None
    is_suppressed: bool = False
    is_undetectable: bool = False
    status_pemeriksaan: Optional[str] = "Selesai"

class LabCD4IngestSchema(BaseModel):
    pasien_id: str
    no_rekam_medik: Optional[str] = None
    tanggal_pemeriksaan: str
    nilai_cd4: Optional[float] = None
    kategori_cd4: Optional[str] = None
