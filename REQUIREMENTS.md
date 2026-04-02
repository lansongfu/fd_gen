# FD Generator - 需求规格说明书

**项目:** SoC 顶层 Feedthrough 自动生成工具  
**版本:** v1.0.0  
**日期:** 2026-04-02  
**作者:** 克劳 (木叶村火影助理)  
**GitHub:** https://github.com/lansongfu/fd_gen

---

## 📋 项目背景

在 SoC 顶层集成设计中，floorplan 确认后，有些子系统间无法直接连线，需要穿过中间的某些子系统才可以最终连接。这种操作称为 **Feedthrough (FD)**。

本工具通过脚本自动检测需要 FD 的信号，并生成中间的 FD 串线模块。

---

## 🎯 核心需求

### 输入文件

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `-top` | ✅ | - | 顶层网表（Verilog，含 `SOC_IGT comment list`） |
| `-floorplan` | ✅ | - | 相邻关系文件（每行：`模块名 相邻模块 1 相邻模块 2 ...`） |
| `-output` | ❌ | `fd_output/` | 输出目录 |
| `-maxfdnum` | ❌ | `3` | 最大允许穿过的中间模块数量 |
| `-h/--help` | ❌ | - | 显示帮助信息 |

### 输出文件

```
fd_output/
├── fd_modules/
│   ├── FD_CORE_CRG.v
│   ├── FD_MODULE1.v
│   └── ...
├── fd_path_report.txt
└── fd_generator.log
```

---

## 📝 输入格式详解

### 顶层网表（top.v）

```verilog
// ------------ begin SOC_IGT comment list ------------//
//INSTANCE(../crg/core_crg.v, CORE_CRG, U_CORE_CRG);
//CONNECT(w, wire1, U_CORE_CRG`out1, 32, o);
//CONNECT(w, wire1, U_MODULE1`in1, 32, i);
// ------------ end SOC_IGT comment list ------------//
```

**INSTANCE 行：**
- 格式：`//INSTANCE(源文件，模块定义名，例化名);`
- 提取：模块定义名（如 `CORE_CRG`），用于 FD 模块命名 `FD_CORE_CRG.v`

**CONNECT 行：**
- 格式：`//CONNECT(类型，信号名 [位选], 模块`端口，位宽，方向);`
- 参数说明：

| 参数 | 说明 | 处理规则 |
|------|------|---------|
| 1. 类型 | `i/o/b/w` | `w`=模块间连接，`i`=顶层输入，`o`=顶层输出，`b`=顶层 inout |
| 2. 信号名 | 支持位选、拼接、固定值、悬空 | 拼接需拆分，悬空/固定值跳过 |
| 3. 模块`端口 | 提取模块名（去 `U_`）和端口名 | 端口名用于 path report |
| 4. 位宽 | 信号位宽 | 与信号名位宽对比，不一致 WARNING |
| 5. 方向 | `i/o/b` | 决定流向，`b` 为双向全程 inout |

### Floorplan 文件（adjacency.txt）

```txt
CORE_CRG MODULE1 MODULE2
MODULE1 CORE_CRG MODULE3
MODULE2 CORE_CRG MODULE3
MODULE3 MODULE1 MODULE2
```

**规则：**
- 每行第一个词：模块名
- 后面所有词：与该模块相邻的模块列表
- 空格分隔（支持连续空格）
- 相邻关系是双向的（脚本自动处理）

---

## 🔧 核心功能

### 1. 相邻关系解析

- 解析 floorplan 文件
- 构建双向邻接表
- 自动去重

### 2. 顶层网表解析

- 解析 `SOC_IGT comment list` 注释块
- 提取 INSTANCE 信息（模块列表）
- 提取 CONNECT 信息（信号连接关系）
- 信号拼接拆分为独立信号

### 3. FD 信号检测

- 对每个信号，检查源模块和目的模块是否相邻
- 不相邻 → 需要 FD
- 使用 BFS 算法计算最短路径（带缓存优化）
- **BFS 缓存：** 相同模块对的路径只计算一次

### 4. 路径长度检查

- 检查最短路径的中间模块数量
- 中间模块数 ≤ `maxfdnum` → 生成 FD
- 中间模块数 > `maxfdnum` → ERROR，继续处理其他信号

### 5. FD 模块生成

- 按模块分组 FD 信号
- 每个穿过模块生成一个 FD 模块（如 `FD_MODULE2.v`）
- 所有穿过该模块的信号共用一个 FD 模块
- 自动推断信号方向

### 6. Path Report 生成

- 生成 `fd_path_report.txt`
- 一行一个连接的完整 FD 路径
- 包含起点端口、FD 端口、终点端口

### 7. 报告生成

- 生成 `fd_generator.log`
- 包含 WARNING 和 ERROR 汇总

---

## 📐 FD 模块结构

### 单向信号（小写）

```verilog
// FD_MODULE2.v - 信号 wire1 从 CORE_CRG 流向 MODULE3
module FD_MODULE2 (
    input  wire [31:0] fd_wire1_from_core_crg,
    output wire [31:0] fd_wire1_to_module3
);
    assign fd_wire1_to_module3 = fd_wire1_from_core_crg;
endmodule
```

### 单向信号（大写）

```verilog
// FD_MODULE2.v - 信号 WIRE1 从 CORE_CRG 流向 MODULE3
module FD_MODULE2 (
    input  wire [31:0] FD_WIRE1_FROM_CORE_CRG,
    output wire [31:0] FD_WIRE1_TO_MODULE3
);
    assign FD_WIRE1_TO_MODULE3 = FD_WIRE1_FROM_CORE_CRG;
endmodule
```

### 双向信号

```verilog
// FD_MODULE2.v - 信号 ARREADY 双向
module FD_MODULE2 (
    inout wire [1:0] FD_ARREADY_FROM_MODULE1,
    inout wire [1:0] FD_ARREADY_TO_CORE_CRG
);
    assign FD_ARREADY_TO_CORE_CRG = FD_ARREADY_FROM_MODULE1;
endmodule
```

**命名规则：**
- 模块名：`FD_<模块定义名>.v`
- 端口名：
  - 单向输入：`fd_<信号>_from_<模块>` 或 `FD_<信号>_FROM_<模块>`
  - 单向输出：`fd_<信号>_to_<模块>` 或 `FD_<信号>_TO_<模块>`
  - 双向：`FD_<信号>_FROM_<模块>` / `FD_<信号>_TO_<模块>`

---

## 📄 Path Report 格式

```txt
# fd_path_report.txt
# Format: start_port -> fd_port1 -> fd_port2 -> ... -> end_port

A.clk -> C.fd_wire1_from_a -> C.fd_wire1_to_b -> B.clk
A.wire1 -> C.fd_wire1_from_a -> C.fd_wire1_to_d -> D.fd_wire1_from_c -> D.fd_wire1_to_b -> B.wire1
A.arready <-> C.FD_ARREADY_FROM_A <-> C.FD_ARREADY_TO_D <-> D.FD_ARREADY_FROM_C <-> D.FD_ARREADY_TO_B <-> B.arready
```

**规则：**
- 一行一个连接
- 单向：`->`
- 双向：`<->`
- 模块名去掉 `U_` 前缀
- FD 模块用原模块名（如 `C` 而不是 `FD_C`）
- 端口名直接使用 FD 模块的端口名

---

## ⚠️ 边界情况处理

| 边界情况 | 处理方式 |
|---------|---------|
| **位宽不一致** | WARNING，以声明位宽为准 |
| **悬空/固定值** | 跳过，不处理 |
| **信号拼接** | 拆分为独立信号分别处理 |
| **直接相邻** | 不需要 FD，直接连线 |
| **无路径** | ERROR，该信号报错，继续处理其他 |
| **路径超长** | ERROR（中间模块数 > maxfdnum），继续处理其他 |
| **自连接** | 跳过，不需要 FD |
| **一对多信号** | 每个 (源，宿) 对独立 FD 路径 |
| **双向信号 (b)** | 全程 inout，简单 assign 直连 |
| **顶层连接** | 顶层本身不需要 FD 模块 |

---

## 🔄 去重逻辑

**去重 key：** `(信号名，端点 1，端点 2)` 的无序对

| 情况 | 处理 |
|------|------|
| `wire1`: A→B | 处理 |
| `wire1`: B→A | **跳过**（与 A→B 重复） |
| `wire1`: A→B 和 A→C | **都处理**（不同连接） |
| `wire1`: A→B 和 C→D | **都处理**（不同连接） |

---

## 🎨 大小写规则

**FD 端口命名大小写取决于信号名：**

| 信号名 | FD 端口命名 |
|--------|------------|
| `wire1`（全小写） | `fd_wire1_from_a`, `fd_wire1_to_b`（全小写） |
| `WIRE1`（全大写） | `FD_WIRE1_FROM_A`, `FD_WIRE1_TO_B`（全大写） |
| `Wire1`（混合） | `FD_WIRE1_FROM_A`, `FD_WIRE1_TO_B`（转全大写） |

**规则：**
- 全小写 → 全小写（包括 `fd_` 前缀）
- 全大写 → 全大写（包括 `FD_` 前缀）
- 混合大小写 → 全大写

**模块名：** 保持原样，不转换大小写

---

## 🛠️ 技术要求

### 语言版本

- **必须兼容:** Python 2.7
- **推荐:** Python 3.x

**注意事项:**
- 使用 `from __future__ import print_function` 实现兼容
- 不使用 Python 3 特有高级特性
- 字符串处理注意 Unicode 问题

### 依赖库

- **标准库优先** - 减少外部依赖
- `argparse`（Python 2.7 需特殊处理）

### 代码风格

- 模块化设计
- 清晰的函数注释
- 错误处理完善

---

## 📁 项目结构

```
fd_gen/
├── REQUIREMENTS.md       # 本文件
├── README.md             # 使用说明
├── fd_generator.py       # 主入口
├── parser.py             # 解析器（INSTANCE + CONNECT）
├── floorplan.py          # Floorplan 解析 + 邻接表
├── algorithm.py          # BFS 算法（带缓存）
├── generator.py          # Verilog 代码生成
├── report.py             # Path Report 生成
├── utils.py              # 工具函数
└── tests/                # 测试用例（不推送）
    ├── sample_top.v
    ├── sample_floorplan.txt
    └── expected_output/
```

---

## 🚀 开发计划

| 阶段 | 内容 | 交付物 | 状态 |
|------|------|--------|------|
| Phase 1 | 解析器（INSTANCE + CONNECT）+ 数据结构 | 可解析输入 | ⏳ |
| Phase 2 | floorplan 解析 + BFS 算法 + FD 检测 | FD 路径检测完成 | ⏳ |
| Phase 3 | Verilog 代码生成 | FD 模块输出 | ⏳ |
| Phase 4 | Path Report 生成 | fd_path_report.txt | ⏳ |
| Phase 5 | 日志 + 错误处理 | fd_generator.log | ⏳ |
| Phase 6 | 完整测试 + 调试 | 测试通过 | ⏳ |
| Phase 7 | GitHub 推送 + 文档 | 仓库发布 | ⏳ |

---

## ✅ 验收标准

1. **功能验收**
   - [ ] 能正确解析 `SOC_IGT comment list`
   - [ ] 能正确解析 floorplan 文件
   - [ ] 能正确检测需要 FD 的信号
   - [ ] 能生成正确的 FD 模块 Verilog
   - [ ] 能生成完整的 path report

2. **边界情况验收**
   - [ ] 位宽不一致时输出 WARNING
   - [ ] 无路径时输出 ERROR 但继续处理
   - [ ] 路径超长时输出 ERROR 但继续处理
   - [ ] 自连接信号被跳过
   - [ ] 一对多信号正确处理
   - [ ] 双向信号正确处理

3. **性能验收**
   - [ ] BFS 缓存生效，相同模块对不重复计算
   - [ ] 大规模信号（1000+）处理时间合理

4. **兼容性验收**
   - [ ] Python 2.7 下正常运行
   - [ ] Python 3.x 下正常运行

---

## 📅 更新日志

| 日期 | 版本 | 更新内容 |
|------|------|---------|
| 2026-04-01 | v0.1.0 | 初始版本，记录需求讨论结果 |
| 2026-04-02 | v1.0.0 | 完整需求规格，包含所有确认细节 |

---

## 📞 联系方式

**项目讨论:** QQ 私聊  
**火影:** E6D2F83F24DA26F8BA8073FD702D91F2  
**克劳:** 木叶村火影助理

---

**🍃 木叶村出品，必属精品！**
