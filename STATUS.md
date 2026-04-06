# FD Generator - 项目状态

_最后更新：2026-04-05_

---

## 🎯 项目简介

SoC Feedthrough Auto Generation Tool - SoC 顶层集成设计自动化工具，自动检测需要 FD 串线的信号并生成中间 FD 模块 Verilog 代码。

**GitHub:** https://github.com/lansongfu/fd_gen

---

## ✨ 功能列表

- [x] CONNECT 解析
- [x] BFS 路径查找（带缓存）
- [x] FD 模块自动生成
- [x] fd_top.v 生成
- [x] waive 模块过滤
- [x] only 模块限制
- [x] 位宽差异检测（>4 倍 ERROR，≤4 倍 WARNING）
- [x] 多驱动检测
- [x] 路径报告生成
- [x] CONNECT 自动对齐
- [x] 确定性 BFS（100% 稳定）

---

## 📂 项目结构

```
fd_gen/
├── fd_generator.py    # 主程序（1800+ 行）
├── tests/
│   ├── README_TESTS.md    # 测试平台说明
│   ├── run_full_tests.py  # 主测试（6/6 通过）
│   ├── basic_top.v        # ⭐ 推荐基准模板（6 模块）
│   ├── test_standard_top.v # 标准测试（5 模块）
│   └── ...                # 其他测试文件
├── README.md
└── STATUS.md          # 本文件
```

---

## 📝 修改记录

| 日期 | 版本 | 修改内容 |
|------|------|---------|
| 2026-04-01 | v1.0.0 | 初始版本发布 |
| 2026-04-02 | v1.1.0 | 添加 -link/-waive/-only 参数，双向信号处理 |
| 2026-04-03 | v1.1.13 | CONNECT 对齐修复，BFS 确定性修复 |
| 2026-04-04 | v1.1.13 | 版本号修复（1.1.1→1.1.13），语法警告修复 |
| 2026-04-05 | v1.1.14 | 默认最大穿线基数 3→5，新增基准测试和大型测试 |
| 2026-04-06 | v1.1.14 | 更新 STATUS.md，添加基准测试文件，推送至 GitHub |

---

## 🚦 当前状态

- **版本:** v1.1.14
- **状态:** ✅ 已推送
- **测试:** 49/49 通过（100%）
- **GitHub:** https://github.com/lansongfu/fd_gen
- **最新提交:** `5103236` - v1.1.14: Update STATUS.md and add benchmark test files

---

## 🧪 测试覆盖

### 测试用例映射

| 类别 | 测试用例数 | 状态 |
|------|-----------|------|
| 核心功能 | 16 | ✅ |
| 边界情况 | 10 | ✅ |
| 回归测试 | 19 | ✅ |
| 基准测试 | 2 | ✅ |
| **总计** | **47** | ✅ |
| 大规模测试 | 2 | ✅ |
| 错误处理 | 2 | ✅ |
| **总计** | **49** | **✅ 100%** |

### 主要测试场景

| 编号 | 功能 | 测试文件 | 状态 |
|------|------|---------|------|
| TC01 | 基础 FD 生成 | tests/tc01_basic/ | ✅ |
| TC02 | Waive 模块过滤 | tests/tc02_waive/ | ✅ |
| TC03 | Only 模块白名单 | tests/tc03_only/ | ✅ |
| TC04 | 位宽差异检测 | tests/tc04_width/ | ✅ |
| TC05 | 单模块场景 | tests/tc05_single/ | ✅ |
| TC06 | 空 SOC_IGT 处理 | tests/tc06_empty/ | ✅ |
| TC07 | 多驱动检测 | tests/tc07_multidriver/ | ✅ |
| TC08 | 标准 5 模块场景 | tests/test_standard_top.v | ✅ |
| TC09 | 双向信号跳过 | tests/test2_bidir_top.v | ✅ |
| TC10 | 顶层连接处理 | tests/test3_top_top.v | ✅ |
| TC11 | 拼接信号拆分 | tests/test6_concat.v | ✅ |
| TC12 | 大小写端口命名 | tests/test6_case_top.v | ✅ |
| TC13 | -link 参数 | tests/test7_link_top.v | ✅ |
| RT05 | 完整测试套件 | tests/run_full_tests.py | ✅ |

**测试规则：**
- ✅ 每次修改后运行回归测试
- ✅ 全部通过才能提交
- ✅ 新功能必须添加测试用例
- ✅ 修改功能必须调整测试用例

---
