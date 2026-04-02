# FD Generator - 需求规格说明书

**项目:** SoC 顶层 Feedthrough 自动生成工具  
**版本:** v1.1.0  
**日期:** 2026-04-02（2026-04-02 更新）  
**Author:** Crow (Konoha Ninja)  
**GitHub:** https://github.com/lansongfu/fd_gen

---

## 📝 更新日志

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.1.0 | 2026-04-02 | 新增 `-link/-waive/-only/-autocase` 参数，修复双向信号处理，优化 TOP 连接逻辑 |
| v1.0.0 | 2026-04-01 | 初始版本，记录需求讨论结果 |

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
| `-link` | ❌ | `false` | 生成 `fd_top.v`，修改 CONNECT 注释（v1.1.0 新增） |
| `-waive` | ❌ | - | Waive 文件，排除模块（v1.1.0 新增） |
| `-only` | ❌ | - | Only 文件，白名单模块（v1.1.0 新增） |
| `-autocase` | ❌ | `false` | 保留信号大小写（v1.1.0 新增） |
| `-h/--help` | ❌ | - | 显示帮助信息 |
| `-version` | ❌ | - | 显示版本号 |

### 输出文件

```
fd_output/
├── fd_modules/
│   ├── fd_module1.v        # 注意：文件名小写（v1.1.0 变更）
│   ├── fd_module2.v
│   └── ...
├── fd_path_report.txt       # 使用实际端口名（v1.1.0 变更）
├── fd_top.v                 # 仅当 -link 启用时生成（v1.1.0 新增）
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

| 边界情况 | 处理方式 | 版本 |
|---------|---------|------|
| **位宽不一致** | WARNING，以第一个 CONNECT 声明的位宽为准（v1.1.0 明确） | v1.1.0 |

**位宽优先级说明（v1.1.0 明确）：**

当信号名位宽（如 `sig[31:0]`）与 CONNECT 声明位宽不一致时，**以第一个 CONNECT 的位宽为准**。

**原因：**
1. CONNECT 的位宽是显式声明的
2. 第一个 CONNECT 通常是信号源端的声明
3. 保持一致性，避免不同模块使用不同位宽

**示例：**
```verilog
//CONNECT(w, sig[31:0], U_A`out, 32, o);  // 使用 32
//CONNECT(w, sig[15:0], U_B`in, 16, i);   // WARNING: 位宽不一致 (32 vs 16)
// 最终 FD 模块使用 32 位宽
```
| **悬空/固定值** | 跳过，不处理 | v1.0.0 |
| **信号拼接** | 拆分为独立信号分别处理 | v1.0.0 |
| **直接相邻** | 不需要 FD，直接连线 | v1.0.0 |
| **无路径** | ERROR，该信号报错，继续处理其他 | v1.0.0 |
| **路径超长** | ERROR（中间模块数 > maxfdnum），继续处理其他 | v1.0.0 |
| **自连接** | 跳过，不需要 FD | v1.0.0 |
| **一对多信号** | 每个 (源，宿) 对独立 FD 路径 | v1.0.0 |
| **双向信号 (b)** | **完全跳过，不生成 FD**（v1.1.0 设计决策） | v1.1.0 |

**双向信号处理说明（v1.1.0 设计决策）：**

双向信号（`direction='b'`）需要三态门（tri-state buffer）处理，涉及方向控制逻辑，超出了 FD 工具的简单串线范围。

**处理方式：**
- 检测到双向信号时，直接跳过，不生成任何 FD 模块
- 日志记录：`"Signal 'xxx': bidirectional signal, skipping FD (per v1.1.0 design decision)."`
- 用户需要手动处理双向信号的 FD 逻辑

**原因：**
1. 双向信号需要方向控制（OE 信号）
2. 三态门逻辑复杂，容易出错
3. 不同设计风格的三态门实现不同
4. 安全起见，让用户手动处理更可靠

**示例：**
```verilog
// CONNECT 中 direction='b' 的信号
//CONNECT(b, bidir_sig, U_MODULE1`io, 8, b);

// 脚本会跳过此信号，不生成 FD 模块
// 用户需要手动创建 FD 模块并添加三态门逻辑
```
| **顶层连接** | 顶层本身不需要 FD 模块，通过相邻模块 FD 连接 | v1.1.0 |
| **多驱动信号** | ERROR（多个 output），跳过该信号 | v1.1.0 |

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
| Phase 1 | 解析器（INSTANCE + CONNECT）+ 数据结构 | 可解析输入 | ✅ |
| Phase 2 | floorplan 解析 + BFS 算法 + FD 检测 | FD 路径检测完成 | ✅ |
| Phase 3 | Verilog 代码生成 | FD 模块输出 | ✅ |
| Phase 4 | Path Report 生成 | fd_path_report.txt | ✅ |
| Phase 5 | 日志 + 错误处理 | fd_generator.log | ✅ |
| Phase 6 | 完整测试 + 调试 | 测试通过 | ✅ |
| Phase 7 | GitHub 推送 + 文档 | 仓库发布 | ✅ |
| Phase 8 | v1.1.0 新功能 | -link/-waive/-only/-autocase | ✅ |

---

## 🔧 v1.1.0 新增功能详解

### 1. `-link` 参数

**功能：** 生成 `fd_top.v`，修改 CONNECT 注释以反映 FD 连接

**实现：**
- 复制 `top.v` → `fd_top.v`
- 修改起始模块的 CONNECT（wire 名改为 FD 端口名）
- 为中间 FD 模块添加新的 CONNECT

**示例：**
```verilog
// 原始 top.v
//CONNECT(w, clk, U_CORE_CRG`clk_out, 1, o);

// fd_top.v（修改后）
//CONNECT(w, fd_clk_from_core_crg, U_CORE_CRG`clk_out, 1, o);
//CONNECT(w, fd_clk_from_core_crg, U_MODULE1`fd_from_core_crg_clk, 1, i);
```

### 2. `-waive` 参数

**功能：** 排除指定模块，不在这些模块中生成 FD

**文件格式：** 空格分隔的模块名列表

**示例：**
```txt
# waive.txt
MODULE1 MODULE3
```

**优先级：** `-only` > `-waive`（同时使用时 waive 被忽略）

### 3. `-only` 参数

**功能：** 仅允许指定模块生成 FD（白名单）

**文件格式：** 空格分隔的模块名列表

**示例：**
```txt
# only.txt
MODULE2
```

### 4. `-autocase` 参数

**功能：** 根据信号名大小写决定 FD 端口命名风格

**规则：**
- 全小写信号 → 全小写端口（`fd_from_a_clk`）
- 全大写/混合信号 → 全大写端口（`FD_FROM_A_CLK`）

**默认：** 不使用 `-autocase` 时，全部使用小写

### 5. 双向信号处理（变更）

**v1.0.0 需求：** "双向信号全程 inout，简单 assign 直连"

**v1.1.0 变更：** **完全跳过双向信号，不生成 FD**

**原因：** 双向信号需要三态门处理，超出 FD 工具范围

**实现：**
```python
if any(c.direction == 'b' for c in conns):
    logger.info("Signal '{}': bidirectional signal, skipping FD.".format(signal_name))
    continue
```

### 6. TOP 连接优化

**功能：** 正确处理顶层连接（TOP 作为虚拟模块）

**实现：**
- 提取 `_find_path_to_top()` 和 `_find_path_from_top()` 函数
- TOP 本身不需要 FD 模块
- 信号通过 TOP 相邻模块的 FD 连接到 TOP

### 7. Path Report 端口名（修复）

**v1.0.0 问题：** 使用信号名而非实际端口名

**v1.1.0 修复：** 从 `connections` 提取实际端口名

**示例：**
```
# Before
A.wire1 -> C.fd_wire1_from_a -> B.wire1

# After
A.clk_out -> C.fd_clk_from_a -> B.clk_in
```

### 8. FD 模块文件名（变更）

**v1.0.0：** `FD_MODULE1.v`（大写）

**v1.1.0：** `fd_module1.v`（小写）

**原因：** Verilog 文件名通常小写，避免大小写敏感问题

---

## ❓ 待确认问题

### 1. 位宽优先级

**当前实现：** 使用第一个 CONNECT 的位宽

**需求描述：** "以声明位宽为准"

**问题：** "声明位宽"指什么？
- 第一个 CONNECT 的位宽？✅ 当前实现
- 信号本身的位宽（从信号名解析）？
- CONNECT 和信号名位宽不一致时以哪个为准？

**建议：** 明确为"以第一个 CONNECT 的位宽为准"

### 2. 双向信号处理

**v1.0.0 需求：** "全程 inout，简单 assign 直连"

**v1.1.0 实现：** 完全跳过

**问题：** 是否需要重新确认需求？
- 如果双向信号需要 FD，应该生成三态门逻辑
- 当前跳过是最安全的处理方式

**建议：** 确认双向信号是否真的需要 FD

### 3. 一对多信号处理

**当前实现：** 每个 (源，宿) 无序对独立处理

**示例：**
```
信号 wire1：A→B 和 A→C
- A→B 路径：生成 FD
- A→C 路径：生成 FD
```

**问题：** 是否需要特殊处理？
- 当前处理正确
- 但 FD 模块中会有多个端口对

**建议：** 确认当前处理符合预期

### 4. TOP 连接的 direction

**问题：** TOP 连接的 CONNECT 的 direction 是什么？
- `i`：顶层输入（信号从子模块流向 TOP）
- `o`：顶层输出（信号从 TOP 流向子模块）
- `b`：顶层 inout（双向）

**当前实现：** 根据 direction 判断信号流向

**建议：** 确认 TOP 连接的 direction 使用规则

### 5. 多驱动检测

**当前实现：** 检测多个 `direction='o'` 且 `is_top=False` 的连接

**问题：**
- 如果一个是 TOP output，一个是子模块 output，是否算多驱动？
- 当前排除 TOP 连接

**建议：** 确认多驱动检测规则

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
**Hokage (User):** E6D2F83F24DA26F8BA8073FD702D91F2  
**Assistant:** Crow

---

**Quality Guaranteed!**
