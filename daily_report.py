import os
import glob
import yaml
from datetime import datetime, timedelta, timezone
import pandas as pd
import re
from dotenv import load_dotenv
from openai import OpenAI
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

# 加载 .env 里的 DEEPSEEK_API_KEY
load_dotenv()

RAW_DIR = "data/raw"
SETTINGS_PATH = "config/settings.yaml"
REPORT_DIR = "data/reports"
SEEN_PATH = "data/seen_items.csv"   # ⭐ 已推送过的链接集合


# ======================
# 基础配置与工具函数
# ======================

def load_settings():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def translate_to_zh(text: str) -> str:
    """
    使用 DeepSeek 进行英文标题 → 中文翻译。
    """
    text = text or ""
    if not text.strip():
        return ""

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        # 没 key 就直接返回原文，不报错
        return text

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个精准翻译助手，只输出翻译结果。"},
                {"role": "user", "content": f"请把下面英文翻成自然简洁的中文：\n{text}"},
            ],
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        # 出错就退回英文标题，避免整个脚本挂掉
        return text


def get_recent_data(df: pd.DataFrame, days_window: int) -> pd.DataFrame:
    """
    取最近 days_window 天内的新闻。
    （现在 df 基本是当天的，但保留这个函数以防以后改动）
    """
    df = df.copy()
    for col in ["published", "fetched_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    ts = df["published"].fillna(df["fetched_at"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_window)
    return df[ts >= cutoff]


def load_today_news() -> pd.DataFrame:
    """
    ✅ 优先加载“今天”的 news_YYYY-MM-DD.csv；
    如果没有，就退而求其次，使用 data/raw 里最新的一份 news_*.csv。
    """
    os.makedirs(RAW_DIR, exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_path = os.path.join(RAW_DIR, f"news_{today_str}.csv")

    if os.path.exists(today_path):
        print(f"[信息] 读取今天的新闻文件: {today_path}")
        return pd.read_csv(today_path)

    # 兜底：找 raw 里最新的 news_*.csv
    pattern = os.path.join(RAW_DIR, "news_*.csv")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(
            f"未找到任何 news_*.csv 文件，请先运行抓取脚本生成数据（目录：{RAW_DIR}）"
        )

    latest_file = max(files, key=os.path.getmtime)
    print(f"[警告] 今天的文件不存在，改为使用最新的文件: {latest_file}")
    return pd.read_csv(latest_file)


# ======================
#   已推送链接管理
# ======================

def load_seen_links() -> set:
    """
    读取历史已推送的链接集合（seen_items.csv）。
    如果不存在，则返回空集合（表示第一天，所有都算新）。
    """
    if not os.path.exists(SEEN_PATH):
        print("[信息] 未发现 seen_items.csv，视为第一天推送。")
        return set()

    try:
        df_seen = pd.read_csv(SEEN_PATH)
        if "link" not in df_seen.columns:
            return set()
        links = set(df_seen["link"].dropna().astype(str))
        print(f"[信息] 已加载历史已推送链接 {len(links)} 条。")
        return links
    except Exception as e:
        print(f"[警告] 读取 {SEEN_PATH} 出错: {e}，视为无历史记录。")
        return set()


def save_seen_links(links: set):
    """
    把最新的已推送链接集合写回 seen_items.csv。
    """
    os.makedirs(os.path.dirname(SEEN_PATH), exist_ok=True)
    df_seen = pd.DataFrame(sorted(links), columns=["link"])
    df_seen.to_csv(SEEN_PATH, index=False)
    print(f"[信息] 已更新已推送链接集合，共 {len(links)} 条 -> {SEEN_PATH}")


def filter_unseen_items(df: pd.DataFrame, seen_links: set) -> pd.DataFrame:
    """
    从 df 中只保留“还没有推送过的新闻”（link 不在 seen_links 中）。
    """
    if "link" not in df.columns:
        print("[警告] 数据中没有 link 字段，无法做历史去重，全部保留。")
        return df

    if not seen_links:
        print("[信息] 当前没有历史记录，保留所有新闻用于首次推送。")
        return df

    links_today = df["link"].astype(str)
    mask_new = ~links_today.isin(seen_links)
    df_new = df[mask_new].copy()

    removed = len(df) - len(df_new)
    print(f"[信息] 今日共 {len(df)} 条新闻，其中 {removed} 条已推送过，保留 {len(df_new)} 条新新闻。")

    return df_new


# =======================
#   DeepSeek 个性化推荐
# =======================

def get_deepseek_client():
    """
    初始化 DeepSeek 客户端。
    需要环境变量 DEEPSEEK_API_KEY。
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("[警告] 未检测到环境变量 DEEPSEEK_API_KEY，跳过个性化推荐部分。")
        return None

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )
    return client


def score_item_with_deepseek(client: OpenAI, user_profile: str, item: dict) -> float:
    """
    给单条新闻打兴趣分（0-100），使用 DeepSeek。
    只返回一个数字；解析失败时返回 0。
    """
    title = item.get("title", "") or ""
    summary = item.get("summary", "") or ""
    feed_name = item.get("feed_name", "") or ""
    link = item.get("link", "") or ""

    content_snippet = summary if summary.strip() else title

    prompt = f"""
你是一个个性化新闻推荐助手，请严格按照下面要求打分：

[用户画像]
{user_profile}

[新闻信息]
- 学校 / 媒体: {feed_name}
- 标题: {title}
- 摘要: {content_snippet}
- 链接: {link}

任务：请根据“用户画像”和这条新闻的大致内容，
判断用户看到这条新闻时的兴趣程度，打出一个 0-100 的分数：
- 0 分：完全不感兴趣
- 50 分：一般般，可以看看
- 80 分以上：很感兴趣，强烈推荐推送

**非常重要：你的回复只能包含一个阿拉伯数字（0 到 100 之间的整数），不要带任何解释和其他内容。**
"""

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个只返回数字评分的推荐系统，不要输出解释。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            stream=False,
        )
        content = resp.choices[0].message.content.strip()
        # 有时会返回“85/100”之类，这里提取第一个数字
        digits = re.findall(r"\d+", content)
        if not digits:
            return 0.0
        score = float(digits[0])
        return max(0.0, min(100.0, score))
    except Exception as e:
        print(f"[DeepSeek 错误] 打分失败: {e}")
        return 0.0


def personalized_recommendations(recent_df: pd.DataFrame, settings: dict) -> Optional[pd.DataFrame]:
    """
    使用 DeepSeek 对最近的新闻做个性化打分，返回 Top N 的 DataFrame。
    并发调用 DeepSeek，加速打分过程。
    """
    personalization = settings.get("personalization", {})
    enable = personalization.get("enable", False)
    if not enable:
        print("[提示] personalization.enable = false，未开启个性化推荐。")
        return None

    user_profile = personalization.get("user_profile", "").strip()
    if not user_profile:
        print("[提示] settings.yaml 中 personalization.user_profile 为空，跳过个性化推荐。")
        return None

    client = get_deepseek_client()
    if client is None:
        return None

    max_candidates = int(personalization.get("max_candidates", 80))
    top_n = int(personalization.get("top_n", 10))
    # 可以在 settings.yaml 里加 personalization.max_workers 配置，否则默认 30
    max_workers = int(personalization.get("max_workers", 30))

    if recent_df.empty:
        print("[提示] recent_df 为空，没有可以做个性化推荐的新闻。")
        return None

    # 按时间排序，最新在前
    tmp = recent_df.copy()
    for col in ["published", "fetched_at"]:
        if col in tmp.columns:
            tmp[col] = pd.to_datetime(tmp[col], errors="coerce", utc=True)
    ts = tmp["published"].fillna(tmp["fetched_at"])
    tmp = tmp.assign(_ts=ts).sort_values("_ts", ascending=False)

    # 取前 max_candidates 条作为候选
    candidates = tmp.head(max_candidates).copy()

    print(f"[信息] 正在使用 DeepSeek 并发为最近 {len(candidates)} 条新闻打兴趣分（max_workers={max_workers}）...")

    # 把每一行转成 dict，方便在线程池里传参
    items = list(candidates.to_dict(orient="records"))

    def _score(item_dict):
        # 单条的包装函数，方便在线程池里调用
        return score_item_with_deepseek(client, user_profile, item_dict)

    # 使用线程池并发请求
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        scores = list(executor.map(_score, items))

    candidates = candidates.assign(_personal_score=scores)
    ranked = candidates.sort_values("_personal_score", ascending=False).head(top_n)

    return ranked


# ======================
#         主程序
# ======================

def main():
    try:
        df = load_today_news()   # 当天 / 最新的抓取结果
    except FileNotFoundError as e:
        print(str(e))
        return

    # 1. 读取历史已推送链接
    seen_links = load_seen_links()

    # 2. 只保留“还没推送过的新闻”
    df = filter_unseen_items(df, seen_links)
    if df.empty:
        print("今天没有新的新闻（全部都已经推送过了）。结束。")
        return

    settings = load_settings()

    # 3. 最近 days_window 内的新闻（其实一般就是今天）
    recent = get_recent_data(df, settings["hot_topics"]["days_window"])

    now = datetime.now()
    print("=" * 80)
    print("美国大学校园资讯 - 个性化推荐日报")
    print("生成时间：", now.strftime("%Y-%m-%d %H:%M"))
    print("=" * 80, "\n")

    # 4. DeepSeek 个性化推荐（只在未推送的新新闻里选 topN）
    personalized = personalized_recommendations(recent, settings)

    if personalized is None or personalized.empty:
        print("当前没有可推荐的新闻（可能是 recent 为空，或者 personalization 未开启 / 未配置）。")
        print("结束。")
        return

    # ===== 这里开始：既打印，也顺便拼一个邮件文本 =====
    print("【个性化推荐】根据你的性格和兴趣挑出的新闻：\n")

    email_lines = []
    email_lines.append("美国大学校园资讯 - 个性化推荐日报")
    email_lines.append(f"生成时间：{now.strftime('%Y-%m-%d %H:%M')}")
    email_lines.append("")
    email_lines.append("【个性化推荐】根据你的性格和兴趣挑出的新闻：")
    email_lines.append("")

    # 用来更新 seen_links：只把“真正推送出去的”记到历史里
    recommended_links = set()

    for _, row in personalized.iterrows():
        zh_title = translate_to_zh(row.get("title", ""))
        en_title = row.get("title", "")
        feed_name = row.get("feed_name", "")
        link = str(row.get("link", ""))
        score = row.get("_personal_score", 0)

        line1 = f"- [{feed_name}] ({int(score)} 分) {zh_title}"
        line2 = f"    EN: {en_title}"
        line3 = f"    链接: {link}"

        # 打印到终端
        print(line1)
        print(line2)
        print(line3)
        print()

        # 同时存到邮件文本里
        email_lines.append(line1)
        email_lines.append(line2)
        email_lines.append(line3)
        email_lines.append("")

        if link:
            recommended_links.add(link)

    print("结束。")

    # 5. 把本次“真正推荐”的链接并入 seen_links
    if recommended_links:
        seen_links.update(recommended_links)
        save_seen_links(seen_links)

    # ===== 把邮件文本写入文件 =====
    os.makedirs(REPORT_DIR, exist_ok=True)
    date_str = now.strftime("%Y-%m-%d")
    txt_path = os.path.join(REPORT_DIR, f"recommendations_{date_str}.txt")

    email_body = "\n".join(email_lines)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(email_body)

    print(f"\n[信息] 已将推荐内容保存到：{txt_path}")


if __name__ == "__main__":
    main()
