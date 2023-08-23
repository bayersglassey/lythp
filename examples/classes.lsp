

(class Adder ()
    """A class for adding things together."""
    (def __init__ ((self) (value 0))
        (= (. self _value) value)
        None # __init__ must return None, not the result of the above assignment...
    )
    (def get (self) (. self _value))
    (def add ((self) (n 1))
        (= (. self _value) (+ (. self _value) n))
    )
)


(print (. Adder __doc__))


(= a (Adder))
(print ((. a get)))
(assert (== ((. a get)) 0))


(= a (Adder 10))
((. a add))
((. a add) 2)
(print ((. a get)))
(assert (== ((. a get)) 13))
