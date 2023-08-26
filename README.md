# Lythp

It's Python turned into a LISP!
```python
def greet (name)
    print (+ "Hello " name "!")

# Outputs: Hello Jim!
greet "Jim"
```

The goal is not to preserve LISP traditions, keywords, and features; rather,
the goal is to have fun fitting Python into a LISP syntax in the most natural
way I can find, using Python's built-in tokenizer (including significant
whitespace).

Here is a slightly more interesting example:
```python
# A global dict for caching function values:
= _fib_cache (dict)


def fib (n)
    ; """Returns the nth Fibonacci number.
    Maintains a global cache of values, to avoid needless recalculation."""
    if
        (< n 0) (raise (ValueError "Less than 0"))
        (< n 2) n # Base cases: 0, 1
        (in _fib_cache n) ([n] _fib_cache)
        else
            = value (+ (fib (- n 1)) (fib (- n 2)))
            = [n] _fib_cache value
            ; value


# Print out the first 10 Fibonacci numbers:
for x (range 10)
    print (fib x)
```

For more examples, see: [examples](examples)

## The interpreter

NOTE: currently, Lythp has its own runtime, instead of transpiling to Python.
For instance, Lythp variables are stored in a stack of contexts, i.e. a list
of dicts, and classes are built by calling [type](https://docs.python.org/3/library/functions.html#type).
It would be nice to transpile to Python instead, either by using `exec`
or by generating bytecode directly.
(Although then we would lose some LISP-y features of the current
implementation, like functions returning the value of their last statment.
But that's not a very Pythonic thing to be doing anyway.)

Make sure you're in a python3 virtual environment:
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
pip install pytest
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

### Whitespace is significant

Like Python, Lythp uses whitespace, particularly indentation, as part of
its syntax.

Consider the following Lythp code.
These two function definitions are 100% equivalent:
```python
def f (x) (+ x 1)
def f (x)
    + x 1
```

If Lythp did not support significant whitespace, the above example could be
written with explicit parentheses as:
```python
(def f (x) (+ x 1))
(def f (x)
    (+ x 1)
)
```

NOTE: indentation is handled by Python's built-in tokenizer.
In particular, within `(...)`, `[...]`, and `{...}`, indentation is ignored.
Also, backslash can be used to ignore a newline.
So for instance, the following Lythp function definitions are 100% equivalent
(they are different ways of expressing the exact same code structure):
```python
def f (x y)
    + x y

def f (
  x   y
           )
    + x y

def f (x y)
    + \
        x y
```

...look, I didn't make the rules for Python's tokenizer, I'm just using
it as I found it, okay? O_o

The rules of whitespace in Lythp are:
* Each line is secretly wrapped in parentheses, unless the line begins with `;`
* Indented blocks of code are treated as continuations of the previous line

For the meaning of `;`, consider the following 100% equivalent function
definitions:
```python
def f (x)
    + x 1

; (def f (x)
    (+ x 1)
    # NOTE: the preceding line needs explicit parentheses, because we
    # are inside a `(...)` block, so Python's tokenizer does not consider
    # these lines to be indented!
)
```

As an example of how `;` is useful in practice, consider the following
function definitions:
```python
# Equivalent definitions of a function which calls f with no arguments
def call_f (f) (f)
def call_f (f)
    f

# Equivalent definitions of a function which returns x
def return_x (x) x
def return_x (x)
    ; x
```

Another use case for `;` is docstrings:
```python
def f (x y z)
    ; """I am a docstring."""
    # Without the `;`, the preceding line would attempt to call the
    # string literal as a function with no arguments!..
    ...etc...
```

### Built-ins and literals

The following values have the same syntax as in Python:
```python
None
True
False
...  # the "ellipsis" object

123
-10.5
1.3e6

"hello"
r"(\n+)"
b"beep boop"

"""I am a
multiline
string"""
```

Everything from the [builtins module](https://docs.python.org/3/library/functions.html)
is included in the global variables.

The syntax for literal tuples, lists, sets, dicts, comprehensions, and
generator expressions uses a `:` prefix:
```python
# Equivalent to Python's (1, 2, 3)
:tuple 1 2 3

# Equivalent to Python's [1, 2, 3]
:list 1 2 3

# Equivalent to Python's {1, 2, 3}
:set 1 2 3

# Equivalent to Python's {'x': 1, 'y': 2}
:dict 'x' 1 'y' 2

# Equivalent to Python's (i * 2 for i in range(5))
:genexp (* i 2) (for i (range 5))

# Equivalent to Python's [i * 2 for i in range(5)]
:listcomp (* i 2) (for i (range 5))

# Equivalent to Python's {i * 2 for i in range(5)}
:setcomp (* i 2) (for i (range 5))

# Equivalent to Python's {i: i * 2 for i in range(5)}
:dictcomp i (* i 2) (for i (range 5))
```

Comprehensions and generator expressions support multiple `for` clauses
and an optional `if` clause:
```python
# Equivalent to Python:
#
#     [(i, j)
#         for i in range(3)
#         for j in range(3)
#         if (i + j) % 2]
#
# ...i.e. [(0, 1), (1, 0), (1, 2), (2, 1)]
:listcomp (:tuple i j)
    for i (range 3)
    for j (range 3)
    if (% (i + j) 2)
```

Note the difference between literals and references to built-in types:
```python
# Syntax error
print :list

# Equivalent to Python's print(list)
print list

# Equivalent to Python's print(['abc'])
print (:list 'abc')

# Equivalent to Python's print(list('abc')), i.e. ['a', 'b', 'c']
print (list 'abc')
```

Also, keep in mind the rules for indentation!
```python
# WRONG!.. will attempt to call 'x' and 'y' like functions!..
:dict
    'x' 1
    'y' 2

# Correct:
(:dict
    'x' 1
    'y' 2
)

# ...luckily, in practice the correct form is more natural anyway, since
# you're generally creating a dict and then doing something with it,
# like storing it in a variable:
= d (:dict
    'x' 1
    'y' 2
)
```

### Attribute and item lookup: `.`, `[...]`

Basic usage:
```python
# Python
obj.x
arr[i]
obj.x.y.z[n + 1]

# Lythp
.x obj
[i] arr
.x.y.z[+ n 1] obj
```

### Assignment: `=`, '+=', etc

Basic usage:
```python
# Python
x = 1
x += 1

# Lythp
= x 1
+= x 1
```

NOTE: there is no equivalent of Python's destructuring (e.g. `x, y = a, b`).

Assigning to attributes/indices:
```python
# Python
obj.x.y.z[n + 1] = value

# Lythp
= .x.y.z[+ n 1] obj value
```

### Operators and function calls

Basic usage:
```python
# Python
x + y
x + y + z
f(x, y, z=3)
obj.method(x)

# Lythp
+ x y
+ x y z
f x y [z 3]
(.method obj) x
```

Args and kwargs:
```python
# Python
f(x, y, *args, z=3, **kwargs)

# Lythp
f x y [*args] [z 3] [**kwargs]

### Conditionals

Basic `if` usage:
```python
# Python
if cond1:
    ...etc...
elif cond2:
    ...etc...
else:
    ...etc...

# Lythp
if (cond1 ...etc...) (cond2 ...etc...) (else ...etc...)
```

Example (one-liner):
```python
# Python
if x < 3: return 99

# Lythp
if (< x 3) (return 99)
```

Example (multi-line):
```python
# Python
if x < 3:
    print("A")
elif x < 5:
    print("A")
else:
    print("C")

# Lythp
if
    (< x 3)
        print "A"
    (< x 5)
        print "B"
    else
        print "C"
```python

### Loops

Basic usage:
```python
# Python
while cond:
    ...etc...

# Lythp
while cond ...etc...

# Python
for x in xs:
    ...etc...

# Lythp
for x xs ...etc...
```

Example:
```python
# Python
while x < 3:
    for i in range(x):
        print(x)
        print(i)

# Lythp
while (< x 3)
    for i (range x)
        print x
        print i
```

NOTE: `continue` and `break` should be "called" like functions:
```python
while cond ...etc... (continue)

while cond ...etc... (break)

while cond
    ...etc...
    continue

while cond
    ...etc...
    break
```

NOTE: there is no support for the `for` loop's `else` clause, so sorry

### Lambdas and function definitions: `lambda`, `def`

Basic usage:
```python
# Python
def f(x, y, z=3): ...etc...
f = lambda x: x + 1

# Lythp
def f (x y [z 3]) ...etc...
= f (lambda (x) (+ x 1))
```

NOTE: while Python only allows a single expression as the lambda's body,
Lythp allows arbitrary statements, like a regular function definition.

Args and kwargs:
```python
# Python
def f(x, /. y, *args, z=3, **kwargs): ...etc...

# Lythp
def f (x [/] y [*args] [z 3] [**kwargs]) ...etc...
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
class A (B C)
    = x 3
    def __init__ (self value)
        ...etc...

= a (A value)
```

### Assertions, exceptions

```python
# Python
raise Exception("BOOM!")
assert x == 3
assert x == 3, "x was not 3"

# Lythp
raise (Exception "BOOM!")
assert (== x 3)
assert (== x 3) "x was not 3"
```

TODO: figure out try/except/finally

### Imports

```python
# Python
import csv
import os.path
from csv import reader, writer as csv_writer
from csv import (
    reader,
    writer as csv_writer,
)

# Lythp
import (csv)
import (os path)
from (csv) reader (writer csv_writer)
from (csv)
    reader
    writer csv_writer
```
