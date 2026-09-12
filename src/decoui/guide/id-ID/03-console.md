# Keluaran dan Log

Semua yang dicetak (print) atau dicatat dalam log oleh alat akan muncul secara langsung pada konsol keluaran di bawah formulir saat alat berjalan. Tingkat log diberi kode warna, dan keluaran ``print`` standar ditampilkan dengan warnanya sendiri agar tetap mudah dibedakan dari catatan log.

Jika aplikasi mengaktifkannya, nilai kembalian dari eksekusi yang berhasil dicetak di akhir keluaran: satu baris kosong, garis ``========== Hasil ==========``, lalu nilainya. Tidak ada yang dicetak ketika eksekusi gagal, dibatalkan, atau tidak mengembalikan apa pun.

* ``Salin`` (``Copy``): menyalin seluruh isi konsol ke papan klip.
* ``Lihat Log`` (``View Log``): membuka keluaran eksekusi kali ini dalam jendela terpisah yang ukurannya dapat disesuaikan.

Jendela log sangat disarankan saat terdapat volume keluaran yang besar. Jendela ini menyediakan fitur tambahan:

* Tombol alih untuk setiap tingkat log — nonaktifkan ``DEBUG`` untuk hanya melihat hal penting, atau tekan ``Tidak Ada`` (``None``) lalu aktifkan ``ERROR`` untuk hanya melihat kesalahan.
* Kotak pencarian untuk memfilter baris yang cocok.
* Tombol ``Salin Semua`` (``Copy All``).

Memfilter pada jendela log tidak akan memengaruhi konsol pada halaman asal; jendela ini menyimpan salinan barisnya sendiri.

Keluaran setiap eksekusi akan disimpan, sehingga log yang sama dapat dibuka kembali dari riwayat meskipun tab telah ditutup lama.
