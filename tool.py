#!/usr/bin/env python3
from py3_sg import read_as_bin_str, write

def main():
    with open('/dev/sda', 'rb') as f:

        cmd = bytes([
            0xe0,   # chip info opcode?
            0xf4,
            0xe7,
            0x00,
            ]) + b'\x00'*8

        assert len(cmd) == 0xc

        read_ver = read_as_bin_str(f, cmd, 16, 1000)

        # last 4 bytes are the four version fields
        #
        # my broken one w/ 100.1.0.0 says f4e7152d056900003536393164010000

        print(read_ver.hex())

if __name__ == "__main__":
    main()

"""

Mystery "read" bulk request data (21:39:08) looks like 31 bytes:

21:39:08.062873 earlier one

0040   55 53 42 43 10 a0 57 aa 00 20 00 00 80 00 0a 28   USBC..W.. .....(
0050   00 00 00 00 00 00 00 10 00 00 00 00 00 00 00      ...............


third to last:

0040   55 53 42 43 10 40 36 a8 00 20 00 00 80 00 0c df   USBC.@6.. ......
0050   10 00 20 00 00 00 00 01 e0 00 fa 00 00 00 00      .. ............

21:39:08.241957 last

0040   55 53 42 43 c0 1a f7 a7 00 20 00 00 80 00 0a 28   USBC..... .....(
0050   00 00 00 00 00 00 00 10 00 00 00 00 00 00 00      ...............


21:39:08.243471 maybe erase command?

0040   55 53 42 43 10 40 36 a8 00 00 00 00 00 00 0c ff   USBC.@6.........
0050   04 26 4a 4d 00 00 00 00 00 00 00 00 00 00 00      .&JM...........


"""
