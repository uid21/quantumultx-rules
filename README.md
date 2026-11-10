# Quantumult X rules

##一些 Vibe & 聚合 来的自用规则&重写

## B 站 PCDN

先添加基础版远程分流。在 Quantumult X 的「分流 → 资源」中填入下面地址，策略选 `reject`，资源解析器关闭，每天更新：

```text
https://raw.githubusercontent.com/uid21/quantumultx-rules/main/quantumultx/filter/bilibili-pcdn.list
```

直接编辑配置时，将这一行放在 `[filter_remote]` 下、B 站/国内直连资源之前：

```ini
https://raw.githubusercontent.com/uid21/quantumultx-rules/main/quantumultx/filter/bilibili-pcdn.list, tag=B站PCDN, force-policy=reject, update-interval=86400, opt-parser=false, enabled=true
```

无需 HTTPS 解密或证书。开启后重启 B 站 App，再用同一视频、同一清晰度比较首次加载和快进；在 QX 的网络活动里确认相关域名命中了 `reject`。若已有 B 站直连规则抢先命中，调整规则优先级；启用「分流匹配优化」时也要检查实际命中结果。

基础版包含 `*pcdn*.biliapi.net`、`mcdn.bilivideo.cn/com/net` 和 `szbdyd.com`。扩展版还拦截 MBGA 分类器识别的 302 跳转入口和第三方 PCDN 域名，包含全部基础规则：

```text
https://raw.githubusercontent.com/uid21/quantumultx-rules/main/quantumultx/filter/bilibili-pcdn-extended.list
```

先用基础版；仍命中未拦截 PCDN 时，再把资源 URL 换成扩展版。扩展版里的第三方 PCDN 域名可能也被其他 App 使用。若视频反而打不开或切源变慢，关闭这条资源即可回退。

规则靠客户端失败后换源来改善效果，不能保证每个网络都更快，也不会修复播放器清晰度越界、解码失败、过期签名或登录风控。纯 IP、HTTPDNS、已有连接可能绕过域名规则。它也不会让家中电视自动受益；电视流量要经过 QX 才能命中这些规则。

MBGA 的网页脚本还会读播放接口的全部候选地址、按签名类型选源，实验分支还包含并发分块下载；这些能力无法等价地装进域名拦截列表。

### 自动更新

GitHub Actions 每天 UTC 18:23（北京时间次日 02:23）读取上游；也可在 Actions → **Update Bilibili PCDN rules** → **Run workflow** 手动执行。QX 每 24 小时拉取一次已生成文件。

下载、结构、域名范围或正常 CDN 保护检查失败时，工作流报错并保留已发布文件。输出排序去重，日常无规则变化不提交。仓库的手工补充写在 [`sources/bilibili-pcdn-manual.json`](sources/bilibili-pcdn-manual.json)，不会被自动更新覆盖；生成文件不直接手改。

本地更新和测试只需 Python 3.10+，没有额外依赖：

```sh
python -m unittest discover -s tests -v
python scripts/update_bilibili_pcdn.py
```

如上游改成不兼容结构，需修改解析器后重新运行。[GitHub 会在公开仓库 60 天无活动时停用定时工作流](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。为此，工作流在规则无变化且距最近一次提交或保活已满 45 天时，才将当前 UTC 日期写入 `.github/bilibili-updater-heartbeat.txt` 并提交一次；近期已有更新时不会另加保活提交。保活文件不触发该工作流，不增加第三方 Action 或权限。

上游下载失败时仍可按需保活，但失败的规则更新不会提交，工作流仍显示失败。保活依赖定时工作流仍能执行；手动停用、仓库 Actions 被禁用或平台已停用的工作流无法自行启动，需要从 Actions 重新启用。

### Sources

- [SukkaW / Make Bilibili Great Than Ever Before](https://github.com/SukkaW/Make-Bilibili-Great-Than-Ever-Before/blob/master/src/core/player/cdn-classify.ts)：读取 PCDN 分类数据，保留 [MIT 许可证](licenses/MBGA-MIT.txt)。不执行下载到的 TypeScript，也不复制播放器实现。
- [uselibrary / PCDN](https://github.com/uselibrary/PCDN/blob/main/pcdn.list)：只导入 B 站有关的已审核域名和 PCDN 模式；不导入其他平台、整份去广告规则或全局关键词。保留 [GPLv3 许可证](licenses/PCDN-GPL-3.0.txt)。生成列表中的派生数据按 GPLv3 分发。
- [Quantumult X 官方配置示例](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)：`host-wildcard`、远程分流与更新间隔语法依据。

各来源 URL、抓取内容 SHA-256 及规则数量保存在 [`sources/bilibili-pcdn-lock.json`](sources/bilibili-pcdn-lock.json)，只有内容变化时才更新。

## Claude登录状态刷新

 `quantumultx/claude-ios-reset.conf` 为临时登录状态清理资源，按文件内说明使用。
