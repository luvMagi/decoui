# Temas

El botón de engranaje situado en la esquina superior derecha abre Configuración, donde se muestran todos los temas disponibles y se selecciona inicialmente el que está activo en ese momento.

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

decoui incluye 4 temas predeterminados: un tema claro por defecto y tres temas con estilo de paneles.

Sus temas personalizados se leen desde ``~/.decoui/themes``: un archivo JSON por tema, sin necesidad de código Python. El archivo de tema define colores, radios de esquinas y fuentes; la forma más sencilla de crear uno es partir de un tema integrado usando ``extends`` y sobrescribir únicamente lo que desee modificar.

Dado que el tema es solo una configuración visual, un archivo defectuoso nunca resulta fatal: los archivos que no puedan leerse se omiten y los demás temas se cargan con normalidad, y si no se puede resolver una selección se vuelve al tema claro predeterminado. Ambos casos se notifican al iniciar la aplicación.

Su selección se guarda por ID, por lo que renombrar un tema no hace que se pierda la configuración, y si un tema desaparece temporalmente no se deselecciona: volverá a aplicarse tan pronto como el archivo esté disponible de nuevo.
