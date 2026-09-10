# Temas

El botón de engranaje situado en la esquina superior derecha abre Configuración, donde se muestran todos los temas disponibles y se selecciona inicialmente el que está activo en ese momento.

Los temas se aplican una sola vez al iniciar la aplicación, por lo que cualquier cambio surte efecto la **próxima** vez que se ejecute. La ventana abierta no cambia en absoluto al cerrar el cuadro de diálogo; este mismo mensaje se indica antes de realizar la selección.

decoui incluye 4 temas predeterminados: un tema claro por defecto y tres temas con estilo de paneles.

Sus temas personalizados se leen desde ``~/.decoui/themes``: un archivo JSON por tema, sin necesidad de código Python. El archivo de tema define colores, radios de esquinas y fuentes; la forma más sencilla de crear uno es partir de un tema integrado usando ``extends`` y sobrescribir únicamente lo que desee modificar.

Dado que el tema es solo una configuración visual, un archivo defectuoso nunca resulta fatal: los archivos que no puedan leerse se omiten y los demás temas se cargan con normalidad, y si no se puede resolver una selección se vuelve al tema claro predeterminado. Ambos casos se notifican al iniciar la aplicación.

Su selección se guarda por ID, por lo que renombrar un tema no hace que se pierda la configuración, y si un tema desaparece temporalmente no se deselecciona: volverá a aplicarse tan pronto como el archivo esté disponible de nuevo.
