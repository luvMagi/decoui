# テーマ

右上の歯車ボタンを押すと「設定」が開き、利用可能なすべてのテーマが一覧表示され、現在適用されているテーマが初期選択されます。

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

decoui には 4 種類のテーマが同梱されています: デフォルトのライトテーマと、3 種類のパネルスタイルのテーマです。

カスタムテーマは ``~/.decoui/themes`` から読み込まれます。1 つのテーマにつき 1 つの JSON ファイルを作成し、Python コードを書く必要はありません。テーマファイルには色、角丸の半径、フォントなどを指定します。作成する最も簡単な方法は、組み込みテーマを ``extends`` で継承し、変更したい部分のみをオーバーライドすることです。

テーマは表示設定に過ぎないため、定義が壊れていても致命的なエラーにはなりません。読み込めないファイルはスキップされて他のテーマが通常どおり読み込まれ、解決できないテーマが選択されていた場合はライトテーマにフォールバックします。いずれの場合もアプリケーション起動時に通知されます。

選択内容は ID で保存されるため、テーマの名前を変更しても選択が失われることはなく、テーマファイルが一時的に見つからない場合でも選択解除されることはありません（ファイルが元に戻れば再び適用されます）。
