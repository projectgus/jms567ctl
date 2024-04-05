# JMS567 Flasher Tool

This is an unofficial, unstable, very alpha quality, flashing tool for the JMicron JMS567 USB to SATA interface chip. It is written in Python.

## Has worked with

(This is not a guarantee of support!)

* Icybox IB-3640SU3
* StarTech S355BU33ERM ([reference](https://github.com/projectgus/jms567ctl/issues/1))

## Probably also works with

* StarTech S358BU33ERM ([reference](https://github.com/projectgus/jms567ctl/issues/1))

*If you've used this tool with another device, please send a PR or open an issue to add to these lists.*

## Background

This is written based on black box reverse engineering of the USB transfers sent by the the closed source ARM Linux binary [flasher tool distributed by Odroid](https://forum.odroid.com/viewtopic.php?t=41926), and some of the other Windows vendor flashing tools available online.

I wrote it because I managed to upgrade my chip to a broken firmware which all of the official tools refused to upgrade again, but seemingly it was still possible to erase the flash via USB rather than having to open the enclosure up and manually erase the flash. Then I figured: "I've wasted this many hours already, might as well clean it up and share it."

## Dependencies

Recommended to use [py3_sg](https://github.com/tvladyslav/py3_sg) on Linux to access the chip (`pip install py3_sg`). A SATA disk must be attached to the chip before it enumerates over USB at all.

There's a very experimental [pyusb](https://github.com/pyusb/pyusb/) backend, but it is pretty unreliable especially (it seems) on some UAS-enabled firmwares... :|

Or if you [install Nix](https://github.com/DeterminateSystems/nix-installer?tab=readme-ov-file#the-determinate-nix-installer) you can run it like this e.g.:

```
$ nix run github:projectgus/jms567ctl -- --help
```

## Commands

### Read firmware version

With no arguments, the current firmware version is printed:

```
$ sudo ./jms567ctl.py -d /dev/sdX
Opening block device /dev/sda...
Reading firmware version...
Firmware version: 20.6.0.1
Done
```

### Read flash

```
sudo ./jms567ctl.py -d /dev/sdX read_flash name_of_firmware_dump_file.bin
```

By default this command reads 64KB of flash, which seems to be bigger than any firmware in use. Pass the `-l LENGTH` option after `read_flash` in order to read a specific number of bytes.

### Write new firmware to flash

```
sudo ./jms567ctl.py -d /dev/sdX write_flash --erase /path/to/new_firmware.bin
```

The `--erase` option after `write_flash` will erase the whole chip before writing. If you don't pass this option, only bits in flash written 1->0 will actually change - if there is already a firmware on the flash rather than empty FF bytes, then you may get a garbled output. This is not ideal, but I don't know how to tell the chip to erase only the sectors which you are going to write (maybe it can't?!?)

To skip writing the "NVS" region at offset 0xc000, which holds custom VID/PID settings and other configuration options, pass the `--skip-nvs` argument after `write_flash`. Note that if you do this and `--erase`, the NVS region ends up empty (all 0xFFs). Some firmwares seem to not work 100% if you don't flash the matching NVS regions (see below for notes).

### Erase flash

This erases the entire attached flash chip (becomes all 0xFF bytes). The chip will boot its internal mask ROM firmware (shows up as version 0.0.0.1).

```
sudo ./jms567ctl.py -d /dev/sdX erase_flash
```

## Known Issues

* The `reset_chip` step often fails with a SCSI error because the chip has already reset before responding to the SCSI command.
* The `write_flash` command has a footgun with not erasing sectors before writing them. The only workaround is to pass `--erase` and erase the whole chip. PRs to add whatever vendor SCSI command issues "erase sector" or "erase region" commands to the flash are welcome!
* The `pyusb` backend doesn't work very well (see [Accessing via pyusb](#Accessing-via-pyusb)).

## Firmware

In theory, every individual product needs custom firmware and the product vendor will provide updates.

In practice, most product vendors build minor variations on the same few reference designs so firmware can be shared across products. This is particularly useful if you have a product where the vendor only shipped one old and buggy firmware version!

Here are some combinations reported to work, please add more if you find them:

| Firmware                    | SHA256                                                           | Features?                          | Product(s)        |
|-----------------------------|------------------------------------------------------------------|------------------------------------|-------------------|
| JMS567_SSI_v20.06.00.01.bin | b0947f0989b45ca81a56280476dd2f3c7e282681f29b20947f57503262c2af61 | UAS, supports SATA port multiplier | Icybox IB-3640SU3 |

Because the firmware binaries themselves are intellectual property of JMicron and/or the product vendor, they're not distributed here.

*Note: Just because someone reported a random firmware works with their enclosure, does not constitute any guarantee that firmware will work with your enclosure. Nor that it will not catch fire, not permanently damage the enclosure, etc, etc. Use at own risk!*

## Accessing via pyusb

By default the above commands use `py3_sg` to send raw SCSI commands to a disk in the JMS567 device on Linux. There's also a very experimental pyusb backend that you can try to use instead:

```
sudo ./jms567ctl.py -d 152d: erase_flash
```

Where the `-d` arguments are USB PID and optionally VID (i.e. `152d:0567`).

You'll need to make sure no other driver is claiming the USB device first, in Linux you can do this by [unbinding](https://lwn.net/Articles/143397/) the usb_storage or maybe uas driver from the device. It's possible this will also work on Windows by using [Zadig](https://github.com/pbatard/libwdi/wiki/Zadig) or similar to switch drivers to WinUSB or similar. This is untested and unsupported, but I am curious to find out if it works!

I thought supporting direct USB transfers might help when there is no disk attached, but I'd missed that the USB device doesn't enumerate at all in this case - so there's nothing to talk to.

This method did, however, help me run an `erase_flash` on a particular UAS firmware that the official flasher tools refused to recognise. However I'm not able to make this work with every UAS firmware, even after requesting the chip switches back to the USB BOT interface (non-UAS) then it doesn't seem to actually do that. You probably need to reset the chip, and then do something like blacklist it from the UAS driver so it doesn't switch back to UAS when it re-enumeratees.

So yeah, this may not very useful... It might work if it was updated to also encapsulate SCSI commands as UASP rather than only as USB BOT and send those to the UASP USB interface, but UASP is a lot fiddlier so I don't think I can be bothered to do that... PRs welcome!

## Unbricking

The JMS567 seems really simple - if there's an external flash connected then it reads the contents into its SRAM, verifies some kind of checksum[*], then runs the program. If there's no program then it runs a basic firmware from mask ROM.

So you should always be able to unbrick it by erasing the flash, even if somehow it doesn't recognise any of the USB commands then you could program the flash chip directly on the board.

Even simpler, it seems that if you short the flash chip CS pin to ground and then power on, the boot-time verification will fail and it will boot the mask ROM firmware. The ROM firmware can then be used to flash a new firmware over USB.

In general, if using this program or following what you read in this README then you should assume anything is possible - including but not limited to permanent bricking, physical damage, disk catches fire, etc, etc.

[*] I wasn't sure if there even was a checksum, maybe just a watchdog timer, but I changed a random error message string in the middle of the firmware binary(!) and it went back to the mask ROM firmware. So I guess there's a checksum!

## Other technical info I've noticed

The USB flashing protocol is all implemented via custom vendor SCSI opcodes, which is probably the best way to do it really.

I've noticed at least three opcodes in use - `df` for flash-related stuff, `ff` for reset and probably other things, and `e0` for chip info and maybe other things. It's quite possible that the rest of some of these commands is an address and the opcode is to call a subroutine and/or reading arbitrary bytes from memory, I don't know.

The firmware .bin file format for JMS567 seems to be copied 1:1 onto the flash chip, and there's no other data or framing stored in flash or passed in the USB data packets. The file format looks like bare 8051 opcodes, starting with an interrupt vector table at the top (I'm no 8051 expert but `12 xx xx xx` is the `LCALL` opcode with a 3-byte destination address, and `c3 22` is a return opcode, and the first 0x200 bytes of most JMS567 firmware is variations of these opcode sequences spaced 0x10 bytes apart).

There does appear to be a checksum of some kind, probably the two bytes right before the "NVS" section.

The "NVS" section  starts at 0xc000 and is really just another part of the flash. It contains data that's intended for product vendors to customise without JMicron needing to rebuild the firmware binary: USB VID and PID, and some other product-specific values like the [annoying automatic disk spindown feature](https://gbatemp.net/threads/how-to-update-firmware-of-jmicron-jms578-usb3-0-sata-enclosure-black-screen-lock-music-stop.569158/).

In some firmware, including at least one v20.06.00.01 firmware that supports UASP, there is an unknown piece of extra data in the NVS region that's required for the chip to enable UASP at all (the chip offers UASP as an alternate USB Interface, and if the NVS region is erased then this alternate USB interface does not appear). I don't know if this is just a single flag for "be a UAS chip", or if some additional data is stored there...

## Other JMicron chips

There seem to be a bunch of JMicron USB/SATA ICs from the same period that are all basically the same silicon wearing different hats (or, more likely, different packages and mask ROMs). Some firmware binaries for JMS567 contain a bunch of strings referring to JMS569, for example.

That said, I have no idea if this tool will work with any other chips without modifications. Some of the other binary formats look like they might be more sophisticated than just "load vector table from flash address 0x00, jump to firmware".  The USB flashing protocols are probably similar, but if I know consumer silicon vendors then they will have annoying small and arbitrary differences.

One thing that will probably be different is the offset in the .bin file where the "NVS" data lives.
