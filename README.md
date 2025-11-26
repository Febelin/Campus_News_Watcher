# Campus_News_Watcher
A Python-based watcher that fetches campus news daily, filters articles, and sends automated email reports
> 自动抓取美国大学校园新闻 & 个性化中文日报推送（GitHub Actions 自动运行）

## 📌 项目简介
**Campus News Watcher** 是一个自动化的校园资讯推送项目，使用 GitHub Actions 每日定时运行，抓取美国多所大学/媒体的 RSS 新闻源，并根据你的兴趣偏好生成 **个性化新闻推荐报告（中文）**，最终通过电子邮件自动发送给你。

整个流程完全自动：

1. 📰 抓取最新新闻（RSS）
2. 🧹 过滤重复推送（seen_items.csv）
3. 🤖 DeepSeek 个性化兴趣打分（0–100）
4. 🇨🇳 英文标题自动翻译成中文
5. 📄 生成日报文本文件
6. 📧 自动发送到你的电子邮箱

---

## 🧱 项目结构

```
Campus_News_Watcher/
├── .github/workflows/
│   └── campus_news_daily.yml     # GitHub Actions 定时任务
├── config/
│   ├── feeds.yaml                # RSS 源列表
│   └── settings.yaml             # 个性化推荐设置
├── data/
│   ├── raw/                      # 每次抓取的新闻
│   ├── reports/                  # 每日生成的中文日报
│   └── seen_items.csv            # 已推送新闻记录（去重）
├── daily_report.py               # 生成个性化日报
├── fetch_feed.py                 # 抓取 RSS 数据
├── send_email.py                 # 发送邮件
├── requirements.txt              # Python 依赖
└── README.md
```

---

## ⚙️ GitHub Actions 自动运行

项目使用 GitHub Actions **每天 UTC 15:00 定时运行**（大约是美西早上 7–8 点）：

```yaml
on:
  schedule:
    - cron: "0 15 * * *"
  workflow_dispatch:
```

你也可以手动运行：

```
Actions → Campus News Daily → Run workflow
```

---

## 🔑 配置 GitHub Secrets（必做）

前往：

```
Repo → Settings → Secrets and variables → Actions
```

创建以下 Secrets：

| 名称 | 用途 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `EMAIL_FROM` | 发件邮箱（如 Gmail 地址） |
| `EMAIL_TO` | 收件邮箱 |
| `EMAIL_PASSWORD` | 邮箱 App Password（Gmail 是 16 位） |
| `EMAIL_SMTP_SERVER` | SMTP 服务器（例：smtp.gmail.com） |
| `EMAIL_SMTP_PORT` | SMTP 端口（例：587） |

---

## 🧠 个性化推荐设置（config/settings.yaml）

你可以通过用户画像提升推荐准确度：

```yaml
personalization:
  enable: true
  user_profile: |
    我喜欢校园政策、安全事件、科技相关新闻，不太关心体育比赛。
  max_candidates: 80
  top_n: 10
```

---

## 🌐 添加你的 RSS 源（config/feeds.yaml）

可自由增加任何学校或媒体的 RSS：

```yaml
- name: University of Oregon News
  url: https://around.uoregon.edu/news/feed

- name: The Chronicle of Higher Education
  url: https://www.chronicle.com/rss/latest
```

---

## 🚀 本地运行（可选）

```bash
pip install -r requirements.txt
python fetch_feed.py
python daily_report.py
python send_email.py
```

---

## 📨 日报示例

```
美国大学校园资讯 - 个性化推荐日报
生成时间：2025-11-26 07:20

【个性化推荐】
- [UOregon] (92 分) 校园安全部门发布节假日防盗指南
    EN: Campus safety releases holiday theft prevention tips
    链接：https://...

- [Chronicle] (87 分) 大学研究人员开发新型心理健康干预系统
    EN: Researchers develop new mental health intervention system
    链接：https://...
```

---

## 📄 License
MIT License
