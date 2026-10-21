def preprocess(data: bytes, mode: str) -> np.ndarray:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    arr = np.array(img)
    
    # 1. Perbaikan Resolusi khusus Kamera Web
    h, w = arr.shape[:2]
    sisi_panjang = max(h, w)
    if sisi_panjang > 2000:  
        # Kecilkan jika terlalu besar
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
    # Sangat ampuh untuk meratakan pencahayaan kamera HP yang gelap/berbayang
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    if mode == "Grayscale":
        return gray
        
    # 4. Filter Noise Kamera dan Hitam-Putih (Adaptive Threshold)
    # Angka GaussianBlur dan Threshold diubah agar lebih ramah terhadap noise kamera
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 11
    )
