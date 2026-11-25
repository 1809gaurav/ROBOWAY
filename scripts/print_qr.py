from __future__ import annotations

import sys

import qrcode


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: print_qr.py URL", file=sys.stderr)
        return 2
    code = qrcode.QRCode(border=1)
    code.add_data(sys.argv[1])
    code.make(fit=True)
    code.print_ascii(invert=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
