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


def parse_bool(value):
    return value and value.lower() in ('1', 'true')


DEBUG_PARSE = parse_bool(os.environ.get('DEBUG_PARSE'))
DEBUG_EXEC = parse_bool(os.environ.get('DEBUG_EXEC')) # TODO: do something with this...


REPL_PROMPT = '> '


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
    '+': operator.add,
    '-': operator.sub,
    '*': operator.mul,
    '%': operator.mod,
    '@': operator.matmul,
    '/': operator.truediv,
    '//': operator.floordiv,
    '**': operator.pow,
    '<<': operator.lshift,
    '>>': operator.rshift,
    '&': operator.and_,
    '|': operator.or_,
    '^': operator.xor,
    '~': operator.invert,

    # Python's classic "variables you thought were keywords"
    'None': None,
    'True': True,
    'False': False,
    '...': ...,

    # This is how we import things
    'import': __import__,
}

IN_PLACE_OPERATORS = {
    # See: https://docs.python.org/3/library/operator.html#in-place-operators
    '+=': operator.iadd,
    '-=': operator.isub,
    '*=': operator.imul,
    '%=': operator.imod,
    '@=': operator.imatmul,
    '/=': operator.itruediv,
    '//=': operator.ifloordiv,
    '**=': operator.ipow,
    '<<=': operator.ilshift,
    '>>=': operator.irshift,
    '&=': operator.iand,
    '|=': operator.ior,
    '^=': operator.ixor,
}


def mklambda(name, var_names, *, var_defaults, env, exprs):
    def f(*args, **kwargs):
        vars = var_defaults.copy()
        for name, value in zip(var_names, args):
            vars[name] = value
        vars.update(**kwargs)
        return exec_exprs(exprs, env, vars=vars)

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

        >>> eval_expr(('paren', [('name', '.'), ('literal', 3), ('name', '__class__')]), [])
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
        if expr0 == ('name', 'def'):
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
        if expr0 == ('name', 'class'):
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
            value = exec_exprs(data[2:], env, vars=vars)
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
        elif expr0 == ('name', '='):
            # Evaluating a series of s-expressions, and storing the value
            # of the last one in a variable
            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            if data[0][0] == 'name':
                name = data[0][1]
                value = exec_exprs(data[1:], env)
                set_var(name, value, env)
            elif data[0][0] == 'paren':
                subexprs = data[0][1]
                assert subexprs[:1] == [('name', '.')], f"{cmd}: if first argument is a paren, it should start with a '.'"
                subexprs = subexprs[1:]
                assert len(subexprs) >= 1, f"{cmd}: in '.': need at least 1 argument"
                obj = eval_expr(subexprs[0], env)
                names = []
                for subexpr in subexprs[1:]:
                    assert subexpr[0] == 'name', f"{cmd}: in '.': all arguments after the first must be names, got s-expression of type: {subexpr[0]!r}"
                    names.append(subexpr[1])
                for name in names[:-1]:
                    obj = getattr(obj, name)
                value = exec_exprs(data[1:], env)
                setattr(obj, names[-1], value)
            else:
                raise AssertionError(f"{cmd}: first argument must be a name or paren, got s-expression of type: {data[0][0]!r}")
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
        elif expr0 == ('name', '.'):
            # Attribute lookup
            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            value = eval_expr(data[0], env)
            for subexpr in data[1:]:
                assert subexpr[0] == 'name', f"{cmd}: all arguments after the first must be names, got s-expression of type: {subexpr[0]!r}"
                name = subexpr[1]
                value = getattr(value, name)
            return value
        elif expr0 == ('name', 'do'):
            # Evaluating a series of s-expressions, and returning the value
            # of the last one
            value = exec_exprs(data, env)
            return value
        elif expr0 == ('name', 'raise'):
            # Evaluating a series of s-expressions, and raising the value
            # of the last one
            value = exec_exprs(data, env)
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
                value = exec_exprs(exprs, env, vars=vars)
            return value
        elif expr0 == ('name', 'while'):
            # While loop
            assert len(data) >= 1, f"{cmd}: need at least 1 argument"
            cond_expr = data[0]
            exprs = data[1:]

            value = None
            while eval_expr(cond_expr, env):
                value = exec_exprs(exprs, env)
            return value
        elif expr0 == ('name', 'if'):
            # If expression
            for subtag, subdata in data:
                assert subtag == 'paren', f"{cmd}: each sub-expression must be of type 'paren', but got: {subtag!r}"
                assert len(subdata) >= 1, f"{cmd}: each sub-expression needs at least 1 argument"
                cond_value = eval_expr(subdata[0], env)
                if cond_value:
                    return exec_exprs(subdata[1:], env)
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


def exec_exprs(exprs, env, *, vars=None, repl=False):
    """Executes a list of s-expressions

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(def f ((x) (y "default")) (, x y)) (print (f 1 2)) (print (f 1))')
        >>> exec_exprs(exprs, [], vars=vars)
        (1, 2)
        (1, 'default')

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(for x [1 2] (print "x:" x))')
        >>> exec_exprs(exprs, [], vars=vars)
        x: 1
        x: 2

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(= x 0) (while (< x 3) (print "x:" x) (+= x 1))')
        >>> exec_exprs(exprs, [], vars=vars)
        x: 0
        x: 1
        x: 2
        3

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(if (False (print "Branch A") 1) (else (print "Branch B") 2))')
        >>> exec_exprs(exprs, [], vars=vars)
        Branch B
        2

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(list (map (lambda (x) (* x 10)) (range 3)))')
        >>> exec_exprs(exprs, [], vars=vars)
        [0, 10, 20]

        >>> vars = get_global_vars()
        >>> exprs = text_to_exprs('(class A()) (= a (A)) (= (. a x) (A)) (= (. a x y) 3) (. a x y)')
        >>> exec_exprs(exprs, [], vars=vars)
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
        exec_exprs(exprs, [], vars=global_vars, repl=repl)


if __name__ == '__main__':
    main()
