"""
This file doesn't work right now, we get this error:

    Traceback (most recent call last):
      File "./lythp.py", line 652, in <module>
        main()
      File "./lythp.py", line 648, in main
        exec_exprs(exprs, [], vars=global_vars, repl=repl)
      File "./lythp.py", line 583, in exec_exprs
        value = eval_expr(expr, env)
      File "./lythp.py", line 404, in eval_expr
        cls = type(name, bases, vars)
      File "/usr/lib/python3.8/enum.py", line 175, in __new__
        enum_members = {k: classdict[k] for k in classdict._member_names}
    AttributeError: 'dict' object has no attribute '_member_names'

...I think it's 'cos we don't support metaclasses?..
See: https://stackoverflow.com/questions/69328274/enum-raises-attributeerror-dict-object-has-no-attribute-member-names
"""

(= enum (import 'enum'))
(= Enum (. enum Enum))

(class MyEnum (str Enum)
    (= x "XXX")
    (= y "YYY")
)

(assert (== (. MyEnum x) "XXX"))
(assert (== (type (. MyEnum x)) MyEnum))
