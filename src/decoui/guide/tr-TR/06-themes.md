# Temalar

Sağ üstteki dişli simgesi, mevcut tüm temaları listeleyen ve o anda etkin olan temanın seçili olarak geldiği Ayarlar'ı açar.

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

decoui 4 dahili tema ile birlikte gelir: varsayılan bir açık renk tema ve üç panel tarzı tema.

Özel temalarınız ``~/.decoui/themes`` dizininden okunur — Python kodu gerekmeksizin her tema için bir JSON dosyası kullanılır. Bir tema dosyası renklerini, köşe yuvarlama yarıçaplarını ve yazı tiplerini tanımlar; özel bir tema oluşturmanın en kolay yolu, dahili bir temadan ``extends`` ile miras alıp yalnızca değiştirmek istediğiniz özellikleri geçersiz kılmaktır.

Tema yalnızca bir görsel sunum ayarı olduğundan, bozuk bir tema dosyası asla uygulamanın çökmesine yol açmaz: okunamayan bir dosya atlanır ve diğer tüm temalar normal şekilde yüklenir; çözümlenemeyen bir tema seçilmişse varsayılan açık renk temaya geri dönülür. Her iki durumda da uygulama başlatılırken bir bildirim gösterilir.

Seçiminiz ID ile saklanır, bu sayede bir temayı yeniden adlandırmak ayarınızı kaybettirmez ve geçici olarak bulunamayan bir temanın seçimi kaldırılmaz — dosya geri geldiğinde otomatik olarak yeniden uygulanır.
