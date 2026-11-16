# Translation guide

The dashboard speaks English, Kannada (ಕನ್ನಡ), Telugu (తెలుగు) and Hindi (हिन्दी). The text lives in one file, `dashboard/i18n.js`.
The server's own messages are in English, except for the message codes listed below, which the dashboard translates itself.

## Status

| Language | Status |
|---|---|
| English (`en`) | The source text, written by the project. |
| Kannada (`kn`) | **First draft.** Not reviewed by a native speaker. Do not rely on it for public information until it is. |
| Telugu (`te`) | **First draft**, new in version 3.0. Not reviewed by a native speaker. Do not rely on it for public information until it is. |
| Hindi (`hi`) | **First draft.** Not reviewed by a native speaker. Do not rely on it for public information until it is. |

Every Kannada, Telugu and Hindi string is unreviewed. The Telugu text was written for version 3.0. The Kannada and Hindi text
was written for version 2.0 and extended in version 3.0.

Each language has 344 keys. Against version 2.0, which had 309 keys in each language, version 3.0 adds 41 keys and removes 6:

- The 41 new keys start with `journey.`, `msgcode.`, `admin.import_`, `offline.` or `app.disclaimer`.
- The 6 removed keys are the 2.0 table headings `journey.col_arrives`, `journey.col_departs`, `journey.col_from`,
  `journey.col_minutes`, `journey.col_route` and `journey.col_to`.
- The key `msgcode.NO_DIRECT_SERVICE` was missing from earlier 3.0 builds, although the server still sends its code. It is
  present in this release, with the 2.0 wording for English, Kannada and Hindi and new Telugu wording.

The browser checks confirm that switching to Kannada, Telugu or Hindi translates the navigation, applies that script's font
rule, keeps text running left to right, and fits the screen on a phone. They do not confirm that the wording is correct.

## What is and is not translated

- **Translated:** the dashboard's own text, read from `i18n.js` by key. This includes the title of each year banner, the
  scenario notice, the backup confirmation and the non-affiliation notice in the footer. The static tests check that every
  key the code uses exists in every language, and that every key is used.
- **Message codes:** some server answers carry a message code, and the dashboard shows the translation for that code. There
  are 14 codes: `DESTINATION_NOT_FOUND`, `DESTINATION_NOT_SERVED`, `NEED_BOTH_STOPS`, `NOT_COVERED`, `NO_DEPARTURES`,
  `NO_DIRECT_SERVICE`, `NO_OFFICIAL_DATA`, `NO_PLANNED_JOURNEY`, `NO_SERVICE`, `NO_TRIPS`, `NO_UNVERIFIED_DATA`,
  `ORIGIN_NOT_FOUND`, `ORIGIN_NOT_SERVED` and `SAME_STOP`. A code without a translation shows the server's English text. The test
  `test_every_message_code_the_server_can_send_is_translated_in_every_language` checks each code the server can send.
- **Not translated (English from the server):** the year-coverage sentences under each year banner, for example "Unverified
  feed data covers all of 2027.", the feed checker's errors and warnings, and the error details that the API sends with its
  responses.
- **Exports:** the CSV and PDF files are in English. The PDF writer cannot draw Hebrew, Arabic, Indic or Southeast Asian
  scripts, so it replaces those characters with `?` and the PDF says so in a notice. The CSV keeps the full text.
- **Fonts:** no font is bundled. Each script has its own stack, and text in these three scripts has a line height of 1.75:
  - Kannada: `"Noto Sans Kannada", "Nirmala UI", "Tunga", "Kedage"`, then the Latin font.
  - Telugu: `"Noto Sans Telugu", "Nirmala UI", "Gautami", "Vani"`, then the Latin font.
  - Hindi: `"Noto Sans Devanagari", "Nirmala UI", "Mangal"`, then the Latin font.

  Other systems fall back to whatever font they have. Test the page on the devices your users have.

## The file format

`dashboard/i18n.js` has four blocks, `var en`, `var kn`, `var te` and `var hi`. Each entry is one line:

```js
    "admin.verify": "Verify",
```

The static tests enforce these rules (`tests/test_dashboard_static.py`):

1. Every language has exactly the same keys. A key missing from one language fails the tests.
2. Each `{name}` placeholder in the English text must also appear in every other language, spelled the same way. The app
   replaces it with a value, so do not translate the placeholder name.
3. Do not put a straight double quote inside a text. Use curly quotes (“ ”) instead. A line with one does not match the
   entry format, and the tests fail.
4. No text may be empty.
5. A text may be the same as the English only where that is deliberate, such as "PDF". The keys allowed to match English are
   listed in `ALLOWED_UNTRANSLATED`. Add a key to that list only when its text is deliberately the same in every language.
6. Each block ends with its `// end: en`, `// end: kn`, `// end: te` or `// end: hi` line. Keep them. The tests use them to find
   each block.

## Adding a language

1. Copy the `var en = { … };` block, rename it (for example `var ta`), and translate each value. Keep the keys.
2. Add the new block's end marker (`// end: ta`) after its closing brace.
3. Add an entry with `code` and `name` to the `languages` list, with the name written in that language.
4. Change `messages` to include the new block, for example `messages: { en: en, kn: kn, te: te, hi: hi, ta: ta }`.
5. In `dashboard/styles.css`, add an `html:lang(ta)` rule that names a font for the script, with a line height if the script
   needs one. Add the same code to the `:not(:lang(...))` chain in the default font rule, so the Latin font is not applied on
   top of the script's own font. The test `test_the_default_font_rule_leaves_out_exactly_the_languages_with_their_own_font`
   fails when the two lists do not match. A selector that is more specific than a language rule would otherwise replace
   that language's font without any error.
6. In `dashboard/index.html`, add the new language to the `<noscript>` message.
7. In `tests/test_dashboard_static.py`, add the code to `LANGUAGES` and update the expected list of languages in
   `test_the_dictionary_lists_the_four_languages_and_nothing_else`.
8. In `tests/browser/ui_check.py`, add the new language to the navigation and font check and to the phone check.
9. Run `python -m pytest` and `python tests/browser/run_browser_checks.py`.
10. Have the translation reviewed by a native speaker before publishing it, and update the status table above.

## Right-to-left languages

`dashboard/app.js` sets the page's direction with `directionOf`. It reads an optional `dir` field on each entry of the `languages` list in `i18n.js`, and uses left to right unless that field is `rtl`. None of the four entries sets it, so every language is left to right, and the browser checks confirm that each one runs left to right. No right-to-left language has been added or tested. To add one, give its entry `dir: "rtl"`, then check the layout in a browser: the stylesheet uses physical left and right properties in five lines, such as margins.
