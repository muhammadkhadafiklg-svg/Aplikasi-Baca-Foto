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
    page_title="Baca Foto",
    page_icon="📷",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("📷 Baca Foto")
st.caption("Upload foto dari HP, atau gunakan kamera langsung untuk ambil teks/angka.")

# ---------- Pengaturan ----------
with st.expander("⚙️ Pengaturan (Buka untuk setel kamera)", expanded=False):
    yang_dibaca = st.radio(
        "Yang dibaca",
        ["Teks + angka", "Hanya angka"],
        horizontal=True,
        help="'Hanya angka' lebih akurat untuk nominal, nomor, atau meteran.",
    )
    mode = st.radio(
        "Pra-proses gambar",
        ["Asli", "Grayscale", "Hitam-putih"],
        index=1, # Diubah default ke Grayscale agar lebih ramah kamera web HP
        horizontal=True,
        help="Gunakan 'Grayscale' untuk hasil kamera HP langsung.",
    )
    bahasa = st.selectbox("Bahasa teks di foto", ["ind+eng", "ind", "eng"])
    psm_label = st.selectbox(
        "Jenis tata letak",
        [
            "6 - Blok teks (Default)", 
            "11 - Teks tersebar (Bagus untuk kamera)", 
            "4 - Kolom", 
            "3 - Otomatis"
        ],
        index=0
    )
    psm_value = int(psm_label.split(" ")[0])
    cari_data = st.checkbox("Cari tanggal & nominal otomatis", value=True)


# ---------- Fungsi ----------
def preprocess(data: bytes, mode: str) -> np.ndarray:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    arr = np.array(img)
    
    # 1. Perbaikan Resolusi khusus Kamera Web
    h, w = arr.shape[:2]
    sisi_panjang = max(h, w)
    if sisi_panjang > 2000:  
        # Kecilkan jika foto terlalu besar agar cepat
        s = 2000 / sisi_panjang
        arr = cv2.resize(arr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    elif sisi_panjang < 1200: 
        # Perbesar paksa resolusi kamera web agar OCR bisa membaca pixelnya
        s = 1500 / sisi_panjang 
        arr = cv2.resize(arr, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
        
    if mode == "Asli":
        return arr
        
    # 2. Ubah ke Grayscale
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    
    # 3. Tambahkan CLAHE (Peningkatan Kontras Otomatis)
    # Sangat ampuh meratakan pencahayaan gelap/berbayang dari kamera HP
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    if mode == "Grayscale":
        return gray
        
    # 4. Filter Noise Kamera dan Hitam-Putih (Adaptive Threshold)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 11
    )


@st.cache_data(show_spinner=False, max_entries=30)
def proses(data: bytes, mode: str, bahasa: str, psm: int, yang_dibaca: str):
    arr = preprocess(data, mode)
    config = f"--oem 3 --psm {psm}"
    
    if yang_dibaca == "Hanya angka":
        # Spasi di akhir whitelist penting agar angka tidak saling menempel
        config += ' -c tessedit_char_whitelist="0123456789.,-/: "'
        
    teks = pytesseract.image_to_string(arr, lang=bahasa, config=config).strip()
    return arr, teks


def cari_info(teks: str) -> dict:
    tanggal = re.findall(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b", teks)
    nominal = re.findall(r"(?:Rp\.?\s?)?\d{1,3}(?:[.,]\d{3})+(?:,\d{2})?", teks)
    
    # Menggunakan \n agar hasil yang diekstrak tampil berjejer ke bawah
    return {
        "Tanggal": "\n".join(dict.fromkeys(tanggal)),
        "Nominal": "\n".join(dict.fromkeys(n.strip() for n in nominal)),
    }


def simpan_ke_sheet(rows: list) -> tuple:
    """Kirim data ke Google Apps Script -> Google Sheet."""
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
    "Pilih foto dari galeri:",
    type=["jpg", "jpeg", "png", "webp", "bmp", "heic", "heif"],
    accept_multiple_files=True,
)
items = [(f.name, f.getvalue()) for f in (files or [])]

with st.expander("📸 Atau gunakan kamera langsung"):
    kamera = st.camera_input("Ambil foto", label_visibility="collapsed")
    if kamera:
        items.append(("kamera_langsung.jpg", kamera.getvalue()))

if not items:
    st.info("Upload gambar atau gunakan kamera untuk memulai.")
    st.stop()

# ---------- Proses ----------
hasil = []
for i, (nama, data) in enumerate(items, start=1):
    with st.expander(f"Hasil: {nama}", expanded=True):
        try:
            with st.spinner("Sedang memproses gambar..."):
                arr, teks = proses(data, mode, bahasa, psm_value, yang_dibaca)
        except pytesseract.TesseractNotFoundError:
            st.error("Tesseract belum terpasang. Pastikan file packages.txt ada di server/GitHub.")
            st.stop()
        except Exception as e:  # noqa: BLE001
            st.error(f"Gagal membaca {nama}: {e}")
            continue

        st.image(arr, caption=f"Gambar diproses mode: {mode}", use_container_width=True)
        teks_edit = st.text_area("Teks Lengkap (Bisa diedit manual)", teks, height=150, key=f"t{i}")
        
        info = cari_info(teks_edit) if cari_data else {}
        
        # Tampilkan ekstraksi data dengan rapi (berjejer ke bawah)
        if info:
            st.markdown("### 📌 Deteksi Angka & Tanggal:")
            if info.get("Tanggal"):
                st.markdown("**📅 Tanggal:**")
                for tgl in info["Tanggal"].split("\n"):
                    st.markdown(f"- {tgl}")
                    
            if info.get("Nominal"):
                st.markdown("**💰 Nominal:**")
                for nom in info["Nominal"].split("\n"):
                    st.markdown(f"- **{nom}**")
                    
        hasil.append({"File": nama, "Teks": teks_edit, **info})

# ---------- Unduh & Simpan ----------
if hasil:
    st.divider()
    df = pd.DataFrame(hasil)
    st.subheader("Rekap Data")
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
            "hasil_ocr.csv",
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
            "hasil_ocr.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
