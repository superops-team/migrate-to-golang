# Telemetry 评分模型与边界语义加固（migrate-to-golang）

## 1. 文档状态

| 项 | 值 |
|---|---|
| 状态 | 已实施 |
| 类型 | Bug 修复（附带行为保持型重构） |
| 创建日期 | 2026-11-06 |
| 关联项 | Brooks-Lint 审查发现（read-only 计划 `690931a5…` / `7ad8b2a3…`）；基线提交 `0150ca8` |
| 版本关系 | 首次设计；替代无 |
| 仓库 | `superops-team/migrate-to-golang`（工作分支 `fix/review-findings`） |

## 2. 问题、影响与证据

### 2.1 实际行为与期望行为

| 编号 | 条件 | 实际行为 | 期望行为 |
|---|---|---|---|
| B-1 | 任一评分维度平均分落在 50–54 / 65–69 / 75–79 / 85–89 | 维度卡显示后端等级（如 `A-`/`B+`/`B`/`C`/`D`），汇总行显示 JS 计算的另一等级（如 `B`/`C`/`D`/`F`），同一份报告自相矛盾 | 同一分数在同一报告内只有一个等级 |
| B-2 | `scan-codebase --phase after --dir` 指向空目录或无 `.go` 文件 | JSON 输出 `no_unsafe: true`、`unsafe_imports: null`、`scanned: false`；"零文件"被判为"100% 安全" | 无文件时不给出安全结论，`no_unsafe` 与 `unsafe_imports` 同为 `null` |
| B-3 | 扫描到的 Go 文件中函数识别数为 0（如仅 `package`+`var`/`const`） | `avg_fn_loc` 回退为 `code_loc`（如 3），伪造成"平均函数 3 行" | 无函数时 `avg_fn_loc = null` |
| B-4 | 任意报告字段语义 | 字段名为 `branch_coverage_pct`，而 `SKILL.md`/`guide` 声明度量的是 `>= 95% statement coverage` | 字段名与文档使用同一语义（statement coverage） |

### 2.2 影响范围与严重性

- 受影响对象：使用 `scripts/telemetry.py render-infographic` 产出 `migration_infographic.html` 的 skill 使用者；以及依赖 `migration_telemetry.json` 字段的下游消费方。
- 严重性：B-1 产生用户可见的错误结论（同一报告等级矛盾）；B-2/B-3 在空数据/正则漏识别时产出误导性评分（安全维度与认知简化维度）；B-4 影响对外表述准确性。
- 环境：本地 CLI（`python3` 标准库），无线上部署形态。频率：B-1 在约 24.7%（25/101）的整数分数上必现；B-2/B-3 在对应输入下必现。

### 2.3 复现步骤和证据

下表中的 `path:line` 均以基线提交 `0150ca8` 为准；本次重构后行号已位移，复核时用 `git show 0150ca8:<path>` 回溯。

| ID | 类型 | 结论 | 精确证据 | 设计影响 | 验证/关闭方式 |
|---|---|---|---|---|---|
| FACT-1 | 已验证事实 | `grade_from_score` 为 9 档（含 A-、B+），阈值 95/90/85/80/75/65/50 | `scripts/telemetry.py:64-79` | 后端写入各维度 `before_grade`/`after_grade` | 已验证（代码阅读） |
| FACT-2 | 已验证事实 | 模板 JS `gradeFromScore` 为 7 档（无 A-/B+，阈值 95/90/80/70/55），且被汇总行调用 | `references/infographic_template.html:873-882`、调用点 `:1066-1071` | 同一报告两套等级算法 | 已验证（node 执行对比） |
| FACT-3 | 已验证事实 | 101 个整数分数中有 25 个两处等级不一致（50–54、65–69、75–79、85–89 区段） | 复现命令见下；实测输出 `mismatched scores: 25/101`，样例 `score=50: python='D' vs js='F'` | 必须消除双实现 | 已验证（node v22 执行） |
| FACT-4 | 已验证事实 | 空目录扫描产出 `no_unsafe: true` 且 `unsafe_imports: null` | `scripts/telemetry.py:415-416`；实测 JSON 同 B-2 | 需修正空数据语义 | 已验证（命令复现） |
| FACT-5 | 已验证事实 | `avg_fn_loc` 在有代码但零函数时等于 `code_loc` | `scripts/telemetry.py:395-397`；实测 `code_loc=3`、`avg_fn_loc=3` | 需修正零函数语义 | 已验证（命令复现） |
| FACT-6 | 已验证事实 | 字段名 `branch_coverage_pct` 与文档 `statement coverage` 不一致 | `scripts/telemetry.py:204,447,449,522,811`；`SKILL.md:57-59`；`references/pgo_and_telemetry_guide.md:93` | 改名需兼容旧文件 | 已验证（代码阅读） |
| FACT-7 | 已验证事实 | 仓库不存在任何测试文件与 CI 工作流 | `find . -name '*test*'` 为空；`.github/` 不存在 | 无默认回归门禁 | 已验证（文件系统取证） |
| FACT-8 | 已验证事实 | `compute_derived_metrics` 单函数 384 行，`analyze_directory` 单函数 179 行 | `scripts/telemetry.py:644-1028`、`:253-431` | 拆分不改输出结构 | 已验证（行号核对） |
| FACT-9 | 已验证事实 | `latent_bugs_found` 存在两处写入路径 | `scripts/telemetry.py:456-463`、`:483-489` | 收敛为单点写入 | 已验证（代码阅读） |
| FACT-10 | 已验证事实 | guide 目录硬编码行号 `Lines 33-102` 等 | `references/pgo_and_telemetry_guide.md:10-29` | 文档维护风险 | 已验证（代码阅读） |

复现命令（B-1）：

```bash
cd /Users/bytedance/DoubaoWork/chats/2026-11-05/new-chat-1/migrate-to-golang
python3 - <<'PY'
import re, subprocess, sys
sys.path.insert(0, "scripts")
import telemetry
tpl = open("references/infographic_template.html", encoding="utf-8").read()
js_fn = re.search(r"function gradeFromScore\(s\) \{.*?\n    \}", tpl, re.S).group(0)
open("/tmp/grade.js","w").write(js_fn + "\nfor (let s=0;s<=100;s++) console.log(s+' '+gradeFromScore(s));\n")
out = subprocess.run(["node","/tmp/grade.js"], capture_output=True, text=True).stdout
js = {int(l.split()[0]): l.split()[1] for l in out.strip().splitlines()}
print(sum(1 for s in range(101) if telemetry.grade_from_score(s) != js[s]))
PY
```

复现命令（B-2 / B-3）：

```bash
python3 scripts/telemetry.py init --telemetry /tmp/t.json --project-name repro --legacy-lang "C++"
mkdir -p /tmp/empty_go && python3 scripts/telemetry.py scan-codebase --telemetry /tmp/t.json --phase after --dir /tmp/empty_go
printf 'package main\n\nvar x = 1\n\nconst y = 2\n' > /tmp/nofunc.go
```

## 3. 根因与防线缺口

### 3.1 已确认根因（均有 FACT 证据）

| 编号 | 缺陷 | 机制 |
|---|---|---|
| C-1 | B-1 | 等级映射被复制到 Python 与 HTML JS 两处（FACT-1/2），且阈值表各自独立演进后分叉（FACT-3）；JS 版本被汇总行直接调用，与维度卡的 Python 写入值并存 |
| C-2 | B-2 | `no_unsafe` 用 `unsafe_imports == 0` 无条件推导，而 `unsafe_imports` 在 `num_files==0` 时被置为 `None`，两者语义源不同导致自相矛盾（FACT-4） |
| C-3 | B-3 | `max(1, fn_count)` 作为除数兜底，`fn_count==0` 时把 `total_code` 当成均值返回（FACT-5） |
| C-4 | B-4 | 字段名沿用了"branch"的历史命名，而实现与文档语义均为语句覆盖率（FACT-6） |

### 3.2 为什么现有防线未拦截

仓库没有任何自动化测试与 CI（FACT-7），评分逻辑与模板 JS 的耦合只靠人工全链路冒烟验证；冒烟用例未入库，无法在字段或阈值变更时自动发现分叉。

### 3.3 GateGap 闭环

状态：`inconclusive`。判定理由：仓库当前不存在可被"放行"的默认自动化门禁（无测试套件、无 CI 工作流，FACT-7），因此无法取得"门禁放行 faulty state"的证据。本次新增的 `tests/test_telemetry.py` 将作为该缺陷类别的首个稳定 check 承载点，但不宣称运行态 GateGap 闭环，也不登记 `GG-N`。

## 4. 目标、非目标与修复范围

### 4.1 目标

1. 同一分数在 `migration_infographic.html` 内只产生一个等级（维度卡与汇总行一致），25/101 的不一致降为 0。
2. 空数据与零函数输入不再产生"100% 安全"与伪 `avg_fn_loc` 结论（B-2/B-3 复现输入输出 `null`）。
3. 覆盖率字段语义与文档统一为 statement coverage，且旧 telemetry JSON 仍可正常渲染。
4. 新增可回归测试套件，覆盖上述缺陷与既有评分分支。

### 4.2 非目标

- 不重做信息图视觉设计、不调整评分权重数值（权重仅提取为具名常量，值不变）。
- 不将全量遥测数据改造为 TypedDict/dataclass 类型模型（成本高、收益低于本次范围）。
- 不引入第三方测试/校验依赖（保持标准库可运行）。
- 不与上游 `migrate-to-rust` 做行为对齐（本仓库已独立演进）。

### 4.3 范围

| 范围 | 内容 |
|---|---|
| 范围内 | `scripts/telemetry.py`（评分/扫描/渲染入口）、`references/infographic_template.html`（等级与字段消费）、`references/pgo_and_telemetry_guide.md`（目录行号）、新增 `tests/`、新增 `prd-spec/` 文档 |
| 范围外 | `SKILL.md` 的主体流程（仅接受必要的字段名表述同步）、README 文案重写、Go 侧被测代码生成逻辑 |

## 5. 修复方案

### 5.1 方案与机制

| 编号 | 修复要求 | 机制 | 生效边界 |
|---|---|---|---|
| FR-1 | 等级单一来源 | 删除模板 JS `gradeFromScore`；后端在 `compute_derived_metrics` 中一次性生成 8 维度等级与 `summary_grade`（基于同一 `grade_from_score`），汇总行直接消费 JSON 字段 | `render-infographic` 输出的 HTML 与 JSON |
| FR-2 | 空数据语义 | `no_unsafe` 仅在 `num_files > 0` 时为布尔，否则 `None`；`avg_fn_loc` 要求 `fn_count > 0`，否则 `None` | `scan-codebase` 输出 |
| FR-3 | 覆盖率命名 | 新键 `statement_coverage_pct`；读取时回退旧键 `branch_coverage_pct`；写入时双写新键（旧键保留一版兼容期） | JSON schema（向后兼容） |
| FR-4 | 评分函数拆分 | `compute_derived_metrics` 拆为 `_score_speed/_score_memory/_score_safety/_score_parity/_score_quality/_score_hygiene/_score_simplicity/_score_cost` + `_build_scorecard`，编排函数 ≤ 60 行，单维度函数 ≤ 60 行 | 内部结构；JSON 输出结构不变 |
| FR-5 | 扫描函数拆分 | `analyze_directory` 拆为 `iter_source_files`、`classify_line`、`track_nesting`、`summarize_metrics`，输出字段与算法不变 | 内部结构；扫描结果不变 |
| FR-6 | 权重常量 | 评分公式中的魔法数字提取为模块级具名常量（值不变） | 内部结构 |
| FR-7 | 派生字段单点写入 | `latent_bugs_found` 仅在 `log-opportunity` 写入；`scan-codebase` 只读不写 | 内部结构 |
| FR-8 | 文档目录 | 移除 `pgo_and_telemetry_guide.md` 目录中的 `Lines N-M` 硬编码行号，保留锚点 | 文档 |
| FR-9 | 回归测试 | 新增 `tests/test_telemetry.py`（unittest），覆盖扫描分支、评分边界、渲染替换、等级档位 | 测试套件 |

### 5.2 接口、数据与错误语义

| 项 | 契约 |
|---|---|
| `census.after.no_unsafe` | `bool`（扫描到 ≥1 个文件时）或 `null`（未扫描/零文件） |
| `census.after.avg_fn_loc` | 正整数（存在函数时）或 `null`（无函数/未扫描） |
| `census.after.statement_coverage_pct` | `float 0–100` 或 `null`；`branch_coverage_pct` 保留为兼容别名（下一主版本移除） |
| `census.before.latent_bugs_found` | 唯一写入方为 `log-opportunity`；`scan-codebase` 不再写入，未记录时保持 `null`（报告显示 `Audit Not Measured`） |
| `scorecard[i].before_grade` / `after_grade` | 由 `grade_from_score` 生成，9 档；`null` 分数时为 `N/A` |
| `overall` | 新增顶层对象：`before_avg`/`before_grade`/`after_avg`/`after_grade`，模板汇总行直接消费 |
| `summary_grade` | 新增顶层字段：`overall.after_grade` 的别名，逐字与评测卡同源 |
| 错误语义 | 既有 `TelemetryError` 行为不变；空目录不再被视为成功安全证据，但也不新增报错（保持扫描语义） |

版本兼容：旧 `migration_telemetry.json`（仅含 `branch_coverage_pct`）在新版本可正常渲染（读取回退）；新文件同时写 `statement_coverage_pct` 与 `branch_coverage_pct`，模板优先读新键。

### 5.3 备选方案与取舍

| 方案 | 正确性 | 回归面 | 兼容/维护 | 结论 |
|---|---|---|---|---|
| A（采用）：后端单一等级来源 + JSON 消费 | 高（一处定义） | 模板 JS 小改、JSON 增 `summary_grade` | 新增字段向后兼容 | 采用 |
| B：模板保留 JS 实现但将其阈值改为与 Python 一致 | 中（仍双实现，未来再分叉） | 小 | 长期维护成本高 | 放弃 |
| C：把等级完全交给前端，从 JSON 移除 grade 字段 | 中（后端不再单一来源） | 需改所有读取方 | 破坏既有消费方 | 放弃 |

重新评估条件：若未来需要多语言模板或前端独立渲染，再考虑把等级迁移为共享生成逻辑。

## 6. 边界、失败与恢复

| 场景 | 处理 | 状态/信号 | 恢复 |
|---|---|---|---|
| 扫描目录为空 | 输出零文件指标，`no_unsafe=null`、`avg_fn_loc=null` | JSON `scanned=false`；CLI 正常返回 0 | 修正目录参数后重扫 |
| 扫描目录不存在 | 抛出 `TelemetryError`（既有行为） | CLI 退出码 1，stderr 提示 | 修正 `--dir` |
| 旧 telemetry 文件缺新键 | 渲染时回退读 `branch_coverage_pct` | 报告正常显示覆盖率 | 重新 `scan-codebase` 写新键 |
| 模板被替换/占位符缺失 | `render_infographic_from_template` 原样返回未替换 HTML | 无报错但内容为空 JSON | 恢复默认模板 |
| 部分维度无数据 | 该维度 `score=null`，等级 `N/A`，不参与平均 | 汇总行仅对已测量维度取平均 | 补跑对应阶段遥测 |

## 7. 回归风险、兼容、迁移与回滚

- 行为变化：等级一致性（修复）、空数据返回 `null`（修复）、字段新增（兼容）。评分数值不变（FR-4/5/6 为行为保持型重构，用 golden 对比验证）。
- 可见行为变化一处：`scan-codebase --phase before` 不再写 `latent_bugs_found`。若无 `log-opportunity` 记录，报告该处从原先的 `0 Bugs` 变为 `Audit Not Measured`；有记录时数值不变（唯一来源 `log-opportunity`）。这是 FR-7 的预期结果，与"零数据不伪装"一致。
- 受影响调用方：`render-infographic` 的模板消费方；直接读 JSON 的下游。旧字段保留一版过渡期。
- 回滚：分支 `fix/review-findings` 独立于 `main`，回滚即丢弃分支或 `git revert` 合并提交；无持久化数据迁移，无不可逆状态。

## 8. 安全、可观测性与发布检查

- 安全：不适用——本地 CLI 工具，无网络、无身份、无外部输入信任边界；唯一外部输入为本地文件路径，保持既有 `TelemetryError` 校验。
- 可观测性/发布：不适用——无部署形态。验证信号以测试输出与 CLI 命令结果为准（见第 10 节）。

## 9. 实施计划与影响范围

| 阶段 | 内容 | 前置 | 完成证据 | 停止点 |
|---|---|---|---|---|
| P1 测试骨架（红） | 建 `tests/test_telemetry.py`，先写 B-1/B-2/B-3 失败用例 | 无 | 实测 6 failures + 1 error（预期失败） | 若环境无 `python3` 则停 |
| P2 缺陷修复 | FR-1/2/3 | P1 红态证据 | 13 项用例转绿（11 tests OK）；node 对比 0 不一致 | 出现非预期回归则停 |
| P3 结构重构 | FR-4/5/6/7/8 | P2 绿 | golden diff 0（census/8 维度/ROI/benchmarks/全 scorecard 字段） | golden 差异出现则停 |
| P4 集成验证 | 端到端冒烟：init→scan(before/after)→log-benchmark/log-test-run/log-parity-run/log-spotlight/set-story→render | P3 | 13 条 CLI 命令退出码均为 0；渲染报告 `overall` = before 70→C / after 90→A | 渲染失败则停 |
| P5 收尾 | 汇总证据；不提交/推送（未获授权） | P4 | 待用户决定提交范围 | — |

影响范围（已确认）：`scripts/telemetry.py`、`references/infographic_template.html`、`references/pgo_and_telemetry_guide.md`、新增 `tests/`、新增 `prd-spec/`。

影响范围（已确认）：`scripts/telemetry.py`、`references/infographic_template.html`、`references/pgo_and_telemetry_guide.md`、新增 `tests/`、新增 `prd-spec/`。

## 10. 验收标准与防回归验证

| ID | Given | When | Then | 验证方法/命令 | 环境 |
|---|---|---|---|---|---|
| AC-1 | 8 维度分数构造覆盖 50–54/65–69/75–79/85–89 | 调用后端等级函数与模板汇总行数据源 | 同一分数等级完全一致；不一致计数 = 0 | `python3 -m unittest tests.test_telemetry` 中断言；node 对比脚本 | 本地 |
| AC-2 | 空目录 | `scan-codebase --phase after` | `no_unsafe=null` 且 `unsafe_imports=null` | unittest 用例 + CLI 复现命令 | 本地 |
| AC-3 | 零函数 Go 文件 | `scan-codebase --phase after` | `avg_fn_loc=null`，`code_loc>0` | unittest 用例 | 本地 |
| AC-4 | 旧 JSON 仅含 `branch_coverage_pct` | `render-infographic` | 报告覆盖率为该值，无 `null` 丢失 | unittest + CLI | 本地 |
| AC-5 | 完整遥测（含 4 阶段 benchmark） | 重构前后渲染 | 除新增 `summary_grade`/新键字段外，JSON 数值与结构一致 | golden JSON diff | 本地 |
| AC-6 | 标准 fixture | 运行全部 unittest | 全部通过，0 失败 | `python3 -m unittest discover tests -v` | 本地 |
| AC-7 | 端到端 fixture | init→scan→4 类 log→render | 命令退出码 0，HTML 含注入 JSON 且等级一致 | CLI 冒烟脚本断言 | 本地 |
| AC-8 | 无 `log-opportunity` 记录 | `scan-codebase --phase before` 后读账本 | `latent_bugs_found` 保持 `null`（唯一写入方为 `log-opportunity`） | unittest `test_scan_does_not_duplicate_latent_bug_writes` | 本地 |

## 11. 风险与待确认项

| ID | 触发条件 | 概率/影响 | 缓解措施 | 监测信号 | 兜底/回滚 |
|---|---|---|---|---|---|
| RISK-1 | 重构改动评分公式副作用 | 中/中 | golden 对比锁定数值；单维度小函数便于定位 | unittest + JSON diff | 回到 P2 前状态 |
| RISK-2 | 字段双写期下游仍读旧键 | 低/低 | 保留 `branch_coverage_pct` 一版兼容期，文档标注移除计划 | 契约测试读取旧键用例 | 延长兼容期 |
| RISK-3 | 模板 JS 改动引入渲染异常 | 低/中 | 保留占位符替换契约测试；端到端冒烟断言关键字段 | 渲染断言用例 | 回滚模板单文件 |

| ID | 问题 | 为什么重要 | 影响的决策 | 确认方式 | 最晚确认阶段 |
|---|---|---|---|---|---|
| OPEN-1 | 旧键 `branch_coverage_pct` 的移除时点 | 影响兼容窗口长度 | DEC-2 兼容期 | 用户确认下一主版本计划 | P5 收尾 |

## 12. 追踪矩阵

| 需求 | 方案位置 | 验收标准 | 验证方法 | 覆盖状态 |
|---|---|---|---|---|
| FR-1 | 5.1 FR-1、5.2 `summary_grade` | AC-1 | unittest + node 对比 | 已覆盖 |
| FR-2 | 5.1 FR-2、5.2 `no_unsafe` | AC-2、AC-3 | unittest + CLI | 已覆盖 |
| FR-3 | 5.1 FR-3、5.2 `statement_coverage_pct` | AC-4 | unittest + CLI | 已覆盖 |
| FR-4 | 5.1 FR-4 | AC-5、AC-6 | golden diff + unittest | 已覆盖 |
| FR-5 | 5.1 FR-5 | AC-5、AC-6 | golden diff + unittest | 已覆盖 |
| FR-6 | 5.1 FR-6 | AC-5 | golden diff | 已覆盖 |
| FR-7 | 5.1 FR-7、5.2 `latent_bugs_found` | AC-6、AC-8 | unittest | 已覆盖 |
| FR-8 | 5.1 FR-8 | AC-6 | 文档检查 + unittest（TOC 无 `Lines`） | 已覆盖 |
| FR-9 | 5.1 FR-9 | AC-1…AC-7 | `python3 -m unittest` | 已覆盖 |
| NFR-1（标准库零依赖） | 5.1、5.2 | AC-6 | 测试仅 import 标准库 | 已覆盖 |
| NFR-2（旧 JSON 兼容） | 5.2 版本兼容 | AC-4 | unittest | 已覆盖 |
| NFR-3（行为保持） | 5.1 FR-4/5/6 | AC-5 | golden diff | 已覆盖 |
