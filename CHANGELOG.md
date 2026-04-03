# CHANGELOG

All notable changes to FD Generator will be documented in this file.

## [v1.1.13] - 2026-04-03

### Fixed
- **CONNECT 对齐格式错误**
  - 问题：逗号位置没有对齐，空格填充位置错误
  - 修复：字段左对齐，字段后补空格，然后逗号 + 空格
  - 格式：`field + padding + ", " + next_field`
  - 效果：所有逗号现在在固定列位置对齐

### Changed
- 优化 CONNECT 格式化逻辑，确保美观和对齐

### Tested
- BFS 稳定性测试：10/10 一致
- 对齐格式验证：通过
- 全面测试通过率：6/6 (100%)

## [v1.1.2] - 2026-04-03

### Fixed
- **CONNECT modify 正则表达式不支持位宽格式**
  - 问题：正则 `(\w+)` 无法匹配 `ab2[2:0]` 等位宽格式
  - 修复：改为 `([\w\[\]:]+)` 支持位宽格式
  - 增强：添加 base wire 匹配逻辑，`ab2[2:0]` 可以匹配到 `ab2`

- **CONNECT 扫描过早终止**
  - 问题：遇到空行或注释就停止扫描 CONNECT 行
  - 修复：跳过空行和注释，继续扫描直到非 CONNECT 内容

- **测试脚本路径错误**
  - 问题：`FD_GEN` 指向 `tests/fd_generator.py`（不存在）
  - 修复：改为 `fd_generator.py`（tests 目录外）

### Tested
- 全面测试通过率：6/6 (100%)
- 测试覆盖：核心功能、Waive/Only、位宽格式

## [v1.1.1] - 2026-04-03

### Fixed
- **严重 Bug 修复**: 一对多信号（如 TOP 输入到多个模块）中，FD 模块的原始连接被错误修改
  - 问题：对于 ata 信号（TOP→A/B/C/D/E），当只有部分路径需要 FD 时（如 TOP→A 经过 B），B 模块的原始 ata 连接被错误改为 `fd_from_b_ata`
  - 修复：在 `generate_fd_top()` 函数中，根据 `conn_type` 正确识别源端模块，只修改真正的源端连接，不修改 FD 模块的原始连接
  - 验证：B/C/D/E 模块的原始 ata 连接现在都正确保持为 `ata`

- **Waive 功能修复**: FD 模块生成时未检查 waive_modules
  - 修复：在 FD 模块生成循环中添加 waive_modules 检查
  - 验证：waive B 后正确生成 fd_d.v 和 fd_e.v，路径绕过 B

- **Only 功能修复**: FD 模块生成时未检查 only_modules
  - 修复：在 FD 模块生成循环中添加 only_modules 检查
  - 验证：only B 后只生成 fd_b.v

- **路径查找修复**: `_find_path_to_top` 和 `_find_path_from_top` 函数未过滤 only_modules
  - 修复：在两个函数中添加 valid_top_adjacent 过滤逻辑
  - 验证：only C 时正确报告 9 个错误（不可行场景）

### Changed
- 改进错误报告：不可行场景现在会报告详细的路径错误信息

### Tested
- 全面测试通过率：11/11 (100%)
- 测试覆盖：核心功能、Waive/Only、连接验证、回归测试、边界情况

---

## [v1.1.0] - 2026-03-23

### Added
- 初始发布版本
- 支持 FD 信号自动检测和路径计算
- 支持 `-link` 功能生成完整的 fd_top.v
- 支持 `-waive` 功能跳过指定模块
- 支持 `-only` 功能限制 FD 模块范围
- 支持位宽信号处理
- 支持双向信号处理
- 生成 FD 模块和路径报告

### Features
- BFS 最短路径算法
- 一对多信号处理（TOP 输入/输出）
- CONNECT 类型自动判断（i/o/w）
- 网络名自动命名（TOP 用原名，其他用 fd_from_X）
- 详细的日志输出和错误报告
