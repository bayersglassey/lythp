
(= _fac_cache {})


(def fac (n)
    (if
        ((<= n 0) 1)
        ((in _fac_cache n) (getitem _fac_cache n))
        (else
            (= value (* n (fac (- n 1))))
            (setitem _fac_cache n value)
            value
        )
    )
)


(for x (range 10) (print (fac x)))


(assert (== _fac_cache {
    (1 1)
    (2 2)
    (3 6)
    (4 24)
    (5 120)
    (6 720)
    (7 5040)
    (8 40320)
    (9 362880)
}) _fac_cache)
