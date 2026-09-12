# Menjalankan Alat

Formulir input suatu alat dibuat secara otomatis berdasarkan parameter yang dideklarasikan oleh fungsinya, sehingga kolom input sesuai persis dengan kebutuhan alat tersebut.

* Kolom yang ditandai dengan tanda bintang merah (*) bersifat wajib diisi dan tidak memiliki nilai bawaan.
* ``Parameter`` (``Parameters``) akan melipat formulir setelah diisi, guna memberikan ruang lebih luas bagi area keluaran.
* ``Jalankan`` (``Run``) memulai alat. Saat sedang berjalan, tombol ``Jalankan`` akan berubah menjadi ``Hentikan`` (``Stop``).
* ``Atur Ulang`` (``Reset``) mengembalikan setiap kolom ke nilai bawaan yang telah ditentukan.

Beberapa alat meminta konfirmasi sebelum dimulai; hal ini ditentukan oleh alat itu sendiri, bukan keputusan aplikasi.

``Hentikan`` akan menginterupsi alat yang sedang berjalan. Alat yang hanya melakukan komputasi murni atau dalam status jeda (sleep) akan berhenti seketika. Alat yang sedang menunggu program eksternal hanya akan berhenti jika pembuatnya telah menyiapkan pembersihan untuk kasus tersebut — jika tidak, halaman akan kembali ke status diam (idle) sementara program eksternal tetap berjalan.

Bilah kemajuan akan bergerak bolak-balik jika alat tidak menentukan total volume pekerjaan, dan akan menampilkan persentase sebenarnya jika informasi tersebut tersedia.

Setelah eksekusi selesai, ada tiga hal yang bisa dilakukan dengan nilai yang
dikembalikan:

* ``Salin hasil`` menaruh nilai itu di papan klip.
* ``Kirim hasil`` mengisikannya ke kolom alat lain, membuka alat tersebut dan
  membawanya ke depan. Tombol ini hanya muncul bila ada alat lain yang
  menyatakan menerima nilai sejenis, dan ia menimpa isi kolom yang ada.
* Aplikasi juga dapat meminta nilai itu dicetak ke konsol keluaran -- lihat
  halaman berikutnya.

Kedua tombol menampilkan nilainya pada tooltip, dan keduanya tetap nonaktif
sampai sebuah eksekusi mengembalikan sesuatu.
