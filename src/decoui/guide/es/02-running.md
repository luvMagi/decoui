# Ejecutar una Herramienta

El formulario de una herramienta se genera a partir de los parámetros declarados por su función, por lo que los campos corresponden a lo que esa herramienta específica requiere.

* Un campo marcado con un asterisco rojo (*) es obligatorio y no tiene valor predeterminado.
* ``Parámetros`` (``Parameters``) pliega el formulario una vez completado, para dar más espacio al área de salida.
* ``Ejecutar`` (``Run``) inicia la herramienta. Mientras se ejecuta, el botón ``Ejecutar`` se reemplaza por ``Detener`` (``Stop``).
* ``Restablecer`` (``Reset``) devuelve todos los campos a su valor predeterminado declarado.

Algunas herramientas solicitan confirmación antes de iniciarse; esto lo declara la propia herramienta, no es una decisión de la aplicación.

``Detener`` interrumpe una herramienta en ejecución. Una herramienta que solo esté calculando o en reposo (sleep) se detiene de inmediato. Aquella que esté esperando a un programa externo solo se detendrá si su autor implementó la limpieza para ese caso; de lo contrario, la página vuelve al estado inactivo mientras el programa externo continúa ejecutándose.

La barra de progreso oscila de un lado a otro cuando una herramienta no ha especificado la cantidad total de trabajo, y muestra un porcentaje real cuando sí lo ha hecho.
