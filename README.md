# Lythp

It's Python turned into a LISP!
```python
(def greet (name)
    """A function which greets someone.

        >>> (greet "Jim")
        Hello Jim!

    """
    (print (+ "Hello " name "!"))
)
```

The goal is not to preserve LISP traditions, keywords, and features; rather,
the goal is to have fun fitting Python into a LISP syntax in the most natural
way I can find, using Python's built-in tokenizer.

Here is a slightly more interesting example:
```python
# A global dict for caching function values:
(= _fib_cache (dict))


(def fib (n)
    """Returns the nth Fibonacci number.
    Maintains a global cache of values, to avoid needless recalculation."""
    (if
        ((< n 0) (raise (ValueError "Less than 0")))
        ((< n 2) n) # Base cases: 0, 1
        ((in _fib_cache n) ([n] _fib_cache))
        (else
            (= value (+ (fib (- n 1)) (fib (- n 2)) ))
            (= [n] _fib_cache value)
            value
        )
    )
)


# Print out the first 10 Fibonacci numbers:
(for x (range 10) (print (fib x)))
```

For more examples, see: [examples](examples)

## The interpreter

Currently, Lythp has its own runtime, instead of transpiling to Python.
For instance, variables are stored in a stack of contexts, i.e. a list of
dicts.
It would be nice to transpile to Python instead, either by using `exec`
or by generating bytecode directly.

In any case, make sure you're in a python3 virtual environment:
```shell
python3 -m venv venv
. venv/bin/activate
```

Then run files like so:
```shell
./lythp.py examples/fac.lsp
```

You can also run the interpreter in REPL mode like so:
```shell
./lythp.py
```

It may be helpful to install [rlwrap](https://github.com/hanslub42/rlwrap)
to improve the REPL experience:
```shell
rlwrap ./lythp.py
```

You can run the unit tests like so:
```shell
pip install pytest pytest-cov
pytest
```

And run all example programs like so:
```shell
./run.sh
```

## Syntax

The basic syntax is quite simple: the source code is chopped into tokens using Python's
built-in [tokenize module](https://docs.python.org/3/library/tokenize.html), and a tree
structure representing the program is then built, with the following types of node:
* Names: `x`, `None`, `True`, `,`, `*`, `==`
* Literals: `100`, `"Hello!"`, `"""Docstrings too!"""`
* Parentheses: `(...)`
* Brackets: `[...]`
* Braces: `{...}`

NOTE: f-strings (e.g. `f"Hello, {name}!"`) are not currently supported.

As usual in a LISP, parentheses represent statements and function calls.
Here is the syntax of specific statements:

### Built-ins and literals

The following values have the same syntax as in Python:
```python
None
True
False
123
"hello"
r"(\n+)"
b"beep boop"
...  # the "ellipsis" object
```

TODO: describe lists, dicts, sets, etc

### Attribute and item lookup: `.`, `[...]`

Basic usage:
```python
# Python
obj.x
arr[i]
obj.x.y.z[n + 1]

# Lythp
(.x obj)
([i] arr)
(.x.y.z[+ n 1] obj)
```

### Assignment: `=`

Basic usage:
```python
# Python
x = 1
x += 1

# Lythp
(= x 1)
(+= x 1)
```

Assigning with setattr/setitem:
```python
# Python
obj.x.y.z[n + 1] = value

# Lythp
(= .x.y.z[+ n 1] obj value)
```

NOTE: there is no equivalent of Python's destructuring (e.g. `x, y = a, b`).

### Function calls

Basic usage:
```python
# Python
x + y
f(x, y, z=3)
obj.method(x)

# Lythp
(+ x y)
(f x y [z 3])
((.method obj) x)
```

Args and kwargs:
```python
# Python
f(x, y, *args, z=3, **kwargs)

# Lythp
(f x y [*args] [z 3] [**kwargs])
```

### Lambdas and function definitions: `lambda`, `def`

Basic usage:
```python
# Python
def f(x, y, z=3): ...etc...
f = lambda x: x + 1

# Lythp
(def f (x y [z 3]) ...etc...)
(= f (lambda (x) (+ x 1)))
```

NOTE: while Python only allows a single expression per lambda, Lythp allows
statements, like a regular function definition.

Args and kwargs:
```python
# Python
def f(x, /. y, *args, z=3, **kwargs): ...etc...

# Lythp
(def f (x [/] y [*args] [z 3] [**kwargs]) ...etc...)
```

### Classes

```python
# Python
class A(B, C):
    x = 3
    def __init__(self, value):
        ...etc...

a = A(value)

# Lythp
(class A (B C)
    (= x 3)
    (def __init__ (self value)
        ...etc...
    )
)

(= a (A value))
```
