# 主题

右上角的齿轮按钮可打开“设置”，其中列出了所有可用主题，并默认定位到当前生效的主题。

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

decoui 自带 4 种主题：默认浅色主题，以及 3 种面板风格的主题。

您自定义的主题从 ``~/.decoui/themes`` 读取——每个主题对应一个 JSON 文件，无需编写 Python 代码。主题文件定义了颜色、圆角半径和字体；编写自定义主题最简单的方法是使用 ``extends`` 从内置主题继承，并仅覆盖需要修改的部分。

主题属于展示层配置，因此损坏的主题绝不会导致程序崩溃：无法读取的文件会被跳过，其他主题仍能正常加载；如果所选主题无法解析，则会回退到浅色主题。无论哪种情况，都会在应用程序启动时给出提示。

您的选择按 ID 保存，因此重命名主题不会导致选择丢失，暂时缺失的主题也不会被取消选择——一旦文件恢复，它将重新生效。
