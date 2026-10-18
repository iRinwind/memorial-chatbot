# 基于 Cloudflare Tunnel 搭建稳定家庭服务器对外服务管道指南

> **核心价值**：中国绝大多数家庭宽带处于动态公网 IP 或大内网环境下，IP 经常变动且入站 Web 端口受限。
> 使用免费的 **Cloudflare Named Tunnel**，无需固定公网 IP、无需配置路由器端口映射，即可实现开机自愈、全天候稳定的对外安全连接。

---

## 一、核心原理简介

与传统“端口映射”（容易被全网扫描且受动态 IP 影响）不同，Cloudflare Tunnel 采用**本地主动向外出站建立长连接**的机制：

```mermaid
flowchart LR
    Mobile["访客手机 / 微信服务"] -->|HTTPS 访问自定义域名| CF["Cloudflare 全球边缘节点"]
    CF <-->|双向安全加密隧道| Client["本地 cloudflared 守护进程"]
    Client -->|本地转发| App["本地纪念机器人服务"]
```

**为什么适合家庭服务器**：
- **无惧动态 IP 变动**：本地主动保持心跳，家庭路由器断网重拨或切换 IP 时，连接在数秒内自动恢复。
- **无需公网 IP 与端口映射**：路由器无需开端口，避免直接暴露在公网被扫描攻击。
- **免配置 HTTPS 证书**：Cloudflare 自动颁发并续期免费 SSL 证书。

---

## 二、通用搭建步骤 (三步建立管道)

### 步骤 1：准备一个托管在 Cloudflare 的自定义域名
- 将你在任何平台购买的域名权威 DNS 改为 Cloudflare 提供的地址即可免费接入托管。

### 步骤 2：在 Cloudflare 仪表盘创建 Named Tunnel
1. 登录 [Cloudflare Zero Trust 仪表盘](https://one.dash.cloudflare.com/)；
2. 导航至 **Networks** $\to$ **Tunnels** $\to$ 点击 **Create a tunnel**；
3. 选择 **Cloudflared** 类型，设置隧道名称并保存，复制后台生成的安装命令与 Token。

### 步骤 3：在家庭服务器上安装并以系统服务运行 cloudflared

根据系统选择安装命令，并注册为开机自启系统服务：

#### macOS 环境 (Homebrew)：
```bash
brew install cloudflared
sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
```

#### Linux 环境 (Debian / Ubuntu / Armbian)：
```bash
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
```

---

## 三、配置对外路由 (Public Hostname 映射)

在 Cloudflare 仪表盘该 Tunnel 的 **Public Hostname** 中添加一条规则：

- **Subdomain**：二级子域名（如 `memorial`）
- **Domain**：你托管的主域名（如 `yourdomain.com`）
- **Service Type**：`HTTP`
- **URL**：`localhost:你的服务端口`

保存后，外界即可通过 `https://memorial.yourdomain.com` 安全访问本地服务。

---

## 四、对接消息回调

将生成的公网域名配置到企业通讯软件（企业微信）自建应用的【接收消息服务器配置 (Webhook URL)】中（例如 `https://memorial.yourdomain.com/webhook`），即可打通手机端日常双向互动。
