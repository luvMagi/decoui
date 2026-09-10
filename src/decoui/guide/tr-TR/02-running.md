# Bir Aracı Çalıştırma

Bir aracın formu, fonksiyonunun bildirdiği parametrelerden otomatik olarak oluşturulur; bu sayede giriş alanları ilgili aracın tam olarak ihtiyaç duyduğu değerlerle eşleşir.

* Kırmızı yıldız (*) ile işaretlenmiş alanlar zorunludur ve varsayılan bir değeri yoktur.
* ``Parametreler`` (``Parameters``), form doldurulduktan sonra çıktı alanına daha fazla yer açmak için formu daraltır.
* ``Çalıştır`` (``Run``) aracı başlatır. Çalışma sırasında ``Çalıştır`` butonu ``Durdur`` (``Stop``) ile değiştirilir.
* ``Sıfırla`` (``Reset``) tüm alanları bildirilen varsayılan değerlerine geri döndürür.

Bazı araçlar başlamadan önce onay ister; bu durum uygulamanın kararı değil, aracın kendi bildirdiği bir davranıştır.

``Durdur`` çalışan bir aracı kesintiye uğratır. Yalnızca hesaplama yapan veya bekleme (sleep) durumundaki bir araç hemen durur. Harici bir programı bekleyen bir araç ise, yalnızca geliştiricisi bu durum için bir temizleme mantığı tanımlamışsa durur — aksi takdirde harici program çalışmaya devam ederken sayfa boşta (idle) durumuna döner.

İlerleme çubuğu, bir araç toplam iş miktarını belirtmediğinde iki yana salınır; iş miktarı belirtildiğinde ise gerçek bir yüzde gösterir.
