# Tema

Ikon roda gigi di kanan atas membuka Pengaturan, yang menampilkan daftar semua tema yang tersedia dan memilih tema yang saat ini sedang aktif secara default.

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

decoui dilengkapi dengan 4 tema bawaan: tema terang bawaan dan tiga tema bergaya panel.

Tema kustom Anda dibaca dari ``~/.decoui/themes`` — satu berkas JSON untuk setiap tema, tanpa memerlukan kode Python. Berkas tema menentukan warna, radius sudut (border-radius), dan font; cara paling mudah untuk membuatnya adalah dengan mewarisi tema bawaan menggunakan ``extends`` dan hanya menimpa properti yang ingin Anda ubah.

Karena tema hanyalah pengaturan tampilan visual, berkas tema yang rusak tidak akan menyebabkan aplikasi crash: berkas yang tidak dapat dibaca akan dilewati dan tema lainnya tetap dimuat seperti biasa; jika tema yang dipilih tidak dapat dimuat, aplikasi akan kembali ke tema terang bawaan. Dalam kedua kasus, pemberitahuan akan ditampilkan saat aplikasi dimulai.

Pilihan Anda disimpan berdasarkan ID, sehingga mengubah nama tema tidak akan menghilangkan setelan Anda, dan tema yang sementara hilang tidak akan dibatalkan pemilihannya — tema akan kembali aktif begitu berkas tersedia lagi.
