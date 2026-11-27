# Third-party notices

SONOFF AES-CBC wire compatibility and empty `getState` request shape were adapted
from AlexxIT/SonoffLAN v3.13.3, `custom_components/sonoff/core/ewelink/local.py`
and `base.py`. No SonoffLAN control loop, cloud login or integration is bundled.
Sources: https://github.com/AlexxIT/SonoffLAN/tree/v3.13.3

MIT License

Copyright (c) 2020 AlexxIT

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

The observer imports Home Assistant's existing python-zeroconf package; it does
not bundle or modify that LGPL-2.1-or-later library. Raw-record API review targets
python-zeroconf 0.150.0. Home Assistant APIs target Core 2026.8.3. Cryptography
uses Home Assistant's bundled `cryptography` package. This protocol uses legacy
MD5 key derivation and AES-CBC for device compatibility, not authenticated
cryptographic source or hostile-network replay protection.
