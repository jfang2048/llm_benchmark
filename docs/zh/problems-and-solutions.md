# 问题与解决方法总结（中文版）

这份文档把编码/软件工程能力评估层在设计和实现过程中遇到的所有问题、每个问题的解决方法、以及"为什么这样解决"汇总在一起。这是复盘记录，不是操作手册。对应的英文公开版在 [docs/capability-troubleshooting.md](../capability-troubleshooting.md)。文档总览见 [docs/README.md](../README.md)。

## 这份文档怎么读（费曼式前言）

一句话概括：**这 20 来个问题，归根结底都来自同一件事——"在 6 GB 显存的本地硬件上，做一套可复现的 agentic 编码评估"，这件事本身就是一连串物理约束和工程坑的组合。**

问题分两大类，你可以这样理解：

- **第一类（第一部分，P0–P18）：想错了。** 这些是"设计时没想清楚"——报告解析格式用错、来源信息被覆盖、两套评估混在一起、占位符目标冒充真实现。这类问题的共同点是：**不是代码写错了，是对"正确性/可复现性"这个目标想得不彻底**。解决方式都是"回到第一性原理，把语义理清楚"。

- **第二类（第二部分，19 个）：跑出来的坑。** 这些是"写的时候以为没问题，一跑就炸"——服务器挂死、结果格式变了、模型名字对不上、Docker 镜像超时、上下文溢出。这类问题的共同点是：**本地硬件 + 第三方工具（llama.cpp、mini-swe-agent、swebench、Docker）之间的配合，藏着大量只有在真实跑起来才会暴露的坑**。

每个问题都按固定三段式写：**问题是什么 → 怎么解决 → 为什么这么解决**。读的时候不需要记细节，抓住"根因"就够了——大多数坑的根因都能追溯到那个 6 GB 显存的物理天花板，或者"第三方工具的默认行为 ≠ 我们以为的行为"。

## 第一部分：设计 / 正确性问题（审计阶段发现，P0–P18）

### P0 — SWE-bench 报告解析错了

问题：初版代码读 `report["f2p"]` / `report["p2p"]`，但官方 SWE-bench 固定版本写出的报告结构完全不同，实际是：

```json
{ "resolved": false, "patch_exists": true, "patch_successfully_applied": true,
  "tests_status": { "FAIL_TO_PASS": {"success": [], "failure": []},
                    "PASS_TO_PASS": {"success": [], "failure": []} } }
```

解决：`evals/swe.py` 改为解析真实字段，并加了 `classify_report()`，把每个实例映射到 `RESOLVED / NO_PATCH / PATCH_INVALID / TEST_FAILURE / ENVIRONMENT_ERROR / MISSING_REPORT`。基础设施失败单独统计，绝不悄悄算成模型失败；每个百分比的分子分母都显式给出。为什么：官方报告结构是唯一可信的判定来源，按旧字段解析会把"通过"和"失败"完全搞反。

### P1 — manifest 覆盖了来源信息

问题：每个 benchmark 一个 `manifest.json`，后跑的模型会把前面模型的来源信息覆盖掉。

解决：`normalize.write_manifest` 改成追加式多 run 结构（`benchmark_metadata` + `runs[]`），按"协议指纹"（benchmark commit、模型 SHA256、引擎 commit、agent commit、上下文、生成参数）去重。为什么：可复现性要求每次 run 的来源都保留，覆盖等于造假。

### P2 — manifest 语义把两套评估混在一起

问题：直接编码和 agentic SWE 用同一份协议元数据。

解决：`make_manifest(kind=...)` 按类型记录真实值：`direct` 记 direct_coding_profile、agent=none、直接编码生成参数；`agent` 记 agent_profile、agent 名字/commit、最大迭代次数、上下文、生成参数。为什么：两类评估的协议本质不同，混写会让结果不可比。

### P3 — 环境不可复现

问题：代码硬编码 `~/venvs/aiperf` 和 `~/venvs/eval`。

解决：统一用项目自有的 `.venv-eval/`（gitignore），配 `requirements-eval.txt`；`scripts/eval_setup.sh` 从 `.cache/evals/` 里的固定 git clone 安装 mini-swe-agent + swebench（钉死 commit，不用可变的 PyPI 版本）。为什么：换机器/换会话要能一模一样地复现。

### P4 — 公开 Make 目标是占位符

问题：好几个 `eval-*` 目标只是 echo 了 benchmark 名字。

解决：每个目标都接上真实 adapter；真正推迟的（SWE-bench Pro、SWE-EVO）明确写 DEFERRED，不再 echo。为什么：公开仓库的 Makefile 不能"看起来能跑其实不能跑"。

### P5 — 准入会被单个模型卡死

问题：一个不合格的模型就能让整个循环中断。

解决：`eval-admit` 对每个模型独立跑 context + agent 准入，失败继续；资格（ELIGIBLE / CONTEXT_INELIGIBLE / TRANSPORT_INELIGIBLE / OOM / ERROR）是"测出来"的，不是"假设"的。为什么：准入的目的是筛掉不适合的模型，而不是让流程崩掉。

### P6 — EvalPlus 措辞

问题：生成器自建了 chat prompt，不能宣称是"官方 prompt"。

解决：结果统一描述为"本地 chat 生成协议 + 官方 EvalPlus 执行器"（temperature 0、n=1、reasoning off），并报告 base→plus 的下降。为什么：官方 prompt 和本地 prompt 是两回事，含糊其辞会误导读者。

### P7 — LiveCodeBench

解决：使用 LOCAL PROTOCOL（n=1）跑本地端点，明确标注"不等同于排行榜"，每次 run 记录 release 版本。

### P8–P11 — 直接编码 / SWE 范围

- EvalPlus 已跑完 5 个模型（HumanEval / HumanEval+ / MBPP / MBPP+）。
- SWE-bench Verified Local-20、DeepSWE Local-10、SWE-Multilingual Local-18、Terminal-Bench Local-10、SWE-bench-Live Local-10 子集已提交（seed 42 分层采样，task-ID 哈希写在每个文件里）。
- DeepSWE/Multilingual/Terminal/Live 都有真实 adapter（官方 pier / harbor / swebench harness + mini-swe-agent，没有自造评分器）。

### P12 — 2026 前沿选择

- 加了 SWE-bench-Live（抗污染、反映当前能力）、Senior SWE-Bench（试点）、ProgramBench（试点）。
- SWE-bench Pro 标 DEFERRED（任务质量待审），SWE-EVO / SWE-rebench 推迟。

### P13–P15 — 安全、CI、Pages

- SWE/DeepSWE/Harbor 的任务容器视为不可信：不挂 `$HOME`、SSH 密钥、凭据、`.env`、Docker socket；网络在 benchmark 允许范围内受限；只有宿主编排器控制 Docker。
- CI 编译 `evals/*.py`、跑 `tests/test_capability.py`、重新生成 `capability.json`、校验 eval JSON。
- Pages 监听 `results/capability/**`、`evals/**` 并重新生成 `capability.json`。

### P16–P17 — 看板与文档

- 看板的"能力评估"半边和"服务性能"半边彻底分开（顶部导航拆分）：概览矩阵、直接编码、每个 benchmark 的 resolved rate + Wilson 置信区间、失败分类、任务浏览器。没有合成总分；Spark 保持 `REFERENCE / 4B`。
- 文档：`capability-methodology.md`、`capability-results.md`、`benchmark-selection.md`，每个本地子集都标注"不等同于排行榜"。

## 第二部分：实现过程中遇到的问题与解决方法

按出现顺序排列。

1. **llama.cpp 服务器持续负载下挂死。** 为了路由 thinking token 加的 `--reasoning-format deepseek` 导致 v0.4.0 服务器在约 100 个请求后不再响应。解决：去掉该 flag，保留 `--reasoning off`，加 180 秒单请求超时 + 挂死自动重启重试。

2. **EvalPlus v0.3.1 结果格式变了。** 执行器写的是 `eval[tid] = [{base_status, plus_status, ...}]`，不是原先假设的 base/plus 布尔列表。解决：`parse_eval` 改读 `base_status`/`plus_status`。

3. **模型 arm 和 id 对不上。** 5 个模型里 4 个的短 `arm` 和完整 `id` 不一致（如 `deepseek_r1_8b` vs `deepseek_r1_distill_llama_8b`），只有 `qwen3_8b` 匹配。解决：`model_by_arm` 两者都匹配，评估脚本统一用短 arm。

4. **summary.tsv / tasks.tsv 被覆盖。** 每个数据集 run 都把别的 run 覆盖。解决：`_merge_rows` 按关键列（如 `model+dataset`、`task_id+model`）upsert。

5. **security_check 误报 `/home/jfang`。** 某 docstring 示例里的绝对路径触发告警。解决：改成 `$HOME`。

6. **XHToken（Spark）fork 在某些 prompt 上卡住。** Spark fork 偶尔停止解码。解决：挂死自动重启 + 续跑（每个任务的采样已缓存，续跑跳过已完成部分）。

7. **DeepSeek-R1-Distill 在 reasoning-off 下退化。** 关掉 reasoning 后，R1-distill 频繁输出 `"\nWait,"` 之类被截断的思考片段，导致它的 EvalPlus 分数（HumanEval 20.1%、MBPP 31.2%）是下限，不能代表它真实（带思考）的能力。解决：在结果里如实标注，不隐藏。

8. **mini-swe-agent 首次启动卡住。** `mini` 首次运行弹交互式设置向导、无 TTY 时阻塞。解决：子进程环境里设 `MSWEA_CONFIGURED=true` + `OPENAI_API_KEY=sk-local`。

9. **litellm 成本统计报错。** 本地模型名不在 litellm 价格表里，算成本时抛 `RuntimeError`。解决：`MSWEA_COST_TRACKING=ignore_errors`。

10. **轨迹步数总是 0。** 轨迹 JSON 用的是 `messages`，不是 `trajectory`/`steps`。解决：改解析 `messages`；准入判定改成"harness 连通 且 产生 ≥1 个 bash action"，任务 `resolved` 单独记录（作为能力信号，不是准入门槛）。

11. **Docker 镜像拉取超过 mini-swe-agent 的 120 秒 `docker run` 超时。** SWE-bench 镜像 10+ GB。解决：跑之前先把镜像预拉好。

12. **上下文溢出。** SWE 问题描述 + 模板约 9.7K token，溢出 `--ctx-size 8192`（`ContextWindowExceededError`）。解决：agent 上下文提到 16384——这是 8-9B IQ4_XS 模型在 6 GiB 显存上的上限（由上下文准入实测）。

13. **残留空 patch 导致续跑跳过。** 第一次失败 run 写了空 patch，第二次被判定"已跑过"直接跳过。解决：重跑前删掉残留预测文件。

14. **`.venv-eval/` 一度被 stage 进去。** `git add -A` 在 `.gitignore` 生效前把 venv 加进去了。解决：补 `.gitignore` + reset。

15. **`eval_setup.sh` 里 `VPY` 没加引号**，被 bash 当成命令名（command not found）。解决：改成 `"$VPY"`。

16. **tmux 会话在上下文重建时丢失。** 长 GPU 任务每次从采样缓存续跑。解决：长任务放 tmux + 脚本可续跑；启动前先查有没有重复任务。

17. **SWE-bench-Live 的 HF 数据集名错了。** `microsoft/SWE-bench-Live` 在 Hub 上不存在，正确的是 `SWE-bench-Live/SWE-bench-Live`，用冻结的 `verified` split。解决：`live.py` 改用正确数据集名 + split。

18. **SWE-bench Multilingual 没有 `language` 字段。** 语言不在数据集列里，是从仓库主语言反推的（逐个仓库用 GitHub 核实，和论文的 9 语言计数对得上）。

19. **准入 schema 冲突。** context 准入和 agent 准入写不同列集到同一个 `admission/tasks.tsv`。解决：拆成两个 bench（`admission` 存 context、`admission-agent` 存 harness），用显式关键列。

## 第三部分：当前状态

- EvalPlus 5 个模型全部跑完（HumanEval / HumanEval+ / MBPP / MBPP+），官方执行器、temperature 0、n=1、reasoning off。
- 上下文准入：qwen3_8b / deepseek_r1_8b / glm4_9b / spark_llama 在 16384 处 ELIGIBLE；yi_15_9b TRANSPORT_INELIGIBLE（原生约 4K）。
- Agent 准入（reasoning off）：所有模型 harness 都能连通；只有 Spark 解出了迷你任务；8-9B 模型动作很少——证实 reasoning-off 限制了 agentic 能力，所以 SWE 扫测改用 `--reasoning auto`。
- SWE Verified 单任务验证进行中（qwen3_8b、astropy、ctx 16384、reasoning auto）。
- Agentic 的 reasoning 策略：直接编码 = reasoning off（统一本地协议）；agentic SWE = reasoning auto（自然模式）。
