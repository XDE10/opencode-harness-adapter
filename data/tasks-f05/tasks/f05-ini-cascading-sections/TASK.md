Implement/fix `load_ini_config(text, target_section, defaults=None)` in `solution.py`.

Parses INI configuration text with section inheritance and `${...}` variable interpolation, returning a `dict[str, str]` of resolved keys for `target_section`.

Specification:
- Blank lines and comment lines starting with `#` or `;` (after optional leading whitespace) are ignored.
- Section headers have the form `[name]` or `[child < parent]` (whitespace around `<` and inside brackets is trimmed). Empty section or parent names raise `ValueError`.
- Repeated `[section]` headers merge keys in order (later keys overwrite earlier ones); if a repeated header specifies a parent, it must match any prior parent or raise `ValueError`.
- Key-value lines outside any section raise `ValueError`. Keys and values are separated by the earliest occurrence of `=` or `:` on the line (so `url = http://a:80` splits on `=`, and `url: http://a=b` splits on `:`). Lines with neither delimiter or an empty key raise `ValueError`.
- Precedence for any section `S` (lowest to highest): `defaults` dict -> `[DEFAULT]` section -> ancestor chain (root parent down to immediate parent) -> `S` itself.
- Missing `target_section` or a missing parent section raises `KeyError`. Cyclic section inheritance raises `ValueError`.
- Interpolation on values of `target_section`:
  - `${key}` resolves `key` in `target_section` (using its full inherited dict).
  - `${sec.key}` resolves `key` in `sec` (using `sec`'s full inherited dict; missing `sec` or `key` raises `KeyError`).
  - Literal `$$` produces `$`. Unclosed `${` or cyclic interpolation raises `ValueError`. Missing key raises `KeyError`.

Example:
```python
ini = "[DEFAULT]\nenv = dev\n[base]\nport = 8000\n[web < base]\nurl = http://localhost:${port}/${env}\n"
load_ini_config(ini, "web")
# -> {"env": "dev", "port": "8000", "url": "http://localhost:8000/dev"}
```
