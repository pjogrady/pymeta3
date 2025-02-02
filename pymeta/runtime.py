# -*- test-case-name: pymeta.test.test_runtime -*-
"""
Code needed to run a grammar after it has been compiled.
"""
import operator

# The public parse error
class ParseError(Exception):
    pass

# The internal ParseError
class _MaybeParseError(Exception):
    """
    ?Redo from start
    """

    @property
    def position(self):
        return self.args[0]

    @property
    def error(self):
        return self.args[1]

    def __init__(self, *a):
        Exception.__init__(self, *a)
        if len(a) > 2:
            self.message = a[2]

    def __getitem__(self, n):
        return self.args[n]

    def __eq__(self, other):
        if other.__class__ == self.__class__:
            return (self.position, self.error) == (other.position, other.error)

    def formatReason(self):
        if self.error is None:
            return ''
        if len(self.error) == 1:
            if self.error[0][0] == 'message':
                return self.error[0][1]
            elif self.error[0][2] == None:
                return 'expected a ' + self.error[0][1]
            else:
                return 'expected the %s %s' % (self.error[0][1], self.error[0][2])
        else:
            bits = []
            for s in self.error:
                if s[2] is None:
                    desc = "a " + s[1]
                else:
                    desc = repr(s[2])
                    if s[1] is not None:
                        desc = "%s %s" % (s[1], desc)
                bits.append(desc)

            return "expected one of %s, or %s" % (', '.join(bits[:-1]), bits[-1])

    def formatError(self, input):
        """
        Return a pretty string containing error info about string parsing failure.
        """
        reason = self.formatReason()
        if not isinstance(input, str):
            return ("Parse error at input %s: %s\n" % (input, reason))
        lines = input.split('\n')
        counter = 0
        line_number = 1
        column = 0
        for line in lines:
            new_counter = counter + len(line) + 1
            if new_counter > self.position:
                column = self.position - counter
                break
            else:
                counter = new_counter
                line_number += 1
        return ('\n' + line + '\n' + (' ' * column + '^') +
                "\nParse error at line %s, column %s: %s\n" % (line_number,
                                                               column,
                                                               reason))

class EOFError(_MaybeParseError):
    def __init__(self, position):
        _MaybeParseError.__init__(self, position, eof())


def expected(typ, val=None):
    """
    Return an indication of expected input and the position where it was
    expected and not encountered.
    """

    return [("expected", typ, val)]


def eof():
    """
    Return an indication that the end of the input was reached.
    """
    return [("message", "end of input")]

def joinErrors(errors):
    """
    Return the error from the branch that matched the most of the input.
    """
    # This next statement doesn't work on python3 as None
    # is not sortable with respect to int.
    #errors.sort(reverse=True, key=operator.itemgetter(0))
    def noneSorter(o):
        r = o[0]
        if r == None:
            return 0
        return r
    errors.sort(reverse=True, key=noneSorter)
    results = set()
    pos = errors[0][0]
    for err in errors:
        if pos == err[0]:
            e = err[1]
            if e is not None:
                for item in e:
                        results.add(item)
        else:
            break

    return [pos, list(results)]

class character(str):
    """
    Type to allow distinguishing characters from strings.
    """

    def __iter__(self):
        """
        Prevent string patterns and list patterns from matching single
        characters.
        """
        raise TypeError("Characters are not iterable")

class unicodeCharacter(str):
    """
    Type to distinguish characters from Unicode strings.
    """
    def __iter__(self):
        """
        Prevent string patterns and list patterns from matching single
        characters.
        """
        raise TypeError("Characters are not iterable")

class InputStream(object):
    """
    The basic input mechanism used by OMeta grammars.
    """

    def fromIterable(cls, iterable):
        """
        @param iterable: Any iterable Python object.
        """
        if isinstance(iterable, str):
            data = [character(c) for c in iterable]
        elif isinstance(iterable, str):
            data = [unicodeCharacter(c) for c in iterable]
        else:
            data = list(iterable)
        return cls(data, 0)
    fromIterable = classmethod(fromIterable)

    def __init__(self, data, position):
        self.data = data
        self.position = position
        self.memo = {}
        self.tl = None

    def head(self):
        if self.position >= len(self.data):
            raise EOFError(self.position)
        return self.data[self.position], [self.position, None]

    def nullError(self):
        return _MaybeParseError(self.position, None)

    def tail(self):
        if self.tl is None:
            self.tl = InputStream(self.data, self.position + 1)
        return self.tl

    def prev(self):
        return InputStream(self.data, self.position - 1)

    def getMemo(self, name):
        """
        Returns the memo record for the named rule.
        @param name: A rule name.
        """
        return self.memo.get(name, None)


    def setMemo(self, name, rec):
        """
        Store a memo record for the given value and position for the given
        rule.
        @param name: A rule name.
        @param rec: A memo record.
        """
        self.memo[name] = rec
        return rec

class ArgInput(object):
    def __init__(self, arg, parent):
        self.arg = arg
        self.parent = parent
        self.memo = {}
        self.err = parent.nullError()

    def head(self):
        return self.arg, self.err

    def tail(self):
        return self.parent

    def nullError(self):
        return self.parent.nullError()

    def getMemo(self, name):
        """
        Returns the memo record for the named rule.
        @param name: A rule name.
        """
        return self.memo.get(name, None)

    def setMemo(self, name, rec):
        """
        Store a memo record for the given value and position for the given
        rule.
        @param name: A rule name.
        @param rec: A memo record.
        """
        self.memo[name] = rec
        return rec


class LeftRecursion(object):
    """
    Marker for left recursion in a grammar rule.
    """
    detected = False

class OMetaBase(object):
    """
    Base class providing implementations of the fundamental OMeta
    operations. Built-in rules are defined here.
    """
    globals = None
    def __init__(self, string, globals=None):
        """
        @param string: The string to be parsed.

        @param globals: A dictionary of names to objects, for use in evaluating
        embedded Python expressions.
        """
        self.input = InputStream.fromIterable(string)
        self.locals = {}
        if self.globals is None:
            if globals is None:
                self.globals = {}
            else:
                self.globals = globals

        self.currentError = self.input.nullError()

    @classmethod
    def parse(cls, source):
        if isinstance(source, str):
            source = source.decode('utf8')
        try:
            parser = cls(source)
            return parser.apply('grammar')[0]
        except _MaybeParseError:
            raise ParseError(parser.currentError.formatError(source))

    def considerError(self, error):
        if isinstance(error, _MaybeParseError):
            error = error.args
        if error and error[1] and error[0] > self.currentError[0]:
            self.currentError = _MaybeParseError(*error)

    def superApply(self, ruleName, *args):
        """
        Apply the named rule as defined on this object's superclass.

        @param ruleName: A rule name.
        """
        r = getattr(super(self.__class__, self), "rule_" + ruleName, None)
        if r is not None:
            self.input.setMemo(ruleName, None)
            return self._apply(r, ruleName, args)
        else:
            raise NameError("No rule named '%s'" % (ruleName,))

    def apply(self, ruleName, *args):
        """
        Apply the named rule, optionally with some arguments.

        @param ruleName: A rule name.
        """
        r = getattr(self, "rule_" + ruleName, None)
        if r is not None:
            val, err = self._apply(r, ruleName, args)
            return val, _MaybeParseError(*err)
        else:
            raise NameError("No rule named '%s'" % (ruleName,))
    rule_apply = apply

    def _apply(self, rule, ruleName, args):
        """
        Apply a rule method to some args.
        @param rule: A method of this object.
        @param ruleName: The name of the rule invoked.
        @param args: A sequence of arguments to it.
        """
        if args:
            if rule.__code__.co_argcount - 1 != len(args):
                for arg in args[::-1]:
                    self.input = ArgInput(arg, self.input)
                return rule()
            else:
                return rule(*args)
        memoRec = self.input.getMemo(ruleName)
        if memoRec is None:
            oldPosition = self.input
            lr = LeftRecursion()
            memoRec = self.input.setMemo(ruleName, lr)

            #print "Calling", rule
            try:
                memoRec = self.input.setMemo(ruleName,
                                             [rule(), self.input])
            except _MaybeParseError:
                #print "Failed", rule
                raise
            #print "Success", rule
            if lr.detected:
                sentinel = self.input
                while True:
                    try:
                        self.input = oldPosition
                        ans = rule()
                        if (self.input == sentinel):
                            break

                        memoRec = oldPosition.setMemo(ruleName,
                                                     [ans, self.input])
                    except _MaybeParseError:
                        break
            self.input = oldPosition

        elif isinstance(memoRec, LeftRecursion):
            memoRec.detected = True
            raise _MaybeParseError(None, None)
        self.input = memoRec[1]
        return memoRec[0]


    def rule_anything(self):
        """
        Match a single item from the input of any kind.
        """
        h, p = self.input.head()
        self.input = self.input.tail()
        return h, p

    def exactly(self, wanted):
        """
        Match a single item from the input equal to the given specimen.

        @param wanted: What to match.
        """
        i = self.input
        val, p = self.input.head()
        self.input = self.input.tail()
        if wanted == val:
            return val, p
        else:
            self.input = i
            raise _MaybeParseError(p[0], expected(None, wanted))

    rule_exactly = exactly

    def many(self, fn, *initial):
        """
        Call C{fn} until it fails to match the input. Collect the resulting
        values into a list.

        @param fn: A callable of no arguments.
        @param initial: Initial values to populate the returned list with.
        """
        ans = []
        for x, e in initial:
            ans.append(x)
        while True:
            try:
                m = self.input
                v, _ = fn()
                ans.append(v)
            except _MaybeParseError as ex:
                e = ex # save the exception
                self.input = m
                break
        return ans, e
        
    def manyn(self, fn, value):
        """
        Call C{fn} <value> times. Collect the resulting values into a list.

        @param fn: A callable of no arguments.
        @param value: Number of times to call the function.
        """
        ans = [fn()[0] for x in range(value)]
        return ans, self.input.nullError() # Is this the correct return value?

    def _or(self, fns):
        """
        Call each of a list of functions in sequence until one succeeds,
        rewinding the input between each.

        @param fns: A list of no-argument callables.
        """
        errors = []
        for f in fns:
            try:
                m = self.input
                ret, err = f()
                errors.append(err)
                return ret, joinErrors(errors)
            except _MaybeParseError as ex:
                e = ex # save the exception
                errors.append(e)
                self.input = m
        raise _MaybeParseError(*joinErrors(errors))


    def _not(self, fn):
        """
        Call the given function. Raise _MaybeParseError iff it does not.

        @param fn: A callable of no arguments.
        """
        m = self.input
        try:
            fn()
        except _MaybeParseError:
            self.input = m
            return True, self.input.nullError()
        else:
            raise _MaybeParseError(*self.input.nullError())

    def eatWhitespace(self):
        """
        Consume input until a non-whitespace character is reached.
        """
        while True:
            try:
                c, e = self.input.head()
            except EOFError as ex:
                e = ex # don't toss out the exception
                break
            t = self.input.tail()
            if c.isspace():
                self.input = t
            else:
                break
        return True, e
    rule_spaces = eatWhitespace


    def pred(self, expr):
        """
        Call the given function, raising _MaybeParseError if it returns false.

        @param expr: A callable of no arguments.
        """
        val, e = expr()
        if not val:
            raise _MaybeParseError(*e)
        else:
            return True, e

    def listpattern(self, expr):
        """
        Call the given function, treating the next object on the stack as an
        iterable to be used for input.

        @param expr: A callable of no arguments.
        """
        v, e = self.rule_anything()
        oldInput = self.input
        try:
            self.input = InputStream.fromIterable(v)
        except TypeError:
            raise _MaybeParseError(e[0], expected("an iterable"))
        expr()
        self.end()
        self.input = oldInput
        return v, e


    def end(self):
        """
        Match the end of the stream.
        """
        return self._not(self.rule_anything)

    rule_end = end

    def lookahead(self, f):
        """
        Execute the given callable, rewinding the stream no matter whether it
        returns successfully or not.

        @param f: A callable of no arguments.
        """
        try:
            m = self.input
            x = f()
            return x
        finally:
            self.input = m


    def match_string(self, tok):
        """
        Match and return the given string.
        """
        m = self.input
        try:
            for c in tok:
                v, e = self.exactly(c)
            return tok, e
        except _MaybeParseError as e:
            self.input = m
            raise _MaybeParseError(e[0], expected("string", tok))
    rule_match_string = match_string

    def token(self, tok):
        """
        Match and return the given string, consuming any preceding whitespace.
        """
        m = self.input
        try:
            self.eatWhitespace()
            for c in tok:
                v, e = self.exactly(c)
            return tok, e
        except _MaybeParseError as e:
            self.input = m
            raise _MaybeParseError(e[0], expected("token", tok))

    rule_token = token

    def letter(self):
        """
        Match a single letter.
        """
        x, e = self.rule_anything()
        if x.isalpha():
            return x, e
        else:
            e[1] = expected("letter")
            raise _MaybeParseError(*e)

    rule_letter = letter

    def letterOrDigit(self):
        """
        Match a single alphanumeric character.
        """
        x, e = self.rule_anything()
        if x.isalnum() or x == '_':
            return x, e
        else:
            e[1] = expected("letter or digit")
            raise _MaybeParseError(*e)

    rule_letterOrDigit = letterOrDigit

    def digit(self):
        """
        Match a single digit.
        """
        x, e = self.rule_anything()
        if x.isdigit():
            return x, e
        else:
            e[1] = expected("digit")
            raise _MaybeParseError(*e)

    rule_digit = digit


    def pythonExpr(self, endChars="\r\n"):
        """
        Extract a Python expression from the input and return it.

        @arg endChars: A set of characters delimiting the end of the expression.
        """
        delimiters = {"(": ")", "[": "]", "{": "}"}
        stack = []
        expr = []
        endchar = None
        while True:
            try:
                c, e = self.rule_anything()
            except _MaybeParseError as ex:
                e = ex # save the exception
                endchar = None
                break
            if c in endChars and len(stack) == 0:
                endchar = c
                break
            else:
                expr.append(c)
                if c in delimiters:
                    stack.append(delimiters[c])
                elif len(stack) > 0 and c == stack[-1]:
                    stack.pop()
                elif c in list(delimiters.values()):
                    raise _MaybeParseError(self.input.position,
                                           expected("Python expression"))
                elif c in "\"'":
                    while True:
                        strc, stre = self.rule_anything()
                        expr.append(strc)
                        slashcount = 0
                        while strc == '\\':
                            strc, stre = self.rule_anything()
                            expr.append(strc)
                            slashcount += 1
                        if strc == c and slashcount % 2 == 0:
                            break

        if len(stack) > 0:
            raise _MaybeParseError(self.input.position, expected("Python expression"))
        return (''.join(expr).strip(), endchar), e
