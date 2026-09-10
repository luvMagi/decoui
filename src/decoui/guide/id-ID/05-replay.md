# Menggunakan Ulang Parameter

Fitur Putar Ulang (Replay) memulihkan argumen eksekusi sebelumnya ke dalam formulir. Fitur ini **tidak** menjalankan ulang apa pun secara otomatis — tidak ada yang dieksekusi sampai Anda menekan tombol ``Jalankan`` (``Run``) sendiri. Ini adalah rancangan yang disengaja: memungkinkan Anda memulihkan operasi yang berdampak besar, mengubah satu kolom, dan baru kemudian memutuskan untuk menjalankannya.

Terdapat dua cara akses:

* Dari halaman alat: ``Putar Ulang`` (``Replay``) membuka riwayat yang sudah difilter untuk alat tersebut, sehingga Anda memilih dari riwayat alat itu sendiri, bukan semua alat.
* Dari riwayat: pilih baris mana saja dan tekan ``Gunakan Ulang Parameter`` (``Replay Params``).

Snapshot yang disimpan berbentuk teks, sehingga nilai akan dipulihkan dalam bentuk string dan dikonversi kembali saat alat dijalankan berikutnya. Sebagai contoh, jalur berkas akan dipulihkan sebagai string alih-alih objek jalur — yang kemudian dibaca ulang oleh alat persis seperti jika Anda mengetiknya secara manual.
