import re

_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INT_RE = re.compile(r"^[+-]?\d+$")
_UNARY_ARG_OPS = {"LOAD", "STORE", "JMP", "JZ", "JNZ"}


def _compile(program: str):
    raw_tokens = []
    for line in program.splitlines():
        code = line.split("#", 1)[0]
        raw_tokens.extend(code.split())
    instructions = []
    labels = {}
    i = 0
    while i < len(raw_tokens):
        tok = raw_tokens[i]
        if tok.endswith(":"):
            name = tok[:-1]
            if not _LABEL_RE.match(name) or name in labels:
                raise ValueError(f"invalid or duplicate label: {name}")
            labels[name] = len(instructions)
            i += 1
        elif tok in _UNARY_ARG_OPS:
            if i + 1 >= len(raw_tokens):
                raise ValueError(f"missing operand for {tok}")
            instructions.append((tok, raw_tokens[i + 1]))
            i += 2
        else:
            instructions.append((tok, None))
            i += 1
    return instructions, labels


def run_rpn(program, inputs=None):
    instructions, labels = _compile(program)
    vars_map = dict(inputs) if inputs is not None else {}
    stack = []
    pc = 0
    steps = 0

    def pop_one():
        if not stack:
            raise ValueError("stack underflow")
        return stack.pop()

    while pc < len(instructions):
        steps += 1
        if steps > 10000:
            raise ValueError("step limit exceeded")
        op, arg = instructions[pc]
        if _INT_RE.match(op):
            stack.append(int(op))
        elif op in ("ADD", "SUB", "MUL", "DIV", "MOD"):
            b, a = pop_one(), pop_one()
            if op == "ADD":
                stack.append(a + b)
            elif op == "SUB":
                stack.append(b - a)
            elif op == "MUL":
                stack.append(a * b)
            elif op == "DIV":
                stack.append(b // a)
            else:
                stack.append(a % b)
        elif op == "DUP":
            v = pop_one()
            stack.extend((v, v))
        elif op == "SWAP":
            b, a = pop_one(), pop_one()
            stack.extend((b, a))
        elif op == "DROP":
            pop_one()
        elif op == "OVER":
            if len(stack) < 2:
                raise ValueError("stack underflow")
            stack.append(stack[-2])
        elif op == "LOAD":
            val = vars_map.get(arg)
            if not val:
                raise KeyError(arg)
            stack.append(val)
        elif op == "STORE":
            vars_map[arg] = pop_one()
        elif op in ("JMP", "JZ", "JNZ"):
            if arg not in labels:
                raise ValueError(f"unknown label: {arg}")
            should_jump = True if op == "JMP" else (pop_one() == 0 if op == "JZ" else pop_one() != 0)
            if should_jump:
                pc = labels[arg]
        elif op == "HALT":
            break
        else:
            raise ValueError(f"unknown opcode: {op}")
        pc += 1
    return {"stack": stack, "vars": vars_map, "steps": steps}
