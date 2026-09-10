# 佈景主題

右上角的齒輪按鈕可開啟「設定」，其中列出了所有可用佈景主題，並預設選取目前生效的佈景主題。

Themes are applied at once. Choosing one restyles every window that is open,
without rebuilding anything: a tool that is running goes on running, forms keep
what was typed into them, and output already printed is re-inked in the new
colours. The console's scroll position is the one casualty -- it returns to the
newest line.

The **language**, chosen in the same dialog, is the exception: it takes effect
the next time the application runs. Text is read as each widget is built, in far
more places than colour is, and there is nothing that can catch the rest the way
the stylesheet catches colour.

decoui 內建 4 種佈景主題：預設淺色主題，以及 3 種面板風格的主題。

您自訂的佈景主題從 ``~/.decoui/themes`` 讀取——每個主題對應一個 JSON 檔案，無需撰寫 Python 程式碼。主題檔案定義了顏色、圓角半徑與字型；撰寫自訂主題最簡單的方法是使用 ``extends`` 從內建主題繼承，並僅覆寫需要修改的部分。

佈景主題屬於展示層設定，因此損壞的主題絕不會導致程式崩潰：無法讀取的檔案會被略過，其他主題仍能正常載入；若所選主題無法解析，則會回退至淺色主題。無論哪種情況，都會在應用程式啟動時給予提示。

您的選擇依 ID 儲存，因此重新命名主題不會導致選擇遺失，暫時缺失的主題也不會被取消選擇——一旦檔案恢復，它將重新生效。
