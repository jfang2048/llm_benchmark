# 6 GiB 的显卡，留哪个模型常驻？

我会选 **Qwen3.5-2B**。在这台用 WSL2 跑推理的 RTX 3060 笔记本上，
18 道中英文小任务里，0.8B 做对 6 道，2B 做对 11 道。4B 也做对 11 道，
峰值显存却从 1,678 MiB 升到 3,326 MiB。测的是收据提取、标识遮盖和归档查找，
用的都是虚构资料。

**同时发四个请求，显卡更忙，人等得更久。** 服务端固定两个槽位，输出吞吐从
83 升到 98 token/s，首段回复 p95 从 194 毫秒升到 750 毫秒。沿用半秒的首段
回复目标，每分钟按时做对的任务从 142 个降到 46 个。

这轮共做了五组单变量对照、1,080 个正式请求。除了模型大小和客户端数量，还测了
上下文配额和两套 llama.cpp 构建。[实验方法、图表和逐对数据](../controlled.md)

13 套部署的榜单里，Qwen3-8B 单人模式下按时做对 24/36，2B 是 22/36。
2B 峰值显存为 1,753 MiB，适合和其他应用共用这张卡。
[部署榜单](../home-lab-results.md) · [轻量模型与显存](../lightweight.md)

**模型放在哪也有区别。** 同一台 WSL2 机器上，Phi-4-mini 从 Linux 文件系统
启动到服务就绪的中位数是 3.36 秒，从 Windows 挂载盘启动则是 22.85 秒。
每条路径各测三次，启动前均预读权重。[存储路径测试](../home-lab.md#wsl2-is-part-of-the-machine)

[交互仪表盘](https://jfang2048.github.io/llm_benchmark/#home-lab) · [配对图](https://jfang2048.github.io/llm_benchmark/#controlled) · [English README](../../README.md)
