# Copyright (C) 2021 kevoreilly, enzo
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import struct

import pefile


def extract_config(filebuf):
    cfg = {}
    pe = None
    try:
        pe = pefile.PE(data=filebuf, fast_load=False)
    except Exception:
        pass
    if pe is None:
        return
    for section in pe.sections:
        if section.Name == b".d\x00\x00\x00\x00\x00\x00":
            config_section = bytearray(section.get_data())
            dec = []
            for n, x in enumerate(config_section):
                k = x ^ config_section[n + 64]
                dec.append(k)
                if n > 32:
                    break
            campaign, c2 = struct.unpack("I30s", bytes(dec))
            cfg["family"] = "IcedIDLoader"
            cfg["tcp"] = [{"server_domain": c2.split(b"\00", 1)[0].decode(), "usage": "c2"}]
            cfg["campaign_id"] = campaign
            return cfg


if __name__ == "__main__":
    import sys

    with open(sys.argv[1], "rb") as f:
        print(extract_config(f.read()))
