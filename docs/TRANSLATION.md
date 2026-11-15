# Translation guide

The dashboard speaks English, Kannada (ಕನ್ನಡ) and Hindi (हिन्दी). The text lives in one file, `dashboard/i18n.js`,
and the planner's own words are the only ones that do not go through it.

## Status

| Language | Status |
|---|---|
| English (`en`) | The source text. Reviewed by the project. |
| Kannada (`kn`) | **First draft.** Not yet reviewed by a native speaker. Do not rely on it for public information until it is. |
| Hindi (`hi`) | **First draft.** Not yet reviewed by a native speaker. Do not rely on it for public information until it is. |

The browser checks confirm that switching to Kannada and Hindi translates the navigation, applies the Indic font
rule, keeps text running left to right, and fits the screen on a phone. They do not confirm that the wording is
correct.

## What is and is not translated

- **Translated:** every label, button, message, banner and explanation that the dashboard writes.
- **Not translated:** the planner's server messages, which are in English. These include import errors and warnings
  from the feed validator, validation messages from the API, the year-coverage notices, the journey and scenario
  warnings, and the backup message. A translation needs a message code and a dictionary entry on the dashboard side.
- **Not translated:** exported PDF documents, which are in English. The PDF writer does not shape Indic, Arabic or
  Thai text, so those scripts would not display correctly in a PDF even with a font file.
- **Fonts:** no font is bundled. The page asks for Noto Sans Kannada or Noto Sans Devanagari first, then the fonts
  that Windows ships (Nirmala UI, Tunga, Kedage, Mangal). Other systems fall back to whatever font they have. Test
  the page on the devices your users have.

## The file format

`dashboard/i18n.js` has three blocks, `var en`, `var kn` and `var hi`. Each entry is one line:

```js
    "nav.routes": "Routes and timetables",
```

Rules that the tests enforce:

1. Every language has exactly the same keys. A key missing from one language fails the tests.
2. Each `{name}` placeholder in the English text must also appear in every other language, spelled the same way.
   The app replaces it with a value. Do not translate the placeholder name.
3. Do not put a straight double quote inside a text. Use curly quotes (“ ”) instead.
4. No text may be empty.
5. A language may keep an English word only where the word is correct and intended, such as "PDF". Those words are
   listed in `ALLOWED_UNTRANSLATED` in `tests/test_dashboard_static.py`. Add a word to that list only when it is
   deliberately the same in every language.
6. The `// end: en`, `// end: kn` and `// end: hi` lines close each block. Keep them.

## Adding a language

1. Copy the `var en = { … };` block, rename it (for example `var ta`), and translate each value. Keep the keys.
2. Add the new block's end marker (`// end: ta`) after its closing brace.
3. Add the language to the `languages` list, with its own name written in that language.
4. Change `messages` to include the new block, for example `messages: { en: en, kn: kn, hi: hi, ta: ta }`.
5. In `dashboard/styles.css`, add an `html:lang(ta)` rule that names a font for the script. Add the same code to the
   `:not(:lang(...))` chain in the default rule so the Latin font is not used twice.
6. In `dashboard/index.html`, add the new language to the `<noscript>` message.
7. In `tests/test_dashboard_static.py`, add the code to `LANGUAGES` and update the expected list of languages in
   `test_the_dictionary_lists_the_three_languages_and_nothing_else`.
8. In `tests/browser/ui_check.py`, add the new language to the language checks.
9. Run `python -m pytest` and `python tests/browser/run_browser_checks.py`.
10. Have the translation reviewed by a native speaker before publishing it, and update the status table above.

## Right-to-left languages

The dashboard sets the page direction from the language code, but no right-to-left language has been tested. The
stylesheet uses left and right margins in several places. Check the layout in the browser before adding Arabic,
Urdu or any other right-to-left language.
