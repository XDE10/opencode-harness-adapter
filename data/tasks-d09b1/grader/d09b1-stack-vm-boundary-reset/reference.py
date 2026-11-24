def run(ops):
    if not isinstance(ops, list):
        raise ValueError("ops must be a list")

    stack = []
    variables = {}
    out = []
    calls = []
    pc = 0
    steps = 0

    def pop():
        if not stack:
            raise ValueError("stack underflow")
        return stack.pop()

    def checked_int(value, label):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(label)
        return value

    def checked_name(ins):
        name = ins.get("name")
        if not isinstance(name, str):
            raise ValueError("bad name")
        return name

    def checked_target(ins):
        target = checked_int(ins.get("target"), "bad target")
        if target < 0 or target > len(ops):
            raise ValueError("bad target")
        return target

    while 0 <= pc < len(ops):
        ins = ops[pc]
        pc += 1
        steps += 1
        if not isinstance(ins, dict) or not isinstance(ins.get("op"), str):
            raise ValueError("bad instruction")
        op = ins["op"]

        if op == "push":
            stack.append(checked_int(ins.get("v"), "bad value"))
        elif op == "load":
            stack.append(variables.get(checked_name(ins), 0))
        elif op == "store":
            variables[checked_name(ins)] = pop()
        elif op in ("add", "sub", "mul"):
            b = pop()
            a = pop()
            if op == "add":
                stack.append(a + b)
            elif op == "sub":
                stack.append(a - b)
            else:
                stack.append(a * b)
        elif op == "print":
            out.append(pop())
        elif op == "jmp":
            pc = checked_target(ins)
        elif op == "jz":
            target = checked_target(ins)
            cond = pop()
            if cond == 0:
                pc = target
        elif op == "call":
            target = checked_target(ins)
            calls.append(pc)
            pc = target
        elif op == "ret":
            if not calls:
                raise ValueError("empty call stack")
            pc = calls.pop()
        elif op == "reset":
            stack.clear()
            variables.clear()
            out.clear()
            calls.clear()
        elif op == "halt":
            break
        else:
            raise ValueError("unknown op")

    return {"stack": stack, "vars": variables, "out": out, "steps": steps}
