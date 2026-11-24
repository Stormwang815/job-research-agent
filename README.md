# 职探 · 招聘岗位调研 Agent

将目标岗位、地区和候选人背景整理成岗位画像、技能矩阵、能力差距与 8 周行动计划的中文研究工作台。

基于 **GPT Researcher** 集成通用研究引擎，使用 **FastAPI + SQLite + SSE** 实现任务管理、进度展示和报告留存。适合个人学习、求职研究及可信小团队试用。

[English](README.en.md) · [贡献指南](CONTRIBUTING.md) · [安全与隐私](SECURITY.md) · [更新记录](CHANGELOG.md)

## 能做什么

- 输入目标岗位、地区、经验级别、个人背景和关注点。
- 上传 PDF / DOCX / TXT / Markdown，选择互联网、本地资料或混合研究。
- 输出包含证据与局限性说明的 Markdown 报告，网页安全渲染并支持下载。
- 实时展示执行阶段，SQLite 保存任务、报告、来源、耗时和估算模型成本。
- 来源 URL 规范化与去重，使用域名规则辅助分类；评分不代表事实准确率或官方认证。
- 无密钥演示模式，可检查界面、任务流程和历史记录，不访问模型或搜索服务。

**项目定位：岗位调研与候选人差距分析。当前不提供候选人简历库搜索、自动投递或招聘网站登录抓取。**

## 5 分钟运行演示

要求：Python 3.11 / 3.12，以及 [uv](https://docs.astral.sh/uv/getting-started/installation/)。在项目根目录执行：

```bash
uv sync --frozen
cp .env.example .env
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
```

浏览器打开 <http://127.0.0.1:8010>，保留“演示模式”并点击“开始调研”。演示内容是固定样例，不代表真实招聘市场结论。

## 真实研究

在 `.env` 设置 `OPENAI_API_KEY` 与 `TAVILY_API_KEY`，或通过页面“服务配置”保存密钥，然后取消演示模式。模型名称由 `FAST_LLM`、`SMART_LLM`、`STRATEGIC_LLM` 指定，需确认账户有权限调用所配置模型。

密钥保存在本机 `.env`，不会被接口回显。不要把 `.env` 提交到 GitHub。真实调用可能产生模型、搜索与 Embedding 费用；页面成本指标是引擎估算，不能作为账单总额。

上传资料保存在 `data/`；同一部署中的用户共享这些文件。本地与混合模式可能使用整个共享目录，未做逐任务文件隔离。“仅本地资料”仍会调用外部模型，不能当作离线隐私模式。涉及真实简历前请阅读 [安全说明](SECURITY.md)。

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| `APP_ACCESS_TOKEN` | 空 | 共享访问令牌；可信团队部署时设置长随机值 |
| `COOKIE_SECURE` | `false` | HTTPS 部署时设为 `true` |
| `MAX_ACTIVE_TASKS` | `2` | 单进程活动任务上限 |
| `RESEARCH_TIMEOUT_SECONDS` | `900` | 单个真实研究超时 |
| `RATE_LIMIT_PER_MINUTE` | `60` | 单进程每个客户端 IP 的 API 频率限制 |
| `DATABASE_PATH` | `./var/job_research.db` | 历史数据库 |

## Docker

```bash
cp .env.example .env
# 按需编辑 .env
docker compose up -d --build
```

默认只开放本机 `127.0.0.1:8010`。`data/`、`reports/`、`var/` 与 `.env` 通过卷保留；构建上下文排除所有本地密钥和运行资料。请保持**单个 Worker、单个实例**，内存任务与进度未使用分布式队列。公网访问需另外配置 HTTPS 与访问控制。

停止：`docker compose down`。更改 Compose 注入的环境变量后需重新创建容器。不要在网页研究运行中修改供应商配置，避免过程中的配置变化。

## 架构与代码

```text
浏览器 → FastAPI → 招聘领域任务 / Prompt
                       ↓
             GPT Researcher 规划、搜索、资料处理与报告生成
                       ↓
             来源分类 / SQLite / Markdown
                       ↓
               SSE 进度 → 历史工作台
```

| 目录 | 职责 |
| --- | --- |
| `app/main.py` | API、上传、报告与进度流 |
| `app/service.py` | 演示/真实执行、并发上限、超时与任务状态 |
| `app/prompts.py` | 招聘报告结构与证据约束 |
| `app/database.py` | 任务与来源持久化 |
| `app/security.py` | 令牌、频率与跨站写入检查 |
| `static/` | 无前端构建步骤的工作台 |
| `tests/`、`evals/` | 回归测试与输出结构评测 |

本项目新增领域输入、Prompt、异步任务接口、SSE、SQLite、来源治理、演示模式与界面。通用 Agent 的规划、检索、内容压缩与写作由 GPT Researcher 提供，不能描述为从零自研框架。

API 文档：启动后访问 `/docs`；健康检查：`GET /health`。

## 验证与评测

```bash
uv run pytest -q
node --check static/app.js
uv run python evals/run_eval.py
# 可选真实评测：会产生费用，需要密钥
uv run python evals/run_eval.py --live
```

自动化测试使用临时数据库与资料目录，不读取开发者 `.env`。离线评测检查章节覆盖率、引用数量和局限性说明，**不等于事实准确率、真实岗位匹配效果或模型质量验证**。演示数据没有真实引用，因此引用计数为零是预期行为。

GitHub 自动检查配置模板位于 `docs/ci-workflow.example.yml`。当前发布账号授权未包含 workflow 权限，因此暂未启用 Actions。

## 发布源码

```bash
python3 scripts/build_release.py
```

生成 `dist/job-research-agent-source.zip`。打包采用明确的源码文件清单，排除密钥、个人资料、历史数据库、报告与虚拟环境。发布到 GitHub 时建议使用解压后的干净目录，先检查文件再提交。

## 当前限制

- 单部署共享数据与配置，尚无账户、租户隔离、支付或配额系统。
- 网页可访问性、招聘样本偏差及模型幻觉可能影响结论，重要判断需要人工核验。
- 来源分类使用简单规则；尚无逐条结论支持度检查或自动事实核查。
- 任务重启后标记失败，需要手动重试；无 Redis/Celery、断点续跑或取消接口。
- 未内置资料删除界面、自动脱敏与加密存储。

## 许可与致谢

应用代码以 [Apache License 2.0](LICENSE) 发布。GPT Researcher 及其他依赖保留其自身许可；版本 0.14.7 的元数据与随包许可证存在不一致，具体记录与保留文本见 [第三方说明](THIRD_PARTY_NOTICES.md)。感谢 [GPT Researcher](https://github.com/assafelovic/gpt-researcher) 提供研究引擎。
