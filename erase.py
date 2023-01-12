#!/usr/bin/env python3
import usb.core
import usb.util

# write 0x1f bytes to interface id 0, endpoint 0x02 (OUT BULK)

# then read 13 bytes from interface id 0x81


def main():
    # find our device
    dev = usb.core.find(idVendor=0x152D)

    if dev is None:
        raise ValueError("Device not found")

    dev.set_configuration()  # set first configuration

    # get an endpoint instance
    cfg = dev.get_active_configuration()
    intf = cfg[(0, 0)]

    ep_out = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
        == usb.util.ENDPOINT_OUT,
    )

    ep_in = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
        == usb.util.ENDPOINT_IN,
    )

    # should be 0x02 / 0x81
    print(
        f"Endpoint addresses {ep_out.bEndpointAddress:#x} / {ep_in.bEndpointAddress:#x}"
    )

    cmd = bytes.fromhex(
        "55534243104036a80000000000000cff" + "04264a4d0000000000000000000000"
    )
    print(f"Sending {len(cmd)} bytes: {cmd.hex()} | {cmd}...")
    ep_out.write(cmd)

    res = ep_in.read(13).tobytes()

    print(f"Response {len(res)} bytes: {res.hex()} | {res}")


if __name__ == "__main__":
    main()
