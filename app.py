"""Scanner Laporan Setoran - Powered by Gemini AI
Lebih akurat, anti-coretan, dan memahami konteks struk.
"""
import io
import json
import pandas as pd
import requests
import streamlit as st
from PIL import Image

# Import library Google Gemini
import google.generativeai as genai

st.set_page_config(
    page_title="Scanner Laporan Setoran (AI)",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("🤖 Scanner Laporan (Gemini AI)")
st.caption("Upload foto struk. AI akan menembus coretan dan mencari nominal secara cerdas.")

# ---------- Konfigurasi AI ----------
try:
    # Mengambil API Key dari secrets
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Menggunakan model Gemini 1.5 Flash (Sangat cepat dan jago baca gambar)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error("⚠️ GEMINI_API_KEY belum dipasang di secrets.toml!")
    st.stop()


# ---------- Fungsi Ekstraksi via AI ----------
@st.cache_data(show_spinner=False, max_entries=30)
def proses_dengan_ai(image_bytes: bytes):
    """Mengirim gambar ke Gemini AI dan memintanya mengembalikan format JSON"""
    try:
        # Konversi bytes ke gambar PIL
        img = Image.open(io.BytesIO(image_bytes))
        
        # PROMPT (Perintah) untuk AI: Kita beri tahu dia cara kerjanya layaknya manusia
        prompt = """
        Anda adalah asisten akuntan yang sangat teliti. Baca struk setoran BCA dalam gambar ini.
        Abaikan coretan pulpen, abaikan kertas lain di latar belakang, fokus HANYA pada cetakan struk.
        
        Tugas Anda:
        1. Cari nilai "TOTAL SETORAN" (pastikan angkanya benar, abaikan teks Rp atau koma/titik). Format menjadi angka utuh (contoh: 73463900).
        2. Cari Rincian Transaksi (NO REK, Nominal Rp, dan BERITA). Gabungkan menjadi teks per baris dengan format: "No. Rek: [rekening] | Rp.[nominal] | Berita: [berita]". Gunakan pemisah \n antar baris.
        3. Kembalikan HANYA format JSON murni tanpa markdown tambahan.
        
        Format JSON yang wajib diikuti:
        {
            "Total Setoran": "angka total",
            "Rincian Transaksi": "teks rincian"
        }
        """
        
        # Kirim ke AI (Minta kembalian dalam bentuk JSON yang rapi)
        response = model.generate_content(
            [prompt, img],
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        
        # Ubah respon JSON dari AI menjadi Dictionary Python
        data_json = json.loads(response.text)
        return data_json
        
    except Exception as e:
        return {"error": str(e)}


# ---------- Fungsi Simpan ke Google Sheet ----------
def simpan_ke_sheet(rows: list) -> tuple:
    try:
        url = st.secrets["APPS_SCRIPT_URL"]
        token = st.secrets["APPS_SCRIPT_TOKEN"]
    except Exception:
        return False, "Secrets belum diisi (APPS_SCRIPT_URL dan APPS_SCRIPT_TOKEN)."
    try:
        resp = requests.post(
            url,
            data=json.dumps({"token": token, "rows": rows}),
            headers={"Content-Type": "text/plain"},
            timeout=60,
        )
        hasil_json = resp.json()
    except Exception as e:
        return False, f"Gagal terhubung: {e}"
    if hasil_json.get("ok"):
        return True, f"{hasil_json.get('count', 0)} baris tersimpan."
    return False, hasil_json.get("error", "Gagal menyimpan.")


# ---------- Upload & Kamera ----------
files = st.file_uploader(
    "Pilih foto struk:",
    type=["jpg", "jpeg", "png", "webp", "heic"],
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
        st.image(data, caption="Gambar yang dianalisis AI", use_container_width=True)
        
        with st.spinner("🤖 AI sedang membaca dan memahami struk..."):
            info = proses_dengan_ai(data)
            
        if "error" in info:
            st.error(f"Gagal memproses gambar: {info['error']}")
            continue
            
        # Tampilkan ekstraksi data di UI
        st.markdown("### 📌 Data Laporan Terdeteksi:")
        
        if info.get("Rincian Transaksi"):
            st.markdown("**📝 Rincian Penyetoran:**")
            for rincian in info["Rincian Transaksi"].split("\n"):
                st.info(rincian)
                
        if info.get("Total Setoran"):
            st.success(f"**💰 TOTAL SETORAN:** Rp. {info['Total Setoran']}")
        else:
            st.warning("⚠️ Nominal Total Setoran tidak ditemukan oleh AI.")
                
        hasil.append({
            "File": nama, 
            "Total Setoran": info.get("Total Setoran", ""),
            "Rincian Transaksi": info.get("Rincian Transaksi", "")
        })

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
