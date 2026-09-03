# analyze-insect-fitness

一个面向昆虫与寄生蜂实验数据的轻量 Codex Skill：让 AI 整理异构原始表格、提出可审计的字段映射并分送到合适的分析路线，再由确定性 Python 脚本完成标准化、适合度计算、Bootstrap 和结果导出。

它不是把所有实验设计塞进同一个黑箱公式，而是在统一入口下保留不同“适合度”定义的科学边界。

## 当前能力

- 读取并检查 `.xlsx`、`.xlsm`、`.csv`、`.tsv` 原始表格。
- 识别宽表、长表、重复表头、混合缺失值和中英文列名，生成待确认的映射草案。
- 标准化为可追踪的 `individuals.csv`、`observations.csv`、`issues.csv` 和 `provenance.json`。
- 计算完整队列的年龄—阶段两性生命表核心指标：
  - 内禀增长率 `r`
  - 周限增长率 `lambda`
  - 净增殖率 `R0`
  - 平均世代周期 `T`
  - 种群倍增时间 `doubling_time`
- 汇总寄生蜂表现：寄生率、直接致死率、总寄主影响、羽化率和雌性比例。
- 支持按个体或生物学重复进行 Bootstrap，并保存置信区间、有效重采样比例、参数和随机种子。
- 在计算前审计 `0` 与缺失值、死亡与删失、实验单位、时间起点和后代定义。

## 安装

按照 [OpenAI 的 Skill 文档](https://developers.openai.com/codex/skills)，可以让 Codex 使用 `$skill-installer` 从 GitHub 安装：

```text
$skill-installer 请安装 https://github.com/xiaocaicaibucai/analyze-insect-fitness
```

也可以手动克隆到用户级 Skill 目录：

```bash
git clone https://github.com/xiaocaicaibucai/analyze-insect-fitness.git \
  "$HOME/.agents/skills/analyze-insect-fitness"
```

Codex 通常会自动检测 Skill；如果没有出现，可重启 Codex。仓库内使用时，也可以把本目录放到项目的 `.agents/skills/analyze-insect-fitness` 下。

### Python 依赖

建议使用 Python 3.10 或更新版本。CSV/TSV 路径仅使用 Python 标准库；读取 Excel 文件需要 `openpyxl`：

```bash
python3 -m pip install openpyxl
```

## 在 Codex 中使用

可以显式调用：

```text
$analyze-insect-fitness 请检查这份寄生蜂原始表，先生成字段映射和问题清单，不要在我确认前计算。
```

也可以直接描述任务；当请求涉及昆虫适合度、两性生命表、寄生率、寄主致死率或相关原始表整理时，Codex 可根据 Skill 描述自动调用它。

推荐工作流：

```text
原始文件
  -> 输入画像与映射草案
  -> 人工确认关键语义
  -> 规范化记录与问题审计
  -> 生命表或寄生蜂路线
  -> 可复现结果包
```

## 命令行工作流

以下命令均在仓库根目录运行。

### 1. 检查原始文件

```bash
python3 scripts/profile_input.py INPUT_FILE \
  --output-dir OUTPUT_DIR/profile
```

可用 `--sheet` 只检查一个工作表。程序会输出输入画像、表格预览和每个工作表的映射草案。

### 2. 确认映射

复制并编辑 `profile/mapping_proposals/` 中的草案。按照 [`references/mapping-contract.md`](references/mapping-contract.md) 明确列映射、值字典、缺失标记、宽表日期模式、重复表头策略等，并在所有关键语义确认后设置：

```json
{
  "status": "confirmed"
}
```

草案状态不能进入标准化步骤。

### 3. 标准化记录

```bash
python3 scripts/normalize_records.py INPUT_FILE \
  --mapping CONFIRMED_MAPPING.json \
  --output-dir OUTPUT_DIR/canonical
```

先检查 `issues.csv`。所有 error 级问题应在计算前解决；warning 应保留在最终审计记录中。

### 4A. 计算队列生命表

仅适用于可识别初始队列、时间起点、死亡终点和年龄别繁殖量的数据：

```bash
python3 scripts/life_table.py \
  --individuals OUTPUT_DIR/canonical/individuals.csv \
  --observations OUTPUT_DIR/canonical/observations.csv \
  --output-dir OUTPUT_DIR/life_table \
  --bootstrap-unit biological_replicate \
  --resamples 10000 \
  --seed 20260826
```

输出包括 `metrics.csv`、`age_table.csv` 和 `methods.json`。

### 4B. 汇总寄生蜂表现

```bash
python3 scripts/parasitoid_metrics.py \
  --observations OUTPUT_DIR/canonical/observations.csv \
  --output-dir OUTPUT_DIR/parasitoid \
  --bootstrap-unit biological_replicate \
  --resamples 10000 \
  --seed 20260826
```

输出包括 `individual_metrics.csv`、`metrics.csv` 和 `methods.json`。仅在分子和分母均存在的记录上计算比例，并报告 `valid_n`；缺失计数不会被改写为零。

## 结果目录

```text
profile/
  input_profile.json
  mapping_proposals/
  previews/
mapping.json
canonical/
  individuals.csv
  observations.csv
  issues.csv
  provenance.json
results/
  metrics.csv
  age_table.csv 或 individual_metrics.csv
  methods.json
```

原始文件应保持不变，并与分析输出分开保存。

## 科学与统计边界

- AI 可以解释上下文、提出映射和选择路线，但不能静默重定义零值、缺失、死亡、删失、实验单位、时间起点或后代类型。
- 笼、区组、母体、队列或实验批次是独立单位时，应按生物学重复 Bootstrap，不能把其内部个体当成独立重复。
- 不应通过比较两组各自的置信区间来宣称显著性。
- 只有终生总量、体型代理变量或日期含糊的数据，最多进入描述性汇总，不能凭空补成生命表。
- v1 不覆盖矩阵种群模型、IPM、竞争选择系数、基因组时间序列、密度依赖模型或正式的处理间推断。

详细规则见：

- [`references/canonical-schema.md`](references/canonical-schema.md)
- [`references/mapping-contract.md`](references/mapping-contract.md)
- [`references/method-selection.md`](references/method-selection.md)
- [`references/statistical-guardrails.md`](references/statistical-guardrails.md)

## 项目结构

```text
SKILL.md                         Skill 的主工作流与停止条件
agents/openai.yaml              Codex UI 元数据
references/                     字段规范、映射协议和统计护栏
scripts/profile_input.py        输入画像与映射草案
scripts/normalize_records.py    确定性标准化
scripts/life_table.py           队列生命表计算
scripts/parasitoid_metrics.py   寄生蜂表现汇总
```

---

## English

`analyze-insect-fitness` is a lightweight Codex Skill for heterogeneous insect and parasitoid experiment tables. AI handles context interpretation, traceable mapping proposals, ambiguity review, and route selection; deterministic Python scripts handle normalization, fitness calculations, bootstrap resampling, and export.

### What it supports

- XLSX, XLSM, CSV, and TSV input profiling.
- Canonical individual and observation records with issue and provenance logs.
- Cohort age-stage, two-sex metrics: `r`, `lambda`, `R0`, `T`, and doubling time.
- Parasitoid metrics: parasitism, direct host killing, total host impact, emergence, and female proportion.
- Individual- or biological-replicate bootstrap with fixed seeds and auditable method metadata.

### Quick start

Ask Codex to install the repository with `$skill-installer`, or clone it manually:

```bash
git clone https://github.com/xiaocaicaibucai/analyze-insect-fitness.git \
  "$HOME/.agents/skills/analyze-insect-fitness"
```

Then invoke it explicitly, for example:

```text
$analyze-insect-fitness Profile this parasitoid workbook and prepare a mapping proposal. Do not calculate until the mapping is confirmed.
```

The safe workflow is: profile → confirm semantics and mapping → normalize → inspect issues → route → calculate → report. Draft mappings are rejected by the normalizer, missing counts remain missing, and the bootstrap unit must match the independent experimental unit.

Version 1 intentionally excludes censored-survival models, matrix or integral projection models, competition/genomic fitness inference, density-dependent models, and formal between-treatment inference.
