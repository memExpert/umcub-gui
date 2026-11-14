Translations: Qt Linguist sources (`umcub_gui_<lang>.ts`); `python tools/translations.py release` compiles them to the
`.qm` files the program loads (not kept in git; the release build makes them). `python tools/translations.py update`
brings the sources up to the code, the library's error texts included (`umcub_gui/app/error_texts.py`). A new
language is one file, see `tools/translations.py`.
