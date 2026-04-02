#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FD Generator - SoC Feedthrough Auto Generation Tool

This tool automatically detects signals requiring feedthrough (FD) and generates
intermediate FD modules based on floorplan adjacency.

Usage:
    python fd_generator.py -top <top.v> -floorplan <adjacency.txt> [-output fd_output/] [-maxfdnum 3]

Author: 克劳 (木叶村火影助理)
Version: 1.0.0
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

VERSION = "1.0.0"
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
    def __init__(self, signal_name, module_name, port_name, width, direction, is_top=False):
        self.signal_name = signal_name
        self.module_name = module_name
        self.port_name = port_name
        self.width = width
        self.direction = direction  # 'i', 'o', 'b'
        self.is_top = is_top  # True if connected to top-level
    
    def __repr__(self):
        return "SignalConnection({}, {}, {}, {}, {})".format(
            self.signal_name, self.module_name, self.port_name, 
            self.width, self.direction
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
    def __init__(self, signal_name, from_module, to_module, width, is_bidir=False):
        self.signal_name = signal_name
        self.from_module = from_module
        self.to_module = to_module
        self.width = width
        self.is_bidir = is_bidir
    
    def get_port_name(self, case_style):
        """Generate port name based on case style."""
        if case_style == 'upper':
            if self.is_bidir:
                return "FD_{}_FROM_{}".format(
                    self.signal_name.upper(), self.from_module.upper()
                )
            else:
                return [
                    "FD_{}_FROM_{}".format(
                        self.signal_name.upper(), self.from_module.upper()
                    ),
                    "FD_{}_TO_{}".format(
                        self.signal_name.upper(), self.to_module.upper()
                    )
                ]
        else:  # lower
            if self.is_bidir:
                return "fd_{}_from_{}".format(
                    self.signal_name.lower(), self.from_module.lower()
                )
            else:
                return [
                    "fd_{}_from_{}".format(
                        self.signal_name.lower(), self.from_module.lower()
                    ),
                    "fd_{}_to_{}".format(
                        self.signal_name.lower(), self.to_module.lower()
                    )
                ]


class FDModule:
    """Represents an FD module to be generated."""
    def __init__(self, module_name):
        self.module_name = module_name
        self.ports = []  # List of FDPort
    
    def add_port(self, port):
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
    
    adjacency = defaultdict(set)
    
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
            
            # Add bidirectional relationships
            for adj in adjacent_modules:
                adjacency[module_name].add(adj)
                adjacency[adj].add(module_name)
    
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
                    width=sig_width,
                    direction=direction,
                    is_top=is_top
                ))
        elif wire_name and not wire_name.startswith("'"):
            # Regular signal (not empty, not fixed value)
            # Extract signal name and width from bit selection
            sig_name, sig_width = parse_signal_name(wire_name)
            if sig_name:
                connections.append(SignalConnection(
                    signal_name=sig_name,
                    module_name=module_name,
                    port_name=port_name,
                    width=sig_width,
                    direction=direction,
                    is_top=is_top
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


def get_case_style(signal_name):
    """
    Determine case style for FD port naming.
    
    Returns:
        'upper' if signal is all uppercase or mixed case
        'lower' if signal is all lowercase
    """
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
        """Create unordered key for module pair."""
        return tuple(sorted([src, dst]))
    
    def get(self, src, dst):
        """Get cached path if exists."""
        key = self._make_key(src, dst)
        return self.cache.get(key)
    
    def set(self, src, dst, path):
        """Cache a path."""
        key = self._make_key(src, dst)
        self.cache[key] = path


def bfs_shortest_path(adjacency, src, dst, cache):
    """
    Find shortest path between src and dst modules using BFS.
    
    Args:
        adjacency: dict {module: set(adjacent_modules)}
        src: source module name
        dst: destination module name
        cache: BFSCache instance
    
    Returns:
        list: [src, intermediate1, intermediate2, ..., dst] or None if no path
    """
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
        
        for neighbor in adjacency.get(current, []):
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


# ============================================================================
# FD Detection and Generation
# ============================================================================

def detect_fd_signals(connections, adjacency, max_fd_num, logger):
    """
    Detect signals requiring FD and compute paths.
    
    Args:
        connections: list of SignalConnection
        adjacency: floorplan adjacency dict
        max_fd_num: maximum allowed intermediate modules
        logger: logger instance
    
    Returns:
        tuple: (fd_signals, fd_modules, path_report_lines, errors)
            fd_signals: list of signals requiring FD
            fd_modules: dict {module_name: FDModule}
            path_report_lines: list of path strings for report
            errors: list of error messages
    """
    logger.info("Detecting FD signals...")
    
    # Group connections by signal name
    signal_groups = defaultdict(list)
    for conn in connections:
        # Skip top-level connections for FD detection
        if conn.is_top:
            continue
        signal_groups[conn.signal_name].append(conn)
    
    fd_signals = []
    fd_modules = {}  # {module_name: FDModule}
    path_report_lines = []
    errors = []
    
    cache = BFSCache()
    
    for signal_name, conns in signal_groups.items():
        if len(conns) < 2:
            continue  # Need at least 2 connections
        
        # Get unique modules connected by this signal
        modules = list(set([c.module_name for c in conns]))
        if len(modules) < 2:
            continue  # All connections to same module
        
        # Determine case style from signal name
        case_style = get_case_style(signal_name)
        
        # Get width (use first connection's width)
        width = conns[0].width
        
        # Determine direction
        # If any connection is 'b', it's bidirectional
        is_bidir = any(c.direction == 'b' for c in conns)
        
        # For each pair of modules, check if FD is needed
        processed_pairs = set()
        
        for i, mod1 in enumerate(modules):
            for mod2 in modules[i+1:]:
                # Create unordered pair key for deduplication
                pair_key = tuple(sorted([mod1, mod2]))
                if pair_key in processed_pairs:
                    continue
                processed_pairs.add(pair_key)
                
                # Check if adjacent
                if mod2 in adjacency.get(mod1, set()):
                    continue  # Direct connection, no FD needed
                
                # Find shortest path
                path = bfs_shortest_path(adjacency, mod1, mod2, cache)
                
                if path is None:
                    error_msg = "No path found between {} and {} for signal {}".format(
                        mod1, mod2, signal_name
                    )
                    logger.error(error_msg)
                    errors.append(error_msg)
                    continue
                
                # Check path length (intermediate modules)
                intermediate_modules = path[1:-1]  # Exclude src and dst
                if len(intermediate_modules) > max_fd_num:
                    error_msg = "Path too long for signal {}: {} intermediate modules (max {})".format(
                        signal_name, len(intermediate_modules), max_fd_num
                    )
                    logger.error(error_msg)
                    errors.append(error_msg)
                    continue
                
                # Generate FD modules for intermediate modules
                for fd_module_name in intermediate_modules:
                    if fd_module_name not in fd_modules:
                        fd_modules[fd_module_name] = FDModule(fd_module_name)
                    
                    # Determine from/to based on path order
                    idx = intermediate_modules.index(fd_module_name)
                    from_module = path[idx]
                    to_module = path[idx + 2] if idx + 2 < len(path) else path[-1]
                    
                    # Actually, we need to find the adjacent modules in the path
                    from_module = path[idx]
                    to_module = path[idx + 2] if idx + 2 < len(path) else None
                    
                    # For FD module at position idx in intermediate_modules,
                    # it receives from path[idx] and sends to path[idx+2]
                    # But path is [src, int1, int2, ..., dst]
                    # intermediate_modules is [int1, int2, ...]
                    # So for int1 (idx=0): from=path[0]=src, to=path[2]=int2
                    # For int2 (idx=1): from=path[1]=int1, to=path[3]=int3 or dst
                    
                    # Let me recalculate
                    full_path_idx = idx + 1  # Position in full path
                    from_module = path[full_path_idx - 1]
                    to_module = path[full_path_idx + 1]
                    
                    fd_port = FDPort(
                        signal_name=signal_name,
                        from_module=from_module,
                        to_module=to_module,
                        width=width,
                        is_bidir=is_bidir
                    )
                    fd_modules[fd_module_name].add_port(fd_port)
                
                # Build path report line
                path_line = build_path_line(
                    signal_name, path, intermediate_modules,
                    case_style, is_bidir, adjacency, logger
                )
                path_report_lines.append(path_line)
                
                fd_signals.append({
                    'signal': signal_name,
                    'width': width,
                    'from': mod1,
                    'to': mod2,
                    'path': path,
                    'case_style': case_style,
                    'is_bidir': is_bidir
                })
    
    logger.info("FD detection complete: {} signals require FD".format(len(fd_signals)))
    return fd_signals, fd_modules, path_report_lines, errors


def build_path_line(signal_name, path, intermediate_modules, case_style, is_bidir, adjacency, logger):
    """
    Build a single line for the path report.
    
    Format:
        A.signal -> C.fd_signal_from_a -> C.fd_signal_to_b -> B.signal
    
    Returns:
        str: path line
    """
    if len(path) < 2:
        return ""
    
    segments = []
    arrow = "<->" if is_bidir else "->"
    
    # Start: first module's port
    # We need to find the port name from connections
    # For simplicity, use signal name as port name for endpoints
    start_port = signal_name
    if case_style == 'upper':
        start_port = signal_name.upper()
    else:
        start_port = signal_name.lower()
    
    segments.append("{}.{}".format(path[0], start_port))
    
    # FD modules
    for idx, fd_module in enumerate(intermediate_modules):
        from_module = path[idx]
        to_module = path[idx + 2] if idx + 2 < len(path) else path[-1]
        
        if case_style == 'upper':
            if is_bidir:
                port_name = "FD_{}_FROM_{}".format(
                    signal_name.upper(), from_module.upper()
                )
                segments.append("{}.{}".format(fd_module, port_name))
                
                port_name = "FD_{}_TO_{}".format(
                    signal_name.upper(), to_module.upper() if to_module else "UNKNOWN"
                )
                segments.append("{}.{}".format(fd_module, port_name))
            else:
                port_name = "FD_{}_FROM_{}".format(
                    signal_name.upper(), from_module.upper()
                )
                segments.append("{}.{}".format(fd_module, port_name))
                
                port_name = "FD_{}_TO_{}".format(
                    signal_name.upper(), to_module.upper() if to_module else "UNKNOWN"
                )
                segments.append("{}.{}".format(fd_module, port_name))
        else:
            if is_bidir:
                port_name = "fd_{}_from_{}".format(
                    signal_name.lower(), from_module.lower()
                )
                segments.append("{}.{}".format(fd_module, port_name))
                
                port_name = "fd_{}_to_{}".format(
                    signal_name.lower(), to_module.lower() if to_module else "unknown"
                )
                segments.append("{}.{}".format(fd_module, port_name))
            else:
                port_name = "fd_{}_from_{}".format(
                    signal_name.lower(), from_module.lower()
                )
                segments.append("{}.{}".format(fd_module, port_name))
                
                port_name = "fd_{}_to_{}".format(
                    signal_name.lower(), to_module.lower() if to_module else "unknown"
                )
                segments.append("{}.{}".format(fd_module, port_name))
    
    # End: last module's port
    end_port = signal_name
    if case_style == 'upper':
        end_port = signal_name.upper()
    else:
        end_port = signal_name.lower()
    
    segments.append("{}.{}".format(path[-1], end_port))
    
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
        file_path = os.path.join(fd_dir, "FD_{}.v".format(module_name))
        
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
        case_style = get_case_style(port.signal_name)
        
        if port.is_bidir:
            # Bidirectional port
            if case_style == 'upper':
                port_name = "FD_{}_FROM_{}".format(
                    port.signal_name.upper(), port.from_module.upper()
                )
            else:
                port_name = "fd_{}_from_{}".format(
                    port.signal_name.lower(), port.from_module.lower()
                )
            
            port_lines.append("    inout wire [{}:0] {}".format(port.width - 1, port_name))
            
            if case_style == 'upper':
                port_name_to = "FD_{}_TO_{}".format(
                    port.signal_name.upper(), port.to_module.upper()
                )
            else:
                port_name_to = "fd_{}_to_{}".format(
                    port.signal_name.lower(), port.to_module.lower()
                )
            
            port_lines.append("    inout wire [{}:0] {}".format(port.width - 1, port_name_to))
            assign_lines.append("    assign {} = {};".format(port_name, port_name_to))
        else:
            # Unidirectional ports
            if case_style == 'upper':
                from_port = "FD_{}_FROM_{}".format(
                    port.signal_name.upper(), port.from_module.upper()
                )
                to_port = "FD_{}_TO_{}".format(
                    port.signal_name.upper(), port.to_module.upper()
                )
            else:
                from_port = "fd_{}_from_{}".format(
                    port.signal_name.lower(), port.from_module.lower()
                )
                to_port = "fd_{}_to_{}".format(
                    port.signal_name.lower(), port.to_module.lower()
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
  ├── fd_modules/
  │   ├── FD_MODULE1.v
  │   └── FD_MODULE2.v
  ├── fd_path_report.txt
  └── fd_generator.log
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
    logger.info("=" * 60)
    
    # Parse input files
    adjacency = parse_floorplan(args.floorplan, logger)
    modules, connections = parse_top_file(args.top, logger)
    
    # Detect FD signals
    fd_signals, fd_modules, path_lines, errors = detect_fd_signals(
        connections, adjacency, args.maxfdnum, logger
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
