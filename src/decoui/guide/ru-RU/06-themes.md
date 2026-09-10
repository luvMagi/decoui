# Темы оформления

Кнопка с шестеренкой в правом верхнем углу открывает «Настройки», где перечислены все доступные темы с предварительно выбранной активной темой.

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

В decoui встроено 4 темы: светлая тема по умолчанию и три темы в панельном стиле.

Пользовательские темы считываются из каталога ``~/.decoui/themes`` — по одному файлу JSON на тему, без использования кода на Python. В файле темы определяются цвета, радиусы скругления углов и шрифты. Проще всего создать тему, унаследовав ее от встроенной с помощью ``extends`` и переопределив только нужные свойства.

Поскольку тема относится исключительно к внешнему виду, поврежденный файл никогда не приводит к сбою: нечитаемые файлы пропускаются, а остальные темы загружаются штатно. Если выбранную тему невозможно загрузить, приложение переключается на светлую тему по умолчанию. В обоих случаях при запуске приложения выводится соответствующее уведомление.

Ваш выбор сохраняется по идентификатору, поэтому переименование файла темы не приводит к сбросу настроек, а временно отсутствующая тема не снимается с выбора — она снова применится, как только файл появится на месте.
