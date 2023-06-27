"""A module with platform-specific extended precision
`numpy.number` subclasses.

The subclasses are defined here (instead of ``__init__.pyi``) such
that they can be imported conditionally via the numpy's mypy plugin.
"""

import numpy as np
from . import (
    _80Bit,
    _96Bit,
    _128Bit,
    _256Bit,
)

Uint128 = np.unsignedinteger[_128Bit]
class uint128(np.unsignedinteger[_128Bit]):
    ...

Uint256 = np.unsignedinteger[_256Bit]

class uint256(uint128):
    ...

Int128 = np.signedinteger[_128Bit]
class int128(np.signedinteger[_128Bit]):
    ...

Int256 = np.signedinteger[_256Bit]
class int256(int128):
    ...

Float80 = np.floating[_80Bit]
class float80(np.floating[_80Bit]):
    ...
Float96 = np.floating[_96Bit]
class float96(np.floating[_96Bit]):
    ...
Float128 = np.floating[_128Bit]
class float128(np.floating[_128Bit]):
    ...
Float256 = np.floating[_256Bit]
class float256(np.floating[_256Bit]):
    ...
Complex160 = np.complexfloating[_80Bit, _80Bit]
class complex160(np.complexfloating[_80Bit, _80Bit]):
    ...
Complex192 = np.complexfloating[_96Bit, _96Bit]
class complex192(np.complexfloating[_96Bit, _96Bit]):
    ...
Complex256 = np.complexfloating[_128Bit, _128Bit]
class complex256(np.complexfloating[_128Bit, _128Bit]):
    ...
Complex512 = np.complexfloating[_256Bit, _256Bit]
class complex512(np.complexfloating[_256Bit, _256Bit]):
    ...
