#!/usr/bin/env python
import os
import tokenize
import traceback
import sys
import ast
import builtins
import operator
import inspect
from pprint import pprint
from functools import wraps, reduce


def parse_bool(value):
    return value and value.lower() in ('1', 'true')


DEBUG_PARSE = parse_bool(os.environ.get('DEBUG_PARSE'))
DEBUG_EXEC = parse_bool(os.environ.get('DEBUG_EXEC')) # TODO: do something with this...


REPL_PROMPT = '> '


def get_reducing_operator(op):
    """Returns a version of the given operator function which "reduces",
    i.e. accepts a potentially infinite number of arguments, and keeps
    applying the operator on them pairwise until it has used them up.

        >>> op = get_reducing_operator(operator.add)
        >>> op(1)
        1
        >>> op(1, 2)
        3
        >>> op(1, 2, 3)
        6

    """
    @wraps(op)
    def wrapped_op(x, *args):
        return reduce(op, args, x)
    return wrapped_op


IGNORABLE_TOKEN_TYPES = (
    tokenize.ENCODING,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.COMMENT,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENDMARKER,
)

LITERAL_TOKEN_TYPES = (
    tokenize.NUMBER,
    tokenize.STRING,
)

NAME_TOKEN_TYPES = (
    tokenize.NAME,
    tokenize.OP,
)

CLOSE_TOKEN_TYPES = {
    tokenize.RPAR: ')',
    tokenize.RSQB: ']',
    tokenize.RBRACE: '}',
}

CLOSE_TOKEN_TAGS = {
    # s-expression tags
    tokenize.RPAR: 'paren',
    tokenize.RSQB: 'brack',
    tokenize.RBRACE: 'brace',
}

BUILTINS = {
    # See: https://docs.python.org/3/library/operator.html#mapping-operators-to-functions
    '<': operator.lt,
    '>': operator.gt,
    '<=': operator.le,
    '>=': operator.ge,
    '==': operator.eq,
    '!=': operator.ne,
    'not': operator.not_,
    'neg': operator.neg,
    'pos': operator.pos,
    'in': operator.contains,
    'is': operator.is_,
    'isnot': operator.is_not,
    'getitem': operator.getitem,
    'setitem': operator.setitem,
    'delitem': operator.delitem,
    '+': get_reducing_operator(operator.add),
    '-': get_reducing_operator(operator.sub),
    '*': get_reducing_operator(operator.mul),
    '%': get_reducing_operator(operator.mod),
    '@': get_reducing_operator(operator.matmul),
    '/': get_reducing_operator(operator.truediv),
    '//': get_reducing_operator(operator.floordiv),
    '**': get_reducing_operator(operator.pow),
    '<<': get_reducing_operator(operator.lshift),
    '>>': get_reducing_operator(operator.rshift),
    '&': get_reducing_operator(operator.and_),
    '|': get_reducing_operator(operator.or_),
    '^': get_reducing_operator(operator.xor),
    '~': operator.invert,

    # Python's classic "variables you thought were keywords"
    'None': None,
    'True': True,
    'False': False,
    '...': ...,
}

IN_PLACE_OPERATORS = {
    # See: https://docs.python.org/3/library/operator.html#in-place-operators
    '+=': get_reducing_operator(operator.iadd),
    '-=': get_reducing_operator(operator.isub),
    '*=': get_reducing_operator(operator.imul),
    '%=': get_reducing_operator(operator.imod),
    '@=': get_reducing_operator(operator.imatmul),
    '/=': get_reducing_operator(operator.itruediv),
    '//=': get_reducing_operator(operator.ifloordiv),
    '**=': get_reducing_operator(operator.ipow),
    '<<=': get_reducing_operator(operator.ilshift),
    '>>=': get_reducing_operator(operator.irshift),
    '&=': get_reducing_operator(operator.iand),
    '|=': get_reducing_operator(operator.ior),
    '^=': get_reducing_operator(operator.ixor),
}


def mklambda(name, var_names, *, var_defaults, env, exprs):
    def f(*args, **kwargs):
        vars = var_defaults.copy()
        for name, value in zip(var_names, args):
            vars[name] = value
        vars.update(**kwargs)
        return eval_exprs(exprs, env, vars=vars)

    f.__name__ = f.__qualname__ = name
    if exprs and exprs[0][0] == 'literal' and isinstance(exprs[0][1], str):
        f.__doc__ = exprs[0][1]

    return f


def text_to_exprs(text):
    lines = text.splitlines()
    def readline():
        return lines.pop().encode() if lines else b''
    return tokens_to_exprs(tokenize.tokenize(readline))


def tokens_to_exprs(tokens, *, repl=False):
    """Converts an iterable of tokens into a list of s-expressions"""

    stack = []
    exprs = None

    def produce(expr):
        if exprs is None:
            yield expr
        else:
            exprs.append(expr)

    for token in tokens:
        try:
            if token.type in IGNORABLE_TOKEN_TYPES:
                continue

            if DEBUG_PARSE:
                print(f"Parsing: {token}")

            if token.type in LITERAL_TOKEN_TYPES:
                value = ast.literal_eval(token.string)
                expr = ('literal', value)
                yield from produce(expr)
            elif token.exact_type == tokenize.LPAR:
                stack.append((tokenize.RPAR, exprs))
                exprs = []
            elif token.exact_type == tokenize.LSQB:
                stack.append((tokenize.RSQB, exprs))
                exprs = []
            elif token.exact_type == tokenize.LBRACE:
                stack.append((tokenize.RBRACE, exprs))
                exprs = []
            elif token.exact_type in CLOSE_TOKEN_TYPES:
                assert exprs is not None, f"Unexpected {token.string!r}"
                tag = CLOSE_TOKEN_TAGS[token.exact_type]
                expr = (tag, exprs)
                expected_type, exprs = stack.pop()
                assert expected_type == token.exact_type, f"Expected {CLOSE_TOKEN_TYPES[expected_type]}, got: {token.string!r}"
                yield from produce(expr)
            elif token.type in NAME_TOKEN_TYPES:
                # Make sure this check comes after checks of token.exact_type,
                # since NAME_TOKEN_TYPES contains token.type, which is "inexact"
                expr = ('name', token.string)
                yield from produce(expr)
            else:
                raise Exception(f"Unsupported token: {token!r}")
        except Exception:
            if repl:
                traceback.print_exc(file=sys.stderr)
                print(REPL_PROMPT, end='', file=sys.stderr, flush=True)
            else:
                raise

    if stack:
        raise AssertionError(f"{len(stack)} unclosed parentheses")


def get_var(name, env):
    """Look up a variable value.
    That is, look up the given name in the given "environment", i.e. list
    of dicts representing a stack of variable "contexts".

        >>> env = [{'x': 'old'}, {'x': 'new'}]

        >>> get_var('x', env)
        'new'

    """
    for vars in reversed(env):
        if name in vars:
            return vars[name]
    raise NameError(f"name {name!r} is not defined")


def set_var(name, value, env):
    """Set a variable value.

        >>> env = [{'x': 'old'}, {}]
        >>> set_var('x', 'new', env)
        >>> set_var('y', 'new', env)
        >>> env
        [{'x': 'new'}, {'y': 'new'}]

    """
    for vars in reversed(env):
        if name in vars:
            vars[name] = value
            break
    else:
        env[-1][name] = value


def parse_var_names_and_defaults(expr, env):
    """Parse variable names and defaults from given s-expression.

        >>> env = []

        >>> parse_var_names_and_defaults(('paren', [('name', 'x')]), env)
        (['x'], {})

        >>> parse_var_names_and_defaults(('paren', [('name', 'x'), ('literal', 3)]), env)
        (['x'], {'x': 3})

        >>> parse_var_names_and_defaults(('paren', [('paren', [('name', 'x')]), ('paren', [('name', 'y')])]), env)
        (['x', 'y'], {})

    """

    var_names = []
    var_defaults = {}

    def parse_var(expr):
        tag, data = expr
        assert tag == 'paren', f"Can't parse variable from s-expression of type: {tag!r}"
        assert 1 <= len(data) <= 2, f"Can't parse variable from s-expression of length: {len(data)}"
        assert data[0][0] == 'name', f"Can't parse variable name from s-expression of type: {data[0][0]!r}"
        name = data[0][1]
        var_names.append(name)
        if len(data) == 2:
            value = eval_expr(data[1], env)
            var_defaults[name] = value

    tag, data = expr
    assert tag == 'paren', f"Can't parse variables from s-expression of type: {tag!r}"
    if data and data[0][0] == 'name':
        parse_var(expr)
    else:
        for subexpr in data:
            parse_var(subexpr)

    return var_names, var_defaults


def eval_expr(expr, env):
    """Evaluates a single s-expression, returning its value

        >>> eval_expr(('literal', 3), [])
        3

        >>> eval_expr(('brack', [('literal', 1), ('literal', 2)]), [])
        [1, 2]

        >>> eval_expr(('brace', [('paren', [('literal', 'x'), ('literal', 1)]), ('paren', [('literal', 'y'), ('literal', 2)])]), [])
        {'x': 1, 'y': 2}

        >>> eval_expr(('paren', [('name', ','), ('literal', 1), ('literal', 2)]), [])
        (1, 2)

        >>> env = [{'x': 3}]
        >>> eval_expr(('name', 'x'), env)
        3

        >>> env = [{}]
        >>> eval_expr(('paren', [('name', 'def'), ('name', 'f'), ('paren', [('name', 'x')])]), env)
        <function f at ...>
        >>> env[0]['f']
        <function f at ...>

        >>> eval_expr(('paren', [('name', 'lambda'), ('paren', [('name', 'x')])]), [])
        <function <lambda> at ...>

        >>> env = [{}]
        >>> eval_expr(('paren', [('name', '='), ('name', 'x'), ('literal', 3)]), env)
        3
        >>> env[0]['x']
        3

        >>> env = [{'x': 3}]
        >>> eval_expr(('paren', [('name', '+='), ('name', 'x'), ('literal', 1)]), env)
        4
        >>> env[0]['x']
        4

        >>> eval_expr(('paren', [('name', 'do'), ('literal', 2), ('literal', 3)]), [])
        3

        >>> eval_expr(('paren', [('name', 'raise'), ('literal', Exception("BOOM"))]), [])
        Traceback (most recent call last):
         ...
        Exception: BOOM

        >>> env = [{'f': lambda x: -x}]
        >>> eval_expr(('paren', [('name', 'f'), ('literal', 3)]), env)
        -3

        >>> eval_expr(('paren', [('name', 'and'), ('literal', 1), ('literal', 0)]), [])
        0

        >>> eval_expr(('paren', [('name', 'or'), ('literal', 0), ('literal', 1)]), [])
        1

        >>> eval_expr(('paren', [('name', '.'), ('name', '__class__'), ('literal', 3)]), [])
        <class 'int'>

        >>> eval_expr(('paren', [('name', 'assert'), ('literal', 1)]), [])
        >>> eval_expr(('paren', [('name', 'assert'), ('literal', 0)]), [])
        Traceback (most recent call last):
         ...
        AssertionError
        >>> eval_expr(('paren', [('name', 'assert'), ('literal', 0), ('literal', 'BOOM')]), [])
        Traceback (most recent call last):
         ...
        AssertionError: BOOM

    """

    def call(func, arg_exprs):
        arg_values = (eval_expr(expr, env) for expr in arg_exprs)
        return func(*arg_values)

    tag, data = expr
    if tag == 'literal':
        return data
    elif expr == ('name', 'else'):
        return True
    elif expr == ('name', '__env__'):
        return env
    elif expr == ('name', '__vars__'):
        return env[-1]
    elif tag == 'name':
        name = data
        return get_var(name, env)
    elif tag == 'brack':
        # List constructor
        return [eval_expr(expr, env) for expr in data]
    elif tag == 'brace':
        # Dict constructor
        d = {}
        for subtag, subdata in data:
            assert subtag == 'paren', f"Expected dict item to be a pair, got s-expression of type: {subtag!r}"
            assert len(subdata) == 2, f"Expected dict item to be a pair, got s-expression of length: {len(subdata)}"
            key = eval_expr(subdata[0], env)
            value = eval_expr(subdata[1], env)
            d[key] = value
        return d
    elif tag == 'paren':
        assert data, "Can't evaluate an empty s-expression"
        expr0 = data[0]
        data = data[1:]
        cmd = expr0[1]
        if expr0 == ('name', 'import'):
            # Import module / from module
            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            module_name = eval_expr(data[0], env)
            module = __import__(module_name)
            if len(data) == 1:
                set_var(module_name, module, env)
            else:
                for subtag, subdata in data[1:]:
                    if subtag == 'name':
                        name = subdata
                        value = getattr(module, name)
                        set_var(name, value, env)
                    elif subtag == 'paren':
                        assert len(subdata) == 2, "While importing {module_name}: expected pair of names, got s-expression of length: {len(subdata)}"
                        assert subdata[0][0] == 'name' and subdata[1][0] == 'name', \
                            f"While importing {module_name}: expected pair of names, got s-expressions of type: {subdata[0][0]!r} {subdata[1][0]!r}"
                        name = subdata[0][1]
                        as_name = subdata[1][1]
                        value = getattr(module, name)
                        set_var(as_name, value, env)
                    else:
                        raise AssertionError(f"While importing {module_name}: expected name or list, got s-expression of type: {subtag!r}")
            return module
        elif expr0 == ('name', 'def'):
            # Defining a function (i.e. creating a Lambda and storing it in
            # a variable)
            assert len(data) >= 2, f"{cmd}: need at least 2 arguments"
            assert data[0][0] == 'name', f"{cmd}: first argument must be a name, got s-expression of type: {data[0][0]!r}"
            name = data[0][1]
            var_names, var_defaults = parse_var_names_and_defaults(data[1], env)
            exprs = data[2:]
            func = mklambda(name, var_names, var_defaults=var_defaults, env=env.copy(), exprs=exprs)
            set_var(name, func, env)
            return func
        elif expr0 == ('name', 'class'):
            # Defining a class and storing it in a variable
            assert len(data) >= 2, f"{cmd}: need at least 2 arguments"
            assert data[0][0] == 'name', f"{cmd}: first argument must be a name, got s-expression of type: {data[0][0]!r}"
            name = data[0][1]
            assert data[1][0] == 'paren', f"{cmd}: second argument must be a paren, got s-expression of type: {data[1][0]!r}"
            bases = tuple(eval_expr(subexpr, env) for subexpr in data[1][1])
            subexprs = data[2:]

            vars = {}
            if subexprs and subexprs[0][0] == 'literal' and isinstance(subexprs[0][1], str):
                vars['__doc__'] = subexprs[0][1]
            value = eval_exprs(data[2:], env, vars=vars)
            cls = type(name, bases, vars)
            set_var(name, cls, env)
            return cls
        elif expr0 == ('name', 'lambda'):
            # Creating a Lambda
            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            var_names, var_defaults = parse_var_names_and_defaults(data[0], env)
            exprs = data[1:]
            return mklambda('<lambda>', var_names, var_defaults=var_defaults, env=env.copy(), exprs=exprs)
        elif expr0 == ('name', ','):
            # Tuple constructor
            return tuple(eval_expr(expr, env) for expr in data)
        elif expr0 == ('name', '.') or expr0[0] == 'brack':
            # Item/attr lookup

            # Check (verify) the syntax
            def check_data(expr0, data):
                while True:
                    if expr0 == ('name', '.'):
                        assert data[0][0] == 'name', f"{cmd}: Expected name, got s-expression of type: {data[0][0]}"
                        expr0 = data[1]
                        data = data[2:]
                    elif expr0[0] == 'brack':
                        expr0 = data[0]
                        data = data[1:]
                    else:
                        break
                assert len(data) == 0, f"{cmd}: Expected a single value, got: {len(data) + 1}"
            check_data(expr0, data)

            obj = eval_expr(data[-1], env)
            while True:
                if expr0 == ('name', '.'):
                    name = data[0][1]
                    obj = getattr(obj, name)
                    expr0 = data[1]
                    data = data[2:]
                elif expr0[0] == 'brack':
                    index = eval_exprs(expr0[1], env)
                    obj = obj[index]
                    expr0 = data[0]
                    data = data[1:]
                else:
                    break
            return obj
        elif expr0 == ('name', '=') or expr0[0] == 'name' and cmd in IN_PLACE_OPERATORS:
            # Assignment
            # Evaluating a series of s-expressions, and storing the value
            # of the last one in a variable/attr/item

            func = IN_PLACE_OPERATORS.get(cmd)

            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            if data[0][0] == 'name' and data[0][1] != '.':
                name = data[0][1]
                value = eval_exprs(data[1:], env)
                if func:
                    old_value = get_var(name, env)
                    value = func(old_value, value)
                set_var(name, value, env)
                return value
            expr0 = data[0]
            data = data[1:]

            # Check (verify) the syntax
            def check_data(expr0, data):
                i = 0
                n_parts = 0
                while True:
                    if expr0 == ('name', '.'):
                        assert data[0][0] == 'name', f"{cmd}: Expected name, got s-expression of type: {data[0][0]}"
                        expr0 = data[1]
                        data = data[2:]
                        i += 2
                        n_parts += 1
                    elif expr0[0] == 'brack':
                        expr0 = data[0]
                        data = data[1:]
                        i += 1
                        n_parts += 1
                    else:
                        break
                return i, n_parts
            i, n_parts = check_data(expr0, data)

            obj = eval_expr(data[i-1], env)
            value = eval_exprs(data[i:], env)
            for i in range(n_parts - 1):
                if expr0 == ('name', '.'):
                    name = data[0][1]
                    obj = getattr(obj, name)
                    expr0 = data[1]
                    data = data[2:]
                elif expr0[0] == 'brack':
                    index = eval_exprs(expr0[1], env)
                    obj = obj[index]
                    expr0 = data[0]
                    data = data[1:]

            if expr0 == ('name', '.'):
                name = data[0][1]
                if func:
                    old_value = getattr(obj, name)
                    value = func(old_value, value)
                setattr(obj, name, value)
            elif expr0[0] == 'brack':
                index = eval_exprs(expr0[1], env)
                if func:
                    old_value = obj[index]
                    value = func(old_value, value)
                obj[index] = value
            return value
        elif expr0[0] == 'name' and cmd in IN_PLACE_OPERATORS:
            # In-place operator, and possibly assignment
            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            func = IN_PLACE_OPERATORS[cmd]
            value = call(func, data)
            if data[0][0] == 'name':
                name = data[0][1]
                set_var(name, value, env)
            return value
        elif expr0 == ('name', 'do'):
            # Evaluating a series of s-expressions, and returning the value
            # of the last one
            value = eval_exprs(data, env)
            return value
        elif expr0 == ('name', 'raise'):
            # Evaluating a series of s-expressions, and raising the value
            # of the last one
            value = eval_exprs(data, env)
            raise value
        elif expr0 == ('name', 'for'):
            # For loop
            assert len(data) >= 2, f"{cmd}: need at least 2 arguments"
            assert data[0][0] == 'name', f"{cmd}: first argument must be a name, got s-expression of type: {data[0][0]!r}"
            name = data[0][1]
            for_value = eval_expr(data[1], env)
            exprs = data[2:]

            value = None
            for item in for_value:
                vars = {name: item}
                value = eval_exprs(exprs, env, vars=vars)
            return value
        elif expr0 == ('name', 'while'):
            # While loop
            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            cond_expr = data[0]
            exprs = data[1:]

            value = None
            while eval_expr(cond_expr, env):
                value = eval_exprs(exprs, env)
            return value
        elif expr0 == ('name', 'if'):
            # If expression
            for subtag, subdata in data:
                assert subtag == 'paren', f"{cmd}: each sub-expression must be of type 'paren', but got: {subtag!r}"
                assert len(subdata) >= 1, f"{cmd}: each sub-expression needs at least 1 argument"
                cond_value = eval_expr(subdata[0], env)
                if cond_value:
                    return eval_exprs(subdata[1:], env)
            return None
        elif expr0 == ('name', 'and'):
            # And expression
            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            for subexpr in data:
                value = eval_expr(subexpr, env)
                if not value:
                    break
            return value
        elif expr0 == ('name', 'or'):
            # Or expression
            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            for subexpr in data:
                value = eval_expr(subexpr, env)
                if value:
                    break
            return value
        elif expr0 == ('name', 'assert'):
            # Make an assertion
            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            assert len(data) <= 2, f"{cmd}: need at most 2 arguments, got: {len(data)}"
            value = eval_expr(data[0], env)
            if not value:
                if len(data) == 2:
                    msg = eval_expr(data[1], env)
                    raise AssertionError(msg)
                else:
                    raise AssertionError()
        else:
            # Perform a function call
            func = eval_expr(expr0, env)
            return call(func, data)
    else:
        raise ValueError(f"Unrecognized s-expression tag: {tag!r}")


def eval_exprs(exprs, env, *, vars=None, repl=False):
    """Evaluates a list of s-expressions, returning the value of the last one.

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(def f ((x) (y "default")) (, x y)) (print (f 1 2)) (print (f 1))')
        >>> eval_exprs(exprs, [], vars=vars)
        (1, 2)
        (1, 'default')

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(for x [1 2] (print "x:" x))')
        >>> eval_exprs(exprs, [], vars=vars)
        x: 1
        x: 2

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(= x 0) (while (< x 3) (print "x:" x) (+= x 1))')
        >>> eval_exprs(exprs, [], vars=vars)
        x: 0
        x: 1
        x: 2
        3

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(if (False (print "Branch A") 1) (else (print "Branch B") 2))')
        >>> eval_exprs(exprs, [], vars=vars)
        Branch B
        2

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(list (map (lambda (x) (* x 10)) (range 3)))')
        >>> eval_exprs(exprs, [], vars=vars)
        [0, 10, 20]

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(class A()) (= a (A)) (= .x a (A)) (= .x.y a 3) (.x.y a)')
        >>> eval_exprs(exprs, [], vars=vars)
        3

    """

    # push a fresh dict of local variables onto the environment
    env.append({} if vars is None else vars)

    value = None
    for expr in exprs:
        try:
            value = eval_expr(expr, env)
        except Exception:
            if repl:
                traceback.print_exc(file=sys.stderr)
            else:
                raise
        else:
            if repl:
                print(repr(value), file=sys.stderr)
        if repl:
            print(REPL_PROMPT, end='', file=sys.stderr, flush=True)

    # pop local variables
    env.pop()

    return value


def get_global_vars():
    global_vars = BUILTINS.copy()
    global_vars.update(IN_PLACE_OPERATORS)
    for key, val in builtins.__dict__.items():
        if key.startswith('_'):
            continue
        global_vars[key] = val
    return global_vars


def main():
    if len(sys.argv) > 1:
        filenames = sys.argv[1:]
        file = None
        def readline():
            nonlocal file
            while True:
                if file is None:
                    if not filenames:
                        # Done reading all files
                        return b''
                    filename = filenames.pop(0)
                    print(f"=== Reading file: {filename}", file=sys.stderr)
                    file = open(filename, 'rb')
                line = file.readline()
                if line:
                    return line
                # If we get this far, current file is done, so we
                # should continue around the loop and open the next one
                file = None
        repl = False
    else:
        def readline():
            return sys.stdin.readline().encode()
        repl = True

    if DEBUG_PARSE:
        tokens = tokenize.tokenize(readline)
        exprs = tokens_to_exprs(tokens)
        for expr in exprs:
            pprint(expr)
    else:
        if repl:
            print(REPL_PROMPT, end='', file=sys.stderr, flush=True)
        tokens = tokenize.tokenize(readline)
        exprs = tokens_to_exprs(tokens, repl=repl)
        global_vars = get_global_vars()
        eval_exprs(exprs, [], vars=global_vars, repl=repl)


if __name__ == '__main__':
    main()
