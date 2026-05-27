# 部署到 GitHub

当前项目已经发布到 GitHub 私有仓库：

<https://github.com/icekale/stock-fupan>

## 当前发布状态

- 仓库：`icekale/stock-fupan`
- 可见性：Private
- 分支：`main`
- 当前提交包含：
  - TickFlow-only 行情路径。
  - 参考 HTML 风格报告。
  - 每日报告命令 `make report DATE=YYYY-MM-DD`。
  - 次日强势概率与观察条件。
  - 同花顺/东方财富复盘源接入。
  - 自选股模块默认关闭。

## 本地提交与推送

```bash
git status
git add <files>
git commit -m "message"
git push
```

## 注意事项

不要提交：

- `apps/api/.env`
- `reports/`
- `apps/api/data/`
- API key、token、cookie、截图中的敏感信息

仓库已经通过 `.gitignore` 忽略上述常见本地文件。

## Docker Hub

当前暂不发布到 Docker Hub。

曾尝试推送：

```text
icekale/stock-fupan-api:0.3e
icekale/stock-fupan-api:latest
```

但 Docker Hub 返回 `insufficient_scope`，表示目标仓库不存在或当前 Docker Hub 账号没有写权限。

如果未来要继续 Docker Hub 发布，需要：

1. 在 Docker Hub 创建仓库 `icekale/stock-fupan-api`。
2. 本机执行 `docker login`。
3. 重新执行：

```bash
docker push icekale/stock-fupan-api:0.3e
docker push icekale/stock-fupan-api:latest
```
