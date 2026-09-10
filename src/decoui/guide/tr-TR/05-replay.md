# Parametreleri Yeniden Kullanma

Yeniden Oynatma (Replay) özelliği, önceki bir çalıştırmanın argümanlarını forma geri yükler. Hiçbir şeyi otomatik olarak yeniden **çalıştırmaz** — siz bizzat ``Çalıştır`` (``Run``) butonuna basana kadar hiçbir işlem yürütülmez. Bu bilinçli bir tasarımdır: kritik bir işlemi geri yüklemenize, tek bir alanı değiştirmenize ve ardından devam etmeye karar vermenize olanak tanır.

İki erişim yolu vardır:

* Bir araç sayfasından: ``Yeniden Oynat`` (``Replay``) butonu geçmişi doğrudan o araca göre filtrelenmiş olarak açar, böylece tüm kayıtlar yerine yalnızca o aracın kendi çalıştırmaları arasından seçim yapabilirsiniz.
* Geçmiş sayfasından: herhangi bir satırı seçin ve ``Parametreleri Yeniden Kullan`` (``Replay Params``) butonuna basın.

Kaydedilen anlık görüntü metin formatındadır, bu nedenle değerler dize biçiminde geri yüklenir ve araç bir sonraki çalıştırılışında yeniden dönüştürülür. Örneğin bir dosya yolu, yol nesnesi yerine dize olarak geri yüklenir — araç daha sonra bunu klavyeden yazmışsınız gibi tamamen aynı şekilde okur.
