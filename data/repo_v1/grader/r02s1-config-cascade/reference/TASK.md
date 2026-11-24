# Issue Report: ConfigCascade Inheritance Resolution & Empty Default Env Interpolation

## Context
`r02s1pkg` is our internal layered INI/YAML-lite configuration loader. It parses sectioned text configuration files (`[section]` with `key = value` pairs), resolves file inheritance chains via a `[meta]` section (`extends = parent.cfg`), interpolates environment variables (`${VAR}` and `${VAR:-default}`), and validates the merged configuration against a typed schema.

Recently, two separate production regressions were reported:
1. **Empty string fallback values in `${VAR:-}` expressions are treated as missing required variables**: When a config specifies `prefix = ${APP_PREFIX:-}` (intending an empty string default when `APP_PREFIX` is unset in `env`), interpolation raises `ConfigError` complaining that `APP_PREFIX` is missing, or fails to substitute `""`. Additionally, if `VAR` is set in `env` to an empty string `""`, `${VAR:-fallback}` should use `""` (only *unset* variables should fall back to `default`, matching standard `${VAR:-default}` vs `${VAR-default}` conventions defined below).
2. **Multi-level inheritance (`extends`) overwrites child overrides when a base config is loaded across multiple layers**: When resolving an inheritance chain (`child.cfg` extends `parent.cfg` which extends `base.cfg`), child values must override parent values, which in turn override base values. Also, loading or resolving a config must not mutate cached/parsed layer dictionaries in place nor apply layers in reverse priority order. Currently, when `ConfigLoader.load()` resolves a multi-file `extends` chain, parent values overwrite child values (or child values fail to take precedence over inherited sections).

---

## Behavioral Specification

### 1. Parsing (`r02s1pkg.parser`)
- Input format consists of lines. Empty lines and lines starting with `#` or `;` (after stripping whitespace) are ignored.
- Section headers are `[section_name]` (stripped). Keys before any section header belong to `"default"`.
- Key-value lines use `key = value` (split on the first `=`). Both key and value are stripped of outer whitespace. If a value is wrapped in matching double quotes `"..."` or single quotes `'...'`, the outer quotes are stripped.
- Special section `[meta]` may contain `extends = <filename>` (or comma-separated filenames `base1.cfg, base2.cfg`). The `[meta]` section itself is excluded from the final merged data returned by `ConfigLoader.load()`.

### 2. Environment Interpolation (`r02s1pkg.parser.interpolate_value`)
- Placeholders have the syntax `${VAR}` or `${VAR:-default}` and can appear anywhere inside a string value (including multiple placeholders in a single value, e.g. `http://${HOST:-localhost}:${PORT:-8080}${PATH_PREFIX:-}`).
- Lookup rules given `env: Mapping[str, str]`:
  - If `VAR` is present in `env` (i.e. `VAR in env`, even if `env[VAR] == ""`), its value `env[VAR]` is substituted.
  - If `VAR` is **not** in `env`:
    - If `:-` is present (`${VAR:-default}`), substitute `default` (note: `${VAR:-}` has `default == ""`, which is valid and must substitute `""`).
    - If `:-` is not present (`${VAR}`), raise `ConfigError(f"Missing required environment variable: {VAR}")`.

### 3. Inheritance & Layer Merging (`r02s1pkg.loader.ConfigLoader`)
- `ConfigLoader(files: Mapping[str, str], env: Mapping[str, str] | None = None)` takes an in-memory virtual file map (`filename -> raw_text`) and an environment mapping.
- `load(entry_file: str, schema: ConfigSchema | None = None) -> dict[str, dict[str, Any]]`:
  - Resolves `extends` starting from `entry_file`.
  - If a file specifies `extends = a.cfg, b.cfg` in `[meta]`, `a.cfg` is loaded first, then `b.cfg` overrides `a.cfg`, and finally the child file overrides both.
  - Circular `extends` chains (e.g. `a.cfg -> b.cfg -> a.cfg`) must raise `ConfigError("Circular config inheritance detected")`.
  - Referencing a missing file must raise `ConfigError`.
  - After merging raw string layers (with `[meta]` excluded), every key's value is environment-interpolated using `interpolate_value`, and if `schema` is provided, validated and coerced via `schema.validate(merged)`.
  - Calling `load()` multiple times on the same `ConfigLoader` instance (even with different `env` or different entry files sharing a common base) must be side-effect-free and deterministic.

### 4. Schema Coercion & Validation (`r02s1pkg.schema`)
- `FieldSpec(type: str, required: bool = True, default: Any = None)` supports `type` in `{"str", "int", "bool", "list"}`:
  - `"str"`: string as-is.
  - `"int"`: base-10 integer via `int(val)`, raising `ConfigError` on invalid integer strings.
  - `"bool"`: `"true"`, `"1"`, `"yes"` (case-insensitive) -> `True`; `"false"`, `"0"`, `"no"` (case-insensitive) -> `False`; anything else raises `ConfigError`.
  - `"list"`: comma-separated non-empty stripped items, or `[]` if the string is empty `""`.
