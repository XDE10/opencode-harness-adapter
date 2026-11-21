Fix `canonical_locale(tag)` in `solution.py`. Input is a valid
language tag with a two- or three-letter language, an optional
four-letter script, and an optional two-letter or three-digit region,
in that order. Delimiters may be '-' or '_'. Output uses underscores,
lowercase language, title-case script, uppercase letter region and
unchanged digit region. No variants or encodings are passed.
