# Copyright (C) 2010-2015 Cuckoo Foundation.
# This file is part of Cuckoo Sandbox - http://www.cuckoosandbox.org
# See the file 'docs/LICENSE' for copying permission.

# Based on work of Xabier Ugarte-Pedrero
#  https://github.com/Cisco-Talos/pyrebox/blob/python3migration/pyrebox/volatility_glue.py

# Vol3 docs - https://volatility3.readthedocs.io/en/latest/index.html

import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union

from lib.cuckoo.common.abstracts import Processing
from lib.cuckoo.common.config import Config
from lib.cuckoo.common.constants import CUCKOO_ROOT
from lib.cuckoo.common.exceptions import CuckooProcessingError

try:
    import re2 as re
except ImportError:
    import re

try:
    import volatility3.plugins
    import volatility3.symbols
    from volatility3 import framework
    from volatility3.cli.text_renderer import JsonRenderer
    from volatility3.framework import automagic, constants, contexts, interfaces, plugins

    # from volatility3.plugins.windows import pslist
    HAVE_VOLATILITY = True
except ImportError:
    print("Missed dependency: pip3 install volatility3 -U")
    HAVE_VOLATILITY = False

mem_cfg = Config("midmemory")

log = logging.getLogger()
yara_rules_path = os.path.join(CUCKOO_ROOT, "data", "yara", "index_memory.yarc")

# set logger volatility3


class MuteProgress:
    def __init__(self):
        self._max_message_len = 0

    def __call__(self, progress: Union[int, float], description: str = None):
        pass


class ReturnJsonRenderer(JsonRenderer):
    def render(self, grid: interfaces.renderers.TreeGrid):
        final_output = ({}, [])

        def visitor(
            node: Optional[interfaces.renderers.TreeNode],
            accumulator: Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]],
        ) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
            # Nodes always have a path value, giving them a path_depth of at least 1, we use max just in case
            acc_map, final_tree = accumulator
            node_dict = {}
            for column_index, column in enumerate(grid.columns):
                renderer = self._type_renderers.get(column.type, self._type_renderers["default"])
                data = renderer(list(node.values)[column_index])
                node_dict[column.name] = None if isinstance(data, interfaces.renderers.BaseAbsentValue) else data
            if node.parent:
                acc_map[node.parent.path]["__children"].append(node_dict)
            else:
                final_tree.append(node_dict)
            acc_map[node.path] = node_dict
            return (acc_map, final_tree)

        error = grid.populate(visitor, final_output, fail_on_errors=True)
        return final_output[1], error


class VolatilityAPI:
    def __init__(self, memdump):
        """
        @param memdump: path to memdump. Ex. file:///home/vol3/memory.dmp
        """
        self.context = None
        self.automagics = None
        self.base_config_path = "plugins"
        # Instance of the plugin
        self.volatility_interface = None
        self.loaded = False
        self.plugin_list = []
        self.ctx = False
        self.memdump = f"file:///{memdump}" if not memdump.startswith("file:///") and os.path.exists(memdump) else memdump

    def run(self, plugin_class, pids=None, round=1):
        """Module which initialize all volatility 3 internals
        https://github.com/volatilityfoundation/volatility3/blob/stable/doc/source/using-as-a-library.rst
        @param plugin_class: plugin class. Ex. windows.pslist.PsList
        @param plugin_class: plugin class. Ex. windows.pslist.PsList
        @param pids: pid list -> abstrats.py -> get_pids(), for custom scripts
        @param round: read -> https://github.com/volatilityfoundation/volatility3/pull/504
        @return: Volatility3 interface.
        """
        if not self.loaded:
            self.ctx = contexts.Context()
            constants.PARALLELISM = constants.Parallelism.Off
            framework.import_files(volatility3.plugins, True)
            self.automagics = automagic.available(self.ctx)
            self.plugin_list = framework.list_plugins()
            seen_automagics = set()
            # volatility3.symbols.__path__ = [symbols_path] + constants.SYMBOL_BASEPATHS
            for amagic in self.automagics:
                if amagic in seen_automagics:
                    continue
                seen_automagics.add(amagic)

            single_location = self.memdump
            self.ctx.config["automagic.LayerStacker.single_location"] = single_location
            if os.path.exists(yara_rules_path):
                self.ctx.config["plugins.YaraScan.yara_compiled_file"] = f"file:///{yara_rules_path}"

        if pids is not None:
            self.ctx.config["sandbox_pids"] = pids
            self.ctx.config["sandbox_round"] = round

        plugin = self.plugin_list.get(plugin_class)
        try:
            automagics = automagic.choose_automagic(self.automagics, plugin)
            constructed = plugins.construct_plugin(self.ctx, automagics, plugin, "plugins", None, None)
            runned_plugin = constructed.run()
            json_data, error = ReturnJsonRenderer().render(runned_plugin)
            return json_data  # , error
        except AttributeError:
            log.error("Failing %s on %s", plugin_class, self.memdump)
            return {}


""" keeping at the moment to see if we want to integrate more
    {'windows.statistics.Statistics': <class 'volatility3.plugins.windows.statistics.Statistics'>,
    'timeliner.Timeliner': <class 'volatility3.plugins.timeliner.Timeliner'>,
    'windows.pslist.PsList': <class 'volatility3.plugins.windows.pslist.PsList'>,
    'windows.handles.Handles': <class 'volatility3.plugins.windows.handles.Handles'>,
    'windows.poolscanner.PoolScanner': <class 'volatility3.plugins.windows.poolscanner.PoolScanner'>,
    'windows.bigpools.BigPools': <class 'volatility3.plugins.windows.bigpools.BigPools'>,
    'windows.registry.hivescan.HiveScan': <class 'volatility3.plugins.windows.registry.hivescan.HiveScan'>,
    'windows.registry.hivelist.HiveList': <class 'volatility3.plugins.windows.registry.hivelist.HiveList'>,
    'windows.registry.printkey.PrintKey': <class 'volatility3.plugins.windows.registry.printkey.PrintKey'>,
    'windows.registry.certificates.Certificates': <class 'volatility3.plugins.windows.registry.certificates.Certificates'>,
    'banners.Banners': <class 'volatility3.plugins.banners.Banners'>,
    'frameworkinfo.FrameworkInfo': <class 'volatility3.plugins.frameworkinfo.FrameworkInfo'>,
    'yarascan.YaraScan': <class 'volatility3.plugins.yarascan.YaraScan'>,
    'layerwriter.LayerWriter': <class 'volatility3.plugins.layerwriter.LayerWriter'>,
    'isfinfo.IsfInfo': <class 'volatility3.plugins.isfinfo.IsfInfo'>,
    'configwriter.ConfigWriter': <class 'volatility3.plugins.configwriter.ConfigWriter'>,
    'windows.info.Info': <class 'volatility3.plugins.windows.info.Info'>,
    'windows.psscan.PsScan': <class 'volatility3.plugins.windows.psscan.PsScan'>,
    'windows.cmdline.CmdLine': <class 'volatility3.plugins.windows.cmdline.CmdLine'>,
    'windows.envars.Envars': <class 'volatility3.plugins.windows.envars.Envars'>,
    'windows.hashdump.Hashdump': <class 'volatility3.plugins.windows.hashdump.Hashdump'>,
    'windows.lsadump.Lsadump': <class 'volatility3.plugins.windows.lsadump.Lsadump'>,
    'windows.cachedump.Cachedump': <class 'volatility3.plugins.windows.cachedump.Cachedump'>,
    'windows.pstree.PsTree': <class 'volatility3.plugins.windows.pstree.PsTree'>,
    'windows.memmap.Memmap': <class 'volatility3.plugins.windows.memmap.Memmap'>,
    'windows.vadyarascan.VadYaraScan': <class 'volatility3.plugins.windows.vadyarascan.VadYaraScan'>,
    'windows.vadinfo.VadInfo': <class 'volatility3.plugins.windows.vadinfo.VadInfo'>,
    'windows.modules.Modules': <class 'volatility3.plugins.windows.modules.Modules'>,
    'windows.driverscan.DriverScan': <class 'volatility3.plugins.windows.driverscan.DriverScan'>,
    'windows.driverirp.DriverIrp': <class 'volatility3.plugins.windows.driverirp.DriverIrp'>,
    'windows.verinfo.VerInfo': <class 'volatility3.plugins.windows.verinfo.VerInfo'>,
    'windows.symlinkscan.SymlinkScan': <class 'volatility3.plugins.windows.symlinkscan.SymlinkScan'>,
    'windows.strings.Strings': <class 'volatility3.plugins.windows.strings.Strings'>,
    'windows.virtmap.VirtMap': <class 'volatility3.plugins.windows.virtmap.VirtMap'>,
    'windows.dumpfiles.DumpFiles': <class 'volatility3.plugins.windows.dumpfiles.DumpFiles'>,
    'windows.filescan.FileScan': <class 'volatility3.plugins.windows.filescan.FileScan'>,
    'windows.getservicesids.GetServiceSIDs': <class 'volatility3.plugins.windows.getservicesids.GetServiceSIDs'>,
    'windows.svcscan.SvcScan': <class 'volatility3.plugins.windows.svcscan.SvcScan'>,
    'windows.registry.userassist.UserAssist': <class 'volatility3.plugins.windows.registry.userassist.UserAssist'>,
"""


class VolatilityManager:
    """Handle several volatility results."""

    def __init__(self, memfile):
        self.mask_pid = []
        self.taint_pid = set()
        self.memfile = memfile

        conf_path = os.path.join(CUCKOO_ROOT, "conf", "midmemory.conf")
        if not os.path.exists(conf_path):
            log.error("Configuration file midmemory.conf not found")
            self.voptions = False
            return

        self.voptions = Config("midmemory")

        if isinstance(self.voptions.mask.pid_generic, int):
            self.mask_pid.append(self.voptions.mask.pid_generic)
        else:
            for pid in self.voptions.mask.pid_generic.split(","):
                pid = pid.strip()
                if pid:
                    self.mask_pid.append(int(pid))

        self.no_filter = not self.voptions.mask.enabled

    def run(self, manager=None, vm=None):
        results = {}
        self.key = "midmemory"

        # Exit if options were not loaded.
        if not self.voptions:
            return

        vol3 = VolatilityAPI(self.memfile)
        """
        if self.voptions.idt.enabled:
            try:
                results["idt"] = vol.idt()
            except Exception:
                pass
        if self.voptions.gdt.enabled:
            try:
                results["gdt"] = vol.gdt()
            except Exception:
                pass
        if self.voptions.timers.enabled:
            results["timers"] = vol.timers()
        if self.voptions.messagehooks.enabled:
            results["messagehooks"] = vol.messagehooks()
        if self.voptions.apihooks.enabled:
            results["apihooks"] = vol.apihooks()
        if self.voptions.ldrmodules.enabled:
            results["ldrmodules"] = vol.ldrmodules()
        if self.voptions.devicetree.enabled:
            results["devicetree"] = vol.devicetree()
        """
        vol_logger = logging.getLogger("volatility3")
        vol_logger.setLevel(logging.WARNING)

        # if self.voptions.psxview.enabled:
        #    results["pstree"] = vol3.run("windows.pstree.PsTree")
        if self.voptions.pslist.enabled:
            results["pslist"] = vol3.run("windows.pslist.PsList")
        if self.voptions.callbacks.enabled:
            results["callbacks"] = vol3.run("windows.callbacks.Callbacks")
        if self.voptions.ssdt.enabled:
            results["ssdt"] = vol3.run("windows.ssdt.SSDT")
        if self.voptions.getsids.enabled:
            results["getsids"] = vol3.run("windows.getsids.GetSIDs")
        if self.voptions.privs.enabled:
            results["privs"] = vol3.run("windows.privileges.Privs")
        if self.voptions.malfind.enabled:
            results["malfind"] = vol3.run("windows.malfind.Malfind")
        if self.voptions.dlllist.enabled:
            results["dlllist"] = vol3.run("windows.dlllist.DllList")
        if self.voptions.handles.enabled:
            results["handles"] = vol3.run("windows.handles.Handles")
        if self.voptions.mutantscan.enabled:
            results["mutantscan"] = vol3.run("windows.mutantscan.MutantScan")
        if self.voptions.svcscan.enabled:
            results["svcscan"] = vol3.run("windows.svcscan.SvcScan")
        if self.voptions.modscan.enabled:
            results["modscan"] = vol3.run("windows.modscan.ModScan")
        if self.voptions.yarascan.enabled:
            results["yarascan"] = vol3.run("yarascan.YaraScan")
        if self.voptions.netscan.enabled:
            results["netscan"] = vol3.run("windows.netscan.NetScan")

        self.find_taint(results)

        self.do_strings()
        self.cleanup()

        if not self.voptions.basic.delete_memdump:
            results["memory_path"] = self.memfile
        if self.voptions.basic.dostrings:
            results["memory_strings_path"] = f"{self.memfile}.strings"

        return results

    def find_taint(self, res):
        """Find tainted items."""
        if "malfind" in res:
            for item in res["malfind"]:
                self.taint_pid.add(item["PID"])

    def do_strings(self):
        if not self.voptions.basic.dostrings:
            return None
        try:
            with open(self.memfile, "rb") as f:
                data = f.read()
        except (IOError, OSError, MemoryError) as e:
            raise CuckooProcessingError(f"Error opening file {e}") from e

        nulltermonly = self.voptions.basic.get("strings_nullterminated_only", True)
        minchars = str(self.voptions.basic.get("strings_minchars", 5)).encode()

        if nulltermonly:
            apat = b"([\x20-\x7e]{" + minchars + b",})\x00"
            upat = b"((?:[\x20-\x7e][\x00]){" + minchars + b",})\x00\x00"
        else:
            apat = b"[\x20-\x7e]{" + minchars + b",}"
            upat = b"(?:[\x20-\x7e][\x00]){" + minchars + b",}"

        strings = re.findall(apat, data) + [ws.decode("utf-16le").encode() for ws in re.findall(upat, data)]
        with open(f"{self.memfile}.strings", "wb") as f:
            f.write(b"\n".join(strings))
        return f"{self.memfile}.strings"

    def cleanup(self):
        """Delete the memory dump (if configured to do so)."""

        if self.voptions.basic.delete_memdump:
            for memfile in (self.memfile, f"{self.memfile}.zip"):
                if os.path.exists(memfile):
                    try:
                        os.remove(memfile)
                    except OSError:
                        log.error('Unable to delete memory dump file at path "%s"', memfile)


class MidMemory(Processing):
    """Volatility Analyzer."""

    def run(self):
        """Run analysis.
        @return: volatility results dict.
        """
        self.key = "midmemory"
        self.voptions = mem_cfg

        results = {}
        if not HAVE_VOLATILITY:
            log.error("Cannot run volatility module: volatility library not available")
            return results

        self.midmemory_path = os.path.join(CUCKOO_ROOT, "storage", "analyses", str(self.task["id"]), "midmemory.dmp")
        if os.path.exists(self.midmemory_path):
            try:
                vol = VolatilityManager(self.midmemory_path)
                results = vol.run()
            except Exception:
                log.exception("Generic error executing volatility")
                if self.voptions.basic.delete_memdump_on_exception:
                    try:
                        os.remove(self.midmemory_path)
                    except OSError:
                        log.error('Unable to delete memory dump file at path "%s"', self.midmemory_path)
        else:
            log.error("Memory dump not found: to run volatility you have to enable midmemory_dump")

        return results