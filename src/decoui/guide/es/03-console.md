# Salida y Registros

Todo lo que una herramienta imprime (print) o registra en el log aparece en la consola de salida situada debajo del formulario, en tiempo real, mientras se ejecuta. Los niveles de registro están codificados por colores, y la salida normal de ``print`` se muestra con un color propio para distinguirla fácilmente de los mensajes de registro.

* ``Copiar`` (``Copy``): copia todo el contenido de la consola al portapapeles.
* ``Ver registro`` (``View Log``): abre la salida de la ejecución en una ventana independiente y de tamaño ajustable.

La ventana de registro es la opción indicada cuando hay un volumen elevado de salida. Ofrece las siguientes ventajas:

* Un interruptor por cada nivel: desactive ``DEBUG`` para ver solo lo relevante, o pulse ``Ninguno`` (``None``) y luego ``ERROR`` para ver únicamente los errores.
* Un cuadro de búsqueda que filtra las líneas coincidentes.
* ``Copiar todo`` (``Copy All``).

Filtrar en esa ventana nunca altera la consola de la página de origen; la ventana mantiene su propia copia de las líneas.

La salida de cada ejecución se almacena, por lo que el mismo registro se puede reabrir posteriormente desde el historial mucho después de haber cerrado la pestaña.
