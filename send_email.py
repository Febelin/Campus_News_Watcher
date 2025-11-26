# send_email.py
import os
import smtplib
import yaml
from datetime import datetime
from email.mime.text import MIMEText
from email.header import Header

EMAIL_CONFIG_PATH = "config/email.yaml"
REPORT_DIR = "data/reports"


def load_report():
    """
    从 daily_report.py 生成的文本文件中读取日报内容。

    daily_report.py 会写入：
        data/reports/recommendations_YYYY-MM-DD.txt

    日期优先从环境变量 REPORT_DATE 读取（格式：YYYY-MM-DD），
    如果没有，就用今天的日期。
    """
    date_str = os.environ.get("REPORT_DATE") or datetime.now().strftime("%Y-%m-%d")
    filename = f"recommendations_{date_str}.txt"
    path = os.path.join(REPORT_DIR, filename)

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. 请先运行 daily_report.py 生成当天的推荐日报。"
        )

    with open(path, "r", encoding="utf-8") as f:
        body = f.read()

    return body, date_str


def load_email_config():
    """
    优先用环境变量；如果不全，则从 config/email.yaml 读取。
    兼容 GitHub Actions + secrets。

    支持的 key：
        EMAIL_FROM
        EMAIL_TO
        EMAIL_PASSWORD
        EMAIL_SMTP_SERVER
        EMAIL_SMTP_PORT
    """
    cfg = {}

    # 1）先从环境变量读取
    for key in [
        "EMAIL_FROM",
        "EMAIL_TO",
        "EMAIL_PASSWORD",
        "EMAIL_SMTP_SERVER",
        "EMAIL_SMTP_PORT",
    ]:
        val = os.environ.get(key)
        if val:
            cfg[key] = val

    # 2）如果关键字段缺失，由 YAML 补全
    required_keys = ["EMAIL_FROM", "EMAIL_TO", "EMAIL_PASSWORD"]
    if not all(k in cfg for k in required_keys):
        if not os.path.exists(EMAIL_CONFIG_PATH):
            raise RuntimeError(
                "环境变量和 config/email.yaml 都不完整，无法发送邮件。"
            )
        with open(EMAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
        for k, v in y.items():
            if v is not None and k not in cfg:
                cfg[k] = str(v)

    # 再次检查必备项
    if not all(k in cfg for k in required_keys):
        raise RuntimeError(
            "EMAIL_FROM / EMAIL_TO / EMAIL_PASSWORD 未设置，请检查环境变量或 config/email.yaml。"
        )

    # 默认 SMTP 设置（Gmail）
    cfg.setdefault("EMAIL_SMTP_SERVER", "smtp.gmail.com")
    cfg.setdefault("EMAIL_SMTP_PORT", "587")

    return cfg


def send_email(subject: str, body: str):
    cfg = load_email_config()

    email_from = cfg["EMAIL_FROM"]
    email_to = cfg["EMAIL_TO"]
    smtp_server = cfg["EMAIL_SMTP_SERVER"]
    smtp_port = int(cfg["EMAIL_SMTP_PORT"])
    raw_pwd = str(cfg["EMAIL_PASSWORD"])
    # 去掉空格 / 换行，方便把 16 位 app password 分段写在 .env / yaml 里
    email_password = "".join(raw_pwd.split())

    # 🔍 关键检查：防止 EMAIL_FROM / EMAIL_PASSWORD 里有花括号引号、中文等非 ASCII 字符
    try:
        email_from.encode("ascii")
        email_password.encode("ascii")
    except UnicodeEncodeError:
        raise RuntimeError(
            "EMAIL_FROM 或 EMAIL_PASSWORD 含有非 ASCII 字符（比如中文、全角引号“”或空格）。\n"
            "请在 .env 或 config/email.yaml 里把它们改成只包含英文和数字。\n"
            f"当前 EMAIL_FROM={email_from!r}"
        )

    # 构造邮件内容（正文 UTF-8 即可）
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = Header(email_from, "utf-8")
    msg["To"] = Header(email_to, "utf-8")
    msg["Subject"] = Header(subject, "utf-8")

    # 发送邮件（Gmail: TLS + 587）
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(email_from, email_password)
        server.sendmail(email_from, [email_to], msg.as_string())
        print("邮件已发送至：", email_to)


def main():
    body, date_str = load_report()
    subject = f"美国大学校报中文日报 - {date_str}"
    send_email(subject, body)


if __name__ == "__main__":
    main()
