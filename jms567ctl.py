#!/usr/bin/env python3
#
# Very basic and unofficial JMS567 flashing tool
#
# Based on reverse engineering USB packet captures showing the interactions of other flashing tools.
#
# Copyright 2023 Angus Gratton
# All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
#
import argparse
import struct
import time

try:
    import usb
    import usb.core
    import usb.util
except ImportError:
    print("Failed to import pyusb, USB device interface not available")
    usb = None
try:
    import py3_sg
except ImportError:
    print("Failed to import py3_sg, Linux /dev/sdx devices not available")
    py3_sg = None

if not (usb or py3_sg):
    raise ImportError("Either pyusb or py3_sg must be installed to use this tool.")

MSC_TAG = 0xCAFECAFE  # Nonsense Tag value to use for dCBWTag and dCSWTag

FLASH_OFFS_NVS = 0xC000  # Seems to be where NVS data is stored in JMS567 .bin files

# The DF vendor SCSI opcode seems to have its own set of sub-commands.
#
# These are all for reading and writing the flash.
DF_OPCODE_WRITE = 0x00
DF_OPCODE_READ = 0x10
DF_OPCODE_ERASE = 0x02  # Seems to be used for erase? Unclear of different with 'write


def _make_df_cmd(opcode, offset, length):
    """Return the commond 'DF' vendor scsi command, with the known fields filled in"""
    return struct.pack(
        ">BBBHIHB",
        0xDF,  # Vendor SCSI opcode
        opcode,
        0x00,  # ???
        length,
        0,  # ???
        offset,
        0xFB if opcode != DF_OPCODE_READ else 0xFA,  # Tag value? Not clear
    )


class ScsiCommander:
    def __init__(self, device_path):
        self.f = open(device_path, "rb")

    def write(self, scsi_cmd, buf=b""):
        py3_sg.write(self.f, scsi_cmd, buf or b"")

    def read(self, scsi_cmd, read_len=0):
        return py3_sg.read_as_bin_str(self.f, scsi_cmd, read_len, 1000)


class USBCommander:
    def __init__(self, id_vendor, id_product=None):
        if id_product:
            dev = usb.core.find(idVendor=id_vendor, idProduct=id_product)
        else:
            dev = usb.core.find(idVendor=id_vendor)

        if dev is None:
            raise ValueError(
                f"Available USB device not found. VID={id_vendor:#x} PID={hex(id_product) if id_product else 'Any'}"
            )

        dev.set_configuration()  # set first configuration

        # Find the MSC BOT interface (probably the first one, but can't hurt to check)
        cfg = dev.get_active_configuration()
        intf = None
        for i in cfg:
            if i.bInterfaceClass == 0x08 and i.bInterfaceProtocol == 0x50:
                print(f'Found USB MSC BOT interface {i.bInterfaceNumber}')
                intf = i
                break

        if not intf:
            raise RuntimeError('Failed to find USB MSC interface')

        # If the uas driver has already loaded, the device will have switched interfaces
        if len(list(cfg)) > 0:
            print(f'Setting alt interface to {intf.bAlternateSetting}...')
            intf.set_altsetting()

        self.ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
            == usb.util.ENDPOINT_OUT,
        )

        self.ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
            == usb.util.ENDPOINT_IN,
        )

        if self.ep_out.bEndpointAddress != 0x02 or self.ep_in.bEndpointAddress != 0x81:
            raise RuntimeError('Unexpected bEndpointAddress values')

    def _make_cbw(self, scsi_cmd, data_len, direction_out):
        # Wrap the SCSI command in a USB Mass Storage Command Block
        # Wrapper. This seems to work even if the device is running a UAS
        # firmware, which is convenient!
        assert len(scsi_cmd) <= 16
        cbw = struct.pack(
            "<IIIBBB",
            0x43425355,  # dCBWSignature
            MSC_TAG,  # dCBWTag, nonsense value
            data_len,  # dCBWDataTransferLength
            0 if direction_out else (1 << 7),  # dCBWFlags
            0,  # dCBWLUN, always zero
            len(scsi_cmd),
        ) + scsi_cmd + b'\x00' * (16 - len(scsi_cmd))
        assert len(cbw) == 0x1f
        return cbw


    def _read_csw(self):
        # We don't need to do anything with the CSW, just
        # check it looks coorrect
        csw = bytes(self.ep_in.read(13))

        (dCSWSignature, dCSWTag, dCSWDataResidue, bCSWStatus) = struct.unpack(
            "<IIIB", csw
        )

        if dCSWSignature != 0x53425355:
            raise RuntimeError(f"Invalid CSW Response: {csw.hex()}")

        if dCSWTag != MSC_TAG:
            raise RuntimeError(
                f"CSW TAG mismatch, multiple access to device? {csw.hex()}"
            )

        if dCSWDataResidue != 0:
            print(f"Warning {dCSWDataResidue} bytes of data residue reported")

        if bCSWStatus != 0:
            raise RuntimeError(
                f"Command failed with result {bCSWStatus:#x}. Response: {csw.hex()}"
            )

    def write(self, scsi_cmd, data=None):
        data_len = len(data) if data else 0
        self.ep_out.write(self._make_cbw(scsi_cmd, data_len, True))
        if data:
            self.ep_out.write(data)
        self._read_csw()

    def read(self, scsi_cmd, data_len=0):
        cbw = self._make_cbw(scsi_cmd, data_len, False)
        self.ep_out.write(cbw)
        if data_len:
            result = bytes(self.ep_in.read(data_len))
        else:
            result = None
        self._read_csw()
        return result


class JMS567VendorInterface:
    def __init__(self, commander):
        self._c = commander

    def chip_info(self):
        cmd = (
            bytes(
                [
                    0xE0,  # chip info SCSI opcode
                    0xF4,  # magic values, no clue what these mean
                    0xE7,
                    0x00,
                ]
            )
            + b"\x00" * 8
        )
        assert len(cmd) == 0xC
        return self._c.read(cmd, 16)

    def firmware_version(self):
        """Returns the firmware version as a tuple.
        (0, 0, 0, 1) means 'factory Mask ROM/no-flash' version"""
        info = self.chip_info()
        # Last four bytes in the chip_info structure are the version numbers
        return struct.unpack("BBBB", info[12:])  # TODO: check my math on this

    def erase_flash(self):
        """Erase the flash chip and take JMS567 back to the Mask ROM firmware"""
        cmd = _make_df_cmd(DF_OPCODE_ERASE, 0x0000, 0x1000)
        # Need to also supply a buffer of empty bytes to erase with (maybe? can test without this)
        self._c.write(cmd, b"\xff" * 0x1000)

    def reset_chip(self):
        """Reset the JMS chip"""
        cmd = (
            bytes(
                [
                    0xFF,  # vendor SCSI opcode for reset
                    0x04,  # magic bytes?
                    0x26,
                    0x4A,
                    0x4D,
                ]
            )
            + b"\x00" * 7
        )
        assert len(cmd) == 0x0C
        return self._c.write(cmd)

    def write_flash(self, data, offset, skip_nvs):
        if skip_nvs and offset:
            # If needed this could be implemented, but seems unnecessary
            raise NotImplementedError("If skip_nvs is set, offset must be zero.")
        if skip_nvs:
            if len(data) < FLASH_OFFS_NVS:
                print(
                    "Data to write is shorter than NVS partition offset, no need to truncate"
                )
            else:
                data = data[:FLASH_OFFS_NVS]
                print("Truncated data to skip writing NVS region")

        if offset % 0x1000:
            raise ValueError("Offset must be a multiple of 0x1000")

        if len(data) % 0x1000:
            to_pad = 0x1000 - (len(data) % 0x1000)
            print(f"Padding data by {to_pad} bytes to fill flash sector")
            data = data + b"\xFF" * to_pad
            assert len(data) % 0x1000 == 0

        for o in range(0, len(data), 0x1000):
            print(f"Writing at offset {offset+o:#x}...")
            self._write_sector(data[o : o + 0x1000], offset + o)

    def _write_sector(self, data, offset):
        assert offset % 0x1000 == 0
        assert len(data) % 0x1000 == 0
        cmd = _make_df_cmd(DF_OPCODE_WRITE, offset, len(data))
        self._c.write(cmd, data)

    def read_flash(self, offset, length):
        data = bytearray(length)
        for o in range(0, length, 0x1000):
            to_read = min(0x1000, length - o)
            read_from = o + offset
            print(f"Reading {to_read:#x} bytes from offset {read_from:#x}")
            cmd = _make_df_cmd(DF_OPCODE_READ, read_from, to_read)
            data[read_from : read_from + to_read] = self._c.read(cmd, to_read)
        return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--device",
        "-d",
        help="USB device to connect to. Can be either USB VID:, USB VID:PID combination (i.e. 152d:0569) or a Linux block device path i.e. (/dev/sda)",
        required=True,
    )
    parser.set_defaults(func=None)

    sp = parser.add_subparsers(help="Subcommands")

    chip_info = sp.add_parser("chip_info", help="Connect and print info, only")
    chip_info.set_defaults(func=cmd_chip_info)

    reset_chip = sp.add_parser("reset_chip", help="Reset chip and run any new firmware")
    reset_chip.set_defaults(func=cmd_reset_chip)

    erase_flash = sp.add_parser("erase_flash", help="Erase flash chip")
    erase_flash.add_argument(
        "--no-reset", help="Don't reset chip after erasing flash", action="store_true"
    )
    erase_flash.set_defaults(func=cmd_erase_flash)

    write_flash = sp.add_parser("write_flash", help="Write file to flash")
    write_flash.add_argument(
        "--erase", "-e", help="Erase the chip first", action="store_true"
    )
    write_flash.add_argument(
        "--offset", "-o", help="Offset to write to.", type=int, default=0
    )
    write_flash.add_argument(
        "--skip-nvs", help="Don't write NVS from file to flash", action="store_true"
    )
    write_flash.add_argument(
        "--no-reset", help="Don't reset chip after writing flash", action="store_true"
    )
    write_flash.add_argument("filename", help="Filename to write")
    write_flash.set_defaults(func=cmd_write_flash)

    read_flash = sp.add_parser("read_flash", help="Read flash to file")
    read_flash.add_argument(
        "--offset", "-o", help="Flash offset to read from.", type=int, default=0
    )
    read_flash.add_argument(
        "--length", "-l", help="Flash length to read.", type=int, default=65536
    )
    read_flash.add_argument("filename", help="Filename to read from")
    read_flash.set_defaults(func=cmd_read_flash)

    args = parser.parse_args()

    # Get the interface object
    if ":" in args.device:
        if not usb:
            raise RuntimeError("Specifying USB VID/PID requires pyusb to be installed")
        vid, pid = args.device.split(":")
        if not vid:
            raise RuntimeError("USB VID must be provided, i.e. '-d 152d:'")
        vid = int(vid, 16)
        if pid:
            pid = int(pid, 16)
        else:
            pid = None
        cmd = USBCommander(vid, pid)
    else:
        if not py3_sg:
            raise RuntimeError("Specifying block device requires py3_sg to be installed")
        print(f"Opening block device {args.device}...")
        cmd = ScsiCommander(args.device)

    intf = JMS567VendorInterface(cmd)

    # It seems like erase_flash command may be the only working command in some configs,
    # so go straight to that command in that case
    if args.func != cmd_erase_flash:
        print("Reading firmware version...")
        print("Firmware version: " + ".".join(str(f) for f in intf.firmware_version()))

    # Run the actual command
    if args.func:
        args.func(intf, args)
    print("Done")


def cmd_chip_info(intf, args):
    chip_info = intf.chip_info()
    print("Chip info: " + chip_info.hex())


def cmd_reset_chip(intf, args):
    intf.reset_chip()


def cmd_erase_flash(intf, args):
    intf.erase_flash()
    if not args.no_reset:
        print("Resetting after erase...")
        intf.reset_chip()


def cmd_write_flash(intf, args):
    with open(args.filename, "rb") as f:
        data = f.read()
    if args.erase:
        print("Erasing whole flash...")
        intf.erase_flash()
    intf.write_flash(data, args.offset, args.skip_nvs)
    if not args.no_reset:
        print("Resetting after write...")
        intf.reset_chip()


def cmd_read_flash(intf, args):
    data = intf.read_flash(args.offset, args.length)
    print(f"Writing {len(data)} bytes to {args.filename}...")
    with open(args.filename, "wb") as f:
        f.write(data)


if __name__ == "__main__":
    main()
