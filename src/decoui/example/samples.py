"""Sample text in every language decoui's interface ships in.

Data, not code: one entry per locale file, used by
:meth:`decoui.example.running.RunTools.language_samples` and by nothing else.
It lives apart so that reading the toolsets does not mean scrolling past two
hundred lines of prose in twelve scripts.
"""
from __future__ import annotations

# Three lines per language, in the order the locale files are shipped in.
#
# Line 1 is prose: it shows whether the face has the script at all. Line 2 is
# fixed-width bait -- digits, box drawing and, for the CJK entries, half- and
# full-width forms of the same characters -- because a console only reads as a
# console if those columns line up. Line 3 is the punctuation and diacritics
# that fall through to a fallback face first, which is where a stack shows its
# seams. The tags are deliberately ASCII: they are the fixed point the eye
# measures the rest of the line against.
LANGUAGE_SAMPLES: list[tuple[str, str, tuple[str, str, str]]] = [
    ("en", "English", (
        "The quick brown fox jumps over the lazy dog.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "Curly “quotes”, an em—dash, ellipsis… and a fraction ½.",
    )),
    ("de-DE", "Deutsch", (
        "Falsches Üben von Xylophonmusik quält jeden größeren Zwerg.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "ÄÖÜ äöü ß — „Großschreibung“ heute üblich.",
    )),
    ("es", "Español", (
        "El veloz murciélago hindú comía feliz cardillo y kiwi.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "¿Qué año? ¡Ninguno! — áéíóú ü ñ « comillas »",
    )),
    ("fr-FR", "Français", (
        "Portez ce vieux whisky au juge blond qui fume.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "àâæçéèêëîïôœùûüÿ — « espace fine » ; oui !",
    )),
    ("id-ID", "Bahasa Indonesia", (
        "Muharjo seorang xenofobia universal yang takut pada warga Qatar.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "Riwayat dijalankan — “tanda kutip”, titik… dan tanda hubung-.",
    )),
    ("ja-JP", "日本語", (
        "実行履歴を更新しました。ツールを検索してください。",
        "0123456789  ０１２３４５６７８９  ﾊﾝｶﾞｸ / 全角  ──────",
        "漢字・ひらがな・カタカナ、「括弧」と長音ー。",
    )),
    ("ko-KR", "한국어", (
        "다람쥐 퓨즈를 마시며 실행 기록을 새로 고칩니다.",
        "0123456789  ０１２３４５６７８９  가나다라  ──────",
        "한글·漢字 혼용, 「괄호」와 마침표.",
    )),
    ("pt-BR", "Português", (
        "Zebras caolhas de Java querem passar fax para moscovita.",
        "0123456789  ILil1 O0o  |||||| ──────  [{(<>)}]",
        "áâãàçéêíóôõú — execução concluída, não?",
    )),
    ("ru-RU", "Русский", (
        "Съешь же ещё этих мягких французских булок.",
        "0123456789  АВЕКМНОРСТ  авекмнорст  ──────",
        "Ёё Щщ Ъъ Ьь — «ёлочки» и тире.",
    )),
    ("tr-TR", "Türkçe", (
        "Pijamalı hasta yağız şoföre çabucak güvendi.",
        "0123456789  ILil1 O0o  İi Iı  ──────  [{(<>)}]",
        "ÇĞİÖŞÜ çğıöşü — dotted İ vs dotless ı.",
    )),
    ("zh-CN", "简体中文", (
        "已刷新运行历史，请在上方搜索工具。",
        "0123456789  ０１２３４５６７８９  一二三四  ──────",
        "全角标点：，。；：“”‘’（）【】——",
    )),
    ("zh-TW", "繁體中文", (
        "已重新整理執行歷史，請在上方搜尋工具。",
        "0123456789  ０１２３４５６７８９  壹貳參肆  ──────",
        "全形標點：，。；：「」『』（）【】──",
    )),
]
