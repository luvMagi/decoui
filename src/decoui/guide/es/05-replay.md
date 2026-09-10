# Reutilizar Parámetros

La función Repetir (Replay) restaura en el formulario los argumentos de una ejecución anterior. **No** vuelve a ejecutar nada automáticamente: no se ejecuta nada hasta que usted mismo pulsa ``Ejecutar`` (``Run``). Esto es intencionado: le permite recuperar una ejecución que realiza acciones críticas, modificar un solo campo y solo entonces decidir seguir adelante.

Hay dos formas de acceder:

* Desde la página de una herramienta, ``Repetir`` (``Replay``) abre el historial ya filtrado para esa herramienta, de modo que podrá elegir entre las ejecuciones de esa herramienta en lugar de verlas todas.
* Desde el historial, seleccione cualquier fila y pulse ``Reutilizar parámetros`` (``Replay Params``).

La instantánea guardada es texto, por lo que los valores se restauran en su formato de cadena de texto y se vuelven a convertir la próxima vez que se ejecute la herramienta. Una ruta de archivo, por ejemplo, se recupera como texto en lugar de un objeto de ruta, y la herramienta la vuelve a procesar exactamente igual que si la hubiera escrito usted mismo.
