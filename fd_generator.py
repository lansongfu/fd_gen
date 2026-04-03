#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FD Generator - SoC Feedthrough Auto Generation Tool

This tool automatically detects signals requiring feedthrough (FD) and generates
intermediate FD modules based on floorplan adjacency.

Usage:
    python fd_generator.py -top <top.v> -floorplan <adjacency.txt> [-output fd_output/] [-maxfdnum 3]
    python fd_generator.py -top <top.v> -floorplan <adjacency.txt> -link [-autocase] [-waive waive.txt] [-only only.txt]

Author: Konoha Ninja (Crow)
Version: 1.1.13

Changelog:
  v1.1.13 (2026-04-03) - CONNECT Alignment Fix Release
    - Fix: CONNECT alignment format with wrong comma positions
      * Changed padding from before comma to after field (left-align fields)
      * Format: field + padding + ", " + next_field
      * Result: All commas now at fixed column positions
    - Test: BFS stability 10/10 runs identical
    - Test: Full test suite 6/6 passed (100%)

  v1.1.2 (2026-04-03) - Modify Bug Fix Release
    - Fix: CONNECT modify regex not matching bit-select wires (e.g., ab2[2:0])
      * Changed regex from (\w+) to ([\w\[\]:]+) to support bit-select format
      * Added base wire matching logic for bit-select wires
    - Fix: CONNECT scan stopping at empty lines/comments
      * Now skips empty lines and comments between CONNECT lines
      * Continues scanning until non-CONNECT content found
    - Fix: Test script FD_GEN path pointing to wrong location
      * Changed from tests/fd_generator.py to fd_generator.py
    - Test: 6/6 tests passed (100% pass rate)
  
  v1.1.1 (2026-04-03) - Bug Fix Release
    - Fix: One-to-many signal FD module original connection bug (ata signal)
      * Issue: For TOP input signals (e.g., ata: TOP->A/B/C/D/E), when only some paths need FD
        (e.g., TOP->A via B), B module's original ata connection was incorrectly modified to
        fd_from_b_ata instead of keeping original name 'ata'
      * Fix: In generate_fd_top(), correctly identify source module based on conn_type,
        only modify true source module's connects, don't modify FD module's original connects
      * Test: All B/C/D/E modules' original ata connections now correctly remain 'ata'
    - Fix: Waive modules not checked during FD module generation
      * FD modules now skip waived modules
      * Paths correctly reroute around waived modules
    - Fix: Only modules not checked during FD module generation
      * FD modules now only include modules in only list
    - Fix: _find_path_to_top and _find_path_from_top not filtering only_modules
      * Added valid_top_adjacent filtering in both functions
    - Test: 11/11 tests passed (100% pass rate)
  
  v1.1.0 (2026-04-02)
    - Fix: fd_top.v INSTANCE regex pattern causing modify failure
    - Fix: Skip bidirectional signals (direction='b') from FD processing
    - Fix: TOP module support - properly handle is_top connections
    - Add: -link parameter to generate fd_top.v with updated CONNECT comments
    - Add: -waive parameter to exclude modules from FD routing
    - Add: -only parameter to whitelist modules for FD routing
    - Add: -autocase parameter to preserve signal case in port names
    - Add: Multi-driver detection (skip signals with multiple outputs)
    - Fix: FD module filenames now lowercase (fd_module1.v)
    - Fix: FD port naming format (fd_from_<module>_<signal>)
  
  v1.0.0 (2026-04-01)
    - Initial release
    - Core FD detection and module generation
    - BFS shortest path with caching
    - Path report generation
"""

from __future__ import print_function
import argparse
import os
import sys
import re
import logging
from collections import defaultdict
from datetime import datetime

# ============================================================================
# Global Configuration
# ============================================================================

VERSION = "1.1.1"
DEFAULT_OUTPUT_DIR = "fd_output"
DEFAULT_MAX_FD_NUM = 3

# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging(output_dir):
    """Setup logging to both file and console."""
    log_file = os.path.join(output_dir, "fd_generator.log")
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# ============================================================================
# Data Structures
# ============================================================================

class SignalConnection:
    """Represents a signal connection between modules."""
    def __init__(self, signal_name, module_name, port_name, width, direction, is_top=False, conn_type=None):
        self.signal_name = signal_name
        self.module_name = module_name
        self.port_name = port_name
        self.width = width
        self.direction = direction  # 'i', 'o', 'b'
        self.is_top = is_top  # True if connected to top-level
        self.conn_type = conn_type  # 'i', 'o', 'b', 'w' - original CONNECT type
    
    def __repr__(self):
        return "SignalConnection({}, {}, {}, {}, {}, type={})".format(
            self.signal_name, self.module_name, self.port_name, 
            self.width, self.direction, self.conn_type
        )


class ModuleInfo:
    """Represents a module instance."""
    def __init__(self, module_name, instance_name):
        self.module_name = module_name
        self.instance_name = instance_name
    
    def __repr__(self):
        return "ModuleInfo({}, {})".format(self.module_name, self.instance_name)


class FDPort:
    """Represents an FD module port."""
    def __init__(self, signal_name, from_module, to_module, width, is_bidir=False, autocase=False):
        self.signal_name = signal_name
        self.from_module = from_module
        self.to_module = to_module
        self.width = width
        self.is_bidir = is_bidir
        self.autocase = autocase
    
    def get_port_key(self):
        """Generate unique key for deduplication."""
        case_style = get_case_style(self.signal_name, self.autocase)
        if self.is_bidir:
            if case_style == 'upper':
                return "FD_FROM_{}_{}".format(
                    self.from_module.upper(), self.signal_name.upper()
                )
            else:
                return "fd_from_{}_{}".format(
                    self.from_module.lower(), self.signal_name.lower()
                )
        else:
            if case_style == 'upper':
                return [
                    "FD_FROM_{}_{}".format(
                        self.from_module.upper(), self.signal_name.upper()
                    ),
                    "FD_TO_{}_{}".format(
                        self.to_module.upper(), self.signal_name.upper()
                    )
                ]
            else:
                return [
                    "fd_from_{}_{}".format(
                        self.from_module.lower(), self.signal_name.lower()
                    ),
                    "fd_to_{}_{}".format(
                        self.to_module.lower(), self.signal_name.lower()
                    )
                ]


class FDModule:
    """Represents an FD module to be generated."""
    def __init__(self, module_name):
        self.module_name = module_name
        self.ports = []  # List of FDPort
        self._port_keys = set()  # For deduplication
    
    def add_port(self, port):
        """Add port with deduplication."""
        key = port.get_port_key()
        if isinstance(key, list):
            # Unidirectional: check both from and to ports
            for k in key:
                if k in self._port_keys:
                    return  # Skip duplicate
                self._port_keys.add(k)
        else:
            # Bidirectional: check single key
            if key in self._port_keys:
                return  # Skip duplicate
            self._port_keys.add(key)
        
        self.ports.append(port)


class PathSegment:
    """Represents a segment in the FD path."""
    def __init__(self, module_name, port_name):
        self.module_name = module_name
        self.port_name = port_name
    
    def __str__(self):
        return "{}.{}".format(self.module_name, self.port_name)

# ============================================================================
# Parser
# ============================================================================

def parse_floorplan(floorplan_file, logger):
    """
    Parse floorplan file to build adjacency list.
    
    Format:
        MODULE1 MODULE2 MODULE3
        MODULE2 MODULE1 MODULE3
    
    Returns:
        dict: {module_name: set(adjacent_modules)}
    """
    logger.info("Parsing floorplan: {}".format(floorplan_file))
    
    adjacency = defaultdict(list)
    
    with open(floorplan_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Split by whitespace (supports multiple spaces)
            parts = line.split()
            if len(parts) < 2:
                logger.warning("Line {}: Invalid format, skipping".format(line_num))
                continue
            
            module_name = parts[0]
            adjacent_modules = parts[1:]
            
            # Add bidirectional relationships (with deduplication)
            for adj in adjacent_modules:
                if adj not in adjacency[module_name]:
                    adjacency[module_name].append(adj)
                if module_name not in adjacency[adj]:
                    adjacency[adj].append(module_name)
    
    # Sort all adjacency lists for deterministic BFS traversal
    for module in adjacency:
        adjacency[module] = sorted(adjacency[module])
    
    logger.info("Floorplan parsed: {} modules".format(len(adjacency)))
    return dict(adjacency)


def parse_top_file(top_file, logger):
    """
    Parse top.v file to extract INSTANCE and CONNECT information.
    
    Only processes content between:
        // ------------ begin SOC_IGT comment list ------------//
        // ------------ end SOC_IGT comment list ------------//
    
    Returns:
        tuple: (modules_dict, connections_list)
            modules_dict: {module_name: ModuleInfo}
            connections_list: [SignalConnection]
    """
    logger.info("Parsing top file: {}".format(top_file))
    
    modules = {}
    connections = []
    
    in_comment_block = False
    
    with open(top_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Check for comment block start/end
            if 'begin SOC_IGT comment list' in line:
                in_comment_block = True
                logger.debug("Found SOC_IGT comment block start at line {}".format(line_num))
                continue
            elif 'end SOC_IGT comment list' in line:
                in_comment_block = False
                logger.debug("Found SOC_IGT comment block end at line {}".format(line_num))
                continue
            
            if not in_comment_block:
                continue
            
            # Parse INSTANCE line
            if line.startswith('//INSTANCE('):
                module_info = parse_instance(line, line_num, logger)
                if module_info:
                    modules[module_info.module_name] = module_info
            
            # Parse CONNECT line
            elif line.startswith('//CONNECT('):
                conn_list = parse_connect(line, line_num, logger)
                connections.extend(conn_list)
    
    logger.info("Top file parsed: {} modules, {} connections".format(
        len(modules), len(connections)
    ))
    
    return modules, connections


def parse_instance(line, line_num, logger):
    """
    Parse INSTANCE line.
    
    Format: //INSTANCE(../path/to/file.v, MODULE_NAME, U_MODULE_NAME);
    
    Returns:
        ModuleInfo or None
    """
    try:
        # Extract content between parentheses
        match = re.search(r'//INSTANCE\((.*?)\);', line)
        if not match:
            logger.warning("Line {}: Invalid INSTANCE format".format(line_num))
            return None
        
        content = match.group(1)
        parts = [p.strip() for p in content.split(',')]
        
        if len(parts) < 3:
            logger.warning("Line {}: INSTANCE requires 3 parts".format(line_num))
            return None
        
        # parts[0] = source file (ignore)
        # parts[1] = module definition name
        # parts[2] = instance name
        module_name = parts[1]
        instance_name = parts[2]
        
        return ModuleInfo(module_name, instance_name)
    
    except Exception as e:
        logger.warning("Line {}: Error parsing INSTANCE: {}".format(line_num, e))
        return None


def parse_connect(line, line_num, logger):
    """
    Parse CONNECT line.
    
    Format: //CONNECT(type, wire_name[range], U_MODULE`port, width, direction);
    
    Returns:
        list of SignalConnection (may be multiple if signal is concatenated)
    """
    connections = []
    
    try:
        # Extract content between parentheses
        match = re.search(r'//CONNECT\((.*?)\);', line)
        if not match:
            logger.warning("Line {}: Invalid CONNECT format".format(line_num))
            return connections
        
        content = match.group(1)
        parts = split_connect_parts(content)
        
        if len(parts) < 5:
            logger.warning("Line {}: CONNECT requires 5 parts".format(line_num))
            return connections
        
        conn_type = parts[0].strip()
        wire_name = parts[1].strip()
        module_port = parts[2].strip()
        width_str = parts[3].strip()
        direction = parts[4].strip()
        
        # Parse width
        try:
            width = int(width_str)
        except ValueError:
            logger.warning("Line {}: Invalid width '{}'".format(line_num, width_str))
            width = 1
        
        # Parse module and port name
        module_name, port_name = parse_module_port(module_port, logger)
        if not module_name:
            return connections
        
        # Check if this is a top-level connection
        is_top = conn_type in ['i', 'o', 'b']
        
        # Handle concatenated signals: {sig1[3:2],sig2}
        if wire_name.startswith('{') and wire_name.endswith('}'):
            # Parse concatenated signals
            concat_signals = parse_concatenated_signals(wire_name[1:-1], logger)
            for sig_name, sig_width in concat_signals:
                connections.append(SignalConnection(
                    signal_name=sig_name,
                    module_name=module_name,
                    port_name=port_name,
                    width=width,  # Use declared width from CONNECT
                    direction=direction,
                    is_top=is_top,
                    conn_type=conn_type
                ))
        elif wire_name and not wire_name.startswith("'"):
            # Regular signal (not empty, not fixed value)
            # Extract signal name from bit selection
            sig_name, _ = parse_signal_name(wire_name)
            if sig_name:
                connections.append(SignalConnection(
                    signal_name=sig_name,
                    module_name=module_name,
                    port_name=port_name,
                    width=width,  # Use declared width from CONNECT
                    direction=direction,
                    is_top=is_top,
                    conn_type=conn_type
                ))
        
        return connections
    
    except Exception as e:
        logger.warning("Line {}: Error parsing CONNECT: {}".format(line_num, e))
        return connections


def split_connect_parts(content):
    """Split CONNECT content by comma, respecting nested parentheses and braces."""
    parts = []
    current = ""
    depth = 0
    
    for char in content:
        if char in '({':
            depth += 1
            current += char
        elif char in ')}':
            depth -= 1
            current += char
        elif char == ',' and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    
    if current:
        parts.append(current)
    
    return parts


def parse_module_port(module_port_str, logger):
    """
    Parse module`port string.
    
    Format: U_MODULE_NAME`port_name
    
    Returns:
        tuple: (module_name_without_U_, port_name)
    """
    if '`' not in module_port_str:
        logger.warning("Invalid module`port format: {}".format(module_port_str))
        return None, None
    
    parts = module_port_str.split('`')
    if len(parts) != 2:
        logger.warning("Invalid module`port format: {}".format(module_port_str))
        return None, None
    
    module_name = parts[0]
    port_name = parts[1]
    
    # Remove U_ prefix if present
    if module_name.startswith('U_'):
        module_name = module_name[2:]
    
    return module_name, port_name


def parse_concatenated_signals(concat_str, logger):
    """
    Parse concatenated signals: sig1[3:2],sig2,sig3[7:0]
    
    Returns:
        list of tuples: [(signal_name, width), ...]
    """
    signals = []
    parts = concat_str.split(',')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        sig_name, sig_width = parse_signal_name(part)
        if sig_name:
            signals.append((sig_name, sig_width))
    
    return signals


def parse_signal_name(wire_name):
    """
    Parse signal name and extract width from bit selection.
    
    Examples:
        wire1 -> (wire1, 1)
        wire1[31:0] -> (wire1, 32)
        wire1[3:2] -> (wire1, 2)
        wire1[7] -> (wire1, 1)
    
    Returns:
        tuple: (signal_name, width)
    """
    # Check for bit selection
    match = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)(?:\[(\d+)(?::(\d+))?\])?', wire_name)
    if not match:
        return None, 1
    
    sig_name = match.group(1)
    if match.group(2):  # Has bit selection
        msb = int(match.group(2))
        if match.group(3):  # Range [msb:lsb]
            lsb = int(match.group(3))
            width = abs(msb - lsb) + 1
        else:  # Single bit [bit]
            width = 1
    else:
        width = 1
    
    return sig_name, width


def get_case_style(signal_name, autocase=False):
    """
    Determine case style for FD port naming.
    
    Args:
        signal_name: original signal name
        autocase: if True, preserve case based on signal; if False, always lowercase
    
    Returns:
        'upper' if autocase enabled and signal is all uppercase or mixed case
        'lower' otherwise
    """
    if not autocase:
        # Default: always lowercase
        return 'lower'
    else:
        # autocase enabled: preserve case based on signal
        if signal_name.islower():
            return 'lower'
        else:
            # All uppercase or mixed case -> use uppercase
            return 'upper'

# ============================================================================
# BFS Algorithm with Caching
# ============================================================================

class BFSCache:
    """Cache for BFS shortest path results."""
    
    def __init__(self):
        self.cache = {}
    
    def _make_key(self, src, dst):
        """Create ordered key for module pair (direction matters!)."""
        return (src, dst)
    
    def get(self, src, dst):
        """Get cached path if exists."""
        key = self._make_key(src, dst)
        return self.cache.get(key)
    
    def set(self, src, dst, path):
        """Cache a path."""
        key = self._make_key(src, dst)
        self.cache[key] = path


def bfs_shortest_path(adjacency, src, dst, cache, waive_modules=None, only_modules=None):
    """
    Find shortest path between src and dst modules using BFS.
    
    Args:
        adjacency: dict {module: set(adjacent_modules)}
        src: source module name
        dst: destination module name
        cache: BFSCache instance
        waive_modules: set of modules to exclude from routing
        only_modules: set of modules allowed for routing
    
    Returns:
        list: [src, intermediate1, intermediate2, ..., dst] or None if no path
    """
    if waive_modules is None:
        waive_modules = set()
    if only_modules is None:
        only_modules = set()
    
    # Check cache first
    cached_path = cache.get(src, dst)
    if cached_path is not None:
        return cached_path[:] if cached_path else None
    
    # BFS
    if src == dst:
        cache.set(src, dst, [src])
        return [src]
    
    if src not in adjacency or dst not in adjacency:
        cache.set(src, dst, None)
        return None
    
    visited = set([src])
    queue = [(src, [src])]
    
    while queue:
        current, path = queue.pop(0)
        
        # Neighbors are already sorted in parse_floorplan
        for neighbor in adjacency.get(current, []):
            # Skip TOP module (cannot place FD on TOP)
            if neighbor == 'TOP':
                continue
            
            # Skip waived modules (but allow src/dst even if waived)
            if neighbor in waive_modules and neighbor != src and neighbor != dst:
                continue
            
            # Skip modules not in only list (but allow src/dst even if not in only)
            if only_modules and neighbor not in only_modules and neighbor != src and neighbor != dst:
                continue
            
            if neighbor == dst:
                result = path + [neighbor]
                cache.set(src, dst, result)
                return result
            
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    
    # No path found
    cache.set(src, dst, None)
    return None


def _find_path_to_top(adjacency, src_module, cache, waive_modules, only_modules):
    """
    Find path from src_module to TOP.
    
    TOP is a virtual module - signals reach TOP through adjacent submodules.
    This function finds the shortest path from src_module to any TOP-adjacent module,
    then appends TOP to the path.
    
    Args:
        adjacency: floorplan adjacency dict
        src_module: source module name
        cache: BFSCache instance
        waive_modules: set of modules to exclude
        only_modules: set of modules allowed for routing
    
    Returns:
        list: path ending with 'TOP', or None if no path
    """
    top_adjacent = adjacency.get('TOP', [])
    
    # Filter top_adjacent by waive_modules and only_modules
    valid_top_adjacent = []
    for adj_module in top_adjacent:
        if adj_module in waive_modules:
            continue
        if only_modules and adj_module not in only_modules:
            continue
        valid_top_adjacent.append(adj_module)
    
    # Check if src_module is directly adjacent to TOP (via valid adjacent module)
    if src_module in valid_top_adjacent:
        return [src_module, 'TOP']
    
    # Check if src_module is adjacent to any valid TOP-adjacent module (1 intermediate)
    for adj_module in valid_top_adjacent:
        if adj_module in adjacency.get(src_module, []):
            return [src_module, adj_module, 'TOP']
    
    # BFS to find path to any valid TOP-adjacent module
    for adj_module in valid_top_adjacent:
        if adj_module == src_module:
            continue
        path = bfs_shortest_path(adjacency, src_module, adj_module, cache, waive_modules, only_modules)
        if path:
            return path + ['TOP']
    
    return None


def _find_path_from_top(adjacency, dst_module, cache, waive_modules, only_modules):
    """
    Find path from TOP to dst_module.
    
    TOP is a virtual module - signals originate from TOP through adjacent submodules.
    This function finds the shortest path from any TOP-adjacent module to dst_module,
    then prepends TOP to the path.
    
    Args:
        adjacency: floorplan adjacency dict
        dst_module: destination module name
        cache: BFSCache instance
        waive_modules: set of modules to exclude
        only_modules: set of modules allowed for routing
    
    Returns:
        list: path starting with 'TOP', or None if no path
    """
    top_adjacent = adjacency.get('TOP', [])
    
    # Filter top_adjacent by waive_modules and only_modules
    valid_top_adjacent = []
    for adj_module in top_adjacent:
        if adj_module in waive_modules:
            continue
        if only_modules and adj_module not in only_modules:
            continue
        valid_top_adjacent.append(adj_module)
    
    # Check if dst_module is directly adjacent to TOP (via valid adjacent module)
    if dst_module in valid_top_adjacent:
        return ['TOP', dst_module]
    
    # Check if dst_module is adjacent to any valid TOP-adjacent module (1 intermediate)
    for adj_module in valid_top_adjacent:
        if adj_module in adjacency.get(dst_module, []):
            return ['TOP', adj_module, dst_module]
    
    # BFS to find path from any valid TOP-adjacent module
    for adj_module in valid_top_adjacent:
        if adj_module == dst_module:
            continue
        path = bfs_shortest_path(adjacency, adj_module, dst_module, cache, waive_modules, only_modules)
        if path:
            return ['TOP'] + path
    
    return None


# ============================================================================
# FD Detection and Generation
# ============================================================================

def _process_single_path(src_module, dst_module, signal_name, width, case_style,
                         adjacency, cache, waive_modules, only_modules,
                         fd_modules, fd_signals, path_report_lines, errors,
                         max_fd_num, connections, logger, is_bidir=False):
    """
    Process a single source-to-destination path for a signal.
    
    Handles FD module generation and path report for one connection.
    """
    # Check if adjacent (no FD needed)
    if dst_module in adjacency.get(src_module, []):
        return  # Direct connection, no FD needed
    
    # Find path based on whether TOP is involved
    if dst_module == 'TOP':
        path = _find_path_to_top(adjacency, src_module, cache, waive_modules, only_modules)
    elif src_module == 'TOP':
        path = _find_path_from_top(adjacency, dst_module, cache, waive_modules, only_modules)
    else:
        path = bfs_shortest_path(adjacency, src_module, dst_module, cache, waive_modules, only_modules)
    
    if path is None:
        error_msg = "No path found between {} and {} for signal {}".format(
            src_module, dst_module, signal_name
        )
        logger.error(error_msg)
        errors.append(error_msg)
        return
    
    # Intermediate modules are all modules between src and dst (excluding endpoints)
    # path = [src, int1, int2, ..., dst]
    # intermediate_modules = [int1, int2, ...]
    intermediate_modules = path[1:-1]  # Exclude start (path[0]) and end (path[-1])
    
    if len(intermediate_modules) > max_fd_num:
        error_msg = "Path too long for signal {}: {} intermediate modules (max {})".format(
            signal_name, len(intermediate_modules), max_fd_num
        )
        logger.error(error_msg)
        errors.append(error_msg)
        return
    
    # Generate FD modules for intermediate modules
    for fd_module_name in intermediate_modules:
        # Skip waived modules
        if fd_module_name in waive_modules:
            logger.info("Signal '{}': skipping FD module {} (waived)".format(signal_name, fd_module_name))
            continue
        
        # Skip modules not in only list
        if only_modules and fd_module_name not in only_modules:
            logger.info("Signal '{}': skipping FD module {} (not in only list)".format(signal_name, fd_module_name))
            continue
        
        if fd_module_name not in fd_modules:
            fd_modules[fd_module_name] = FDModule(fd_module_name)
        
        # Determine from/to based on path order
        # path = [src, int1, int2, ..., dst]
        # For FD module at position idx in intermediate_modules:
        #   receives from path[idx], sends to path[idx+2]
        idx = intermediate_modules.index(fd_module_name)
        from_module = path[idx]  # Module before this FD module
        to_module = path[idx + 2]  # Module after this FD module
        
        fd_port = FDPort(
            signal_name=signal_name,
            from_module=from_module,
            to_module=to_module,
            width=width,
            is_bidir=is_bidir,
            autocase=False  # Use global autocase setting if needed
        )
        fd_modules[fd_module_name].add_port(fd_port)
    
    # Build path report line
    path_line = build_path_line(
        signal_name, path, intermediate_modules,
        case_style, is_bidir, connections, logger
    )
    path_report_lines.append(path_line)
    
    fd_signals.append({
        'signal': signal_name,
        'width': width,
        'from': src_module,
        'to': dst_module,
        'path': path,
        'case_style': case_style,
        'is_bidir': is_bidir
    })


def detect_fd_signals(connections, adjacency, max_fd_num, logger, waive_modules=None, autocase=False, only_modules=None):
    """
    Detect signals requiring FD and compute paths.
    
    Args:
        connections: list of SignalConnection
        adjacency: floorplan adjacency dict
        max_fd_num: maximum allowed intermediate modules
        logger: logger instance
        waive_modules: set of modules to exclude from FD routing
        autocase: whether to preserve signal case in port names
        only_modules: set of modules allowed for FD routing
    
    Returns:
        tuple: (fd_signals, fd_modules, path_report_lines, errors)
            fd_signals: list of signals requiring FD
            fd_modules: dict {module_name: FDModule}
            path_report_lines: list of path strings for report
            errors: list of error messages
    """
    logger.info("Detecting FD signals...")
    
    if waive_modules is None:
        waive_modules = set()
    if only_modules is None:
        only_modules = set()
    
    # Group connections by signal name
    # Include is_top connections - they indicate signals that need to reach TOP
    signal_groups = defaultdict(list)
    for conn in connections:
        signal_groups[conn.signal_name].append(conn)
    
    fd_signals = []
    fd_modules = {}  # {module_name: FDModule}
    path_report_lines = []
    errors = []
    
    cache = BFSCache()
    
    for signal_name, conns in signal_groups.items():
        # Check for top-level signals (only one connection, other end is TOP)
        has_top_input = any(c.conn_type == 'i' for c in conns)
        has_top_output = any(c.conn_type == 'o' for c in conns)
        
        if len(conns) < 2:
            # Single connection: only process if it's a top-level signal
            if has_top_input or has_top_output:
                pass  # Continue processing
            else:
                continue  # Need at least 2 connections for module-to-module signals
        
        # Skip bidirectional signals (direction='b')
        # Design Decision (v1.1.0): Bidirectional signals are completely ignored.
        # Reason: Bidirectional signals require tri-state buffer handling, which is
        #         beyond the scope of this FD tool. User should handle these manually.
        # Reference: REQUIREMENTS.md - Boundary Cases - Bidirectional Signals
        if any(c.direction == 'b' for c in conns):
            logger.info("Signal '{}': bidirectional signal, skipping FD (per v1.1.0 design decision).".format(signal_name))
            continue
        
        # Check for multi-driver (multiple outputs, excluding TOP connections)
        output_conns = [c for c in conns if c.direction == 'o' and not c.is_top]
        if len(output_conns) > 1:
            error_msg = "Signal '{}': multi-driver detected ({} outputs: {}). Skipping.".format(
                signal_name, len(output_conns), ', '.join([c.module_name for c in output_conns])
            )
            logger.error(error_msg)
            errors.append(error_msg)
            continue  # Skip this signal
        
        # Determine case style from signal name
        case_style = get_case_style(signal_name)
        
        # Get width (use first connection's width) and check consistency
        # Note: Use first CONNECT's declared width as the reference
        width = conns[0].width
        width_mismatch = False
        has_severe_mismatch = False
        for conn in conns[1:]:
            if conn.width != width:
                width_mismatch = True
                # Check if width difference is severe (>4x)
                if max(width, conn.width) > min(width, conn.width) * 4:
                    has_severe_mismatch = True
                    error_msg = "Signal '{}': severe width mismatch - declared {} vs {} at module {} (difference >4x). Skipping.".format(
                        signal_name, width, conn.width, conn.module_name
                    )
                    logger.error(error_msg)
                    errors.append(error_msg)
                else:
                    logger.warning("Signal '{}': width mismatch - declared {} vs {} at module {}".format(
                        signal_name, width, conn.width, conn.module_name
                    ))
        
        # Skip signal if severe width mismatch
        if has_severe_mismatch:
            continue
        
        # All signals reaching here are unidirectional (not bidirectional)
        is_bidir = False
        
        # Identify source and sink modules for this signal using conn_type and direction
        # For conn_type='i' (top input): TOP is source, submodules are sinks
        # For conn_type='o' (top output): submodules are sources, TOP is sink
        # For conn_type='w' (wire): direction='o' is source, direction='i' is sink
        
        top_input_conns = [c for c in conns if c.conn_type == 'i']  # TOP outputs to submodules
        top_output_conns = [c for c in conns if c.conn_type == 'o']  # TOP receives from submodules
        submodule_outputs = [c for c in conns if c.direction == 'o' and c.conn_type == 'w']
        submodule_inputs = [c for c in conns if c.direction == 'i' and c.conn_type == 'w']
        
        # Determine source(s) and sink(s)
        source_module = None
        sink_modules = []
        
        if top_input_conns:
            # TOP input signal: TOP is source, all submodules are sinks
            # Handle TOP to each submodule path independently
            source_module = 'TOP'
            sink_modules = list(set([c.module_name for c in conns]))
        elif top_output_conns:
            # TOP output signal: all submodules are sources, TOP is sink
            # Handle each submodule to TOP path independently
            source_modules = list(set([c.module_name for c in conns]))
            for src_mod in source_modules:
                _process_single_path(src_mod, 'TOP', signal_name, width, case_style,
                                    adjacency, cache, waive_modules, only_modules,
                                    fd_modules, fd_signals, path_report_lines, errors,
                                    max_fd_num, connections, logger, is_bidir)
            continue
        elif submodule_outputs and submodule_inputs:
            # Module-to-module wire: need to handle bidirectional pairs correctly
            # Group by (source, sink) pairs based on direction
            # Each output module connects to each input module
            source_modules = list(set([c.module_name for c in submodule_outputs]))
            sink_mods = list(set([c.module_name for c in submodule_inputs]))
            
            # Process each source-to-sink pair independently
            for src_mod in source_modules:
                for sink_mod in sink_mods:
                    _process_single_path(src_mod, sink_mod, signal_name, width, case_style,
                                        adjacency, cache, waive_modules, only_modules,
                                        fd_modules, fd_signals, path_report_lines, errors,
                                        max_fd_num, connections, logger, is_bidir)
            continue
        else:
            # Cannot determine direction, skip
            logger.info("Signal '{}': cannot determine direction (conn_type={}, direction={}), skipping.".format(
                signal_name, [c.conn_type for c in conns], [c.direction for c in conns]))
            continue
        
        # Process each source-to-sink path independently (handles one-to-many signals)
        if source_module and sink_modules:
            for sink_module in sink_modules:
                _process_single_path(source_module, sink_module, signal_name, width, case_style,
                                    adjacency, cache, waive_modules, only_modules,
                                    fd_modules, fd_signals, path_report_lines, errors,
                                    max_fd_num, connections, logger, is_bidir)
    
    logger.info("FD detection complete: {} signals require FD".format(len(fd_signals)))
    return fd_signals, fd_modules, path_report_lines, errors


def build_path_line(signal_name, path, intermediate_modules, case_style, is_bidir, connections, logger):
    """
    Build a single line for the path report.
    
    Format:
        A.port -> C.fd_signal_from_a -> C.fd_signal_to_b -> B.port
    
    Args:
        signal_name: signal name
        path: module path list
        intermediate_modules: list of intermediate FD modules
        case_style: 'upper' or 'lower'
        is_bidir: is bidirectional signal
        connections: list of SignalConnection (for extracting actual port names)
        logger: logger instance
    
    Returns:
        str: path line
    """
    if len(path) < 2:
        return ""
    
    segments = []
    arrow = "<->" if is_bidir else "->"
    
    # Extract actual port names from connections for endpoints
    start_port_name = signal_name
    end_port_name = signal_name
    
    if connections:
        # Find port name for start module (path[0])
        for conn in connections:
            if conn.signal_name == signal_name and conn.module_name == path[0]:
                start_port_name = conn.port_name
                break
        
        # Find port name for end module (path[-1])
        for conn in connections:
            if conn.signal_name == signal_name and conn.module_name == path[-1]:
                end_port_name = conn.port_name
                break
    
    # Apply case style to port names
    if case_style == 'upper':
        start_port = "{}.{}".format(path[0], start_port_name.upper())
        end_port = "{}.{}".format(path[-1], end_port_name.upper())
    else:
        start_port = "{}.{}".format(path[0], start_port_name.lower())
        end_port = "{}.{}".format(path[-1], end_port_name.lower())
    
    segments.append(start_port)
    
    # FD modules
    for idx, fd_module in enumerate(intermediate_modules):
        from_module = path[idx]
        to_module = path[idx + 2] if idx + 2 < len(path) else path[-1]
        
        if case_style == 'upper':
            if is_bidir:
                port_name = "FD_FROM_{}_{}".format(
                    from_module.upper(), signal_name.upper()
                )
                segments.append("{}.{}".format(fd_module, port_name))
                
                port_name = "FD_TO_{}_{}".format(
                    to_module.upper() if to_module else "UNKNOWN", signal_name.upper()
                )
                segments.append("{}.{}".format(fd_module, port_name))
            else:
                port_name = "FD_FROM_{}_{}".format(
                    from_module.upper(), signal_name.upper()
                )
                segments.append("{}.{}".format(fd_module, port_name))
                
                port_name = "FD_TO_{}_{}".format(
                    to_module.upper() if to_module else "UNKNOWN", signal_name.upper()
                )
                segments.append("{}.{}".format(fd_module, port_name))
        else:
            if is_bidir:
                port_name = "fd_from_{}_{}".format(
                    from_module.lower(), signal_name.lower()
                )
                segments.append("{}.{}".format(fd_module, port_name))
                
                port_name = "fd_to_{}_{}".format(
                    to_module.lower() if to_module else "unknown", signal_name.lower()
                )
                segments.append("{}.{}".format(fd_module, port_name))
            else:
                port_name = "fd_from_{}_{}".format(
                    from_module.lower(), signal_name.lower()
                )
                segments.append("{}.{}".format(fd_module, port_name))
                
                port_name = "fd_to_{}_{}".format(
                    to_module.lower() if to_module else "unknown", signal_name.lower()
                )
                segments.append("{}.{}".format(fd_module, port_name))
    
    # End: last module's port (already computed above with actual port name)
    segments.append(end_port)
    
    return " {} ".format(arrow).join(segments)


def generate_fd_modules(fd_modules, output_dir, logger):
    """
    Generate FD module Verilog files.
    
    Args:
        fd_modules: dict {module_name: FDModule}
        output_dir: output directory path
        logger: logger instance
    """
    logger.info("Generating FD modules...")
    
    fd_dir = os.path.join(output_dir, "fd_modules")
    if not os.path.exists(fd_dir):
        os.makedirs(fd_dir)
    
    for module_name, fd_module in fd_modules.items():
        file_path = os.path.join(fd_dir, "fd_{}.v".format(module_name.lower()))
        
        with open(file_path, 'w') as f:
            f.write(generate_fd_module_verilog(fd_module))
        
        logger.info("Generated: {}".format(file_path))


def generate_fd_module_verilog(fd_module):
    """
    Generate Verilog code for a single FD module.
    
    Args:
        fd_module: FDModule instance
    
    Returns:
        str: Verilog code
    """
    lines = []
    
    # Module declaration
    lines.append("// FD Module: {}".format(fd_module.module_name))
    lines.append("// Auto-generated by FD Generator v{}".format(VERSION))
    lines.append("")
    lines.append("module FD_{} (".format(fd_module.module_name))
    
    # Port declarations
    port_lines = []
    assign_lines = []
    
    for port in fd_module.ports:
        case_style = get_case_style(port.signal_name, port.autocase)
        
        if port.is_bidir:
            # Bidirectional port
            if case_style == 'upper':
                port_name = "FD_FROM_{}_{}".format(
                    port.from_module.upper(), port.signal_name.upper()
                )
            else:
                port_name = "fd_from_{}_{}".format(
                    port.from_module.lower(), port.signal_name.lower()
                )
            
            port_lines.append("    inout wire [{}:0] {}".format(port.width - 1, port_name))
            
            if case_style == 'upper':
                port_name_to = "FD_TO_{}_{}".format(
                    port.to_module.upper(), port.signal_name.upper()
                )
            else:
                port_name_to = "fd_to_{}_{}".format(
                    port.to_module.lower(), port.signal_name.lower()
                )
            
            port_lines.append("    inout wire [{}:0] {}".format(port.width - 1, port_name_to))
            assign_lines.append("    assign {} = {};".format(port_name, port_name_to))
        else:
            # Unidirectional ports
            if case_style == 'upper':
                from_port = "FD_FROM_{}_{}".format(
                    port.from_module.upper(), port.signal_name.upper()
                )
                to_port = "FD_TO_{}_{}".format(
                    port.to_module.upper(), port.signal_name.upper()
                )
            else:
                from_port = "fd_from_{}_{}".format(
                    port.from_module.lower(), port.signal_name.lower()
                )
                to_port = "fd_to_{}_{}".format(
                    port.to_module.lower(), port.signal_name.lower()
                )
            
            port_lines.append("    input  wire [{}:0] {}".format(port.width - 1, from_port))
            port_lines.append("    output wire [{}:0] {}".format(port.width - 1, to_port))
            assign_lines.append("    assign {} = {};".format(to_port, from_port))
    
    # Join port lines with commas
    for i, line in enumerate(port_lines):
        if i < len(port_lines) - 1:
            lines.append(line + ",")
        else:
            lines.append(line)
    
    lines.append(");")
    lines.append("")
    
    # Assign statements
    for line in assign_lines:
        lines.append(line)
    
    lines.append("")
    lines.append("endmodule")
    lines.append("")
    
    return "\n".join(lines)


def generate_path_report(path_lines, output_dir, logger):
    """
    Generate fd_path_report.txt file.
    
    Args:
        path_lines: list of path strings
        output_dir: output directory path
        logger: logger instance
    """
    logger.info("Generating path report...")
    
    report_path = os.path.join(output_dir, "fd_path_report.txt")
    
    with open(report_path, 'w') as f:
        f.write("# fd_path_report.txt\n")
        f.write("# Format: start_port -> fd_port1 -> fd_port2 -> ... -> end_port\n")
        f.write("# Generated by FD Generator v{}\n".format(VERSION))
        f.write("# Date: {}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        f.write("#\n")
        f.write("\n")
        
        for line in path_lines:
            f.write(line + "\n")
    
    logger.info("Generated: {}".format(report_path))


def generate_fd_top(top_file, fd_signals, output_dir, logger, autocase=False, connections=None, debug_print=False):
    """
    Generate fd_top.v with updated CONNECT comments.
    
    Args:
        top_file: path to original top.v
        fd_signals: list of FD signal dicts
        output_dir: output directory path
        logger: logger instance
        autocase: whether to preserve signal case
        connections: list of SignalConnection (for finding output modules)
    """
    logger.info("Generating fd_top.v...")
    
    import shutil
    
    # Copy top.v to fd_top.v
    fd_top_path = os.path.join(output_dir, "fd_top.v")
    shutil.copy(top_file, fd_top_path)
    
    # Read fd_top.v lines
    with open(fd_top_path, 'r') as f:
        lines = f.readlines()
    
    # Build module -> connects mapping
    module_connects = defaultdict(list)
    
    for fd_sig in fd_signals:
        path = fd_sig['path']
        signal = fd_sig['signal']
        width = fd_sig['width']
        is_bidir = fd_sig['is_bidir']
        
        if len(path) < 2:
            continue
        
        # Determine case style
        case_style = get_case_style(signal, autocase)
        
        # Helper to get port name
        def get_port_name(sig, mod, prefix):
            if case_style == 'upper':
                return "FD_{}_{}_{}".format(prefix.upper(), mod.upper(), sig.upper())
            else:
                return "fd_{}_{}_{}".format(prefix.lower(), mod.lower(), sig.lower())
        
        # Determine source and sink modules based on conn_type from connections
        # For conn_type='i' (TOP input): TOP is source, submodules are sinks
        # For conn_type='o' (TOP output): submodules are sources, TOP is sink
        # For conn_type='w' (wire): direction='o' is source, direction='i' is sink
        
        signal_conns = [c for c in connections if c.signal_name == signal]
        top_input = any(c.conn_type == 'i' for c in signal_conns)
        top_output = any(c.conn_type == 'o' for c in signal_conns)
        
        # Determine source module (for modify logic)
        source_module = None
        if path[0] == 'TOP':
            # TOP is source (top input signal)
            # Don't modify TOP's connects, only modify sink module if needed
            source_module = 'TOP'
        elif path[-1] == 'TOP':
            # TOP is sink (top output signal)
            # Source is the first module in path
            source_module = path[0]
        else:
            # Module-to-module signal
            # Find module with direction='o'
            for conn in signal_conns:
                if conn.direction == 'o' and conn.module_name == path[0]:
                    source_module = path[0]
                    break
            if source_module is None:
                source_module = path[0]
        
        # Only modify source module's connect if it's not TOP and not an intermediate FD module
        # For top input signals (TOP->...->sink), don't modify intermediate FD modules
        # For top output signals (src->...->TOP), modify src module
        # For module-to-module signals (src->...->sink), modify src module
        
        if source_module != 'TOP' and source_module not in path[1:-1]:  # Not TOP and not intermediate
            start_wire = get_port_name(signal, source_module, 'from')
            
            # Determine direction from connections
            conn_dir = 'o'  # default
            if connections:
                for conn in connections:
                    if conn.signal_name == signal and conn.module_name == source_module:
                        conn_dir = conn.direction
                        break
            
            module_connects[source_module].append({
                'type': 'modify',
                'old_wire': signal,
                'new_wire': start_wire,
                'width': width,
                'direction': conn_dir
            })
        
        # Also modify the destination module's CONNECT
        # The destination module should use fd_from_last_fd_module_signal
        if len(path) > 2:
            # There are FD modules, destination uses fd_from_last_fd
            end_module = path[-1]
            last_fd_module = path[-2]
            if end_module != 'TOP':  # Don't modify TOP's connects
                end_wire = get_port_name(signal, last_fd_module, 'from')
                
                # Find direction for end module
                end_dir = 'i'  # default
                if connections:
                    for conn in connections:
                        if conn.signal_name == signal and conn.module_name == end_module:
                            end_dir = conn.direction
                            break
                
                module_connects[end_module].append({
                    'type': 'modify',
                    'old_wire': signal,
                    'new_wire': end_wire,
                    'width': width,
                    'direction': end_dir
                })
        
        # Intermediate modules (append CONNECTs)
        for i in range(1, len(path) - 1):
            fd_module = path[i]
            from_module = path[i - 1]
            to_module = path[i + 1]
            
            # FD module port names
            input_port = get_port_name(signal, from_module, 'from')
            output_port = get_port_name(signal, to_module, 'to')
            
            # Wire names and CONNECT types
            # When connected to TOP, use original signal name and i/o type
            # When connected to regular module, use fd_from_X format and w type
            
            # Input side (from from_module to this FD module)
            if from_module == 'TOP':
                input_wire = signal  # Use original signal name (TOP port name)
                input_type = 'i'  # Top-level input
            else:
                input_wire = get_port_name(signal, from_module, 'from')
                input_type = 'w'  # Module-to-module
            
            # Output side (from this FD module to to_module)
            # Rule: Only the connection to TOP uses original signal name
            # All other connections (including to final destination module) use fd_from_X format
            if to_module == 'TOP':
                output_wire = signal  # Use original signal name (TOP port name)
                output_type = 'o'  # Top-level output
            else:
                output_wire = get_port_name(signal, fd_module, 'from')  # Wire from this FD module
                output_type = 'w'
            
            module_connects[fd_module].append({
                'type': 'append',
                'wire': input_wire,
                'port': input_port,
                'width': width,
                'direction': 'i',
                'conn_type': input_type
            })
            module_connects[fd_module].append({
                'type': 'append',
                'wire': output_wire,
                'port': output_port,
                'width': width,
                'direction': 'o',
                'conn_type': output_type
            })
    
    # Process each module
    for module_name, connects in module_connects.items():
        # Find instance line
        instance_idx = None
        instance_pattern = r"//INSTANCE.*\b{}\b".format(module_name)
        
        for idx, line in enumerate(lines):
            if re.search(instance_pattern, line):
                instance_idx = idx
                break
        
        if instance_idx is None:
            logger.warning("Instance {} not found in top file".format(module_name))
            continue
        
        # Find CONNECT lines for this instance (re-scan to get current position after previous inserts)
        connect_start = instance_idx + 1
        connect_end = connect_start
        
        # Scan all CONNECT lines for this module
        # Stop only when we hit the next INSTANCE or end of comment list
        while connect_end < len(lines):
            stripped = lines[connect_end].strip()
            if stripped.startswith('//CONNECT'):
                connect_end += 1
            elif stripped.startswith('//INSTANCE'):
                # Hit next module's INSTANCE, stop here
                break
            elif stripped.startswith('// ------------ end SOC_IGT comment list'):
                # Hit end of comment list, stop here
                break
            else:
                # Skip empty lines and other comments, continue scanning
                connect_end += 1
        
        # connect_end now points to the actual current position (after any previous inserts)
        
        # Separate modify and append connects
        modify_connects = [c for c in connects if c['type'] == 'modify']
        append_connects = [c for c in connects if c['type'] == 'append']
        
        # Debug print
        if debug_print:
            logger.info("[FD_TOP] === Module: {} ===".format(module_name))
            logger.info("[FD_TOP] CONNECT lines range: {} to {} (total: {} lines)".format(
                connect_start + 1, connect_end, connect_end - connect_start))
            logger.info("[FD_TOP] Modify connects: {}, Append connects: {}".format(
                len(modify_connects), len(append_connects)))
            for i, conn in enumerate(modify_connects):
                logger.info("[FD_TOP]   Modify[{}]: old_wire='{}' -> new_wire='{}'".format(
                    i, conn['old_wire'], conn['new_wire']))
            logger.info("[FD_TOP] Scanning CONNECT lines (first 30):")
            for idx in range(connect_start, min(connect_end, connect_start + 30)):
                logger.info("[FD_TOP]   Line[{}]: {}".format(idx + 1, lines[idx].strip()[:100]))
        
        # Process modify connects first
        for conn in modify_connects:
            for idx in range(connect_start, connect_end):
                line = lines[idx]
                # Use cleaned line for matching only, preserve original line for output
                clean_line = line.replace(' ', '').replace('\t', '').replace('\r', '').replace('\n', '')
                
                # Check if this is a CONNECT line
                if not clean_line.startswith('//CONNECT('):
                    continue
                
                # Simple comma-based parsing
                # Format: //CONNECT(type,wire,instance`port,width,dir);
                if clean_line.endswith(');'):
                    clean_line = clean_line[:-2]  # Remove ');'
                
                parts = clean_line.split(',')
                if len(parts) >= 5:
                    # parts[0] = "//CONNECT(type"
                    # parts[1] = wire name (may include bit-select like [7:0])
                    # parts[2] = instance`port
                    # parts[3] = width
                    # parts[4] = direction
                    existing_wire = parts[1]
                    # Keep original line intact for replacement to preserve formatting
                    wire_match = False
                    if existing_wire == conn['old_wire']:
                        wire_match = True
                    elif '[' in existing_wire:
                        base_wire = existing_wire.split('[')[0]
                        if base_wire == conn['old_wire']:
                            wire_match = True
                    
                    if wire_match:
                        new_line = re.sub(
                            r',\s*' + re.escape(existing_wire) + r'\s*,',
                            ', ' + conn['new_wire'] + ',',
                            line
                        )
                        lines[idx] = new_line
                        if debug_print:
                            logger.info("[FD_TOP]   *** MODIFIED: {} -> {}".format(conn['old_wire'], conn['new_wire']))
                        break
        
        # Deduplicate append connects
        seen = set()
        unique_appends = []
        for conn in append_connects:
            key = (conn['wire'], conn['port'], conn['direction'])
            if key not in seen:
                unique_appends.append(conn)
                seen.add(key)
        
        # Process append connects - insert after this module's last CONNECT
        # connect_end is already the current position (re-scanned after previous inserts)
        if unique_appends:
            insert_pos = connect_end
            # Insert FD CONNECTs (no blank line before)
            for conn in unique_appends:
                instance_name = "U_" + module_name
                conn_type = conn.get('conn_type', 'w')
                connect_line = "//CONNECT({}, {}, {}`{}, {}, {});\n".format(
                    conn_type,
                    conn['wire'],
                    instance_name,
                    conn['port'],
                    conn['width'],
                    conn['direction']
                )
                lines.insert(insert_pos, connect_line)
                insert_pos += 1
            
            # Add blank line AFTER FD CONNECTs (before next INSTANCE)
            lines.insert(insert_pos, '\n')
    
    # Align all CONNECT lines after all modifications are complete
    # Scan entire file, align CONNECTs within each INSTANCE block
    align_all_connects(lines)
    
    # Write back
    with open(fd_top_path, 'w') as f:
        f.writelines(lines)
    
    logger.info("Generated: {}".format(fd_top_path))


def align_all_connects(lines):
    """
    Align all CONNECT lines in the file.
    - Scan line by line
    - For each INSTANCE block, collect all CONNECT lines
    - Calculate max width for each column (wire, inst_port, width)
    - Format all CONNECT lines with aligned commas
    """
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check if this is an INSTANCE line
        if line.strip().startswith('//INSTANCE('):
            # Found INSTANCE, now collect all CONNECT lines in this block
            connect_start = i + 1
            connect_end = connect_start
            connect_data = []
            
            # Scan forward to find all CONNECT lines until next INSTANCE or end marker
            for j in range(connect_start, min(connect_start + 500, len(lines))):
                scan_line = lines[j].strip()
                
                if scan_line.startswith('//CONNECT(') or scan_line.startswith('//CONNECT ('):
                    # Parse this CONNECT line
                    clean = lines[j].replace(' ', '').replace('\t', '').replace('\r', '').replace('\n', '')
                    if clean.endswith(');'):
                        clean = clean[:-2]
                    
                    parts = clean.split(',')
                    if len(parts) >= 5:
                        conn_type = parts[0].replace('//CONNECT(', '')
                        wire = parts[1]
                        inst_port = parts[2]
                        width = parts[3]
                        direction = parts[4]
                        
                        connect_data.append({
                            'line_idx': j,
                            'type': conn_type,
                            'wire': wire,
                            'inst_port': inst_port,
                            'width': width,
                            'direction': direction
                        })
                    
                    connect_end = j + 1
                elif scan_line.startswith('//INSTANCE') or 'end SOC_IGT comment list' in scan_line:
                    # End of this INSTANCE block
                    break
                else:
                    # Empty line or other comment, continue scanning
                    continue
            
            # Align CONNECTs in this block
            if connect_data:
                # Calculate max widths
                max_wire_len = max(len(d['wire']) for d in connect_data)
                max_inst_len = max(len(d['inst_port']) for d in connect_data)
                max_width_len = max(len(d['width']) for d in connect_data)
                
                # Format all CONNECT lines
                # Format: field + padding + ", " + next_field
                # - Field is left-aligned
                # - Padding AFTER field to reach fixed column width
                # - Then comma + space
                # This ensures all commas are at fixed column positions
                for d in connect_data:
                    wire_padding = ' ' * (max_wire_len - len(d['wire']))
                    inst_padding = ' ' * (max_inst_len - len(d['inst_port']))
                    width_padding = ' ' * (max_width_len - len(d['width']))
                    
                    formatted = (
                        "//CONNECT(" + d['type'] + ", " +
                        d['wire'] + wire_padding + ", " +
                        d['inst_port'] + inst_padding + ", " +
                        d['width'] + width_padding + ", " +
                        d['direction'] + ");"
                    )
                    lines[d['line_idx']] = formatted + '\n'
            
            # Continue from end of this INSTANCE block
            i = connect_end
        else:
            i += 1


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="FD Generator - SoC Feedthrough Auto Generation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fd_generator.py -top top.v -floorplan adjacency.txt
  python fd_generator.py -top top.v -floorplan adjacency.txt -output fd_out/
  python fd_generator.py -top top.v -floorplan adjacency.txt -maxfdnum 5

Output:
  fd_output/
    fd_modules/
      FD_MODULE1.v
      FD_MODULE2.v
    fd_path_report.txt
    fd_generator.log
        """
    )
    
    parser.add_argument(
        '-top',
        required=True,
        help='Top-level netlist file (Verilog with SOC_IGT comment list)'
    )
    parser.add_argument(
        '-floorplan',
        required=True,
        help='Floorplan adjacency file (text format)'
    )
    parser.add_argument(
        '-output',
        default=DEFAULT_OUTPUT_DIR,
        help='Output directory (default: {})'.format(DEFAULT_OUTPUT_DIR)
    )
    parser.add_argument(
        '-maxfdnum',
        type=int,
        default=DEFAULT_MAX_FD_NUM,
        help='Maximum number of intermediate FD modules (default: {})'.format(DEFAULT_MAX_FD_NUM)
    )
    parser.add_argument(
        '-print',
        action='store_true',
        dest='debug_print',
        help='Enable detailed debug printing for fd_top generation'
    )
    parser.add_argument(
        '-waive',
        default=None,
        help='Waive file containing modules to exclude from FD routing (space-separated)'
    )
    parser.add_argument(
        '-only',
        default=None,
        help='Only file containing modules allowed for FD routing (space-separated)'
    )
    parser.add_argument(
        '-autocase',
        action='store_true',
        default=False,
        help='Preserve signal case in FD port names (default: all lowercase)'
    )
    parser.add_argument(
        '-link',
        action='store_true',
        default=False,
        help='Generate fd_top.v with updated CONNECT comments'
    )
    parser.add_argument(
        '-version',
        action='version',
        version='FD Generator v{}'.format(VERSION)
    )
    
    args = parser.parse_args()
    
    # Validate input files
    if not os.path.exists(args.top):
        print("Error: Top file not found: {}".format(args.top))
        sys.exit(1)
    
    if not os.path.exists(args.floorplan):
        print("Error: Floorplan file not found: {}".format(args.floorplan))
        sys.exit(1)
    
    # Parse waive/only files
    waive_modules = set()
    only_modules = set()
    if args.waive:
        if not os.path.exists(args.waive):
            print("Error: Waive file not found: {}".format(args.waive))
            sys.exit(1)
        with open(args.waive, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                waive_modules.update(parts)
    
    if args.only:
        if not os.path.exists(args.only):
            print("Error: Only file not found: {}".format(args.only))
            sys.exit(1)
        with open(args.only, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                only_modules.update(parts)
    
    # -only has higher priority than -waive
    if only_modules and args.waive:
        waive_modules = set()  # Ignore -waive when -only is used
    
    # Create output directory
    if not os.path.exists(args.output):
        os.makedirs(args.output)
    
    # Setup logging
    logger = setup_logging(args.output)
    
    logger.info("=" * 60)
    logger.info("FD Generator v{}".format(VERSION))
    logger.info("=" * 60)
    logger.info("Top file: {}".format(args.top))
    logger.info("Floorplan: {}".format(args.floorplan))
    logger.info("Output directory: {}".format(args.output))
    logger.info("Max FD modules: {}".format(args.maxfdnum))
    if only_modules:
        logger.info("Only modules: {}".format(', '.join(sorted(only_modules))))
    elif waive_modules:
        logger.info("Waived modules: {}".format(', '.join(sorted(waive_modules))))
    logger.info("Autocase: {}".format(args.autocase))
    logger.info("=" * 60)
    
    # Parse input files
    adjacency = parse_floorplan(args.floorplan, logger)
    modules, connections = parse_top_file(args.top, logger)
    
    # Detect FD signals
    fd_signals, fd_modules, path_lines, errors = detect_fd_signals(
        connections, adjacency, args.maxfdnum, logger, waive_modules, args.autocase, only_modules
    )
    
    # Generate FD modules
    if fd_modules:
        generate_fd_modules(fd_modules, args.output, logger)
    else:
        logger.info("No FD modules to generate")
    
    # Generate path report
    if path_lines:
        generate_path_report(path_lines, args.output, logger)
    else:
        logger.info("No path report to generate")
    
    # Generate fd_top.v if -link is enabled
    if args.link:
        generate_fd_top(args.top, fd_signals, args.output, logger, args.autocase, connections, args.debug_print)
    
    # Summary
    logger.info("=" * 60)
    logger.info("Summary:")
    logger.info("  Total signals requiring FD: {}".format(len(fd_signals)))
    logger.info("  FD modules generated: {}".format(len(fd_modules)))
    logger.info("  Errors: {}".format(len(errors)))
    logger.info("=" * 60)
    
    if errors:
        logger.warning("Processing completed with {} error(s)".format(len(errors)))
        sys.exit(1)
    else:
        logger.info("Processing completed successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
