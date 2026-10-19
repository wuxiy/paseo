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
| `lzc-build.yml` | 构建配置（默认 `builder: remote`，在盒子的开发者工具里按盒子架构构建）：由 `lzc/build.sh` 生成镜像定义并 `embed:paseo` 打进 lpk |
| `lzc-build.local.yml` | 本地构建变体（`builder: local`，本机 Docker buildx 按 `linux/amd64` 构建后内嵌） |
| `lzc-deploy-params.yml` | 可选安装参数：`paseo_password`（默认留空） |
| `lzc/build.sh` | buildscript：按 `package.yml` 的版本生成 `lzc/gen/Dockerfile` |
| `lzc/agents.env` | 烧进镜像的 agent CLI 版本（唯一的版本来源） |
| `lzc/icon.png` | 应用图标（取自上游 `packages/app/assets/images/icon.png`，1024×1024） |
| `lzc/sync-upstream.sh` | 一键 fetch + merge 上游，并检查 `package.yml` 是否落后 |
| `lzc/verify-lpk.py` | 安装前校验 lpk 内嵌镜像是否完整（见「构建与安装」） |
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
    bind 挂载进来时属主是 root，而入口脚本会把 daemon 和它启动的 agent 降到
    非 root 的 `paseo` 用户，所以 manifest 里有一段 `setup_script: chown paseo:paseo
    /workspace`（每次启动幂等执行），否则在 /workspace 里 clone / 改文件会 EACCES。
  - 升级应用不会丢数据；卸载应用是否保留由盒子侧策略决定。
- **首次启动**：daemon 会后台下载本地语音模型（sherpa-onnx 的
  parakeet/kokoro，来自 GitHub releases），用于语音输入与朗读，落在
  `/lzcapp/var/paseo/.paseo/models`。不想要这些功能/流量时，在应用环境变量里加
  `PASEO_VOICE_MODE_ENABLED=false`、`PASEO_DICTATION_ENABLED=false` 重启即可。
- **Relay**：新 home 默认 `daemon.relay.enabled=false`（上游
  `persisted-config.ts` 的 `DEFAULT_PERSISTED_CONFIG` 就是这么写的），所以
  `paseo daemon status` 里 `relay.enabled` 是 false。手机 App 想走 relay 配对，
  在界面 Settings → Pair Device → Enable relay，或容器里
  `paseo daemon config set daemon.relay.enabled true && paseo daemon restart`。
  relay 连接是盒子出站到 `relay.paseo.sh:443`（已确认可达），端到端加密，
  不需要对外暴露任何端口。

## 客户端怎么接

这个 lpk 现在同时开了两条路，盒子**不需要**外网访问权限：

| 客户端 | 地址 | 鉴权 |
| ------ | ---- | ---- |
| 手机 / 桌面 App（同一局域网） | `http://<盒子局域网IP>:6767` | daemon 密码（12 位，`usage` 里显示，或用 `paseo_password` 参数自定义） |
| 同一局域网的 CLI / agent | `paseo --host http://<盒子局域网IP>:6767` | 同上（CLI 会提示，或 host 里带） |
| 浏览器 | `https://paseo.<域名>` | 懒猫账号登录 + daemon 密码 |
| 外网手机 | relay 配对（Settings → Pair Device → Enable relay，扫码） | 配对链接（端到端加密，盒子只出站） |

实现细节：

- `application.ingress` 用 TCP 把服务的 `6767` 发布到盒子局域网（`publish_port: "6767"`）。
  这是手机 App 在无外网、无 relay 时唯一能直连的入口。
- 端口一旦发布，daemon 必须带密码，所以 `PASEO_PASSWORD` 用
  `{{ printf "%.12s" (stable_secret "paseo_password") }}` 按盒子生成 12 位；
  `lzc-deploy-params.yml` 里的 `paseo_password` 可以覆盖成好记的值。
  `/api/health` 是密码唯一豁免的路径，方便探活。
- 浏览器同样要输这个密码（Paseo 自己的登录，在懒猫账号登录之后）；`usage`
  文本里直接渲染了密码，首次打开应用页就能看到。
- 外网访问（懒猫应用的「外网访问」开关）不是必需的：局域网直连只走盒子内网，
  relay 只走盒子出站。要给第三方客户端走域名直连，才需要 `public_path: [/api, /ws]`
  （当前没开，避免把 daemon 裸露到域名上）。

## NAS 上的其他 agent

Paseo 只在**自己的容器里**启动 provider 进程；NAS 宿主机上已经装好的 CLI 它看不见。
两个方向分开看：

1. **让 Paseo 使用这个 agent（作为 provider）**
   - 最稳：把 CLI 烧进镜像——在 `lzc/agents.env` 加版本、在 `lzc/build.sh` 的
     `npm install -g` 里加包名，重建 lpk。
   - ACP agent 不用改镜像：在 Paseo 的 Providers 目录里添加，或写
     `~/.paseo/config.json`（容器 `/home/paseo/.paseo/config.json`，盒子
     `/lzcapp/var/paseo/.paseo/config.json`）：
     ```json
     {"agents":{"providers":{"my-agent":{"extends":"acp","label":"My Agent","command":["my-agent","--acp"]}}}}
     ```
     然后 `paseo reload`。
   - 宿主机二进制：在 manifest 里 bind 挂载进容器，用 provider 的 `command`
     指到挂载路径；要求二进制能在 Debian bookworm 里跑，登录凭据目录也要一起挂。
2. **让 NAS 上的 agent / 脚本调用 Paseo（作为客户端）**
   - 同一局域网：`npm i -g @getpaseo/cli` 后 `paseo --host http://<盒子IP>:6767`，
     密码用 `usage` 里那个；SDK 用 `ws://<盒子IP>:6767/ws`。
   - Paseo 容器内：`127.0.0.1:6767`。
   - `/mcp/agents` 是注入给 Paseo 自己启动的 agent 的内部端点（每次 daemon 启动
     随机 token），不是外部 agent 的公共 API；外部集成走 CLI 或
     `@getpaseo/client`。

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

# 安装前校验内嵌镜像完整（lpk info 只看元数据，不校验 blob）
python3 lzc/verify-lpk.py release/cloud.lazycat.app.paseo.lpk
```

- **装之前一定跑一次 `lzc/verify-lpk.py`**。`lzc-cli` 的 `.lzc-cli-cache/`
  会按镜像 ID 复用打好的 OCI 包，混用 remote/local 构建时缓存里的 blob 可能不全，
  打出来的 lpk 表面正常（`lpk info` 不报错），装到盒子才失败：
  `pull image failed: ... archive/tar: invalid tar header`。遇到这种情况：

  ```sh
  rm -rf .lzc-cli-cache            # 清掉按镜像 ID 复用的包缓存
  rm -f release/*.lpk
  # 重新 build，再 verify 一次
  ```

  校验器直接读 tar，把 `images/index.json` → manifest → config/layer 全链路
  的 digest 都重算一遍，缺 blob 或哈希不符都会报出来。

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

## 已验证

2026-10-19 在 cywu 盒子（x86_64，`lzc-build.yml` 的 remote 构建）上验证：

- `lzc-cli project info`：`Installed` / `Status_Running`，`app` 与 `paseo` 两个容器 `healthy`。
- 未登录访问 `https://paseo.<域名>/`：307 跳懒猫登录页（没有 `public_path`）。
- 容器内 Host 校验：`/api/health` 直连 200、`Host: <AppDomain>` 200、`Host: paseo` 200、
  `Host: evil.example.com` 403。
- 密码生效：`/api/status` 无 `Authorization` 返回 401、带 `Bearer <密码>` 返回 200；
  `/api/health` 是唯一豁免。`/ws` 握手 101，鉴权在 `hello` 阶段。
- 渲染后的环境变量正确：`PASEO_HOSTNAMES=…`、`PASEO_APP_BASE_URL=https://<域名>`、
  `PASEO_PASSWORD` 为 `usage` 里显示的 12 位密码；`ingress` 发布 `6767`。
- 四个 agent CLI 在 paseo 容器里都能执行（构建时 `--version` 冒烟 + 安装后 `which`）。
- `/workspace` bind 挂载属主问题已修：manifest 里 `setup_script: chown paseo:paseo
  /workspace`，重装后以 `paseo` 身份 `touch /workspace/.probe` 成功。
- **局域网 6767 的可达性未能在本机验证**：这台开发机是通过懒猫隧道（域名解析到
  127.0.0.1）访问盒子的，和盒子不在同一网段，扫不到 6767。请用盒子同网段的手机/
  电脑执行 `curl http://<盒子IP>:6767/api/health`（应 200）确认；如果拒绝连接，
  把 `ingress` 的 `publish_port` 去掉（端口默认取 `port`）或检查盒子防火墙。

## 安全清单

- `public_path` 一个都没开：网页界面、REST API、`/ws` 仍然在懒猫登录之后。
- 局域网 `6767` 是唯一的裸端口暴露，靠 daemon 密码保护；**不要把密码留空**，
  也不要把 `ingress` 加到公网。密码用 `paseo_password` 参数或 `stable_secret`。
- `admin_only: true`；`/workspace` 和 `/home/paseo` 都是应用私有数据，别改成全局可写目录。
- agent 的登录凭据在 `/lzcapp/var/paseo` 里，等于盒子上的敏感文件，按盒子的备份/权限策略对待。
