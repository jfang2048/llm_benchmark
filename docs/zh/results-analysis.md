# Benchmark 结果分析（中文版）

这份文档解释我跑出来的 benchmark 结果：各模型之间有哪些区别、区别在哪里、为什么会有这些区别、可能的原因是什么。分析只基于本地实测数据，不引用任何外部排行榜分数。

## 基础：先把几个概念用大白话讲清楚（第一性原理 + 费曼式）

读下面的分析之前，先用最直白的方式讲清楚几个底层概念。这些是"第一性原理"——从最根本的物理/逻辑事实出发，而不是从类比出发。理解了这些，后面的数字和结论就都是顺理成章的。

### 1. 什么是"模型"？为什么它离不开显存？

一个语言模型，本质是一个**巨大的数学函数**：里面装着几十亿个"参数"（可以理解成几十亿个旋钮），输入一串文字，它算出一个"下一个词最可能是什么"的概率。

- Qwen3-8B 的"8B" = 80 亿个参数。
- 跑一次（专业叫"推理"）就要把这 80 亿个旋钮**全部装进显存（VRAM）**里。
- 一个参数如果用 16 位浮点（FP16）存，占 2 字节 → 80 亿 × 2 字节 = **16 GB**。
- 但这台机器的显卡只有 **6 GB** 显存。16 GB 的东西装不进 6 GB 的盒子——这就是第一性原理：**显存是物理天花板**。

那怎么办？**量化**：把每个参数从 16 位压缩到 4 位（IQ4_XS ≈ 4 bit ≈ 0.5 字节/参数）。80 亿 × 0.5 字节 ≈ **4-5 GB**，能装下了。代价是精度略降（答案质量可能略差一点），但换来"能跑"。这就是为什么本仓库所有模型都用 IQ4_XS 量化——不是偏好，是物理约束逼出来的唯一选择。

### 2. 什么是 token、上下文、KV cache？

- **token（词元）**：模型不是按"字"读文本的，而是切成小片段。一个英文单词 ≈ 1-2 个 token，一个中文字 ≈ 1-2 个 token。模型的一切输入输出都按 token 计。
- **上下文（context）**：模型一次能"同时看到"多少 token，像一个人的"视野"。视野 4096 = 只能看到约 4000 个 token 的历史；视野 16384 = 能看到 16000 多个。超出的部分模型"看不见"。
- **KV cache**：模型生成时，会把已经看过的每个 token 的"键值"缓存下来，避免重复计算。**这个缓存的大小随上下文长度线性增长**——上下文越长，KV cache 越大，占的显存越多。

这就是为什么在 6 GB 机器上，"长上下文"和"大模型"不能兼得：模型参数 + KV cache 都要挤进同一个 6 GB。这也是本仓库"上下文准入"测试要测的东西——**服务器嘴上说支持 16384，不代表模型真能在 16384 下正常回答**（下面第 2 节你会看到 Yi-1.5 就是栽在这里）。

### 3. TTFT vs 吞吐：一个像"响应快不快"，一个像"产能高不高"

- **TTFT（首 token 延迟）**：按下发送，到第一个字蹦出来，要多久。这是"体感响应速度"。
- **吞吐（throughput）**：一秒能吐出多少个 token。这是"总产能"。

两者常常是权衡的：一个引擎可以让第一个字很快（低 TTFT）但整体产能低，也可以反过来。看 benchmark 时要先分清问的是哪个，别把"响应快"误读成"产能高"。

### 4. 推理模型 vs 非推理模型：让"边说边想"的人不许出声

- 普通模型（如 Qwen3、GLM-4）拿到问题直接答。
- **推理模型**（如 DeepSeek-R1）拿到问题会先在心里默念一大段"思考"（thinking token），想清楚了才给答案。

"关闭思考（reasoning off）"对普通模型影响不大（它们本来就不怎么思考），但对推理模型是**致命的**——等于让一个习惯"边说边想"的人**不许出声**，他可能憋得只能蹦出几个词（本仓库实测 R1-Distill-8B 关思考后输出 `"\nWait,"` 这样的碎片）。这就是它 EvalPlus 只有 20% 的根本原因——不是模型笨，是评测方式砍掉了它的核心能力。

### 5. 直接编码 vs 智能体（agentic）：做题 vs 做工程

- **直接编码**：给一道题（"写一个函数，把两个数相加"），模型直接吐出一段代码。考的是"代码能力"本身。
- **智能体（agentic）**：给一个真实仓库 + 一个 bug 描述，模型要自己完成"读代码 → 思考 → 改文件 → 跑测试 → 看结果 → 再改"的**循环**。考的是"模型 + 工具脚手架 + 上下文策略"的组合。

后者难得多——它需要多步决策，每一步都可能出错、越走越偏（本仓库 agent 准入里 Qwen3 就"死循环改了 42 次都没改对"）。所以 agentic 分数**永远不能**说成"纯模型智力"，它包含 harness（工具脚手架）的功劳。

### 6. base vs plus：基础题 vs 陷阱题

- **base**（HumanEval/MBPP 基础版）：用基础测试用例判对错。
- **plus**（HumanEval+/MBPP+）：加了边界条件、隐藏用例的加强版。

一个解法能过 base 但过不了 plus，说明它是"**背出来的**"（见过类似题、套模板）而不是"**推出来的**"（真理解了边界情况）。base→plus 掉得越多 = 解法越脆。

带着这六个概念，下面开始看真实数据。

## 0. 先理清：这是两套完全独立的评估

这个仓库里跑了两类 benchmark，两者衡量的是正交的东西，**不能合成一个分数**：

1. **服务性能 benchmark**（serving）：在固定硬件（RTX 3060 6 GiB、IQ4_XS 量化、llama.cpp）下测"跑得快不快"——首 token 延迟（TTFT）、吞吐（tok/s）、显存占用、可靠性。它衡量的是**引擎 + 量化 + 硬件的部署效率**，和模型聪不聪明无关。

2. **编码能力 benchmark**（capability）：测"代码写得好不好"——EvalPlus（HumanEval/MBPP）、SWE-bench 等。它衡量的是**模型本身的代码能力**（受训练数据、后训练方式影响）。

下面先看能力，再看服务，最后看两者之间"并不相关"这件事。

## 1. 直接编码能力（EvalPlus，reasoning off，temperature 0）

### 1.1 原始分数

| 模型 | 参数量 | HumanEval | HumanEval+ | MBPP | MBPP+ |
|---|---|---|---|---|---|
| Qwen3-8B | 8B | **84.1%** | **79.3%** | **79.1%** | **70.1%** |
| GLM-4-9B-0414 | 9B | 81.7% | 77.4% | 75.7% | 65.1% |
| Yi-1.5-9B-Chat | 9B | 73.8% | 70.1% | 78.3% | 66.4% |
| Spark-X2.5-4B（参考） | 4B | 67.1% | 62.2% | 68.0% | 56.9% |
| DeepSeek-R1-Distill-Llama-8B | 8B | 20.1% | 18.3% | 31.2% | 28.3% |

### 1.2 排名和最大的区别

- **HumanEval 上**：Qwen3-8B（84.1）≈ GLM-4-9B（81.7）是第一梯队；Yi-1.5（73.8）中游；Spark-4B（67.1）垫底但可接受；DeepSeek-R1（20.1）**断崖式落后**。
- **MBPP 上**：Qwen3（79.1）≈ Yi（78.3）领跑，GLM-4（75.7）紧随，Spark（68.0）和 DeepSeek-R1（31.2）落后。

### 1.3 为什么 DeepSeek-R1 这么低？——这是策略造成的下限，不是模型真实能力

这是本套数据里最需要解释的一点。DeepSeek-R1-Distill-Llama-8B 是一个**推理模型**（reasoning model）：它的设计就是"先输出一大段思考 token，再输出答案"。为了做统一的直接编码对比，我把所有模型都设成了 **`--reasoning off`（关闭思考）**。

结果就是：关掉思考后，R1-distill 频繁输出 `"\nWait,"` 这种被截断的思考片段，答案根本出不来，所以分数掉到 20%/31%。

**结论：DeepSeek-R1 的 20%/31% 是"关闭思考模式"下的下限，不代表它带思考时的真实能力。** 要公平测它，必须开 reasoning。这也正是为什么后续的 agentic SWE 扫测改成了 `--reasoning auto`（让每个模型用自然模式）。

### 1.4 为什么 Qwen3-8B 最高、Spark-4B 最低？

- **Qwen3-8B 领跑**：Qwen3 系列在代码 + 通用任务上做了很强的后训练，是这代开源模型里公认的代码强模型，本地实测也印证了这一点。
- **GLM-4-9B 紧随其后**：GLM-4 也是强通用模型，HumanEval 只差 Qwen3 约 2.4 个百分点。
- **Yi-1.5-9B 中游**：Yi-1.5 的代码后训练不如前两者深，HumanEval 低 7-10 个百分点；但 MBPP 反而和 Qwen3 打平（78.3 vs 79.1），说明它在"函数级小任务"上不弱，在"算法题"（HumanEval 更偏算法）上稍弱。
- **Spark-X2.5-4B 垫底**：参数量只有 8-9B 模型的一半（4B），这是最主要的原因——同样的量化、同样的硬件，小模型的知识容量和代码能力就是弱一档。但它 MBPP 有 68%，说明 4B 级别在函数级任务上已经相当可用。

### 1.5 base → plus 的下降：衡量"解法健壮性"

HumanEval+ 和 MBPP+ 是"加强版"——用更多隐藏测试用例（边界条件、输入变体）来测，能通过基础测试、但过不了加强测试的解法会被筛掉。所以 **base 到 plus 的下降幅度，衡量的是模型解法有多"脆"**（是不是只针对基础用例对了，一加边界用例就崩）。

| 模型 | HumanEval 下降 | MBPP 下降 |
|---|---|---|
| Qwen3-8B | 4.9 | **9.0（最小）** |
| GLM-4-9B | 4.3 | 10.6 |
| Yi-1.5-9B | 3.7 | **11.9（最大）** |
| Spark-4B | 4.9 | 11.1 |

两个观察：

1. **MBPP+ 明显比 HumanEval+ 更"狠"**：MBPP 的下降普遍 9-12 个百分点，而 HumanEval 只有 4-5。原因是 MBPP 的加强用例加得更狠（更多输入变体 + 边界）。
2. **Qwen3 在 MBPP 上最健壮（只掉 9.0），Yi 最脆（掉 11.9）**：Yi 在基础 MBPP 上（78.3）能靠"把常见模式背对"拿到高分，但加强用例一上，暴露出它对边界条件的处理更依赖记忆而非泛化，所以掉得最多。

## 2. 上下文准入（context admission）

对每个模型做 8192 → 12288 → 16384 的上下文阶梯测试，看它在近满上下文时能否可靠回答：

| 模型 | 16384 能服务 | 资格 | 说明 |
|---|---|---|---|
| Qwen3-8B | ✅ | ELIGIBLE | |
| DeepSeek-R1-8B | ✅ | ELIGIBLE | |
| GLM-4-9B | ✅ | ELIGIBLE | |
| Spark-4B | ✅ | ELIGIBLE | |
| Yi-1.5-9B | ✅（服务器接受） | **TRANSPORT_INELIGIBLE** | 原生约 4K，近满 8192 时回答失败 |

关键点：**Yi-1.5 的"服务器能接受 16384"和"模型能处理 16384"是两回事。** llama.cpp 服务器可以通过 RoPE 外推接受长上下文，但 Yi-1.5 原生上下文约 4K，一旦 prompt 接近 8192，它就无法可靠生成正确回答（"传输层"掉链子）。所以它被标为 TRANSPORT_INELIGIBLE，后续 SWE 扫测不参与。

## 3. Agent 准入（agent harness，reasoning off 下）

用一个"迷你任务"（修复一个简单的减法 bug）测每个模型能不能驱动 mini-swe-agent：

| 模型 | 是否解出任务 | 步数 | 耗时 | 结论 |
|---|---|---|---|---|
| Spark-4B | ✅ 解出 | 38 | 33 s | 唯一解出的 |
| Qwen3-8B | ❌ 死循环 | 42 | 30 min 超时 | 反复改但不收敛 |
| DeepSeek-R1-8B | ❌ | 6 | 45 s | 早早放弃 |
| GLM-4-9B | ❌ | 6 | 10 s | 早早放弃 |
| Yi-1.5-9B | ❌ | 6 | 12 s | 早早放弃 |

这说明什么：在 **reasoning off** 下，agentic 任务（需要"读代码→想→决定下一步 bash 命令"）对模型是灾难——大多数模型要么生成不出结构化动作（6 步就放弃），要么死循环（Qwen3 改了 42 次都没改对）。只有 4B 的 Spark 靠较强的指令遵循能力解了出来。

**这直接导出了一个方法论决定：agentic SWE 必须用 `--reasoning auto`（自然模式）。** 关闭思考对"写一个孤立函数"（直接编码）影响可控，但对"多步 agent 决策"是致命的。所以：
- 直接编码 = reasoning off（统一、可复现）
- agentic SWE = reasoning auto（自然模式）

## 4. 服务性能 vs 编码能力：两个维度不相关

把服务性能（serving）和能力（capability）放一起看，最说明问题：

| 模型 | TTFT p50（ms，越低越好） | 吞吐（tok/s，越高越好） | 显存（MiB） | HumanEval |
|---|---|---|---|---|
| Qwen3-8B | 104.1 | 94.5 | 4837 | **84.1%** |
| DeepSeek-R1-8B | 91.3 | **98.0（最高）** | 4721 | 20.1%（退化） |
| GLM-4-9B | **54.6（最低）** | 85.4 | 5095 | 81.7% |
| Yi-1.5-9B | 68.6 | 86.7 | 5041 | 73.8% |

三个直接的观察：

1. **服务最快的（GLM-4，TTFT 54.6ms）能力不是最高的（81.7%，第二）**；**吞吐最高的（DeepSeek-R1，98 tok/s）能力是最低的（20%，当然有 reasoning-off 的原因）**。
2. **服务性能和编码能力没有任何正相关**——TTFT/吞吐主要由架构、量化、KV cache、注意力实现决定；编码能力主要由训练数据 + 后训练决定。这两者是正交的。
3. 这**印证了本仓库的核心设计决策：服务和能力必须分开，绝不能合成一个分数**。合成就等于把"跑得快的模型"和"写得好的模型"这两个完全不同的东西强行平均。

## 5. 推理框架的选择：llama.cpp vs XHToken fork vs vLLM

### 5.1 本仓库用了哪些框架

| 框架 | 用途 | 来源 / 版本 |
|---|---|---|
| llama.cpp（上游） | 8-9B 主力队列（Qwen3 / DeepSeek-R1 / GLM-4 / Yi-1.5） | ggml-org/llama.cpp v0.4.0（commit 5ac847190） |
| XHToken llama.cpp fork | Spark-X2.5-4B 参考基线 | XHToken/llama.cpp（commit 4a3635c3） |
| vLLM | 引擎 A/B 对比（默认关闭） | Qwen3-4B 的 GGUF / AWQ 两臂 |

### 5.2 为什么 Spark 必须用 XHToken fork

Spark-X2.5-4B 用的是 XHToken 架构，上游 llama.cpp 不支持，所以只能用 XHToken 的 fork（镜像 `spark-x25-llama:cuda13`）。这个 fork 有代价：本仓库实测它**输入 ≥256 token 时传输不稳定**（fork 特性），所以 Spark 在服务基准里被严格标成 `REFERENCE / 4B`，不和 8-9B 队列做模型排名。

### 5.3 三个框架的优缺点（通用认知 + 本仓库实测）

**llama.cpp（上游，主力引擎）**
- 好处：GGUF 格式 + ggml 后端，量化生态最全（IQ4_XS / Q4_K_M 等）；支持 CPU/GPU 混合卸载（部分层放 CPU）；单 GPU 6 GiB 场景够用且省显存；部署轻量（单进程 HTTP server）；同一个二进制跑所有模型，对比最公平。
- 坏处：高并发吞吐不如 vLLM；连续批处理（continuous batching）能力相对较新、不如 vLLM 成熟；多卡分布式支持弱。

**XHToken llama.cpp fork（仅 Spark）**
- 好处：支持上游不支持的 XHToken 架构，让 Spark-X2.5 能跑；继承了 llama.cpp 的量化/部署生态。
- 坏处：是 fork 而非主线上游，长期维护和特性同步有风险；实测长输入（≥256 token）传输不稳定；和上游引擎的结果不能直接混排对比（引擎不同，会引入混淆变量）。

**vLLM（引擎对比，默认关闭）**
- 好处：PagedAttention + 连续批处理，高并发吞吐三者最强；面向生产/多用户服务的调度（TTFT/吞吐/SLO 控制）成熟；支持多种量化（AWQ / GPTQ / GGUF 插件）和张量并行多卡。
- 坏处：对 GGUF 的支持靠插件，不如 llama.cpp 原生；单卡 6 GiB 小显存场景下并发优势发挥不出来；部署更重、依赖更多；本仓库早期 A/B 尝试里 GGUF 插件和 AWQ 要 HF cache、配置坑多（见 `docs/experiment-history.md`），最终为隔离"模型"变量而统一回 llama.cpp。

### 5.4 为什么最终统一用 llama.cpp

本仓库是"固定硬件 + 固定引擎"的对比：要隔离出"模型"这一个变量，就必须让所有模型用**同一个二进制、同一个量化、同一个工作负载**。llama.cpp 的 GGUF 生态最全、单 GPU 6 GiB 场景够用，所以主力队列统一 llama.cpp。vLLM 的高并发优势在单卡 6 GiB + IQ4_XS 下体现不出来，所以只保留为关闭的 A/B 臂——它的作用是**证明"换引擎会引入混淆变量"**，而不是混进模型排名。Spark 因为架构约束只能走 fork，因此单列为 REFERENCE，永远不参与 8-9B 队列的排名。

## 6. 总结：区别在哪里、为什么

一句话版：

- **直接编码能力**：Qwen3-8B ≈ GLM-4-9B > Yi-1.5-9B > Spark-4B >> DeepSeek-R1（reasoning off 下限）。差距主要来自**模型参数量 + 代码后训练的深度**，以及**是否为推理模型**。
- **解法健壮性（base→plus）**：Qwen3 最稳，Yi 最脆；MBPP+ 比 HumanEval+ 更能暴露"背题"。
- **长上下文**：Yi-1.5 是唯一掉链子的（原生 4K），其余都能到 16384。
- **agentic 能力**：reasoning off 下几乎全军覆没（只有 Spark 解出），所以 agentic 用 reasoning auto。
- **服务 vs 能力**：两者正交，不相关，必须分开报告。

可能的深层原因（供参考，非本仓库结论）：

- Qwen3/GLM-4 的代码优势来自大规模、高质量、包含大量代码 + 多语言 + 工具调用的后训练语料。
- Yi-1.5 在通用 + 中文上强，但代码后训练的广度和深度略弱于前两者，且原生上下文短（4K）。
- DeepSeek-R1 是"推理优先"模型，把能力放在了思考链上，而不是直接输出答案上——关掉思考就等于砍掉了它的核心能力。
- Spark-4B 是 4B 小模型，能力天花板天然比 8-9B 低一档，但函数级任务（MBPP 68%）已经可用。

## 7. 前沿调研（相关博客与论文，附引用）

这部分汇总 2026 年公开博文 / 论文里的前沿信息，给上面的分析提供外部参照。引用编号对应文末的 Sources 列表（英文完整版见 [docs/references.md](../references.md)）。

### 7.1 推理引擎：vLLM vs SGLang vs llama.cpp

- vLLM 和 SGLang 的胜负取决于并发度：低并发 SGLang 完胜（c=1 时 TTFT 583ms vs 2141ms，约 3.7 倍快），高并发 vLLM 反超（峰值吞吐 5129 vs 4638 tok/s，约高 11%）[1]。
- 更大的独立 A/B 测试（149 组公平对比）里 vLLM 赢了 82% 的场次 [2]。
- llama.cpp 系运行时之间差距很小：同一份 sha256 校验的 GGUF 上，llama.cpp 比 Ollama 快 2-6%，Ollama 比 LM Studio 快 5-11% [3]。这印证了本仓库"固定引擎、只把 vLLM 当关闭的 A/B 臂"的做法。

### 7.2 KV cache 量化：小显存跑长上下文的关键

- KV cache 随上下文长度线性增长，是长上下文的显存瓶颈。llama.cpp 把 K/V 量化到 Q8_0 / Q4_0 可以大幅省显存（量化 V cache 需要 flash attention）[9]。
- 研究层面 KVQuant 做到 3-bit KV 量化、困惑度退化 <0.1、KV 显存省约 4.8 倍，让 LLaMA-7B 在单张 A100-80GB 上跑到 1M token 上下文 [10]。本仓库的 agent 层目前 ctx 16384、不用 KV 量化（manifest 记 `kv_cache_policy: none`）——若未来要更长的 agent 上下文，这是最直接的杠杆。

### 7.3 推理模型服务（thinking tokens）

- llama.cpp 可以把思考 token 放进单独的 `reasoning_content` 字段（`--reasoning-format` / `--jinja`），前端不用逐个模型解析思考分隔符 [11]。
- DeepSeek-R1 的工具调用 + `reasoning_content` 是单独合入的；维护者指出 R1-Distill-8B"对工具调用起始标签很随意"、可能跳过 tools 输出标签，建议避免用 8B（或更低量化）做工具调用 [12]。本仓库从另一个方向观察到同类问题：`--reasoning off` 下 R1-Distill-8B 输出截断的思考片段。

### 7.4 agentic 编码 benchmark 前沿（2026）

- **SWE-bench Verified 事实上退役了**：OpenAI 2026 年 2 月停止报告，原因是测试用例有缺陷 + 污染（前沿模型能复现 gold patch 和问题原文）[4]。
- **Terminal-Bench 2.1**（89 任务）在饱和：顶尖模型挤在 74-84% 区间；换个 scaffold 分数能差 5.1 分（比第一名和第三名的差距还大）[4]。
- **Frontier-Bench v0.1**（74 任务、7 个领域）2026 年 7 月上线，最高分 34.4%，还很开阔 [4]。
- **DeepSWE**：113 个从零写的长程任务（91 仓库、5 语言）、手写验证器；独立评审对它的判定分歧只有 1.4%，而对 SWE-bench Pro 继承测试的分歧是 32.4% [5]。（本仓库用的就是 Datacurve 的 DeepSWE 基准，不是那个约 32B 的"DeepSWE-Preview"模型。）
- **SWE-bench-Live**：1319 个 2024 年以来的真实 GitHub issue 任务、93 仓库，用发布日期窗口化来抗污染 [6]。
- **ProgramBench** 是引用度高的基准里最没饱和的：最强模型完全复原（二进制 → 源码）只有约 4.5% [7]。
- 整体：SWE-bench Verified 从 2024 年初的约 13% 涨到 2026 年 5 月约 78%（接近饱和），开源权重 agent 落后闭源 API agent 25-40% [8]。

这些对本仓库的意义：本地 4-9B 模型离前沿很远，本地子集明确标成 `Local-N`、不等同于排行榜——它们测的是"本地模型 + harness + 上下文策略"，不是对前沿名次的声明。

## Sources

[1] https://rawlinson.ca/articles/vllm-vs-sglang-performance-benchmark-h100 — vLLM vs SGLang benchmark (H100)
[2] https://vllm-sglang-dashboard.vercel.app — vLLM vs SGLang dashboard
[3] https://www.kaggle.com/datasets/lowellwoodiblessi/local-llm-runtime-comparison-rtx-5080/data — Ollama vs llama.cpp vs LM Studio (RTX 5080)
[4] https://backgrind.com/blog/agentic-coding-benchmarks-2026 — Agentic coding benchmarks 2026
[5] https://arxiv.org/html/2607.07946v1 — DeepSWE paper
[6] https://arxiv.org/html/2505.23419v2 — SWE-bench-Live paper
[7] https://peterindia.net/OpenSourceBenchmarksForAICodingAgents.html — Coding-agent benchmarks field guide 2026
[8] https://presenc.ai/research/coding-agent-benchmarks-2026 — Coding agent benchmarks 2026
[9] https://github.com/gravitee-io/llamaj.cpp/blob/main/docs/quantized-kv-cache/README.md — llama.cpp quantized KV cache
[10] https://arxiv.org/pdf/2401.18079v4 — KVQuant paper
[11] https://github.com/ggml-org/llama.cpp/discussions/15333 — llama.cpp thinking blocks
[12] https://github.com/ggml-org/llama.cpp/pull/11607 — llama.cpp DeepSeek-R1 reasoning_content
