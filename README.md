# Wishclaim · 礼物愿望认领

发布 → 认领锁定（互斥+TTL）→ 核销/释放。

| 服务 | 端口 |
| --- | --- |
| 前端 | 5200 |
| API | 10200 |

```bash
docker compose up --build
pytest backend/app/tests
```

## 附言确认链路（note ack）

- **未认领**改附言：直接生效（rev+1），不走确认。
- **已认领**改附言：rev+1 并置 `awaiting_ack`，期间 `fulfill` 被门禁拦截（409 `note_awaiting_ack`）；认领人 `ack` 后清除标记。
- 详情 / 我的认领 / 墙卡三路同钉当前 rev 与正文（统一走 `note_projection`）；ack 前详情可回看上一版。
- **拍板①**：`awaiting_ack` 期间再次修改 → **rev 递增**，旧待确认版记 `superseded`，ack 永远针对最新 rev，超时计时从最新修改重算。
- **拍板②**：超过 `settings.ack_timeout_seconds` 未 ack → **自动驳回回上一版**（最近 live 版），扫尾后三路投影与按钮态同步恢复，`fulfill` 解禁。
- 补充：fulfilled 愿望附言冻结；认领释放/TTL 不清 pending（新认领人可 ack，否则超时驳回）。

模块划分（`backend/app/engines/`）：

| 模块 | 职责 |
| --- | --- |
| `note_revision.py` | 修订：rev 递增、live/pending/superseded/rejected 状态迁移计划 |
| `note_gate.py` | ack/超时门禁：edit_mode、fulfill/ack 许可、timeout_due |
| `note_projection.py` | 投影：三路统一的 rev+正文与按钮态派生 |

0-1：`wish_comment` / `secret_santa` / `price_cap`。
