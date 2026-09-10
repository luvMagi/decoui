# 테마

오른쪽 상단의 톱니바퀴 버튼을 누르면 '설정'이 열리며, 사용 가능한 모든 테마 목록이 표시되고 현재 적용 중인 테마가 기본 선택됩니다.

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

decoui에는 4가지 기본 테마가 제공됩니다: 기본 라이트 테마와 3가지 패널 스타일 테마입니다.

사용자 정의 테마는 ``~/.decoui/themes``에서 읽어옵니다. 테마당 하나의 JSON 파일로 구성되며, Python 코드는 필요하지 않습니다. 테마 파일에는 색상, 모서리 둥글기(border-radius), 글꼴 등을 지정합니다. 가장 간단한 작성 방법은 ``extends``를 사용하여 기본 제공 테マ를 상속받은 후 변경하려는 항목만 덮어쓰는 것입니다.

테마는 표시 설정에 불과하므로 테마 파일에 문제가 있더라도 치명적인 오류가 발생하지 않습니다. 읽을 수 없는 파일은 건너뛰고 다른 테마는 정상적으로 로드되며, 유효하지 않은 테マ가 선택된 경우 라이트 테마로 자동 대체됩니다. 두 경우 모두 애플리케이션 시작 시 알림이 표시됩니다.

선택 사항은 ID로 저장되므로 테마 이름을 변경해도 설정이 유지되며, 테마 파일이 일시적으로 누락되더라도 선택이 해제되지 않습니다(파일이 다시 복구되면 자동으로 적용됩니다).
