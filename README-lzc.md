# 懒猫微服 LPK 打包说明

本仓库以 [getpaseo/paseo](https://github.com/getpaseo/paseo) 为上游模板：代码保持与上游一致，
只在独立路径/文件名下追加懒猫微服（Lazycat MicroServer）的 lpk 打包文件，合并上游时不会冲突。

打包的是**上游官方的 Docker 镜像**（`ghcr.io/getpaseo/paseo`，daemon + 自带网页界面），
在它上面补装 agent CLI；不做任何源码改动，所以上游发版后 `git merge` 就能跟上。

## 文件结构

| 文件 | 作用 |
| ---- | ---- |
| `package.yml` | lpk 元数据：包名 `cloud.lazycat.app.paseo`、版本（跟随上游 release）、多语言描述、权限 |
| `lzc-manifest.yml` | 运行结构：一个 `paseo` 服务 + 路由 / 环境变量 / 持久化 / 健康检查 |
| `lzc-build.yml` | 构建配置：由 `lzc/build.sh` 生成镜像定义并 `embed:paseo` 打进 lpk |
| `lzc-deploy-params.yml` | 可选安装参数：`paseo_password`（默认留空） |
| `lzc/build.sh` | buildscript：按 `package.yml` 的版本生成 `lzc/gen/Dockerfile` |
| `lzc/agents.env` | 烧进镜像的 agent CLI 版本（唯一的版本来源） |
| `lzc/icon.png` | 应用图标（取自上游 `packages/app/assets/images/icon.png`，1024×1024） |
| `lzc/sync-upstream.sh` | 一键 fetch + merge 上游，并检查 `package.yml` 是否落后 |
| `README-lzc.md` | 本文档 |

## 运行模型

```
浏览器 ── https://paseo.<盒子域名>/ ─────► lzc-ingress（强制懒猫账号登录）
                                              │
                                              ▼
                                     paseo:6767（官方镜像）
                                     ├─ 网页界面 / REST API
                                     ├─ /ws  WebSocket（daemon 控制通道）
                                     └─ 启动 agent：claude / codex / opencode / copilot …
```

- **鉴权**：只靠懒猫账号登录。manifest 里**故意不设** `PASEO_PASSWORD`，
  这样网页界面打开即用，不用在懒猫登录之后再输一遍密码；`package.yml` 里
  `admin_only: true`，因为 daemon 起的 agent 能在工作目录里执行任意命令。
  要让懒猫账号之外的客户端（第三方 Paseo 桌面端/手机端直连、CLI）也能连，
  安装时填 `paseo_password`，之后浏览器也需要这个密码。
- **Host 校验**：Paseo 有 Vite 风格的 Host 白名单（防 DNS rebinding），
  manifest 里 `PASEO_HOSTNAMES={{ .S.AppDomain }},.lzcapp,paseo,localhost`；
  `localhost` 和 IP 是 daemon 内置放行的。网关转发若改了 Host 头，会在这里
  看到 403 `Invalid Host header`。
- **反向代理**：`PASEO_TRUSTED_PROXIES` 信任盒子内网段，让网关的
  `X-Forwarded-Proto/-For` 生效；`PASEO_APP_BASE_URL` 指向应用域名，配对链接
  和「浏览器打开」地址才会指回这个应用。
- **持久化**：
  - `/lzcapp/var/paseo` → 容器 `/home/paseo`：daemon 状态、会话、worktree，
    以及 agent 的登录凭据（`.claude`、`.codex`、`.config`、`.local` 等）。
  - `/lzcapp/var/workspace` → 容器 `/workspace`：Paseo 与 agent 共享的代码目录。
  - 升级应用不会丢数据；卸载应用是否保留由盒子侧策略决定。
- **首次启动**：daemon 会后台下载本地语音模型（sherpa-onnx 的
  parakeet/kokoro，来自 GitHub releases），用于语音输入与朗读，落在
  `/lzcapp/var/paseo/.paseo/models`。不想要这些功能/流量时，在应用环境变量里加
  `PASEO_VOICE_MODE_ENABLED=false`、`PASEO_DICTATION_ENABLED=false` 重启即可。
- **Relay**：上游新 home 默认 `relay.enabled=true`（连接 `relay.paseo.sh` 用于
  设备配对）。不需要可以设 `PASEO_RELAY_ENABLED=false`。

## 镜像

`lzc/build.sh` 生成 `lzc/gen/Dockerfile`：

```dockerfile
FROM ghcr.io/getpaseo/paseo:<package.yml 的版本，去掉 + 后缀>
USER root
RUN npm config set --location=global registry https://registry.npmmirror.com \
 && npm install -g @anthropic-ai/claude-code@… @openai/codex@… opencode-ai@… @github/copilot@…
RUN claude --version && codex --version && opencode --version && copilot --version
```

- 上游基础镜像故意不带 agent CLI（见上游 `docs/docker.md`），所以这一步是必须的，
  否则装完 Paseo 没有任何 agent 可用。
- agent 版本集中在 `lzc/agents.env`，升级时用 `npm view <pkg> version` 更新并重建。
- npm 走 `registry.npmmirror.com`（盒子和国内开发机直连 npmjs 不稳）；
  用 `NPM_REGISTRY=https://registry.npmjs.org sh lzc/build.sh` 可覆盖，
  生成的 npm 全局配置也会被运行时的 `npx` 安装（Providers 目录里那些 agent）复用。
- 最后一行 `--version` 冒烟：上游改了可执行文件名时构建就报错，而不是等用户第一次开会话才发现。

## 同步上游

```sh
git fetch upstream
git merge upstream/main
```

或者用脚本（会顺带对比版本）：

```sh
sh lzc/sync-upstream.sh          # fetch + merge + 报告
sh lzc/sync-upstream.sh --bump   # 顺便把 package.yml 的 version 改成上游版本
```

合并后要做的事：

1. `package.yml` 的 `version` 必须等于上游 release（镜像 tag 就是它）。
   只改打包、不动上游时，用 `0.12.0+lzc1` 这种 build 后缀（`+` 后的部分不会进镜像 tag）。
2. 确认上游发布了该 tag 的镜像：
   `docker buildx imagetools inspect ghcr.io/getpaseo/paseo:<version>`。
3. 过一眼 `lzc/agents.env`：agent 版本可以单独升，但和上游发版无关时不必每次动。
4. 上游若改了端口、环境变量名或 WebSocket 路径，同步改 `lzc-manifest.yml`；
   改了可执行文件名（`claude`/`codex`/`opencode`/`copilot`）改 `lzc/build.sh` 的冒烟行。

## 构建与安装

前置：`npm install -g @lazycatcloud/lzc-cli`，`lzc-cli box list` 能看到已连接的盒子
（`lzc-cli box switch <name>` 选默认盒子）。

```sh
mkdir -p release
# 终端如果挂了代理，先摘掉，否则 lzc-cli 可能连不上盒子
env -u ALL_PROXY -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  lzc-cli project build -o release/cloud.lazycat.app.paseo.lpk

# 安装到盒子
env -u ALL_PROXY -u http_proxy -u https_proxy \
  lzc-cli lpk install release/cloud.lazycat.app.paseo.lpk

# 粗略看包内容
lzc-cli lpk info release/cloud.lazycat.app.paseo.lpk
```

- 默认 `builder: remote`：镜像在盒子的「懒猫开发者工具」里按盒子架构构建，
  构建上下文只有 `lzc/gen/Dockerfile`（几 KB）。盒子没装开发者工具时改成
  `builder: local`——用本地 Docker 的 buildx 按 `linux/amd64` 构建后内嵌，
  要求本地能拉 `ghcr.io/getpaseo/paseo`。本地构建时如果 buildx 因权限写不了
  `~/.docker`，可以 `BUILDX_CONFIG=$PWD/.buildx docker buildx build …`。
- 想先验证镜像本身：

  ```sh
  sh lzc/build.sh
  docker buildx build --platform linux/amd64 -t paseo-lzc:test -f lzc/gen/Dockerfile lzc/gen --load
  docker run --rm -p 16767:6767 paseo-lzc:test
  curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:16767/api/health   # 200
  ```

## 商店发布

`embed:` 只含构建时那一种架构（remote 是盒子架构，local 是 amd64），上架商店前要：

1. 把派生镜像做成多架构（amd64 + arm64）推到公网 registry，例如
   `ghcr.io/<你>/paseo-lzc:<version>`；
2. `lzc-cli appstore copy-image ghcr.io/<你>/paseo-lzc:<version>` 复制到官方源；
3. 把 `lzc-manifest.yml` 的 `services.paseo.image` 换成返回的
   `registry.lazycat.cloud/...` 地址，并从 `lzc-build.yml` 删掉 `images.paseo`；
4. 准备截图/介绍，`lzc-cli appstore publish <lpk>` 提交审核。

## 安全清单

- `public_path` 一个都没开：网页界面、REST API、`/ws` 全在懒猫登录之后。
- 不发布 daemon 端口的 ingress；需要 box 内直连再加 TCP ingress，并设 `paseo_password`。
- `admin_only: true`；`/workspace` 和 `/home/paseo` 都是应用私有数据，别改成全局可写目录。
- agent 的登录凭据在 `/lzcapp/var/paseo` 里，等于盒子上的敏感文件，按盒子的备份/权限策略对待。
