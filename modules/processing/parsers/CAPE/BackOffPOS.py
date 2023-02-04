from binascii import hexlify
from hashlib import md5
from struct import unpack_from
from sys import argv

import pefile
from Cryptodome.Cipher import ARC4

header_ptrn = b"Content-Type: application/x-www-form-urlencoded"
AUTHOR = "CAPE"
DESCRIPTION = "BackOffPOS configuration parser."


def RC4(key, data):
    cipher = ARC4.new(key)
    return cipher.decrypt(data)


def extract_config(data):
    config_data = {}
    try:
        pe = pefile.PE(data=data)
        for section in pe.sections:
            if b".data" in section.Name:
                data = section.get_data()
                cfg_start = data.find(header_ptrn)
                if not cfg_start or cfg_start == -1:
                    return None
                start_offset = cfg_start + len(header_ptrn) + 1
                rc4_seed = bytes(bytearray(unpack_from(">8B", data, offset=start_offset)))
                key = md5(rc4_seed).digest()[:5]
                enc_data = bytes(bytearray(unpack_from(">8192B", data, offset=start_offset + 8)))
                dec_data = RC4(key, enc_data)
                config_data = {
                    "version": unpack_from(">5s", data, offset=start_offset + 16 + 8192)[0],
                    "encryption": [
                        {
                            "algorithm": "RC4",
                            "key": hexlify(key),
                            "seed": hexlify(rc4_seed),
                            "binaries": [{"data": dec_data[:16].strip("\x00")}],
                            "http": [{"uri": url} for url in [url.strip("\x00") for url in dec_data[16:].split("|")]],
                        }
                    ],
                }
    except pefile.PEFormatError:
        # This isn't a PE file, therefore unlikely to extract a configuration
        pass
    return config_data


if __name__ == "__main__":
    filename = argv[1]
    with open(filename, "rb") as infile:
        t = extract_config(infile.read())
    print(t)
