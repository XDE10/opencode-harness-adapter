# Issue Report: `r02s3pkg` Layered Config Cascade & Schema Validator

## Context
`r02s3pkg` provides an in-memory INI/YAML-lite layered configuration engine (`ConfigCascade`) with section inheritance (`extends`), environment variable interpolation (`${VAR:-default}`), and schema validation (`ConfigSchema`, `FieldSpec`).

## Reported Symptoms
Two bugs have been reported in production deployments:

1. **Quoted values with `:-` or inline `#` inside environment interpolations break parsing / interpolation**:
   - In `parser.py`, inline comment stripping splits on `#` unconditionally before checking whether the `#` is inside double quotes (`"..."`), and environment interpolation `${VAR:-fallback}` treats an explicitly set empty environment variable (`env={"VAR": ""}`) as present instead of using `fallback` when the syntax is `${VAR:-fallback}` (POSIX `:-` must use fallback when `VAR` is unset **or** empty `""`; furthermore, after env interpolation, scalar type coercion is not re-applied when an entire token was `"${PORT:-8080}"` or `${PORT:-8080}`).
   - Specifically:
     - Comments starting with `#` outside double quotes must be stripped, while `#` inside double quotes (e.g. `token = "abc#123"`) must be preserved as part of the string value.
     - `${VAR:-default}` must substitute `default` whenever `VAR` is missing from `env` **or** `env[VAR] == ""`.
     - If a raw value is unquoted (e.g. `port = ${PORT:-8080}` or `enabled = ${FLAG:-true}`), scalar coercion (`int`, `float`, `bool`) must occur **after** environment interpolation so that interpolated numbers/booleans are parsed into `int` / `float` / `bool` rather than remaining raw `str`. Conversely, if the value was explicitly double-quoted in the config source (e.g. `code = "${CODE:-007}"`), it must remain a `str` (`"007"`).

2. **Section `extends` inheritance mutates parent sections and drops schema defaults during cascade resolution**:
   - In `cascade.py`, `ConfigCascade.resolve(env=...)` resolves `extends = <parent_section>` across layers and validates against an optional `ConfigSchema`.
   - Currently, when a child section inherits from a parent section (`extends = base`), modifying or merging keys into the child section mutates the parent section's dictionary in place (or fails to remove the meta-key `extends` from the resolved section dictionary), and `ConfigSchema.validate()` only validates sections already present in the resolved config rather than materializing schema sections that consist entirely of default `FieldSpec` values.
   - Specifically:
     - Every resolved section that declares `extends = <parent>` must inherit all keys from the resolved `<parent>` section (supporting multi-hop chains like `prod -> staging -> base`), override with its own keys, **not** mutate `<parent>`, and **not** include the `"extends"` meta-key in the final resolved section dict. Circular `extends` chains must raise `ConfigError`.
     - When a `ConfigSchema` is attached to `ConfigCascade`, `resolve()` must apply `schema.validate(resolved)`:
       - Any section registered in `ConfigSchema` that is missing from `resolved` must still be created in the output dictionary so its `FieldSpec` defaults are populated (or raise `ConfigError` if that section has a required field with no default).
       - `FieldSpec(required=True, default=None)` must treat `False`, `0`, and `""` as valid provided values (not missing), and must copy default mutable values (like `list` defaults) so mutations to one resolved config do not corrupt future calls.
