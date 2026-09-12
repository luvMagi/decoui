<div align="center">
  <p><a href="README.md">English</a> · <strong>简体中文</strong> · <a href="README-JP.md">日本語</a> · <a href="README-KR.md">한국어</a></p>
  <img src="docs/images/icon.png" width="96" alt="decoui icon">
  <h1>decoui</h1>
  <p><strong>给 Python 方法加上标注，直接交付一个原生桌面工具。</strong></p>
  <p>Decorator-driven GUI framework for Python · Built with PySide6</p>

  <p>
    <a href="https://pypi.org/project/decoui/"><img src="https://img.shields.io/pypi/v/decoui?label=PyPI&color=3775A9" alt="PyPI version"></a>
    <img src="https://img.shields.io/pypi/pyversions/decoui?label=Python" alt="Python versions">
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="Apache 2.0 license"></a>
  </p>
</div>

decoui 把函数签名变成表单，把执行过程变成日志，把每次运行变成可追溯记录。你只需要维护 Python 业务逻辑，不必从零编写 Qt 窗口、线程调度、历史页和帮助中心。

![decoui application preview](docs/images/preview-theme_preview_diagonal.png)

## decoui 可以帮你

| 从代码到工具 | decoui 做了什么 |
|---|---|
| **① 标注** | 用 `@toolset`、`@tool` 和类型注解描述已有 Python 方法。 |
| **② 收集** | 自动发现工具集，或通过 `toolsets=[...]` 精确指定入口内容。 |
| **③ 入口** | 自动生成侧边栏、标签筛选、多工具页签和统一设置入口。 |
| **④ 表单** | 将类型映射为原生控件，并提供自动补全、级联填充和动态默认值。 |
| **⑤ 留痕** | 后台执行任务，实时收集 `print` / `logging`，持久化参数、状态与日志，并支持 Replay。 |
| **⑥ 交付** | 用主题、i18n 和自动收集的帮助文档，把内部脚本交付成真正可用的桌面应用。 |

## 帮助与多语言，开箱即用

### docstring 写一次，用户帮助自动成册

**不再维护第二套说明。** decoui 自动收集 docstring，生成可搜索、可导航的用户帮助页，并完整呈现摘要、参数、返回值、异常和交叉引用。

<p align="center">
  <img src="docs/images/auto-summary-help.png" width="100%" alt="decoui 从 docstring 自动收集并生成用户帮助文档">
</p>

### 一套界面，服务不同语言的用户

**语言不必写死在界面里。** 通过 i18n 选择界面语言，再用应用 catalogue 配置自己的标签、字段、说明与帮助内容，无需重做 UI。

<p align="center">
  <img src="docs/images/i18n-support.png" width="100%" alt="decoui 界面语言选择与 i18n 多语言支持">
</p>

## 不只是“生成一个表单”

- **主题（Themes）**：内置 Light、Cockpit、Mission Control、Industrial 1980s；也可用 JSON 扩展或覆盖，运行中的任务不会因换肤中断。
- **国际化（i18n）**：decoui 自身界面带语言目录；你的工具标签、字段、帮助内容也可以用独立 catalogue 翻译。
- **帮助文档收集（Help authoring）**：从 docstring 自动生成摘要、参数、返回值和异常说明，长文可接入 Markdown，并支持页面交叉引用。
- **可靠执行（Execution）**：工具在后台线程运行，支持进度、超时、停止和子进程输出流式回传。
- **历史与复用（History & Replay）**：SQLite 保存每次执行；筛选、查看完整日志、恢复历史参数都在应用里完成。

## 30 秒开始

```bash
pip install decoui
```

需要 Python 3.10+。默认依赖轻量的 `PySide6-Essentials`，不会额外安装完整 `PySide6-Addons`。

```python
import logging

from decoui import gui_main, tool, toolset


@toolset(label="Text Tools", tags=["text"])
class TextTools:
    @tool(
        label="Count Characters",
        description="Count characters, words, and lines.",
        placeholders={"content": "Paste text here..."},
    )
    def count(self, content: str = "") -> None:
        words = len(content.split())
        logging.info("%d chars / %d words", len(content), words)


if __name__ == "__main__":
    gui_main(title="My Tools")
```

运行文件即可。`gui_main()` 会发现调用方作用域中的 `@toolset`，并生成完整应用入口。

```bash
python app.py
```

## 类型就是表单

| Python 类型 | 自动生成的控件 |
|---|---|
| `str` | 单行输入框 |
| `int` / `float` | 数字输入框 |
| `bool` | 复选框 |
| `list` / `dict` | 多行编辑器 |
| `Enum` | 下拉选择框 |
| `pathlib.Path` | 路径输入框 + 文件/目录选择按钮 |

再通过 `completions`、`cascade`、`defaults` 增加自动补全、联动填充和运行时默认值；业务函数仍然可以脱离 GUI 直接调用和测试。

## 文档入口

完整文档已经从 README 拆出，按任务查找即可：

- [完整 API 与行为参考](docs/reference.md)：装饰器、类型映射、表单辅助、主题、存储、历史等
- [启动生命周期](docs/startup-lifecycle.md)：初始化顺序、加载数据和失败处理
- [应用国际化](docs/translating-an-application.md)：翻译工具文本与长篇帮助
- [帮助内容编写](docs/help-authoring.md)：docstring、Markdown 与交叉引用
- [取消与外部进程](docs/cancelling-a-run.md)：正确实现 Stop、timeout 和清理
- [设计与实现](docs/design.md)：模块结构、执行引擎、存储和 UI 架构

完整示例位于 [`src/decoui/example/`](src/decoui/example/)，运行：

```bash
python -m decoui.example
```

## 适合这些场景

数据处理器、运维工具、批处理入口、内部效率工具、需要交给非开发者使用的 Python 脚本——尤其适合“业务逻辑已经有了，只缺一个可靠桌面入口”的项目。

> decoui 当前处于 Alpha 阶段。欢迎通过 [Issues](https://github.com/luvmagi/decoui/issues) 反馈实际使用中的问题。

## License

[Apache-2.0](LICENSE)
