# 基于 Cloudflare Tunnel 搭建稳定家庭服务器对外服务管道指南 (Zero Trust Tunnel Guide)

> **核心价值**：中国绝大多数家庭宽带处于动态公网 IP 或大内网（NAT444）环境下，不仅 IP 每隔 24~48 小时变动一次，且运营商默认封禁 80/443 等入站 Web 端口。
> 本指南介绍如何利用完全免费的 **Cloudflare Named Tunnel**，在无需固定公网 IP、无需修改家庭路由器端口映射的前提下，建立稳定、安全、防攻击且支持自动重连的全天候对外服务管道。

---

## 一、核心原理：主动向外出站隧道 (Outbound Tunnel)

传统的内网穿透（如 DDNS + 端口转发）要求家庭路由器直接向公网开放端口，不仅容易遭受全网端口扫描与恶意攻击，且一旦家庭宽带 IP 变动就会导致服务中断。

Cloudflare Tunnel 采用了完全相反的**主动向外出站长连接**架构：

```mermaid
flowchart LR
    subgraph ClientSide ["外界访问端 (手机微信 / Web 客户端)"]
        Mobile["用户日常手机 / 企业微信服务"]
    end

    subgraph CloudEdge ["Cloudflare 全球边缘网络 (边缘代理与防护)"]
        CF_Edge["Cloudflare Anycast 边缘节点 (免费 SSL 证书 / DDoS 防护 / WAF)"]
    end

    subgraph LocalEnv ["家庭本地私有服务器 (Mac mini / Linux PC / NAS)"]
        Cloudflared["本地守护进程 (cloudflared)"]
        LocalService["本地常驻纪念机器人服务 (如 127.0.0.1:端口)"]
    end

    Mobile -->|1. 访问自定义域名 HTTPS| CF_Edge
    Cloudflared <==>|2. 主动向外建立 4 条加密 gRPC/QUIC 隧道 (出站流量)| CF_Edge
    Cloudflared -->|3. 内网回环转发至服务| LocalService
```

### 这种架构的 4 大优势：
1. **彻底免疫动态 IP 变动**：本地 `cloudflared` 进程通过主动向外发起连接维护心跳。无论家庭路由器何时断网重连、分配到什么新 IP，长连接隧道都会在几秒内自动愈合，公网访客完全无感知。
2. **零路由器配置与零安全暴露**：家庭路由器无需开启 DMZ、无需配置 UPnP，也无需开放任何公网端口，黑客扫描不到家庭真实公网 IP。
3. **开箱即用的合法 HTTPS 证书**：Cloudflare 自动颁发并续期顶级 SSL 证书，免去繁琐的 Let's Encrypt 配置。
4. **边缘安全与抗攻击**：自带 Cloudflare 免费版 DDoS 防护与 Web 应用防火墙（WAF），拦截恶意请求。

---

## 二、通用搭建步骤 (三步建立管道)

### 步骤 1：准备一个托管在 Cloudflare 的自定义域名
- 如果你已有域名（例如托管在 DNSPod、Dynadot、阿里云或腾讯云），只需将其权威 DNS 服务器修改为 Cloudflare 提供的地址即可完成免费托管。

### 步骤 2：在 Cloudflare 仪表盘创建 Named Tunnel
1. 登录 [Cloudflare Zero Trust 仪表盘](https://one.dash.cloudflare.com/)；
2. 导航至左侧菜单 **Networks** $\to$ **Tunnels**；
3. 点击 **Create a tunnel**，选择类型为 **Cloudflared**；
4. 为隧道起一个代号（例如 `home-memorial-tunnel`），点击保存后会得到一串专属的安装命令与身份 Token。

### 步骤 3：在家庭服务器上安装并以系统服务运行 cloudflared

根据你的家庭服务器操作系统，安装并将其注册为开机自启系统守护进程：

#### macOS 环境 (推荐 Homebrew)：
```bash
# 1. 安装 cloudflared
brew install cloudflared

# 2. 将隧道安装为开机自启系统服务 (替换为您在后台复制的 TOKEN)
sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
```

#### Linux 环境 (Ubuntu / Debian / Armbian)：
```bash
# 1. 下载并安装官方 .deb 包
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# 2. 注册并启动开机自启服务
sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
```

---

## 三、配置对外路由 (Public Hostname 映射)

在 Cloudflare 仪表盘中的刚刚创建的 Tunnel 详情页，点击 **Public Hostname** $\to$ **Add a public hostname**：

| 配置项 | 示例推荐值 | 作用说明 |
| :--- | :--- | :--- |
| **Subdomain** | `memorial` | 二级子域名（外界实际访问的网址前缀） |
| **Domain** | `yourdomain.com` | 你在 Cloudflare 托管的主域名 |
| **Path** | 留空（或按需指定子路径） | 转发的路由路径 |
| **Service Type** | `HTTP` | 协议类型 |
| **URL** | `localhost:你的服务端口` | 本地机器人或网关监听的内网回环地址与端口 |

点击 **Save hostname** 保存后，等待约 30 秒，Cloudflare 的全球边缘 CDN 将自动完成路由下发与 HTTPS 证书生效。

此时访问 `https://memorial.yourdomain.com` 即可安全访问家庭本地运行的服务。

---

## 四、与企业通讯软件（企业微信）回调打通

在对接企业办公软件自建应用时，将上述配置好的公网域名路径填入管理后台的【接收消息服务器配置 (Webhook URL)】中：
- 例如：`https://memorial.yourdomain.com/webhook`
- 无论手机何时发送微信消息，腾讯云服务器都会向该公网域名发起回调请求，通过 Cloudflare 边缘节点瞬间抵达你家中的服务器，完成秒级互动与响应。
