# Hypit 可执行集成

随附 `scripts/analyze_reference.py` 用 Python 标准库通过参数数组调用真实 Hypit CLI，不使用 shell，不复制整个 Hypit Runtime。当前接口已在 Hypit 0.3.1 核验；运行时先记录实际版本，其他版本若不兼容应读其 `--help`，不要静默伪造结果。0.3.1 的 `media cut` 保留视频流，不能把有画面的视频直接输出为 WAV；脚本用 FFmpeg 提取 16 kHz 单声道收听副本，再用 Hypit 探测音频。副本不替代原片音质与空间声场的判断。

## 准备与调用

基础环境：Python 3.9+、Node.js 22.15+（含 npm）、FFmpeg（含 ffprobe）。自动化只安装缺失的 Hypit CLI；基础环境缺失时检查失败并给出具体安装指引，不将“脚本已复制”当成环境就绪。脚本仅使用 Python 标准库。Hypit 官方发行包为 [`@hypit/hypit`](https://github.com/hypit-ai/hypit)，其 [Node.js 要求](https://github.com/hypit-ai/hypit/blob/main/package.json)为 22.15+。本 Skill 的缺失安装锁定已核验版本 `0.3.1`，已有其他版本先检查本任务所需接口，安装验收再实际取证，不自动升级。

安装入口为根目录 `install.py`：先调用 `ensure_environment.py` 检查并补齐 Hypit，生成 1 秒合成片，实际测试 probe、boundaries、tiles 和音频提取，再复制 Skill。更新目标已有版本时先备份；检查失败不替换旧版。单纯解压、复制或第三方 Skill 安装不一定有安装钩子，首次使用必须由 Agent 执行环境检查；`analyze_reference.py` 也自动执行，避免只靠文字约定。

```bash
# 检查并按需安装 Hypit；--smoke 实测媒体链路
python3 "<skill-dir>/scripts/ensure_environment.py" --smoke
# 只检查，不安装；离线/受限环境可用
python3 "<skill-dir>/scripts/ensure_environment.py" --check
```

查找顺序：显式 `--hypit` → PATH → 当前项目及祖先的 npm 安装 → 本 Skill 的用户工具目录 → 常见已有安装与 npm 全局前缀。CLI 缺失时用 `npm install --prefix <tools-dir> --no-audit --no-fund --no-update-notifier --fetch-retries=1 --omit=dev --legacy-peer-deps @hypit/hypit@0.3.1` 安装到 `~/.cache/lei-baokuan-copy/tools`；`LEI_BAOKUAN_COPY_TOOLS` 可改位置。npm 沿用当前 registry/代理配置，脚本不切换镜像。独立工具安装保留发行包声明的运行依赖，跳过开发依赖及 npm 自动补装的 peer 依赖，避免 Vite 开发工具/Vitest 的额外解析；实际取证链路须通过自检。安装最多尝试一次，单次上限 600 秒，失败保留错误；重新执行会复查已有安装。脚本用实际 Node 和绝对入口继续调用，无需重启终端或修改系统/用户 PATH。进程内仅补入已找到的工具目录。

可用 `--hypit /absolute/path/hypit` 或 `--hypit /absolute/path/bin/hypit.mjs` 指定安装；显式路径错误、现有 CLI 损坏或缺接口时明确失败，不覆盖它。环境报告输出实际版本、路径和检查结果，解析时写入 `manifest.json.environment`。`ready` 仅表示所列本地检查通过；`--smoke` 才表示已实测合成片的媒体链路，不承诺任意源文件可解码或外部网站可下载。

本地无付费取证：

```bash
python3 "<skill-dir>/scripts/analyze_reference.py" "/path/reference.mp4" \
  --out "work/task/evidence"
```

解析脚本默认按需安装缺失的 CLI；只允许运行已有工具时加 `--no-install`，不影响产品确认和费用边界。

已有同源、同一时间轴的 Hypit 转写：

```bash
python3 "<skill-dir>/scripts/analyze_reference.py" "/path/reference.mp4" \
  --out "work/task/evidence-with-words" --transcript "/path/transcript.json"
```

需要转写且已经有适用的账户、服务与费用授权时：

```bash
python3 "<skill-dir>/scripts/analyze_reference.py" "/path/reference.mp4" \
  --out "work/task/evidence-transcribed" --transcribe --language zh \
  --runtime "/path/selected-runtime-profile.json"
```

`--runtime` 是可选的实际 Runtime Profile 路径；也支持 `--project` 指定已有项目目录，不凭示例新建 Profile。中文原片明确用 `zh`。转写由 `hypit transcribe` 调用所选 WhisperX Endpoint，可能需要本地服务或付费服务；工具可用不代表已有费用授权。复用已有同源转写，避免重复请求；脚本不接受 `--transcribe` 与 `--transcript` 同时出现。

视频链接可直接作为第一个参数，脚本调用 `hypit download`。它需要已准备的 yt-dlp 环境；若实际报环境未准备，再执行 `hypit download prepare` 并解释需要的下载准备，不自动执行。网站不支持或访问失败时请用户提供原始文件，不伪造下载成功。

## 产物与状态

`--out` 必须是新目录，脚本拒绝覆盖已有目录。文件包括：

- `manifest.json`：原始输入、实际版本、原片指纹、逐步命令/状态/日志、已生成文件和缺口。状态 `complete` 只表示机械取证完成，不表示完成了语义理解或用户确认。
- `probe.json`：时长、尺寸、帧率及音轨信息。
- `boundaries.json`：机械画面变化候选，不是最终镜头清单。
- `grids/`：覆盖全片的时间码拼图，有成功转写时附文字上下文。默认每 1 秒采样，短片仍至少取一个有效时间点。
- `audio.wav`：原片音轨的便于收听版本，只有原片有音轨时产生。
- `transcript.json`：仅复用已有转写或显式申请并成功转写时产生。
- `logs/`：每个命令的标准输出和错误。实际失败会记录为失败，不用空结果伪装成功。

退出码：`0` 机械取证完成；`2` 有可用证据但部分步骤失败；`1` 无法建立基础证据；参数错误同 Python argparse 的 `2`。阅读具体状态和日志后决定下一步。脚本不会自动重试转写，也不会生成语义结论。保留部分结果继续使用；需要重跑时使用新目录和已有转写。

如原片有声音但尚未转写，Agent 仍需收听并还原关键口播；若没有可用收听能力或关键台词无法听清，应取得用户转写或在服务和费用条件满足后转写。不能把“没有转写文件”解释为“原片没有口播”。

## 加密查看与语义解析

概览拼图不能证明一秒内没有短镜头。根据口播、候选变化点和实际回放选择区间，再用下列真实接口获取细节（使用实际路径）：

```bash
hypit media tiles reference.mp4 --start 0 --end 3 --every 0.2 \
  --columns 3 --rows 3 --cell 480 --to evidence/opening-dense
hypit media frames reference.mp4 --at 0.2,0.7,1.4 --label-time \
  --to evidence/hook-frames
hypit media cut reference.mp4 --start 2 --end 4 --label-time \
  --to evidence/transition.mp4
```

词画对应可加 `--transcript transcript.json`，必须与原片共享时间轴。精细动作可用 `tiles --every-frame` 分页查看。输出需新路径，Hypit 自身也拒绝覆盖。

Agent 打开生成的图片、回放原片和音轨、阅读转写后，才撰写 `ANALYSIS.md`、`TIMELINE.md`。区分听到/看到的事实和需求、人群、传播作用推测。音轨含混、抽帧间隙或无法读清的包装小字应保留不确定性。

## 与已有 Hypit Skill 协作

Hypit CLI 与 Hypit Skill 是两个不同的安装项。本流程只强制依赖 CLI，环境脚本不会复制、更新或自动安装另一个 Hypit Skill；本地取证通过已核验接口即可运行，不依赖另一个 Skill 的绝对安装路径。需要配置 Runtime、选择转写服务或处理特殊媒体行为时，若已安装 `$hypit`，读取其 `references/creation/reference-video.md`、`references/environment/model-and-provider.md` 和相关环境文档；优先复用既有服务和素材。本 Skill 到提示词交付为止，不因引入 Hypit 自动启动生成或渲染。
