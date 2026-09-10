<div align="center">
  <p><a href="README.md">English</a> · <a href="README-ZH-CN.md">简体中文</a> · <a href="README-JP.md">日本語</a> · <strong>한국어</strong></p>
  <img src="docs/images/icon.png" width="96" alt="decoui icon">
  <h1>decoui</h1>
  <p><strong>Python 메서드에 어노테이션을 추가해, 바로 사용할 수 있는 네이티브 데스크톱 도구로 만드세요.</strong></p>
  <p>Decorator-driven GUI framework for Python · Built with PySide6</p>

  <p>
    <a href="https://pypi.org/project/decoui/"><img src="https://img.shields.io/pypi/v/decoui?label=PyPI&color=3775A9" alt="PyPI version"></a>
    <img src="https://img.shields.io/pypi/pyversions/decoui?label=Python" alt="Supported Python versions">
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license"></a>
  </p>
</div>

decoui는 함수 시그니처를 폼으로, 실행 과정을 실시간 로그로, 모든 실행을 추적 가능한 기록으로 바꿉니다. 개발자는 Python 비즈니스 로직에만 집중하면 됩니다. Qt 창, 백그라운드 실행, 기록, 재실행, 설정, 도움말 시스템은 decoui가 제공합니다.

![decoui application preview](docs/images/preview-theme_preview_diagonal.png)

## decoui가 해주는 일

| 코드에서 데스크톱 도구까지 | decoui가 제공하는 기능 |
|---|---|
| **① 어노테이션** | 기존 Python 메서드를 `@toolset`, `@tool`, 타입 어노테이션으로 정의합니다. |
| **② 수집** | 도구 모음을 자동으로 탐색하거나 `toolsets=[...]`로 직접 지정합니다. |
| **③ 실행** | 검색 가능한 사이드바, 태그 필터, 여러 도구 탭, 공통 설정 진입점을 자동으로 생성합니다. |
| **④ 입력** | Python 타입을 네이티브 위젯으로 변환하고, 필요에 따라 자동 완성, 연쇄 입력, 지연 기본값을 제공합니다. |
| **⑤ 추적** | 작업을 백그라운드에서 실행하고 `print`와 `logging`, 매개변수, 상태를 저장하며 이전 입력을 다시 사용할 수 있습니다. |
| **⑥ 배포** | 테마, i18n 카탈로그, 자동 수집된 도움말을 적용해 내부 스크립트를 실용적인 데스크톱 애플리케이션으로 제공합니다. |

## 도움말과 다국어 지원을 처음부터

### docstring이 사용자 도움말로 완성됩니다

**메서드 설명은 한 번만 작성하세요.** decoui가 docstring을 자동으로 수집해 요약, 매개변수, 반환값, 예외, 상호 참조를 갖춘 검색 및 탐색 가능한 도움말 페이지를 생성합니다.

<p align="center">
  <img src="docs/images/auto-summary-help.png" width="100%" alt="decoui가 docstring에서 사용자 도움말을 자동으로 생성하는 화면">
</p>

### 하나의 화면을 사용자의 언어로

**언어를 UI에 고정할 필요가 없습니다.** i18n으로 인터페이스 언어를 선택하고 애플리케이션 카탈로그에서 자체 레이블, 필드, 설명, 도움말을 설정할 수 있습니다. UI를 다시 만들 필요도 없습니다.

<p align="center">
  <img src="docs/images/i18n-support.png" width="100%" alt="decoui 인터페이스 언어 선택 및 i18n 다국어 지원">
</p>

## 단순한 “폼 생성” 그 이상

- **테마(Themes)** — Light, Cockpit, Mission Control, Industrial 1980s 등 네 가지 기본 테마를 제공합니다. JSON으로 확장하거나 교체할 수 있으며, 실행 중인 도구를 중단하지 않고 테마를 전환할 수 있습니다.
- **국제화(i18n)** — decoui 자체 인터페이스용 언어 카탈로그가 포함되어 있습니다. 도구의 레이블, 필드, 설명, 도움말에도 애플리케이션별 카탈로그를 사용할 수 있습니다.
- **도움말 자동 수집** — docstring에서 요약, 매개변수 표, 반환값, 예외 설명을 생성합니다. 긴 Markdown 문서와 도움말 페이지 간 상호 참조도 지원합니다.
- **안정적인 실행** — 백그라운드 스레드에서 도구를 실행하며 진행률 표시, 타임아웃, 취소, 자식 프로세스 출력 스트리밍을 지원합니다.
- **기록과 재실행(History & Replay)** — 모든 실행을 SQLite에 저장하고, 기록 필터링, 전체 로그 확인, 이전 매개변수 복원을 애플리케이션 안에서 처리합니다.

## 30초 만에 시작하기

```bash
pip install decoui
```

Python 3.10 이상이 필요합니다. decoui는 기본적으로 더 가벼운 `PySide6-Essentials`에만 의존하며 전체 `PySide6-Addons` 패키지를 추가로 설치하지 않습니다.

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

파일을 실행하면 됩니다. `gui_main()`은 호출한 쪽의 네임스페이스에서 모든 `@toolset`을 탐색하고 완전한 애플리케이션을 구성합니다.

```bash
python app.py
```

## 타입이 곧 폼이 됩니다

| Python 타입 | 생성되는 컨트롤 |
|---|---|
| `str` | 한 줄 텍스트 필드 |
| `int` / `float` | 숫자 입력 |
| `bool` | 체크박스 |
| `list` / `dict` | 여러 줄 편집기 |
| `Enum` | 드롭다운 |
| `pathlib.Path` | 파일 및 폴더 선택 버튼이 있는 경로 입력 |

`completions`, `cascade`, `defaults`를 사용하면 자동 완성, 종속 필드, 실행 시점 기본값을 추가할 수 있습니다. 원래 메서드는 일반 Python 코드로 유지되므로 GUI 없이 직접 호출하고 테스트할 수 있습니다.

## 문서

상세 내용은 README에서 분리되어 있습니다. 필요한 가이드로 바로 이동할 수 있습니다.

- [전체 API 및 동작 참고서](docs/reference.md) — 데코레이터, 타입 매핑, 폼 지원, 테마, 저장소, 기록 등
- [시작 라이프사이클](docs/startup-lifecycle.md) — 초기화 순서, 데이터 로딩, 오류 처리
- [애플리케이션 번역](docs/translating-an-application.md) — 도구 문구와 긴 도움말 현지화
- [도움말 작성](docs/help-authoring.md) — docstring, Markdown, 상호 참조
- [취소와 자식 프로세스](docs/cancelling-a-run.md) — Stop, 타임아웃, 정리 작업의 올바른 구현
- [설계와 구현](docs/design.md) — 모듈 구조, 실행 엔진, 저장소, UI 아키텍처

지원되는 모든 기능을 확인할 수 있는 전체 예제는 [`src/decoui/example/`](src/decoui/example/)에 있습니다. 다음 명령으로 실행하세요.

```bash
python -m decoui.example
```

## 이런 경우에 적합합니다

데이터 처리 도구, 운영 유틸리티, 배치 작업 실행기, 사내 생산성 도구, 비개발자에게 전달할 Python 스크립트 등에 적합합니다. 특히 “비즈니스 로직은 이미 있고 신뢰할 수 있는 데스크톱 진입점만 필요하다”는 프로젝트에 잘 맞습니다.

> decoui는 현재 Alpha 단계입니다. 실제 사용 중 발견한 문제와 피드백은 [GitHub Issues](https://github.com/luvmagi/decoui/issues)에 남겨 주세요.

## 라이선스

[MIT](LICENSE)
