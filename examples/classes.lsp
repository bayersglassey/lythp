

(class Adder ()
    """A class for adding things together."""
    (def __init__ ((self) (value 0))
        (= ._value self value)
        None # __init__ must return None, not the result of the above assignment...
    )
    (def get (self) (._value self))
    (def add ((self) (n 1))
        (+= ._value self n)
    )
)


(print (.__doc__ Adder))


(= a (Adder))
(print ((.get a)))
(assert (== ((.get a)) 0))


(= a (Adder 10))
(print ((.get a)))
((.add a))
((.add a) 2)
(print ((.get a)))
(assert (== ((.get a)) 13))
