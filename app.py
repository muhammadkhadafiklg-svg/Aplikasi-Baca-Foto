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
st.caption("Upload foto dari HP, lalu ambil teks atau angkanya.")

# ---------- Pengaturan (di halaman utama agar mudah di HP) ----------
with st.expander("⚙️ Pengaturan", expanded=False):
    yang_dibaca = st.radio(
        "Yang dibaca",
        ["Teks + angka", "Hanya angka"],
        horizontal=True,
        help="'Hanya angka' lebih akurat untuk nominal, nomor, atau meteran.",
    )
    mode = st.radio(
        "Pra-proses gambar",
        ["Asli", "Grayscale", "Hitam-putih"],
        index=2,
        horizontal=True,
        help="Jika hasil kurang bagus, coba 'Grayscale'.",
    )
    bahasa = st.selectbox("Bahasa teks di foto", ["ind+eng", "ind", "eng"])
    psm_label = st.selectbox(
        "Jenis tata letak",
        ["6 - Blok teks", "4 - Kolom", "3 - Otomatis", "11 - Teks tersebar"],
    )
    psm_value = int(psm_label.split(" ")[0])
    cari_data = st.checkbox("Cari tanggal & nominal otomatis", value=True)


# ---------- Fungsi ----------
def preprocess(data: bytes, mode: str) -> np.ndarray:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    arr = np.array(img)
    h, w = arr.shape[:2]
    sisi_panjang = max(h, w)
    if sisi_panjang > 2000:  # foto HP besar: kecilkan agar cepat
        s = 2000 / sisi_panjang
        arr = cv2.resize(arr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    elif w < 1200:  # foto kecil: perbesar agar OCR akurat
        s = 1200 / w
        arr = cv2.resize(arr, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    if mode == "Asli":
        return arr
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    if mode == "Grayscale":
        return gray
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )


@st.cache_data(show_spinner=False, max_entries=30)
def proses(data: bytes, mode: str, bahasa: str, psm: int, yang_dibaca: str):
    arr = preprocess(data, mode)
    config = f"--oem 3 --psm {psm}"
    if yang_dibaca == "Hanya angka":
        config += " -c tessedit_char_whitelist=0123456789.,-/:"
    teks = pytesseract.image_to_string(arr, lang=bahasa, config=config).strip()
    return arr, teks


def cari_info(teks: str) -> dict:
    tanggal = re.findall(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b", teks)
    nominal = re.findall(r"(?:Rp\.?\s?)?\d{1,3}(?:[.,]\d{3})+(?:,\d{2})?", teks)
    return {
        "Tanggal": ", ".join(dict.fromkeys(tanggal)),
        "Nominal": ", ".join(dict.fromkeys(n.strip() for n in nominal)),
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


# ---------- Upload ----------
files = st.file_uploader(
    "Pilih foto atau ambil dari kamera HP",
    type=["jpg", "jpeg", "png", "webp", "bmp", "heic", "heif"],
    accept_multiple_files=True,
)
items = [(f.name, f.getvalue()) for f in (files or [])]

with st.expander("📸 Atau ambil foto langsung di sini"):
    kamera = st.camera_input("Ambil foto", label_visibility="collapsed")
    if kamera:
        items.append(("kamera.jpg", kamera.getvalue()))

if not items:
    st.info("Upload atau ambil foto untuk mulai.")
    st.stop()

# ---------- Proses ----------
hasil = []
for i, (nama, data) in enumerate(items, start=1):
    with st.expander(f"{i}. {nama}", expanded=True):
        try:
            with st.spinner("Membaca..."):
                arr, teks = proses(data, mode, bahasa, psm_value, yang_dibaca)
        except pytesseract.TesseractNotFoundError:
            st.error("Tesseract belum terpasang. Pastikan file packages.txt ada di GitHub.")
            st.stop()
        except Exception as e:  # noqa: BLE001
            st.error(f"Gagal membaca {nama}: {e}")
            continue

        st.image(arr, caption="Gambar setelah pra-proses", use_container_width=True)
        teks_edit = st.text_area("Hasil (bisa diedit)", teks, height=220, key=f"t{i}")
        info = cari_info(teks_edit) if cari_data else {}
        if info:
            st.write(info)
        hasil.append({"File": nama, "Teks": teks_edit, **info})

# ---------- Unduh ----------
if hasil:
    st.divider()
    df = pd.DataFrame(hasil)
    st.subheader("Rekap")
    st.dataframe(df, use_container_width=True)
    if st.button("💾 Simpan ke Google Sheet", type="primary", use_container_width=True):
        with st.spinner("Menyimpan..."):
            ok, pesan = simpan_ke_sheet(hasil)
        (st.success if ok else st.error)(pesan)
    st.download_button(
        "⬇️ Unduh CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        "hasil_ocr.csv",
        "text/csv",
        use_container_width=True,
    )
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
