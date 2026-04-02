# FD Generator

**SoC Feedthrough Auto Generation Tool**

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/lansongfu/fd_gen)
[![Python](https://img.shields.io/badge/python-2.7%2B-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

---

## 📋 简介

FD Generator 是一个用于 SoC 顶层集成设计的自动化工具，可自动检测需要 Feedthrough (FD) 串线的信号，并生成中间的 FD 模块 Verilog 代码。

**应用场景：**
- SoC 顶层集成
- Floorplan 确认后模块间信号连接
- 自动插入 FD 串线模块

---

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/lansongfu/fd_gen.git
cd fd_gen
```

### 基本用法

```bash
python fd_generator.py -top <top.v> -floorplan <adjacency.txt>
```

### 完整参数

```bash
python fd_generator.py \
    -top top.v \                    # 顶层网表（必需）
    -floorplan adjacency.txt \      # 相邻关系文件（必需）
    -output fd_output/ \            # 输出目录（可选，默认：fd_output/）
    -maxfdnum 3 \                   # 最大中间模块数（可选，默认：3）
    -h                              # 显示帮助
```

---

## 📝 输入文件格式

### 1. 顶层网表（top.v）

使用特殊的 `SOC_IGT comment list` 注释块定义模块和连接：

```verilog
// ------------ begin SOC_IGT comment list ------------//
//INSTANCE(../crg/core_crg.v, CORE_CRG, U_CORE_CRG);
//CONNECT(w, awaddr, U_CORE_CRG`awaddr, 32, o);
//CONNECT(w, awaddr, U_MODULE1`awaddr, 32, i);
// ------------ end SOC_IGT comment list ------------//
```

**INSTANCE 格式：**
```
//INSTANCE(源文件路径，模块定义名，例化名);
```

**CONNECT 格式：**
```
//CONNECT(类型，信号名，模块`端口，位宽，方向);
```

| 参数 | 说明 |
|------|------|
| 类型 | `i`=顶层输入，`o`=顶层输出，`b`=顶层 inout，`w`=模块间连接 |
| 信号名 | 支持位选（`[31:0]`）、拼接（`{sig1,sig2}`） |
| 模块`端口 | 模块名（带 `U_` 前缀）+ 反引号 + 端口名 |
| 位宽 | 信号位宽（如 `32`） |
| 方向 | `i`=输入，`o`=输出，`b`=双向 |

### 2. Floorplan 文件（adjacency.txt）

定义模块间的物理相邻关系：

```txt
CORE_CRG MODULE1
MODULE1 CORE_CRG MODULE2
MODULE2 MODULE1 MODULE3
MODULE3 MODULE2
```

**格式：**
- 每行第一个词：模块名
- 后面所有词：与该模块相邻的模块列表
- 空格分隔（支持连续空格）
- 相邻关系自动视为双向

---

## 📤 输出文件

```
fd_output/
├── fd_modules/
│   ├── FD_CORE_CRG.v
│   ├── FD_MODULE1.v
│   └── ...
├── fd_path_report.txt
└── fd_generator.log
```

### FD 模块（fd_modules/*.v）

```verilog
// FD Module: MODULE1
module FD_MODULE1 (
    input  wire [31:0] fd_awaddr_from_core_crg,
    output wire [31:0] fd_awaddr_to_module2
);
    assign fd_awaddr_to_module2 = fd_awaddr_from_core_crg;
endmodule
```

**端口命名规则：**
- 全小写信号：`fd_<signal>_from_<module>` / `fd_<signal>_to_<module>`
- 全大写/混合信号：`FD_<SIGNAL>_FROM_<MODULE>` / `FD_<SIGNAL>_TO_<MODULE>`

### Path Report（fd_path_report.txt）

```txt
# fd_path_report.txt
CORE_CRG.awaddr -> MODULE1.fd_awaddr_from_core_crg -> MODULE1.fd_awaddr_to_module2 -> MODULE2.awaddr
MODULE1.arready <-> MODULE2.FD_ARREADY_FROM_MODULE1 <-> MODULE2.FD_ARREADY_TO_MODULE3 <-> MODULE3.arready
```

**格式：**
- 一行一个连接的完整 FD 路径
- 单向信号：`->`
- 双向信号：`<->`

---

## ⚙️ 高级选项

### 最大 FD 模块数（-maxfdnum）

限制信号穿过的最大中间模块数量：

```bash
python fd_generator.py -top top.v -floorplan adj.txt -maxfdnum 5
```

**默认值：** 3

**场景：** 避免路径过长导致时序问题

---

## ⚠️ 边界情况处理

| 情况 | 处理方式 |
|------|---------|
| 位宽不一致 | WARNING，使用声明位宽 |
| 悬空/固定值 | 跳过 |
| 信号拼接 | 拆分为独立信号处理 |
| 直接相邻 | 不需要 FD |
| 无路径 | ERROR，继续处理其他信号 |
| 路径超长 | ERROR，继续处理其他信号 |
| 双向信号 | inout + `<->` 箭头 |

---

## 🧪 测试

运行测试用例：

```bash
cd tests
python3 ../fd_generator.py -top sample_top.v -floorplan sample_floorplan.txt -output test_output
```

查看测试报告：`tests/TEST_REPORT.md`

---

## 📊 性能优化

**BFS 路径缓存：** 相同模块对的路径只计算一次，大幅提升处理速度。

**测试数据：**
- 100 个信号，5 个模块
- 无缓存：BFS 执行 ~100 次
- 有缓存：BFS 执行 ~10 次
- **性能提升：约 10 倍**

---

## 🛠️ 技术规格

- **语言：** Python 2.7+（兼容 Python 3.x）
- **依赖：** 标准库（无外部依赖）
- **许可证：** MIT

---

## 📝 更新日志

### v1.0.0 (2026-04-02)
- ✅ 初始版本发布
- ✅ 完整解析器（INSTANCE + CONNECT）
- ✅ BFS 最短路径算法（带缓存）
- ✅ FD 模块自动生成
- ✅ Path Report 生成
- ✅ 大小写规则
- ✅ 错误处理（WARNING/ERROR）

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📞 联系

**Author:** Crow (Konoha Ninja)  
**GitHub：** https://github.com/lansongfu/fd_gen

---

**Quality Guaranteed!**
