# CM Invoice Tracking

CM Invoice Tracking 是一个基于 Django 3.2 + django-admin + Jazzmin 的轻量级系统，用于管理客户工单与四步流程。

## 环境与依赖

- Python 3.8.x
- Django 3.2.x
- django-jazzmin 2.x
- SQLite（默认）/ SQL Server（生产预留）

安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 初始化项目

```bash
cd cm_invoice_tracking
python manage.py migrate
python manage.py createsuperuser
```

本仓库已包含初始迁移文件（invoice/migrations/0001_initial.py），因此无需再执行 makemigrations，直接 migrate 即可。

启动：

```bash
python manage.py runserver
```

管理后台地址：

```
http://127.0.0.1:8000/admin/
```

## 基本配置流程

1. 使用管理员账户登录后台。
2. 在 `System settings` 中创建一条记录，配置 `auto_generation_enabled`。
3. 创建 Customer 与对应的 4 条 CustomerStepRule（Step 1-4）。
4. 打开 Dashboard 页面，点击“批量生成当月”或“批量创建下月”来生成 Work 与 WorkStep。

说明：Work 使用 `work_year` 与 `work_month` 两个数字字段。

Dashboard 地址：

```
/admin/invoice/dashboard/
```

## 自动生成（定时任务）

使用管理命令（支持自动触发）：

```bash
python manage.py generate_work --auto
```

建议使用 cron 或 Windows Task Scheduler 定时执行该命令。命令会在当月倒数第 7 天自动生成下月 Work（前提是 SystemSetting 中开启了 auto_generation_enabled）。

## 数据库切换（SQL Server）

默认使用 SQLite。通过环境变量切换到 SQL Server：

```bash
export DB_ENGINE=sqlserver
export DB_NAME=cm_invoice
export DB_USER=sa
export DB_PASSWORD=your_password
export DB_HOST=your_sqlserver_host
export DB_PORT=1433
export DB_DRIVER="ODBC Driver 17 for SQL Server"
```

然后正常执行 migrate 即可。
