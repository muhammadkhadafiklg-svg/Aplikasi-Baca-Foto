"""Baca Foto (OCR) - versi HP. 100% gratis.
Tools: Python, Streamlit, Tesseract OCR, OpenCV, Pillow, pandas.
Jalankan lokal: streamlit run app.py
"""
import io
import json
import re

import cv2
import numpy as np
import pandas as pd
import pytesseract
import requests
import streamlit as st
from PIL import Image, ImageOps

try:  # dukungan foto HEIC dari iPhone
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:  # noqa: BLE001
    pass

st.set_page_config(
    page_title="Scanner Laporan Setoran",
    page_icon="📷",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("📷 Scanner Laporan Setoran")
st.caption("Upload foto struk, sistem akan otomatis mengekstrak Total Setoran.")

# ---------- Pengaturan ----------
with st.expander("⚙️ Pengaturan Pembacaan", expanded=False):
    yang_dibaca = st.radio(
        "Yang dibaca",
        ["Teks + angka", "Hanya angka"],
        horizontal=True,
        index=0, # Wajib Teks + Angka agar bisa membaca kata "TOTAL SETORAN"
        help="Gunakan 'Teks + angka' agar sistem bisa mengenali format struk.",
    )
    mode = st.radio(
        "Pra-proses gambar",
        ["Asli", "Grayscale", "Hitam-putih"],
        index=1, 
        horizontal=True,
    )
    bahasa = st.selectbox("Bahasa teks di foto", ["ind+eng", "ind", "eng"])
    psm_label = st.selectbox(
        "Jenis tata letak",
        [
            "6 - Blok teks (Default Struk)", 
            "4 - Kolom", 
            "11 - Teks tersebar",
            "3 - Otomatis"
        ],
        index=0
    )
    psm_value = int(psm_label.split(" ")[0])
    cari_data = st.checkbox("Otomatis ekstrak format struk", value=True)


# ---------- Fungsi ----------
def preprocess(data: bytes, mode: str) -> np.ndarray:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    arr = np.array(img)
    
    h, w = arr.shape[:2]
    sisi_panjang = max(h, w)
    if sisi_panjang > 2000:  
        s = 2000 / sisi_panjang
        arr = cv2.resize(arr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    elif sisi_panjang < 1200: 
        s = 1500 / sisi_panjang 
        arr = cv2.resize(arr, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
        
    if mode == "Asli":
        return arr
        
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    if mode == "Grayscale":
        return gray
        
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 11
    )


@st.cache_data(show_spinner=False, max_entries=30)
def proses(data: bytes, mode: str, bahasa: str, psm: int, yang_dibaca: str):
    arr = preprocess(data, mode)
    config = f"--oem 3 --psm {psm}"
    
    if yang_dibaca == "Hanya angka":
        config += ' -c tessedit_char_whitelist="0123456789.,-/: "'
        
    teks = pytesseract.image_to_string(arr, lang=bahasa, config=config).strip()
    return arr, teks


def cari_info(teks: str) -> dict:
    info = {}
    
    # 1. Ekstrak Tanggal Khusus Format Struk (misal: 15 OCT,26)
    match_tgl = re.search(r"DATE/?TIME[^\d]*([0-9]{1,2}\s*[A-Za-z]{3}\s*,\s*[0-9]{2,4})", teks, re.IGNORECASE)
    if match_tgl:
        info["Tanggal"] = match_tgl.group(1).strip()
    else:
        # Fallback format tanggal standar
        tanggal = re.findall(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b", teks)
        if tanggal:
            info["Tanggal"] = "\n".join(dict.fromkeys(tanggal))
            
    # 2. Ekstrak JOB ID (Referensi Struk)
    match_job = re.search(r"JOB\s+ID[^\d]*([0-9]+)", teks, re.IGNORECASE)
    if match_job:
        info["Job ID"] = match_job.group(1).strip()

    # 3. Ekstrak TOTAL SETORAN
    # Mencari kata "TOTAL SETORAN", mengabaikan teks di antaranya (seperti Rp.), dan mengambil angkanya
    match_total = re.search(r"TOTAL\s+SETORAN[^\d]*([0-9.,]+)", teks, re.IGNORECASE)
    if match_total:
        info["Total Setoran"] = match_total.group(1).strip()
    else:
        # Jika "TOTAL SETORAN" tidak terbaca jelas, cari dan tampilkan semua nominal sebagai cadangan
        nominal = re.findall(r"(?:Rp\.?\s?)?\d{1,3}(?:[.,]\d{3})+(?:,\d{2})?", teks)
        if nominal:
            info["Semua Nominal Terbaca"] = "\n".join(dict.fromkeys(n.strip() for n in nominal))

    return info


def simpan_ke_sheet(rows: list) -> tuple:
    try:
        url = st.secrets["APPS_SCRIPT_URL"]
        token = st.secrets["APPS_SCRIPT_TOKEN"]
    except Exception:  # noqa: BLE001
        return False, "Secrets belum diisi (APPS_SCRIPT_URL dan APPS_SCRIPT_TOKEN)."
    try:
        resp = requests.post(
            url,
            data=json.dumps({"token": token, "rows": rows}),
            headers={"Content-Type": "text/plain"},
            timeout=60,
        )
        hasil_json = resp.json()
    except Exception as e:  # noqa: BLE001
        return False, f"Gagal terhubung: {e}"
    if hasil_json.get("ok"):
        return True, f"{hasil_json.get('count', 0)} baris tersimpan."
    return False, hasil_json.get("error", "Gagal menyimpan.")


# ---------- Upload & Kamera ----------
files = st.file_uploader(
    "Pilih foto struk:",
    type=["jpg", "jpeg", "png", "webp", "bmp", "heic", "heif"],
    accept_multiple_files=True,
)
items = [(f.name, f.getvalue()) for f in (files or [])]

with st.expander("📸 Atau gunakan kamera langsung"):
    kamera = st.camera_input("Ambil foto", label_visibility="collapsed")
    if kamera:
        items.append(("kamera_langsung.jpg", kamera.getvalue()))

if not items:
    st.info("Upload gambar atau gunakan kamera untuk memulai scan laporan.")
    st.stop()

# ---------- Proses ----------
hasil = []
for i, (nama, data) in enumerate(items, start=1):
    with st.expander(f"Hasil: {nama}", expanded=True):
        try:
            with st.spinner("Sedang memproses struk..."):
                arr, teks = proses(data, mode, bahasa, psm_value, yang_dibaca)
        except pytesseract.TesseractNotFoundError:
            st.error("Tesseract belum terpasang. Pastikan file packages.txt ada di server/GitHub.")
            st.stop()
        except Exception as e:  # noqa: BLE001
            st.error(f"Gagal membaca {nama}: {e}")
            continue

        st.image(arr, caption=f"Gambar diproses mode: {mode}", use_container_width=True)
        
        # --- PERUBAHAN UTAMA: Teks Dibuat Read-Only (Tidak bisa diedit) ---
        st.markdown("**Teks Mentah Terbaca (Read-Only):**")
        st.code(teks, language="text") 
        # -------------------------------------------------------------------
        
        info = cari_info(teks) if cari_data else {}
        
        # Tampilkan ekstraksi data dengan rapi
        if info:
            st.markdown("### 📌 Data Laporan Terdeteksi:")
            
            if info.get("Tanggal"):
                st.info(f"**📅 Tanggal Struk:** {info['Tanggal']}")
                
            if info.get("Job ID"):
                st.info(f"**🆔 Job ID:** {info['Job ID']}")
                
            if info.get("Total Setoran"):
                st.success(f"**💰 TOTAL SETORAN:** Rp. {info['Total Setoran']}")
            elif info.get("Semua Nominal Terbaca"):
                st.warning("**⚠️ Baris 'TOTAL SETORAN' tidak terbaca jelas. Berikut nominal yang ditemukan:**")
                for nom in info["Semua Nominal Terbaca"].split("\n"):
                    st.markdown(f"- **{nom}**")
                    
        # Saat menyimpan hasil mentah, gabungkan teks agar aman di CSV
        # Info spesifik juga otomatis jadi kolom baru di DataFrame!
        hasil.append({"File": nama, "Teks Mentah": teks, **info})

# ---------- Unduh & Simpan ----------
if hasil:
    st.divider()
    df = pd.DataFrame(hasil)
    st.subheader("Tabel Laporan")
    st.dataframe(df, use_container_width=True)
    
    if st.button("💾 Simpan ke Google Sheet", type="primary", use_container_width=True):
        with st.spinner("Menyimpan ke Google Sheets..."):
            ok, pesan = simpan_ke_sheet(hasil)
        (st.success if ok else st.error)(pesan)
        
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Unduh CSV",
            df.to_csv(index=False).encode("utf-8-sig"),
            "laporan_setoran.csv",
            "text/csv",
            use_container_width=True,
        )
    with col2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False)
        st.download_button(
            "⬇️ Unduh Excel",
            buf.getvalue(),
            "laporan_setoran.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
