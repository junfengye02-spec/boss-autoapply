# BOSS 自动投递 · Codex Skill

告诉助手你的求职条件，让它负责筛选、去重、发起沟通和核验结果。用户不用配置脚本或敲命令。

## 使用

已安装技能后，在支持 Computer Use 的 Codex 中说：

> 用 $boss-apply 帮我投递 BOSS 岗位。

首次使用、尚未安装技能时，复制这一句话给 Codex：

> 从 https://github.com/junfengye02-spec/boss-autoapply 安装 skills/boss-apply 技能，然后用 $boss-apply 帮我投递 BOSS 岗位。

助手会补问你的背景、目标方向、城市、硬条件、投递数量和招呼方式；已提供的信息不用重复说。信息足够、自动投递获授权后，先验证一小批筛选结果，再继续投递。

**全新电脑的必要前提**：先有可用的 Codex 和浏览器控制能力，并由本人登录 BOSS。未安装的技能仅凭名字无法被自动发现，所以首次需要带上仓库链接。登录、验证码及系统要求的授权不能替用户凭空完成。除此之外，环境检测、配置和记录由助手处理。

## 不需要懂技术

- 先检查已连接 Chrome、IAB 内置浏览器及 Playwright 接口，再检查桌面 Computer Use；不因自定义 API 登录直接判定不可用。
- 没有 Python 或篡改猴：可使用可用的浏览器工具直接操作。
- IAB 已验证基础读取和填写，但 BOSS 搜索点击曾出现定位错误及页面闪烁，尚未验证稳定投递；会先做无发送探测，异常即停止。
- 已有脚本环境：使用附带浏览器脚本和本地 Python 服务加速。
- 缺少浏览器控制能力：助手说明所需能力，并保留已收集画像供继续。
- “立即沟通”会触发 BOSS 预设招呼，不重复发送自我介绍。
- 达到本轮数量、额度耗尽或出现未确认发送时停止；不绕过平台验证和限制。

## 隐私与记录

技能包不含个人简历、姓名、联系方式、求职偏好或历史投递记录。画像和台账保存在每个用户自己的独立数据目录，不上传到本仓库。每个账号持久去重，官网投递与 BOSS 沟通分别记录。

“成功沟通”不等于发送了附件简历；附件需要单独授权和核验。

## 实现与验证

[技能入口](skills/boss-apply/SKILL.md) · [首次启动](skills/boss-apply/references/startup.md) · [执行与恢复](skills/boss-apply/references/execution.md)

脚本模式只通过网页按钮发送，不调用 BOSS 私有接口。本地服务仅绑定 localhost，使用 Python 标准库，无 pip 依赖。Codex 负责按当次画像审核实际岗位，网页脚本执行已审核岗位的单次点击。

开发验证（普通用户无需执行）：

```sh
python3 skills/boss-apply/scripts/test_runner.py
python3 skills/boss-apply/scripts/doctor.py
node --check skills/boss-apply/scripts/goodJobs.user.js
```

已做离线测试；不同电脑和 BOSS 页面版本仍须首次小批量验证，不保证平台页面长期不变。
