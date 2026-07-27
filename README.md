# 📚 DrawGen

DrawGen, **Pygame** ve **PyMuPDF** kullanılarak geliştirilmiş modern bir PDF görüntüleme ve çizim uygulamasıdır.

## Özellikler

- 📄 PDF görüntüleme
- 🔍 Yakınlaştırma / Uzaklaştırma
- ✍️ Kalem ile çizim
- 🧽 Silgi
- 📐 Şekil çizme
- 📖 Sayfa geçişleri
- 🖥️ Tam ekran modu
- 📝 Beyaz tahta modu
- ⚡ Yüksek performanslı PDF render sistemi

---

# Pardus Kurulumu

## 1. Sistemi Güncelleyin

```bash
sudo apt update
sudo apt upgrade -y
```

---

## 2. Python Kurulu mu Kontrol Edin

```bash
python3 --version
```

Python yüklü değilse:

```bash
sudo apt install python3 python3-pip python3-venv -y
```

---

## 3. Gerekli Sistem Paketleri

```bash
sudo apt install \
python3-dev \
python3-tk \
libsdl2-dev \
libsdl2-image-dev \
libsdl2-mixer-dev \
libsdl2-ttf-dev \
libfreetype6-dev \
libportmidi-dev \
libjpeg-dev \
zlib1g-dev \
libopenjp2-7 \
libtiff-dev \
build-essential -y
```

---

## 4. Projeyi Klonlayın

```bash
https://github.com/mervankabaah/pardus-drawgen.git
```

veya ZIP indirip çıkartın.

Daha sonra:

```bash
cd DrawGen
```

---

## 5. Sanal Ortam Oluşturun

```bash
python3 -m venv venv
```

Aktifleştirin:

```bash
source venv/bin/activate
```

---

## 6. Gerekli Python Kütüphaneleri

```bash
pip install --upgrade pip
```

Ardından:

```bash
pip install pygame pymupdf
```

İsterseniz:

```bash
pip freeze > requirements.txt
```

ve daha sonra sadece:

```bash
pip install -r requirements.txt
```

kullanabilirsiniz.

---

# Çalıştırma

```bash
python3 main.py
```

---

# Klasör Yapısı

```
DrawGen/
│
├── assets/
│   ├── hand.png
│   ├── pen.png
│   ├── eraser.png
│   ├── shape.png
│   └── trash.png
│
├── pdf_files/
│
├── main.py
│
└── README.md
```

---

# PDF Ekleme

PDF dosyalarınızı:

```
pdf_files/
```

klasörüne kopyalayabilir veya uygulama içerisindeki **PDF Ekle** butonunu kullanabilirsiniz.

---

# Kullanılan Teknolojiler

- Python 3
- Pygame
- PyMuPDF (fitz)
- Tkinter

---

# Lisans

Bu proje açık kaynak olarak paylaşılmıştır.

İstediğiniz gibi geliştirebilir ve katkıda bulunabilirsiniz.
