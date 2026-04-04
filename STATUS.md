# FD Generator - 项目状态

_最后更新：2026-04-04_

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
├── tests/             # 测试用例（7/7 通过）
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

---

## 🚦 当前状态

- **版本:** v1.1.13
- **状态:** ✅ 已推送到 GitHub
- **测试:** 7/7 通过（100%）
- **GitHub:** https://github.com/lansongfu/fd_gen
- **最新提交:** `aa19dd2` - fix: Update VERSION to 1.1.13

---

## 🧪 测试覆盖

| 测试用例 | 状态 |
|---------|------|
| TC01 基本功能 | ✅ |
| TC02 waive 模块 | ✅ |
| TC03 only 模块 | ✅ |
| TC04 位宽差异 | ✅ |
| TC05 单模块 | ✅ |
| TC06 空 SOC_IGT | ✅ |
| TC07 多驱动 | ✅ |

---
