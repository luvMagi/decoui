# Tema

Ikon roda gigi di kanan atas membuka Pengaturan, yang menampilkan daftar semua tema yang tersedia dan memilih tema yang saat ini sedang aktif secara default.

Tema diterapkan sekali saat aplikasi dimulai, sehingga perubahan baru akan berlaku pada eksekusi **berikutnya**. Tidak ada tampilan jendela yang berubah saat dialog ditutup; kotak dialog juga memberikan pemberitahuan ini sebelum Anda memilih.

decoui dilengkapi dengan 4 tema bawaan: tema terang bawaan dan tiga tema bergaya panel.

Tema kustom Anda dibaca dari ``~/.decoui/themes`` — satu berkas JSON untuk setiap tema, tanpa memerlukan kode Python. Berkas tema menentukan warna, radius sudut (border-radius), dan font; cara paling mudah untuk membuatnya adalah dengan mewarisi tema bawaan menggunakan ``extends`` dan hanya menimpa properti yang ingin Anda ubah.

Karena tema hanyalah pengaturan tampilan visual, berkas tema yang rusak tidak akan menyebabkan aplikasi crash: berkas yang tidak dapat dibaca akan dilewati dan tema lainnya tetap dimuat seperti biasa; jika tema yang dipilih tidak dapat dimuat, aplikasi akan kembali ke tema terang bawaan. Dalam kedua kasus, pemberitahuan akan ditampilkan saat aplikasi dimulai.

Pilihan Anda disimpan berdasarkan ID, sehingga mengubah nama tema tidak akan menghilangkan setelan Anda, dan tema yang sementara hilang tidak akan dibatalkan pemilihannya — tema akan kembali aktif begitu berkas tersedia lagi.
