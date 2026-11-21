Fix `optional_choice(value, choices)` in `solution.py`.
Return a bool. None always passes, even with no choices. For any other
JSON string, integer or Boolean, accept only if an item in the choices
list has both the same Python type and the same value. An empty string,
zero and False are real values. Keep the function signature.
