Fix `resolve_path(tree, path, cwd="/")` in `solution.py`.

Implement an in-memory POSIX-style path resolver with symlink expansion. No real filesystem access is used.

Inputs:
- `tree`: a `dict` whose keys are normalized absolute POSIX paths. Each value is a node dict:
  - `{"type": "dir"}`
  - `{"type": "file", "size": int}` (`size` is ignored by resolution)
  - `{"type": "link", "target": str}`
- `path`: an absolute or relative POSIX path string.
- `cwd`: an absolute canonical directory string used only when `path` is relative. Do not resolve symlinks in `cwd` itself.

Resolution rules:
- Split paths on `/`; empty components and `.` are ignored.
- `..` pops the last resolved component and never goes above `/`.
- Components not present in `tree`, and symlink targets not present in `tree`, are treated as ordinary path components.
- If a component names a link node, follow it by inserting the target components before the remaining unprocessed components of the original path.
- A relative symlink target starts from the directory containing the symlink. An absolute symlink target starts from `/`.
- Dot and dot-dot components inside symlink targets are processed with the same rules.
- Trailing slashes are ignored. Return a canonical absolute string with no trailing slash except the root `/`.
- Count each followed symlink. If more than 40 symlinks are followed (the 41st expansion), raise `ValueError`.
- Raise `TypeError` if `path` or `cwd` is not a string, or if a followed link has a non-string `target`.

Examples:
- `resolve_path({"/a": {"type": "dir"}, "/a/link": {"type": "link", "target": "b/c"}}, "/a/link/x")` returns `"/a/b/c/x"`.
- `resolve_path({"/a": {"type": "dir"}, "/a/link": {"type": "link", "target": "/top"}}, "/a/link/x")` returns `"/top/x"`.
- `resolve_path({"/loop": {"type": "link", "target": "loop"}}, "/loop")` raises `ValueError`.
