# OpenClaw 科研助手 🦐

**一键安装、开箱即用的本地科研 AI 助手**

> 打造属于你自己的科研小龙虾

---

## ✨ 功能特性

- 🚀 **一键安装** — 双击 `start.sh` / `start.bat` 完成全部依赖安装和启动
- 🧙 **安装向导** — 浏览器内完成 API Key 配置、技能和智能体预选
- 💬 **智能对话** — 基于用户提供的大模型 API，支持流式输出
- ⚡ **技能管理** — 网页端直接添加/编辑/删除技能，支持参数配置
- 🤖 **智能体配置** — 创建和管理多个专业智能体，自定义系统提示词和关联技能
- ⚙️ **配置中心** — 随时修改 API Key、模型、温度等参数
- 🔌 **多模型支持** — OpenAI、Anthropic Claude、Ollama（本地）、任意 OpenAI 兼容 API

---

## 🚀 快速开始

### 前提条件

- Python 3.9+
- 网络连接（安装依赖）
- 至少一个大模型 API Key（OpenAI、Claude 等）

### 一键启动

**Linux / macOS:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```cmd
双击 start.bat
```

启动后浏览器会自动打开安装向导（`http://localhost:8765`），配置完成后自动跳转到主界面（`http://localhost:8000`）。

### 已有配置时直接启动

```bash
python install.py --skip    # 跳过安装向导，直接启动
```

---

## 📁 项目结构

```
openclaw-research-assistant/
├── install.py          # 一键安装脚本（含安装向导服务器）
├── start.sh            # Linux/macOS 启动脚本
├── start.bat           # Windows 启动脚本
├── requirements.txt    # Python 依赖
│
├── backend/            # FastAPI 后端
│   ├── app.py          # 主应用入口
│   ├── config_manager.py  # 配置管理
│   ├── models.py       # Pydantic 数据模型
│   └── routers/        # API 路由
│       ├── chat.py     # 对话接口（支持流式）
│       ├── config.py   # 配置接口
│       ├── skills.py   # 技能 CRUD
│       └── agents.py   # 智能体 CRUD
│
├── frontend/           # 前端页面（纯 HTML+JS）
│   ├── index.html      # 主界面（对话、配置、技能、智能体）
│   └── installer.html  # 安装向导界面
│
└── config/             # 运行时配置（首次启动后生成）
    ├── openclaw.yaml   # 主配置（API Key 等）
    ├── skills.yaml     # 技能配置
    └── agents.yaml     # 智能体配置
```

---

## 🔧 Web 界面功能

安装完成后，访问 `http://localhost:8000` 即可使用：

### 💬 对话面板
- 选择智能体和模型后开始对话
- 支持流式输出（实时显示回复）
- 快捷问题按钮，一键开始常用对话

### ⚙️ 配置面板
- 随时更换 API Key 和模型
- 支持 OpenAI、Anthropic、本地模型（Ollama/LM Studio）
- 一键测试连接

### ⚡ 技能面板
- 查看所有技能及其参数
- **添加技能** — 填写 ID、名称、描述、参数键值对
- **导入技能文档** — 支持粘贴 frontmatter + Markdown 的完整技能定义（如 weather/wttr.in 示例）
- **编辑技能** — 修改名称、描述和参数
- **启用/禁用** — 一键切换技能状态
- **删除技能** — 移除不需要的技能
- **智能体可用** — 智能体关联并启用后，会在对话系统提示中自动注入技能说明

### 🤖 智能体面板
- 创建多个专业智能体（如：论文写作助手、数据分析助手）
- 配置系统提示词、专用模型、Temperature
- 关联技能模块，扩展智能体能力

---

## 🌐 支持的模型提供商

| 提供商 | API Base URL | 备注 |
|--------|-------------|------|
| OpenAI | (默认) | GPT-4o、GPT-3.5 等 |
| Anthropic | (自动) | Claude 3.5、Claude 3 等 |
| Ollama | `http://localhost:11434/v1` | 本地模型 |
| LM Studio | `http://localhost:1234/v1` | 本地模型 |
| 其他 | 自定义 URL | 任意 OpenAI 兼容 API |

---

## 📝 开发者 API

后端提供完整的 REST API：

```
GET    /api/skills/              # 获取所有技能
POST   /api/skills/              # 创建技能
PUT    /api/skills/{id}          # 更新技能
DELETE /api/skills/{id}          # 删除技能

GET    /api/agents/              # 获取所有智能体
POST   /api/agents/              # 创建智能体
PUT    /api/agents/{id}          # 更新智能体
DELETE /api/agents/{id}          # 删除智能体

GET    /api/config/              # 获取配置
PUT    /api/config/              # 更新配置
POST   /api/config/test-connection  # 测试 API 连接

POST   /api/chat/                # 发送对话消息（支持 SSE 流式）
GET    /api/chat/models          # 获取可用模型列表
```

---

## 🔒 安全提示

- API Key 存储在本地 `config/openclaw.yaml`，仅在本机可访问
- 默认服务器绑定 `127.0.0.1`，仅本地可访问
- 如需局域网共享，在 `config/openclaw.yaml` 中修改 `host` 为 `0.0.0.0`

---

## 📄 许可证

MIT License
