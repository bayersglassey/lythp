
(= _fib_cache {})


(def fib (n)
    (if
        ((< n 0) (raise (ValueError "Less than 0")))
        ((< n 2) n) # Base cases: 0, 1
        ((in _fib_cache n) (getitem _fib_cache n))
        (else
            (= value (+ (fib (- n 1)) (fib (- n 2)) ))
            (setitem _fib_cache n value)
            value
        )
    )
)


(for x (range 10) (print (fib x)))


(assert (== _fib_cache {
    (2 1)
    (3 2)
    (4 3)
    (5 5)
    (6 8)
    (7 13)
    (8 21)
    (9 34)
}) _fib_cache)
