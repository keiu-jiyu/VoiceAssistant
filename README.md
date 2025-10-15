# 🎙️ Voice Assistant - 基于 LiveKit 的实时语音助手

## 📖 项目简介

这是一个基于 **LiveKit**、**阿里云 DashScope** 和 **React** 构建的实时语音助手系统。用户可以通过浏览器与 AI 进行自然语言对话，系统支持：

- ✅ **实时语音识别 (STT)**：阿里云 Paraformer 实时语音转文字
- ✅ **大语言模型对话 (LLM)**：阿里云通义千问 Qwen3-Max
- ✅ **语音合成 (TTS)**：阿里云 CosyVoice 高质量语音合成
- ✅ **低延迟实时通信**：LiveKit WebRTC 实时音视频传输
- ✅ **全异步架构**：基于 Python asyncio 和 React Hooks

---

## 🏗️ 系统架构

```
┌─────────────────┐         WebRTC          ┌─────────────────┐
│                 │  ◄──────────────────►   │                 │
│  React 前端     │      LiveKit Room       │  Python 后端    │
│  (浏览器)       │                          │  (AI Agent)     │
└─────────────────┘                          └─────────────────┘
                                                      │
                                                      ▼
                                            ┌──────────────────┐
                                            │  阿里云服务      │
                                            │  - STT (语音识别)│
                                            │  - LLM (对话模型)│
                                            │  - TTS (语音合成)│
                                            └──────────────────┘
```

### 数据流程

1. **用户说话** → 浏览器捕获麦克风音频 → LiveKit 传输到后端
2. **语音识别** → 后端实时识别音频 → 转换为文本
3. **AI 思考** → 文本发送给 LLM → 生成回复
4. **语音合成** → 回复文本转语音 → LiveKit 传回浏览器
5. **用户听到** → 浏览器播放 AI 语音

---

## 🚀 快速开始

### 1️⃣ 环境要求

- **Python**: 3.10+
- **Node.js**: 16+
- **LiveKit Server**: 参考 [官方文档](https://docs.livekit.io/realtime/self-hosting/local/)

### 2️⃣ 克隆项目

```bash
git clone https://github.com/你的用户名/voice-assistant.git
cd voice-assistant
```

### 3️⃣ 后端配置

#### 安装依赖

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 配置环境变量

创建 `.env` 文件：

```env
# LiveKit 配置
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# 阿里云 DashScope API Key
DASHSCOPE_API_KEY=your_dashscope_key
```

#### 启动后端

```bash
# 启动 FastAPI 服务器 (生成 Token)
python main.py

# 启动 AI Agent (在新终端)
python main.py agent
```

### 4️⃣ 前端配置

#### 安装依赖

```bash
cd frontend
npm install
```

#### 配置环境变量

创建 `.env` 文件：

```env
REACT_APP_LIVEKIT_URL=ws://localhost:7880
REACT_APP_BACKEND_URL=http://localhost:8000
```

#### 启动前端

```bash
npm start
```

访问 `http://localhost:3000` 即可使用！

---

## 📂 项目结构

```
voice-assistant/
├── backend/                    # Python 后端
│   ├── main.py                 # 主程序 (FastAPI + AI Agent)
│   ├── custom_aliyun_stt.py    # 自定义阿里云 STT
│   ├── requirements.txt        # 依赖列表
│   └── .env                    # 环境变量
│
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── App.jsx             # 主组件
│   │   ├── index.js            # 入口文件
│   │   └── index.css           # 样式
│   ├── package.json
│   └── .env
│
└── README.md                   # 项目文档
```

---

## 🔧 核心技术

### 后端技术栈

| 技术 | 用途 |
|------|------|
| **FastAPI** | Web 服务器 (Token 生成、健康检查) |
| **LiveKit Python SDK** | WebRTC 实时通信 |
| **aiohttp** | 异步 HTTP/WebSocket 客户端 |
| **阿里云 DashScope** | STT/LLM/TTS AI 服务 |
| **asyncio** | 异步任务调度 |

### 前端技术栈

| 技术 | 用途 |
|------|------|
| **React 18** | UI 框架 |
| **@livekit/components-react** | LiveKit React 组件 |
| **livekit-client** | WebRTC 客户端 |

---

## ⚙️ 关键实现

### 1. 自定义阿里云 STT (`custom_aliyun_stt.py`)

- **WebSocket 双工通信**：实时发送音频 + 接收识别结果
- **音频重采样**：48kHz → 16kHz (阿里云要求)
- **事件驱动**：支持中间结果 (`INTERIM_TRANSCRIPT`) 和最终结果 (`FINAL_TRANSCRIPT`)

### 2. AI Agent 核心逻辑 (`main.py`)

```python
class AIAssistant:
    async def process_participant_audio(self, participant):
        # 1. 音频流重采样 (48kHz → 16kHz)
        # 2. 推送到 STT 识别
        # 3. 识别结果触发 LLM 生成回复
        # 4. 回复流式推送到 TTS
        # 5. TTS 音频实时播放给用户
```

### 3. 前端音频管理 (`App.jsx`)

- **自动发布麦克风**：用户进入房间后自动启用麦克风
- **订阅远程音频**：监听 AI 的语音轨道并自动播放
- **手动 Audio 元素管理**：避免 React 18 严格模式导致的重复播放

---

## 🐛 常见问题

### 1. 麦克风权限被拒绝

**解决方案**：确保浏览器允许麦克风访问，使用 HTTPS 或 `localhost`。

### 2. 音频无法播放

**解决方案**：点击页面任意位置以允许自动播放（浏览器安全策略）。

### 3. STT 识别不准确

**解决方案**：检查音频采样率是否为 16kHz，环境噪音是否过大。

### 4. LiveKit 连接失败

**解决方案**：
- 检查 `.env` 配置是否正确
- 确认 LiveKit Server 是否启动 (`livekit-server --dev`)

---

## 📊 性能优化

- ✅ **异步任务分离**：STT/LLM/TTS 各自独立任务，避免阻塞
- ✅ **流式处理**：LLM 生成的文本逐句推送到 TTS，降低首字延迟
- ✅ **音频重采样**：使用 LiveKit 的 `AudioResampler` 高效转换采样率
- ✅ **资源管理**：正确关闭 WebSocket/HTTP Session，避免内存泄漏

---

## 🛠️ 开发计划

- [ ] 支持多用户同时对话
- [ ] 添加对话历史记录
- [ ] 支持打断 AI 说话
- [ ] 优化 TTS 音质和语速
- [ ] 添加情感分析和语气控制
- [ ] Docker 一键部署

---

## 📜 开源协议

本项目采用 **MIT License** 开源。

---

## 🙏 致谢

- [LiveKit](https://livekit.io/) - 实时音视频通信框架
- [阿里云 DashScope](https://dashscope.aliyun.com/) - AI 模型服务
- [React](https://react.dev/) - 前端框架

---

## 📧 联系方式

- **作者**: zhao,jiyu
- **Email**: jiyuzhao521@outlook.com
- **GitHub**: 

---

**⭐ 如果这个项目对你有帮助，欢迎 Star！**

---

这个 README 包含了：
- ✅ 项目简介和功能特性
- ✅ 系统架构图和数据流程
- ✅ 详细的安装步骤
- ✅ 技术栈说明
- ✅ 核心实现解析
- ✅ 常见问题排查
- ✅ 开发计划

你可以根据实际情况修改联系方式和 GitHub 链接！🎉
