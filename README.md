# notify-me

给自己推送通知的命令行小工具。发送消息到你的消息推送服务，支持 instant / bark 两种通道。

## 安装

推荐用 [pipx](https://pipx.pypa.io/)（或 `uv tool install`）安装，命令在任何 shell 里都可用：

```bash
# 从本目录安装
pipx install ./notify-me

# 或直接从 GitHub 仓库安装
pipx install git+https://github.com/lxvxl/notify-me.git

# 或发布到 PyPI 之后
pipx install notify-me

# 可选：启用 seal / setup 加密配置功能
pipx install "notify-me[crypto]"
```

没有 pipx 时也可以：

```bash
pip install --user ./notify-me      # 用户级安装
# 或者不安装直接跑
python -m notify_me 哈喽
```

升级与卸载：

```bash
pipx upgrade notify-me
pipx uninstall notify-me
```

## 配置

命令读取 `~/.notify-me/config.json`（可用环境变量 `NOTIFY_ME_CONFIG` 指向其他路径）。

### 交互式配置（推荐）

```bash
notify-me setup
```

向导会逐项提示：任意多个请求头（名称留空结束）、默认 channel（instant/bark）、默认 source、服务地址（回车取默认），写完后可选择立即发送一条测试通知。配置已存在时会先询问是否覆盖。

也可以从密封文件解锁：`notify-me setup 密封文件`（见下文）。

### 手工配置

最小配置：

```json
{
  "headers": { "Authorization": "Bearer <你的token>" },
  "channel": "instant",
  "source": "my-pc"
}
```

可选字段：`base_url`（默认 `https://rosmontis.cc`）、`device_id`、`device_name`、`user_agent`、`timeout`（秒，默认 10）。

`channel` 不做合法性校验：已知通道 `instant` / `bark` / `qq`，其中 `instant` 和 `qq` 的请求会携带 `source` 字段；其他任意值会原样传给服务端，方便以后扩展新通道。

### 环境变量

| 变量 | 作用 |
|---|---|
| `NOTIFY_ME_URL` | **优先级最高**，覆盖配置里的 `base_url` 和默认地址 |
| `NOTIFY_ME_CONFIG` | 指定配置文件路径，代替 `~/.notify-me/config.json` |

```bash
NOTIFY_ME_URL=http://192.168.1.10:8000 notify-me "内网测试"
```

### 密封配置（可选）

不想把 token 明文放在家里目录时，可以加密后再落地：

```bash
pipx install "notify-me[crypto]"
notify-me seal config.json config.sealed    # 设置口令，生成加密文件
notify-me setup config.sealed               # 输入口令，写出 config.json 并删除加密文件
```

## 使用

```bash
notify-me "构建完成"                        # send 是默认子命令
notify-me send -t "标题" "内容"
echo "长文本" | notify-me                   # 从 stdin 读入
notify-me send -c qq "推到 QQ 通道"          # 通道不做校验，任意值都能传
notify-me send -c bark "推到 bark 通道"
notify-me --version
```
