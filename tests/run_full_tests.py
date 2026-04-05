#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FD Generator 全面测试脚本
测试所有功能和边界情况
"""

import os
import sys
import subprocess
import shutil

# 测试目录
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
FD_GEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fd_generator.py')

# 测试结果
test_results = []

def run_test(name, args, expected_fd_modules=None, expected_errors=0, check_link=True):
    """运行单个测试"""
    print("\n" + "="*60)
    print("测试: {}".format(name))
    print("="*60)
    
    output_dir = os.path.join(TEST_DIR, 'test_auto_{}'.format(len(test_results)))
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    
    cmd = [sys.executable, FD_GEN, '-output', output_dir] + args
    # Run from fd_gen directory so relative paths in args work correctly
    fd_gen_dir = os.path.dirname(FD_GEN)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=fd_gen_dir)
    
    # 解析输出
    output = result.stdout + result.stderr
    
    # 检查 FD 模块
    fd_modules_dir = os.path.join(output_dir, 'fd_modules')
    actual_fd_modules = []
    if os.path.exists(fd_modules_dir):
        actual_fd_modules = [f.replace('.v', '') for f in os.listdir(fd_modules_dir) if f.endswith('.v')]
    
    # 检查错误数
    import re
    error_match = re.search(r'Errors: (\d+)', output)
    actual_errors = int(error_match.group(1)) if error_match else 0
    
    # 检查路径报告
    path_report = os.path.join(output_dir, 'fd_path_report.txt')
    path_lines = []
    if os.path.exists(path_report):
        with open(path_report, 'r') as f:
            path_lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    
    # 检查 fd_top.v
    fd_top = os.path.join(output_dir, 'fd_top.v')
    fd_top_content = ""
    if os.path.exists(fd_top):
        with open(fd_top, 'r') as f:
            fd_top_content = f.read()
    
    # 验证
    passed = True
    issues = []
    
    if expected_fd_modules is not None:
        if set(actual_fd_modules) != set(expected_fd_modules):
            passed = False
            issues.append("FD 模块不匹配：期望={}, 实际={}".format(expected_fd_modules, actual_fd_modules))
    
    if expected_errors is not None:
        if actual_errors != expected_errors:
            passed = False
            issues.append("错误数不匹配：期望={}, 实际={}".format(expected_errors, actual_errors))
    
    # 检查 -link 输出
    if check_link and fd_top_content:
        # 检查 CONNECT 格式
        connect_lines = [l for l in fd_top_content.split('\n') if 'CONNECT' in l and not l.strip().startswith('//')]
        if connect_lines:
            # 应该有 CONNECT 语句
            pass
        else:
            # 检查注释形式的 CONNECT
            comment_connects = [l for l in fd_top_content.split('\n') if '//CONNECT' in l]
            if not comment_connects:
                passed = False
                issues.append("fd_top.v 中没有 CONNECT 语句")
    
    result_dict = {
        'name': name,
        'passed': passed,
        'issues': issues,
        'fd_modules': actual_fd_modules,
        'errors': actual_errors,
        'paths': path_lines,
        'output': output
    }
    test_results.append(result_dict)
    
    print("FD 模块: {}".format(actual_fd_modules))
    print("错误数: {}".format(actual_errors))
    print("路径数: {}".format(len(path_lines)))
    if issues:
        print("❌ 问题:")
        for issue in issues:
            print("  - {}".format(issue))
    else:
        print("✅ 通过")
    
    return result_dict

def main():
    print("="*60)
    print("FD Generator 全面自动化测试")
    print("="*60)
    
    # 测试 1: 标准测试
    # Note: With sorted BFS, C->D consistently chooses B (alphabetically first)
    # This results in only fd_b module (all paths go through B)
    run_test(
        "标准测试（5 模块+TOP，9 个 FD 信号）",
        ['-top', 'tests/test_standard_top.v', '-floorplan', 'tests/test_standard_floorplan.txt', '-link'],
        expected_fd_modules=['fd_b'],  # Sorted BFS chooses B for all paths
        expected_errors=0
    )
    
    # 测试 2: waive B
    run_test(
        "Waive B 测试",
        ['-top', 'tests/test_standard_top.v', '-floorplan', 'tests/test_standard_floorplan.txt', '-waive', 'tests/waive_B.txt', '-link'],
        expected_fd_modules=['fd_d', 'fd_e'],
        expected_errors=0
    )
    
    # 测试 3: only B
    run_test(
        "Only B 测试",
        ['-top', 'tests/test_standard_top.v', '-floorplan', 'tests/test_standard_floorplan.txt', '-only', 'tests/only_B.txt', '-link'],
        expected_fd_modules=['fd_b'],
        expected_errors=0
    )
    
    # 测试 4: only DE
    run_test(
        "Only DE 测试",
        ['-top', 'tests/test_standard_top.v', '-floorplan', 'tests/test_standard_floorplan.txt', '-only', 'tests/only_DE.txt', '-link'],
        expected_fd_modules=['fd_d', 'fd_e'],
        expected_errors=0
    )
    
    # 测试 5: only C（不可行）
    run_test(
        "Only C 测试（不可行场景）",
        ['-top', 'tests/test_standard_top.v', '-floorplan', 'tests/test_standard_floorplan.txt', '-only', 'tests/only_C.txt', '-link'],
        expected_fd_modules=[],
        expected_errors=9
    )
    
    # 测试 6: 位宽测试
    run_test(
        "位宽测试（1/8/16 位）",
        ['-top', 'tests/test_width_top.v', '-floorplan', 'tests/test_width_floorplan.txt', '-link'],
        expected_fd_modules=None,  # 不检查具体模块
        expected_errors=0
    )
    
    # 测试 7: basic_top.v 基准测试
    run_test(
        "基准测试（basic_top.v，6 模块）",
        ['-top', 'tests/basic_top.v', '-floorplan', 'tests/basic_floorplan.txt', '-link'],
        expected_fd_modules=None,  # 不检查具体模块，仅验证能正常运行
        expected_errors=0
    )
    
    # 测试 8: 大型复杂测试（6 模块，链式结构）
    run_test(
        "大型测试（6 模块，链式结构）",
        ['-top', 'tests/test_large_top.v', '-floorplan', 'tests/test_large_floorplan.txt', '-link'],
        expected_fd_modules=None,  # 不检查具体模块
        expected_errors=None  # 不检查错误数（允许多驱动警告）
    )
    
    # 打印总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for r in test_results if r['passed'])
    total = len(test_results)
    
    print("通过: {}/{}".format(passed, total))
    
    for r in test_results:
        status = "✅" if r['passed'] else "❌"
        print("{} {}".format(status, r['name']))
        if r['issues']:
            for issue in r['issues']:
                print("    {}".format(issue))
    
    return 0 if passed == total else 1

if __name__ == '__main__':
    sys.exit(main())
