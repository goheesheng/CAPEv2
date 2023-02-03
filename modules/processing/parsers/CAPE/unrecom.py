import string
import xml.etree.ElementTree as ET
from io import BytesIO, StringIO
from zipfile import BadZipFile, ZipFile

from Cryptodome.Cipher import ARC4


def extract_embedded(zip_data):
    raw_embedded = None
    archive = BytesIO(zip_data) if isinstance(zip_data, bytes) else StringIO(zip_data)
    try:
        with ZipFile(archive) as zip:
            for name in zip.namelist():  # get all the file names
                if name == "load/ID":  # contains first part of key
                    partial_key = zip.read(name)
                    enckey = f"{partial_key}DESW7OWKEJRU4P2K"  # complete key
                if name == "load/MANIFEST.MF":  # this is the embedded jar
                    raw_embedded = zip.read(name)
    except BadZipFile:
        # File is not a zip
        pass
    if raw_embedded is None:
        return None
    # Decrypt the raw file
    return decrypt_arc4(enckey, raw_embedded)


def parse_embedded(data):
    newzipdata = data
    newZip = StringIO(newzipdata)  # Write new zip file to memory instead of to disk
    with ZipFile(newZip) as zip:
        for name in zip.namelist():
            if name == "config.xml":  # this is the config in clear
                config = zip.read(name)
    return config


def decrypt_arc4(key, data):
    cipher = ARC4.new(key)  # set the ciper
    return cipher.decrypt(data)  # decrpyt the data


def parse_config(config):
    xml = [x for x in config if x in string.printable]
    root = ET.fromstring(xml)
    raw_config = {}
    for child in root:
        if child.text.startswith("Unrecom"):
            raw_config["Version"] = child.text
        else:
            raw_config[child.attrib["key"]] = child.text
    return {
        "family": "unrecom",
        "version": raw_config["Version"],
        "sleep_delay": [raw_config["delay"]],
        "password": [raw_config["password"]],
        "paths": [
            {"path": raw_config["pluginfoldername"], "usage": "plugins"},
            {"path": raw_config["install"], "usage": "install"},
        ],
        "other": {
            # Need context around how these are used TCP/HTTP connections
            "Prefix": raw_config["prefix"],
            "Domain": raw_config["dns"],
            "Extension": raw_config["extensionname"],
            "Port1": raw_config["p1"],
            "Port2": raw_config["p2"],
        },
    }


def extract_config(data):
    embedded = extract_embedded(data)
    if embedded is None:
        return None
    config = parse_embedded(embedded)
    return parse_config(config) if config is not None else None
