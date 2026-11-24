# 华为云部署指南（白云山夜爬 + 行程体检）

> 本文只写步骤与配置，供作品说明文档引用。实际执行时按顺序照做即可。
> 目标：公网通过 HTTPS 域名访问，支持高德 JS 交互地图。

---

## 0. 先选方案

| 方案 | 适合 | 说明 |
|---|---|---|
| **云耀云服务器 L 实例（HECS）** | ✅ 推荐 | 入门配置即可（2 核 2G），控制台简单，自带防火墙面板 |
| 弹性云服务器 ECS | 需要更灵活的网络/快照 | 配置项多，安全组要自己配 |
| CCE / 容器集群 | 不推荐 | 对单机应用是过度设计，成本与学习成本都高 |

> 为什么 2 核 2G 够：应用是单机 Streamlit + FastAPI，主要开销是 pandas 与请求转发，峰值内存约 400–600 MB。

---

## 1. 前置准备（有先后顺序，别反）

| 步骤 | 说明 | 注意 |
|---|---|---|
| 1.1 购买服务器 | 地域选**广州/深圳**（离用户近） | 镜像选 Ubuntu 22.04 或 Huawei Cloud EulerOS 2.0 |
| 1.2 绑定弹性公网 IP | HECS 通常自带 | 记下公网 IP |
| 1.3 域名 | 阿里云/腾讯云买的也行 | 需要能改 DNS 解析 |
| 1.4 **ICP 备案** | 国内服务器 + 域名必须备案 | **通常要求服务器剩余时长 ≥ 3 个月**，首次备案约 1–3 周，务必提前 |
| 1.5 SSL 证书 | 华为云「SSL 证书管理」申请 DV 免费证书 | 或部署后用 Let's Encrypt |

> **最大的时间风险是备案**。如果只剩两三天，别指望备案下来——直接用「公网 IP + 端口」交付，见第 7 节降级方案。

---

## 2. 安全组（防火墙）规则

只放行必要的三个端口，入方向：

| 端口 | 协议 | 来源 | 用途 |
|---|---|---|---|
| 22 | TCP | 你的出口 IP | SSH 登录（不要对 0.0.0.0/0 开放） |
| 80 | TCP | 0.0.0.0/0 | HTTP（用于证书验证与跳转 HTTPS） |
| 443 | TCP | 0.0.0.0/0 | HTTPS |

**不要**对公网开放 8501 / 8000 —— 让 Nginx 反代，应用端口只监听内网。

---

## 3. 安装 Docker

Ubuntu 22.04：

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # 重新登录生效
docker --version
docker compose version
```

Huawei Cloud EulerOS 2.0：

```bash
sudo dnf install -y docker
sudo systemctl enable --now docker
# compose 插件需单独装
sudo mkdir -p /usr/libexec/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/libexec/docker/cli-plugins/docker-compose
sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose
```

---

## 4. 上传代码

方式一（推荐，简单）：本机打包上传

```bash
# 本机执行（Windows 自带 scp）；把 <项目目录> 换成你的项目路径
scp -r <项目目录> root@<公网IP>:/opt/travel-checkup
```

方式二：走 Git（先在服务器上生成密钥并把公钥加到仓库）

```bash
git clone <仓库地址> /opt/travel-checkup
```

上传后确认目录：`app/ app_ui.py data/ docs/ tools/ Dockerfile docker-compose.yml requirements.txt .env.example`

> **不要上传 `.venv/`**（几百 MB 且平台相关），`.dockerignore` 已排除。

---

## 5. 配置环境变量

```bash
cd /opt/travel-checkup
cp .env.example .env
vim .env
```

填入三个 Key：

```ini
AMAP_KEY=你的Web服务Key
AMAP_JS_KEY=你的Web端JSKey
AMAP_SECURITY_CODE=你的安全密钥
```

**安全要求**：

- `.env` 权限设为 `600`：`chmod 600 .env`
- 绝不提交到仓库（`.gitignore` 已包含）
- Key 泄露过一次就重置（控制台可重新生成）

---

## 6. 启动

```bash
cd /opt/travel-checkup
docker compose up -d --build
docker compose ps          # 两个服务都应为 healthy / running
curl -s http://127.0.0.1:8000/healthz   # {"status":"ok"}
curl -s http://127.0.0.1:8501/_stcore/health  # ok
```

查看日志：

```bash
docker compose logs -f api
docker compose logs -f ui
tail -f logs/agent.log     # Agent 编排日志（挂载在宿主机）
```

---

## 7. Nginx 反向代理 + HTTPS

### 7.1 安装并配置

```bash
sudo apt install -y nginx     # EulerOS: sudo dnf install -y nginx
sudo systemctl enable --now nginx
```

`/etc/nginx/conf.d/travel.conf`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /.well-known/acme-challenge/ { root /var/www/certbot; }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/nginx/ssl/your-domain.pem;
    ssl_certificate_key /etc/nginx/ssl/your-domain.key;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # Streamlit 需要 WebSocket
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
    }

    # 后端接口
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

> Streamlit 必须转发 `Upgrade`/`Connection` 头，否则页面能开但一直"Connecting"。

### 7.2 证书放哪

- 华为云下载的 Nginx 格式证书：把 `.pem` 与 `.key` 放到 `/etc/nginx/ssl/`
- 或用 certbot：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## 8. 把域名加进高德白名单（最容易漏）

高德 JS API 的白名单**只认域名，不认 IP**。

1. 打开高德控制台 → 应用管理 → 你的 Key → 编辑
2. 在「域名白名单」里加入：`your-domain.com`
3. 保存后等 1–2 分钟生效

**不配的后果**：页面能打开，但地图区域空白，控制台报 `INVALID_USER_DOMAIN` 之类的错误。

---

## 9. 上线验证清单

| 检查项 | 怎么验 | 通过标准 |
|---|---|---|
| 域名解析 | `ping your-domain.com` | 解析到服务器公网 IP |
| HTTPS | 浏览器打开 `https://your-domain.com` | 绿锁，无证书警告 |
| 页面 | 首屏 | 出现「广州旅行助手」与两个 Tab |
| 行程体检 | 点「开始体检」 | 出 10 条问题，红黄分组 |
| 夜爬 | 选南门→摩星岭、22:00 | 出 113 分钟路线 + 分段照明 |
| 拒答 | 选柯子岭门、22:30 | 提示门已关，建议南门/西门 |
| JS 地图 | 看地图区域 | 有卫星影像与蓝色路线（不是白块） |
| 接口 | `curl https://your-domain.com/api/healthz` | `{"status":"ok"}` |
| 移动端 | 手机 4G 打开 | 能滚动、能点按钮 |

---

## 10. 降级方案（没备案 / 没域名 / 时间不够）

| 条件 | 做法 | 影响 |
|---|---|---|
| 只有公网 IP | 直接 `http://<IP>:8501`（安全组放行 8501） | JS 地图失效，自动降级静态图；无 HTTPS |
| 有域名但没备案 | 只能 80 端口短期跑，随时被封 | 不建议作为最终交付 |
| 完全没服务器 | 本地 `localhost` 演示 + 录屏 | 评委看视频，效果最好（JS 地图可用） |

> 材料里如实写部署形态，比硬凑一个打不开的链接更稳。

---

## 11. 日常运维

```bash
# 更新代码后重建
cd /opt/travel-checkup && git pull && docker compose up -d --build

# 看资源占用
docker stats --no-stream

# 清理无用镜像
docker image prune -f

# 数据备份（只备份数据与配置，不含镜像）
tar czf backup-$(date +%F).tar.gz data/ docs/ .env
```

**别忘了**：`.env` 只在服务器上，备份包要加密或单独保管。

---

## 12. 成本与时间预估

| 项 | 预估 |
|---|---|
| 服务器 | 入门配置按月计费即可，演示期买 1 个月 |
| 域名 | 首年通常几十元 |
| 备案 | 免费，但耗时 1–3 周 |
| 部署操作 | 熟练后 1–2 小时；首次含排错 3–5 小时 |

---

## 13. 与本地部署的差异（写进作品说明时用）

| 维度 | 本地 | 华为云 |
|---|---|---|
| 访问方式 | `localhost:8501` | `https://域名` |
| 高德 JS 地图 | 可用（白名单含 localhost） | 可用（白名单加域名） |
| 数据 | 本机文件 | 服务器目录 + 挂载卷 |
| 密钥 | 本机 `.env` | 服务器 `.env`（600 权限） |
| 用户 | 自己/同网设备 | 任何人 |
| 风险 | 无 | 端口暴露、密钥泄露、配额被刷 |
