# 广州行程体检 + 白云山夜爬

一个面向广州短途出行的工具，两个页面：

- **行程体检**：贴一份已经排好的行程，检查时间够不够、是否撞上闭馆日、两站之间是否来得及、单日强度是否超载、地点是否在库里，输出带依据的问题清单。
- **白云山夜爬**：给出"某个时刻能走通"的路线，自动避开已关闭的山门与无照明路段；走不通时明确说明卡在哪个门、最远能到哪、建议怎么改。

**不做**：旅游攻略、通用导航。范围只到白云山内部路线 + 城市接驳。

## 目录

```
data/
  poi.csv               广州 34 个地点（开放窗口、夜间状态、照明、坡度、是否需预约）
  baiyun_nodes.csv      白云山 10 个节点（4 个山门 + 岔路口 + 山顶）
  baiyun_edges.csv      白云山 12 条路段（含各段可通行时段）
  demo_itinerary.txt    三天示例行程
docs/
  night_rules.md        通行判定口径（半开区间 / 整段覆盖 / 无法通行时的输出规范）
  decisions.md          9 条边界决策（怎么定、为什么）
  data_dictionary.md    字段字典与校验规则
tools/
  preflight.py          数据校验：字段、枚举、时间窗、坐标、步行速度
  geo_fix.py            用高德地理编码校正坐标
app/                    应用代码
tests/                  测试
```

## 快速开始

```bash
python tools/preflight.py          # 先校验数据，应为 0 FAIL
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
streamlit run app_ui.py
```

可选：校正坐标（数据里带"待校验"字样时建议先跑一次）

```bash
set AMAP_KEY=你的Web服务Key
python tools/geo_fix.py data/poi.csv
```

## 判定口径

- 时间窗是**半开区间** `[start, end)`：`06:00-22:00` 表示 22:00 整点起不可用。
- 一段路可走，要求**整段落在窗口内**：出发时间要够早，到达时间也要在关门前。只看出发时刻是不够的。
- 夜间（21:00 之后）如果结论只依赖未校验的数据，直接说明无法判断，不给路线。
- 走不通时给出「最远能到哪 + 卡在哪个门/哪段路、什么时间 + 建议」，不给"大概能走"的路线。

## 关于高德

只用在三处：坐标校正、城市接驳距离、地图打点。

**景区内部不用第三方路径规划**——它不知道哪个门晚上关、哪段路夜间封闭。这部分由本地数据和时间窗规则计算。

接口调用失败或超时 2 秒时，退回直线距离换算（×1.3、步行 4km/h），并在结果里标明是估算值。

## 部署

本地直接运行：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
streamlit run app_ui.py
```

Docker：

```bash
cp .env.example .env        # 首次必须做：compose 会读取 .env，缺文件会启动失败
docker compose up -d --build
docker compose ps           # 看两个服务是否 healthy
docker compose down         # 停止
```

当前代码尚未读取任何环境变量，`.env` 是为后续接入高德与模型预留的；不填也能跑，但文件要存在。

服务器部署要点：

- 安全组只放行 22 / 80 / 443，**不要**对公网直接暴露 8501 与 8000，让 Nginx 反代；
- 对外必须走 HTTPS，Streamlit 经反代要转发 `Upgrade` / `Connection` 头，否则页面一直在 Connecting；
- 三个高德 Key 只放服务端环境变量，`.env` 权限设 600，不要写进前端代码或镜像；
- 高德 JS Key 的**域名白名单只认域名不认 IP**，绑定域名后必须把域名加进去，否则地图空白；
- 首次启动前 `mkdir -p logs`，避免容器用户写日志没有权限；
- 完整的华为云部署步骤见 [docs/deploy-huawei.md](docs/deploy-huawei.md)。

## 说明

数据于 2026 年 11 月整理，开放时间与门票以景区、场馆公告为准。夜间登山有风险，本工具只作路线参考。
