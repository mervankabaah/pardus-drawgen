# DrawGen 🎨📄

DrawGen, Python ve Pygame kullanılarak geliştirilmiş modern arayüzlü, hızlı bir PDF görüntüleyici ve entegre beyaz tahta uygulamasıdır. Özellikle eğitimciler, öğrenciler ve sunum yapanlar için PDF üzerine çizim yapma, not alma ve boş beyaz tahta özelliklerini bir araya getirir.


## ✨ Özellikler

- **Gelişmiş PDF İşleme:** PyMuPDF (fitz) ile hızlı sayfa yükleme ve yüksek kaliteli (HQ) yakınlaştırma.
- **Çizim Araçları:** Kalem, Silgi ve Geometrik Şekiller (Çizgi, Ok, Kare, Daire, Üçgen).
- **Beyaz Tahta Modu:** PDF'ten bağımsız, sonsuz kaydırılabilir ızgaralı (grid) beyaz tahta alanı.
- **Akıcı Navigasyon:** Mouse tekerleği, klavye ok tuşları, numpad ile sayfaya gitme ve sürükle-bırak (pan) desteği.
- **Dokunmatik Desteği:** İki parmakla yakınlaştırma (pinch-to-zoom) ve dokunmatik kaydırma.
- **Modern Arayüz:** Yarı saydam (glassmorphism) paneller, yumuşak animasyonlar (Tween) ve tam ekran desteği.

---

## 🐧 Pardus İçin Kurulum Rehberi

Pardus (ve diğer Debian/Ubuntu tabanlı Linux dağıtımları) üzerinde uygulamayı sorunsuz çalıştırmak için aşağıdaki adımları sırasıyla terminalinizde uygulayın.

### 1. Gerekli Sistem Paketlerinin Kurulumu
Uygulamanın çalışması için Python, Tkinter (dosya seçici için) ve sanal ortam paketlerinin sistemde kurulu olması gerekir. Terminali açın ve şu komutu girin:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv python3-tk -y
2. Projenin İndirilmesi
Projeyi GitHub'dan bilgisayarınıza klonlayın (veya ZIP olarak indirip çıkartın) ve proje klasörüne girin:
code
Bash
git clone https://github.com/KULLANICI_ADINIZ/drawgen.git
cd drawgen
3. Sanal Ortam (Virtual Environment) Oluşturma ve Aktifleştirme
Modern Pardus sürümlerinde Python paketlerinin sistem genelinde çakışmasını önlemek için sanal ortam kullanılması tavsiye edilir:
code
Bash
python3 -m venv venv
source venv/bin/activate
(Not: Terminalinizde sol tarafta (venv) yazısını gördüğünüzde sanal ortam aktif demektir. Uygulamayı her çalıştırmak istediğinizde proje klasöründe source venv/bin/activate komutunu çalıştırmalısınız.)
4. Python Bağımlılıklarının Yüklenmesi
Uygulamanın ihtiyaç duyduğu Pygame ve PyMuPDF paketlerini kurun:
code
Bash
pip install pygame PyMuPDF
🚀 Kullanım
Kurulum tamamlandıktan sonra (ve sanal ortam aktifken) uygulamayı şu komutla başlatabilirsiniz:
code
Bash
python3 main.py
📂 Klasör Yapısı Hakkında Önemli Not
Uygulama ilk çalıştığında ana dizinde otomatik olarak pdf_files ve assets adında iki klasör oluşturur.
PDF Ekleme: Ana ekrandaki "PDF Ekle" butonunu kullanabilir veya PDF dosyalarınızı doğrudan pdf_files klasörünün içine atabilirsiniz.
İkonlar: Menü butonlarının daha şık görünmesi için aşağıdaki isimlerdeki ikonları (tercihen şeffaf PNG) assets/ klasörünün içine ekleyebilirsiniz:
hand.png
pen.png
shape.png
eraser.png
trash.png
(Eğer ikonları koymazsanız, uygulama otomatik olarak ikonların yerine harf/metin gösterecektir, bu da çalışmasını engellemez.)
⌨️ Kısayollar ve Kontroller
Genel:
F : Tam Ekranı (Fullscreen) aç/kapat.
ESC : PDF okuyucudan çık ve kitaplığa (GridScene) dön.
PDF Görünümü & Çizim:
Sol Tık : Çizim yapma / Butonlara tıklama / Çift tıklama ile yakınlaştırmayı sıfırlama.
Orta Tık (Scroll Tuşu) Basılı Tutma : Sayfayı kaydırma / Sürükleme.
Mouse Tekerleği : Sayfayı Yakınlaştırma / Uzaklaştırma (Zoom).
Yön Tuşları (← → ↑ ↓) veya Page Up/Down : Önceki/Sonraki sayfaya geçiş.
🤝 Katkıda Bulunma
Geliştirmelere açığız! Katkıda bulunmak isterseniz lütfen projeyi fork'layın ve değişikliklerinizi Pull Request olarak gönderin.
Fork'layın
Yeni bir dal (branch) oluşturun (git checkout -b ozellik/YeniOzellik)
Değişikliklerinizi commit'leyin (git commit -m 'Yeni özellik eklendi')
Dalınızı push'layın (git push origin ozellik/YeniOzellik)
Pull Request açın
📝 Lisans
Bu proje MIT Lisansı altında lisanslanmıştır. Daha fazla bilgi için LICENSE dosyasına bakabilirsiniz.
code
Code
### Sizin yapmanız gereken küçük değişiklikler:
1. `https://github.com/KULLANICI_ADINIZ/drawgen.git` kısmını kendi GitHub deponuzun linki ile değiştirin.
2. Varsa uygulamanızın ekran görüntüsünü projenize yükleyip en üstteki `![DrawGen Ekran Görüntüsü]` satırının linkini o ekran görüntüsünün linkiyle güncelleyin.