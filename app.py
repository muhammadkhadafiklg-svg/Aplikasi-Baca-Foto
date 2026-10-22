"""Scanner Laporan Setoran - Powered by Gemini AI (Auto-Detect Model)
"""
import io
import json
import pandas as pd
import requests
import streamlit as st
from PIL import Image
import google.generativeai as genai

st.set_page_config(
    page_title="Scanner Laporan Setoran (AI)",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("🤖 Scanner Laporan (Gemini AI)")
st.caption("Upload foto struk. AI akan menembus coretan dan mencari nominal secara cerdas.")

# ---------- Konfigurasi AI & Auto-Detect Model ----------
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
    
    # 1. Tarik semua model yang diizinkan untuk API Key ini
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    
    if not available_models:
        st.error("⚠️ API Key Anda valid, tetapi tidak memiliki akses ke model apa pun. Silakan buat API Key baru di Google AI Studio.")
        st.stop()
        
    # 2. Pilih model otomatis (Prioritas: flash -> pro -> vision -> apapun yang ada)
    pilihan_model = None
    for target in ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro-vision', 'gemini-1.0-pro-vision']:
        for m_name in available_models:
            if target in m_name:
                pilihan_model = m_name
                break
        if pilihan_model:
            break
            
    if not pilihan_model:
        pilihan_model = available_models[0] # Ambil sembarang model jika tidak ada yang cocok
        
    # Bersihkan nama (Hapus prefix 'models/')
    if pilihan_model.startswith("models/"):
        pilihan_model = pilihan_model.replace("models/", "")
        
    model = genai.GenerativeModel(pilihan_model)
    st.sidebar.success(f"🤖 Model Aktif: {pilihan_model}")
    
except KeyError:
    st.error("⚠️ GEMINI_API_KEY belum dipasang di rahasia (Secrets) Streamlit!")
    st.stop()
except Exception as e:
    st.error(f"⚠️ Gagal menghubungkan ke Server Google: {e}")
    st.stop()


# ---------- Fungsi Ekstraksi via AI ----------
@st.cache_data(show_spinner=False, max_entries=30)
def proses_dengan_ai(image_bytes: bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        prompt = """
        Anda adalah asisten akuntan yang sangat teliti. Baca struk setoran BCA dalam gambar ini.
        Abaikan coretan pulpen, abaikan kertas lain di latar belakang, fokus HANYA pada cetakan struk.
        
        Tugas Anda:
        1. Cari nilai "TOTAL SETORAN" (pastikan angkanya benar, abaikan teks Rp atau koma/titik). Format menjadi angka utuh (contoh: 73463900).
        2. Cari Rincian Transaksi (NO REK, Nominal Rp, dan BERITA). Gabungkan menjadi teks per baris dengan format: "No. Rek: [rekening] | Rp.[nominal] | Berita: [berita]". Gunakan pemisah \n antar baris.
        3. Kembalikan HANYA format JSON murni.
        
        Format JSON yang wajib diikuti (jangan tambahkan tulisan apapun selain JSON ini):
        {
            "Total Setoran": "angka total",
            "Rincian Transaksi": "teks rincian"
        }
        """
        
        # Kirim ke AI
        response = model.generate_content([prompt, img])
        
        # Pembersihan ekstra agar kompatibel dengan semua model lama/baru
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        data_json = json.loads(raw_text.strip())
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
