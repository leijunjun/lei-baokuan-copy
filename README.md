# lei-baokuan-copy · 爆款视频复刻

把参考带货视频拆解成可迁移的传播结构，再结合你的商品，输出可直接复制给视频大模型的完整提示词。

**适合谁**：电商商家、短视频运营、带货编导、AI 视频创作者。

**适用场景**：参考爆款换商品、重写带货脚本、分析视听结构、准备 AI 视频生成提示词。默认交付分析和提示词；生成成片需另行提出。

## 前置条件

- 支持 Skill、可执行本地命令和读写文件的 Agent，例如 Codex。
- Python 3.9+、Node.js 22.15+（含 npm）、FFmpeg（含 ffprobe），工具需可被 Agent 找到。
- 参考视频文件或可访问链接，以及商品名称、图片、卖点等资料；未知项可以之后补充。

**Hypit CLI 无需手动预装**：先复用已有安装，缺失时自动用 npm 安装已核验的 `@hypit/hypit@0.3.1` 到用户目录。首次缺失安装需联网并有该目录写权限；已有可用工具后，本地取证可离线运行。不需要另装 Hypit Skill，本地取证也不需要模型账户或 API Key。

基础工具缺失会给出修复指引，例如 macOS 用 `brew install ffmpeg`，Ubuntu/Debian 用 `apt install ffmpeg`，Windows 用 `winget install --id Gyan.FFmpeg -e`；基础工具的安装权限由当前环境决定。链接下载还需按提示准备 yt-dlp；自动转写需已有可用的转写服务和适用的费用授权，也可提供已有同源转写。

## 安装与使用

下载/解压整个文件夹后，在其中运行（Windows 可将 `python3` 换成 `py -3`）：

```bash
python3 install.py
```

默认安装到 `${CODEX_HOME:-~/.codex}/skills/lei-baokuan-copy`。安装器先检查依赖、自动补装缺失的 Hypit，并用 1 秒合成片验证探测、拼图、画面变化候选和音频提取，再安装 Skill；检查失败不会替换旧版，更新会保留旧版备份。其他支持 Skill 的 Agent 可用 `--dest "/实际/skills/lei-baokuan-copy"` 指定路径。

普通复制或第三方 Skill 安装器不保证执行安装脚本，因此 Skill 也要求 Agent 在使用时先自动检查；解析脚本内置同一检查与缺失安装。仅解压文件不代表环境检查已经通过。

调用示例：

> 使用 $lei-baokuan-copy，拆解这条参考带货视频，换成我的商品，确认需求人群、字幕和分段后，输出完整复刻提示词。

## 执行逻辑

1. **检查环境**：复用工具，缺少 Hypit 自动安装；失败给出具体原因。
2. **拆解原片**：借助 Hypit 取证，Agent 观看、收听，再按需求、人群、类型、特征、画面、声音、金句、组合八个维度展示带时间码分析。
3. **核对商品**：收集商品资料，展示确认卡，请你确认事实。
4. **选择方向**：研究使用需求与人群，给出 A/B 方向，与你确认字幕、分段、时长和画幅。
5. **交付提示词**：按已确认要求输出可独立使用的完整提示词，并保存分析、时间轴和确认记录。不自动花费额度生成视频。

排查安装时可运行：

```bash
python3 scripts/ensure_environment.py --smoke
python3 scripts/ensure_environment.py --check
```

第一条会按需安装并实测，第二条只检查。工具目录可用 `LEI_BAOKUAN_COPY_TOOLS` 指定；已有 Hypit 可用 `--hypit` 指定。完整机制见 [Hypit 集成](references/hypit-integration.md)，工作规范见 [SKILL.md](SKILL.md)。
