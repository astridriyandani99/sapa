# SIHA & SIMRS Clinical & Research Intelligence Dashboard

Aplikasi web analitik data surveilans HIV-AIDS (SIHA Kemenkes RI) dan Rekam Medis Rumah Sakit (SIMRS) yang dirancang dengan antarmuka modern, interaktif, dan presisi tinggi untuk mendukung dua kebutuhan utama:
1. **Direktur Rumah Sakit & Manajemen**: Menyajikan laporan eksekutif, indikator mutu layanan, kaskade 95-95-95 Fast-Track UNAIDS, rasio supresi viral load, serta sistem peringatan dini keterlambatan ambil obat ARV.
2. **Peneliti & Tim Klinis PDP**: Eksplorasi data granular dengan mesin filter multi-dimensi, analisis korelasi rejimen terhadap keberhasilan terapi, data grid interaktif, serta fitur ekspor Excel/CSV yang dilengkapi opsi **Anonimisasi Pasien (Kepatuhan UU PDP & Etika Riset Medis)**.

---

## 🚀 Cara Menjalankan Aplikasi

### Cara 1: Menggunakan File Batch (Paling Mudah)
Cukup klik ganda (double-click) file:
```
start.bat
```
Aplikasi akan secara otomatis memverifikasi database, memulai server lokal, dan membuka browser ke `http://localhost:8000`.

### Cara 2: Melalui Terminal / Command Prompt
```bash
python run_dashboard.py
```
Buka browser di alamat: **`http://localhost:8000`**

---

## 📁 Struktur Direktori Proyek

```
data_siha/
├── start.bat                  # Launcher praktis 1-klik untuk pengguna Windows
├── run_dashboard.py           # Script pembuka server & auto-browser
├── data_siha.db               # Database SQLite persisten (otomatis dibuat)
│
├── backend/                   # Backend Python FastAPI & Analitik
│   ├── database.py            # Model ORM SQLAlchemy (Pasien, Kunjungan, Lab VL, Lab CD4, Log)
│   ├── importer.py            # Parser cerdas, auto-detect file, kalkulasi IMT, klasifikasi VL & CD4
│   ├── analytics.py           # Engine kaskade 95-95-95, cross-tabulation, filter multi-dimensi
│   ├── export_service.py      # Generator ekspor Excel/CSV berformat rapi + anonimisasi
│   └── main.py                # Server FastAPI & endpoint REST API
│
├── frontend/                  # Antarmuka Web Interaktif
│   └── index.html             # Single-Page App (Tailwind CSS, Chart.js, Lucide Icons)
│
├── Data Pasien (2).xlsx       # File contoh ekspor Master Pasien dari SIHA
├── Kunjungan Pasien (8).xlsx  # File contoh ekspor Kunjungan Pasien dari SIHA
└── Hasil Pemeriksaan Viral Load (2).xlsx # File contoh ekspor Hasil Lab VL dari SIHA
```

---

## 🔑 Kebijakan Integritas Data (`Pasien ID` sebagai Golden Key)

1. **Kunci Utama Permanen**: `Pasien ID` dikunci sebagai primary key. Setiap kali ada upload file kunjungan berkala atau hasil lab, data akan dihubungkan ke `Pasien ID` yang bersangkutan.
2. **Toleransi File Parsial**: Jika file kunjungan diunggah untuk pasien yang belum ada di master data, sistem secara otomatis membuat entri master dari data demografi yang tercantum pada kunjungan tersebut tanpa error.
3. **Idempotent Ingestion**: Data kunjungan atau pemeriksaan lab dengan tanggal dan ID yang sama tidak akan terduplikasi jika file yang sama diunggah ulang (*upsert logic*).

---

## 📊 Fitur Utama

### 1. 👔 Mode Direktur Rumah Sakit (Executive View)
- **Ringkasan KPI Mutu**: Total kohor pasien, jumlah aktif on ART, angka supresi viral load (VLS Rate), dan counter pasien telat obat.
- **Kaskade Pelayanan 95-95-95**: Visualisasi funnel care continuum dari Terdiagnosis $\to$ On ART $\to$ Viral Load Tested $\to$ VL Suppressed ($<1.000\text{ kopi/mL}$) $\to$ Undetectable ($U=U$).
- **Bagan Distribusi Virologis & Rejimen**: Donut chart klasifikasi hasil RNA HIV dan bar chart rejimen ARV terbanyak (TLD dominan).
- **Early Warning Retensi**: Tabel deteksi otomatis pasien yang telah melewati batas tanggal *Akhir Follow Up* tanpa jadwal kontrol baru (kandidat penjangkauan tim konselor PDP).
- **Cetak Laporan Eksekutif**: Tombol siap cetak / simpan ke format PDF yang rapi untuk materi rapat direksi.

### 2. 🔬 Mode Peneliti & Klinisi (Research Workspace)
- **Mesin Filter Multi-Dimensi**:
  - *Kata Kunci*: Pencarian bebas nomor rekam medis, ID pasien, atau nama.
  - *Demografi*: Jenis kelamin, rentang usia (min & max), kelompok populasi kunci.
  - *Klinis*: Stadium klinis WHO (1, 2, 3, 4), kategori rejimen ARV, status gizi (IMT).
  - *Laboratorium*: Kategori supresi Viral Load dan kategori hitung sel CD4.
- **Matriks Komparasi (Cross-Tabulation)**: Analisis perbandingan efikasi antar jenis rejimen ARV terhadap persentase keberhasilan supresi virus.
- **Data Grid Granular**: Tabel data interaktif menampilkan profil demografi, antropometri, kunjungan, hasil VL, dan nilai CD4 pasien.
- **Ekspor Data Aman (Kepatuhan UU PDP)**:
  - Format unduhan `.xlsx` (Excel) dan `.csv`.
  - Checkbox **"Anonimkan Data Pasien"**: otomatis menyamarkan NIK (`3374************`), Nama Pasien (`I*** P***`), dan nomor rekam medik demi perlindungan data pribadi dan etika publikasi ilmiah.

### 3. 📤 Pusat Integrasi & Upload Data
- Area drag-and-drop untuk menambahkan data kapan saja tanpa perlu merestart server.
- Deteksi otomatis jenis file (*Pasien*, *Kunjungan*, *Viral Load*, atau *CD4*).
- Log riwayat batch upload lengkap dengan jumlah baris yang berhasil dibaca, baris baru ditambahkan, dan baris diupdate.
- Tombol unduh format **Template CD4 SIMRS** untuk integrasi tarikan data baru di masa mendatang.

---

## 🧪 Format Tarikan Data CD4 Baru dari SIMRS

Jika Anda ingin mengunggah hasil pemeriksaan CD4 di masa mendatang, format kolom yang dikenali sistem adalah:

| Nama Kolom | Contoh Nilai | Keterangan |
| :--- | :--- | :--- |
| **Pasien ID** | `3507969` | Kunci utama pencocokan ke data SIHA |
| **No Rekam Medik** | `D111621` | Nomor rekam medis pasien |
| **Tanggal Pemeriksaan** | `2026-08-15` | Tanggal pemeriksaan lab CD4 |
| **Nilai CD4** | `485` | Nilai absolut hitung CD4 (sel/$\mu\text{L}$) |
| **Keterangan** | `Baseline Terapi` | Catatan klinis tambahan (opsional) |

Template berkas Excel dapat diunduh langsung melalui tombol *"Unduh Template CD4 SIMRS"* di dalam web app.
