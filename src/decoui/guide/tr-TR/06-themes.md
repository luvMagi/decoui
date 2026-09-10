# Temalar

Sağ üstteki dişli simgesi, mevcut tüm temaları listeleyen ve o anda etkin olan temanın seçili olarak geldiği Ayarlar'ı açar.

Temalar uygulama başlatıldığında bir kez uygulanır, bu nedenle yapılan bir değişiklik **bir sonraki** çalıştırmada geçerli olur. İletişim kutusu kapatıldığında açık olan pencerede hiçbir şey değişmez; iletişim kutusunda da seçiminizi yapmadan önce bu durum belirtilir.

decoui 4 dahili tema ile birlikte gelir: varsayılan bir açık renk tema ve üç panel tarzı tema.

Özel temalarınız ``~/.decoui/themes`` dizininden okunur — Python kodu gerekmeksizin her tema için bir JSON dosyası kullanılır. Bir tema dosyası renklerini, köşe yuvarlama yarıçaplarını ve yazı tiplerini tanımlar; özel bir tema oluşturmanın en kolay yolu, dahili bir temadan ``extends`` ile miras alıp yalnızca değiştirmek istediğiniz özellikleri geçersiz kılmaktır.

Tema yalnızca bir görsel sunum ayarı olduğundan, bozuk bir tema dosyası asla uygulamanın çökmesine yol açmaz: okunamayan bir dosya atlanır ve diğer tüm temalar normal şekilde yüklenir; çözümlenemeyen bir tema seçilmişse varsayılan açık renk temaya geri dönülür. Her iki durumda da uygulama başlatılırken bir bildirim gösterilir.

Seçiminiz ID ile saklanır, bu sayede bir temayı yeniden adlandırmak ayarınızı kaybettirmez ve geçici olarak bulunamayan bir temanın seçimi kaldırılmaz — dosya geri geldiğinde otomatik olarak yeniden uygulanır.
