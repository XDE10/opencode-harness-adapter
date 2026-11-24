# Issue in `click`: Stop passing a deprecated command's help text through `gettext`

This repository snapshot comes from `click` (license: BSD-3-Clause).

## Problem Summary
Stop passing a deprecated command's help text through `gettext`

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `src/click/core.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AssertionError: assert 'sub help (DEPRECATED: REASON)' in 'Usage: sub [OPTIONS]\n\n  SUB HELP (DEPRECATED: REASON)\n\nOPTIONS:\n  --help  Show this message and exit.\n'
E    +  where 'Usage: sub [OPTIONS]\n\n  SUB HELP (DEPRECATED: REASON)\n\nOPTIONS:\n  --help  Show this message and exit.\n' = <Result okay>.output
E    +    where <Result okay> = <bound method CliRunner.invoke of <click.testing.CliRunner object at 0x00000236DB47A750>>(<Command sub>, ['--help'])
E    +      where <bound method CliRunner.invoke of <click.testing.CliRunner object at 0x00000236DB47A750>> = <click.testing.CliRunner object at 0x00000236DB47A750>.invoke
FAILED _oca_hidden_tests/test_commands.py::test_deprecated
```
