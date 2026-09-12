# Çıktı ve Günlükler

Bir aracın yazdırdığı (print) veya günlüğe kaydettiği her şey, araç çalışırken formun altındaki çıktı konsolunda gerçek zamanlı olarak görüntülenir. Günlük seviyeleri renkle kodlanmıştır ve standart ``print`` çıktısı, günlük mesajlarından ayırt edilebilmesi için kendi renginde gösterilir.

Uygulama bunu açtıysa, başarılı bir çalıştırmanın dönüş değeri çıktının sonunda yazdırılır: bir boş satır, ``========== Sonuç ==========`` çizgisi ve ardından değerin kendisi. Başarısız olan, iptal edilen ya da hiçbir şey döndürmeyen çalıştırmalarda hiçbir şey yazdırılmaz.

* ``Kopyala`` (``Copy``): Konsolun tüm içeriğini panoya kopyalar.
* ``Günlüğü Görüntüle`` (``View Log``): Bu çalıştırmanın çıktısını ayrı, boyutu ayarlanabilir bir pencerede açar.

Çıktı miktarı çok olduğunda günlük penceresinin kullanılması önerilir. Günlük penceresi şu özellikleri sunar:

* Her seviye için bir açma/kapatma düğmesi — yalnızca önemli olanları görmek için ``DEBUG`` seviyesini kapatabilir veya yalnızca hataları görmek için önce ``Yok`` (``None``) ardından ``ERROR`` seçeneğini açabilirsiniz.
* Eşleşen satırları filtreleyen bir arama kutusu.
* ``Tümünü Kopyala`` (``Copy All``) butonu.

Günlük penceresindeki filtreleme, kaynak sayfadaki konsolu kesinlikle etkilemez; pencere satırların bağımsız bir kopyasını tutar.

Her çalıştırmanın çıktısı kaydedilir, böylece sekme kapatıldıktan uzun bir süre sonra bile geçmişten aynı günlük yeniden açılabilir.
