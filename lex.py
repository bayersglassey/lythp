#!/usr/bin/env python
"""Just a little tool for seeing how Python tokenizes things.
Similar to `python -m tokenize`, but makes indentation a bit easier
to see."""

import sys
import tokenize


if __name__ == '__main__':
    def readline():
        return sys.stdin.readline().encode()
    tokens = tokenize.tokenize(readline)
    depth = 0
    for token in tokens:
        if token.type == tokenize.INDENT:
            depth += 1
        elif token.type == tokenize.DEDENT:
            depth -= 1
        print('  ' * depth + str(token))
