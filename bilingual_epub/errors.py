"""Problems the reader can do something about.

Every failure in this program falls into one of two kinds, and they are shown
to people very differently.

The first kind is a file this tool cannot use: a download that stopped early,
a book sold with DRM, an archive holding two books instead of one. There is
nothing wrong with the program, and the person holding the file is the only
one who can resolve it. Those raise ``UserFacing``, whose message is written
for a reader rather than an operator -- it names what happened and what to do
next, and it carries no paths, no exception names and no jargon.

The second kind is a defect here. Those keep their ordinary exception types,
are logged in full on the server, and reach the reader as a short apology
with a way to report the file, because a stack trace asks them to debug
software they did not write.

Keeping the two apart is the whole point of this module. Before it existed
the loader raised ValueError, which the web interface could not distinguish
from a genuine crash, so a book that had merely been zipped twice told its
owner that "the details are in the terminal running this server" -- a
terminal on someone else's machine, which they could not read and did not
have. Two of the three hosted failure reports were exactly that.
"""
from .i18n import STRINGS, t


class UserFacing(Exception):
    """A failure whose message is meant to be shown verbatim.

    The message is stored as an interface key and resolved on access, so it
    comes out in the language the reader is using rather than the one that
    happened to be set when the engine raised it.

    Anything interpolated into it is resolved the same way: an argument that
    is itself an interface key is translated on access too. Passing the
    finished text instead looks equivalent and is not -- it freezes that
    fragment in whatever language was current when the engine raised, which
    is how "无法从A side (original)读取到任何正文" gets produced.
    """

    def __init__(self, key, *args):
        self.key = key
        self.detail = args
        super().__init__(key)

    def __str__(self):
        parts = tuple(t(a) if isinstance(a, str) and a in STRINGS else a
                      for a in self.detail)
        return t(self.key, *parts)
