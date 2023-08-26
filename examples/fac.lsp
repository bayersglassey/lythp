
= _fac_cache (dict)


def fac (n)
    ; """Calculates the nth factorial"""
    if
        (<= n 0) 1
        (in _fac_cache n) ([n] _fac_cache)
        else
            = value (* n (fac (- n 1)))
            = [n] _fac_cache value
            ; value


for x (range 10)
    print (fac x)


assert
    == _fac_cache (:dict
        1 1
        2 2
        3 6
        4 24
        5 120
        6 720
        7 5040
        8 40320
        9 362880
    )
    _fac_cache
