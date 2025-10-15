import os
import asyncio
from dotenv import load_dotenv
import logging
import sys
import aiohttp
import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from livekit import api, rtc
from livekit.agents.llm import ChatContext
from livekit.agents.stt import SpeechEventType
from livekit.plugins import aliyun
from custom_aliyun_stt import AliyunSTT
# --- 配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

# --- LiveKit 配置 ---
LIVEKIT_URL = os.environ.get("LIVEKIT_URL")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET")
ROOM_NAME = "my-voice-room"
AGENT_IDENTITY = "ai-assistant"

# --- 阿里云配置 ---
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")

# --- 检查环境变量 ---
required_vars = [
    "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "DASHSCOPE_API_KEY"
]
for var in required_vars:
    if not os.environ.get(var):
        raise ValueError(f"环境变量 '{var}' 未设置")

# --- 全局变量 ---
active_rooms = {}


# --- AI 助手核心逻辑 ---
class AIAssistant:
    def __init__(self):
        self.room = None
        self.audio_source = None
        self.stt = None
        self.llm = None
        self.tts = None
        self.http_session = None

    async def initialize(self):
        """初始化AI组件"""
        self.http_session = aiohttp.ClientSession()
        self.stt = AliyunSTT(
            api_key=DASHSCOPE_API_KEY,
            model='paraformer-realtime-v2',
            language='zh-CN'
        )
        self.llm = aliyun.LLM(model="qwen3-max", api_key=DASHSCOPE_API_KEY)
        self.tts = aliyun.TTS(
            model='cosyvoice-v1',  # ← 使用官方推荐模型
            voice='longxiaochun',  # 可选：音色
            http_session=self.http_session
        )

    async def connect_to_room(self):
        """连接到LiveKit房间"""
        token = (
            api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(AGENT_IDENTITY)
            .with_name("AI Assistant")
            .with_grants(api.VideoGrants(
                room_join=True,
                room=ROOM_NAME,
                can_publish=True,
                can_publish_data=True,
                agent=True,
            ))
        ).to_jwt()

        self.room = rtc.Room()
        await self.room.connect(LIVEKIT_URL, token)
        logging.info(f"✅ AI 已连接到房间: {ROOM_NAME}")

        # 创建并发布音频轨道
        self.audio_source = rtc.AudioSource(
            self.tts.sample_rate,
            self.tts.num_channels
        )
        track = rtc.LocalAudioTrack.create_audio_track(
            "ai-voice",
            self.audio_source
        )
        publication = await self.room.local_participant.publish_track(track)
        logging.info(f"🎤 AI 语音轨道已发布: {publication.sid}")

    async def process_participant_audio(self, participant: rtc.Participant):
        """处理参与者的音频流"""
        if participant.identity == AGENT_IDENTITY:
            return

        # 查找音频轨道
        audio_stream = None
        for pub in participant.track_publications.values():
            if (pub.track and
                    pub.kind == rtc.TrackKind.KIND_AUDIO and
                    pub.source == rtc.TrackSource.SOURCE_MICROPHONE):
                audio_stream = rtc.AudioStream(pub.track)
                break

        if not audio_stream:
            logging.warning(f"未找到用户 {participant.identity} 的麦克风轨道")
            return

        logging.info(f"🎧 开始监听用户: {participant.identity}")
        stt_stream = self.stt.stream()
        logging.info("✅ STT 流已创建")
        chat_context = ChatContext()

        async def feed_stt(audio_stream, stt_stream):
            """从音频流读取数据并发送到 STT"""
            try:
                # 创建重采样器：48000Hz → 16000Hz
                resampler = rtc.AudioResampler(
                    input_rate=48000,
                    output_rate=16000,
                    num_channels=1,
                    quality=rtc.AudioResamplerQuality.QUICK
                )

                frame_count = 0
                resampled_count = 0

                logging.info("🔄 开始音频重采样流程")

                async for frame_event in audio_stream:
                    frame = frame_event.frame
                    frame_count += 1

                    if frame_count == 1:
                        logging.info(
                            f"🎵 首帧音频: sample_rate={frame.sample_rate}, channels={frame.num_channels}, samples={frame.samples_per_channel}")

                    # 打印原始音频数据
                    if frame_count % 100 == 0:
                        logging.info(f"📡 已接收 {frame_count} 个原始帧 (48000Hz)")

                    # 推送原始帧到重采样器，并立即处理输出
                    for resampled_frame in resampler.push(frame):
                        resampled_count += 1

                        # 打印重采样后的数据
                        #if resampled_count % 10 == 0:
                            #logging.info(f"🔄 已生成 {resampled_count} 个重采样帧 (16000Hz)")

                        # 推送到 STT
                        stt_stream.push_frame(resampled_frame)

                        if resampled_count % 50 == 0:
                            logging.info(f"✅ 已推送 {resampled_count} 个帧到 STT")

                # 🔥 重要：刷新重采样器，获取剩余数据
                logging.info("🔄 刷新重采样器，获取剩余音频...")
                for resampled_frame in resampler.flush():
                    resampled_count += 1
                    stt_stream.push_frame(resampled_frame)

                logging.info(f"✅ 音频流处理完成: 原始帧={frame_count}, 重采样帧={resampled_count}")

            except Exception as e:
                logging.error(f"❌ 音频流处理错误: {e}")
            finally:
                await stt_stream.aclose()

        async def handle_stt():
            """处理STT结果并生成回复"""
            logging.info("🎯 STT 事件监听器已启动")
            try:
                async for event in stt_stream:
                    logging.info(f"📝 STT事件: type={event.type}")
                    if event.alternatives:
                        logging.info(f"   文本: '{event.alternatives[0].text}'")

                    if (event.type == SpeechEventType.FINAL_TRANSCRIPT and
                            event.alternatives):
                        user_text = event.alternatives[0].text.strip()
                        if not user_text:
                            logging.warning("识别结果为空，跳过")
                            continue

                        logging.info(f"💬 用户 ({participant.identity}) 说: '{user_text}'")
                        chat_context.add_message(role="user", content=user_text)

                        logging.info("🧠 AI 正在思考...")
                        full_response = ""

                        try:
                            # 🔧 修复：使用独立任务处理 TTS，避免阻塞 STT
                            async def process_llm_and_tts():
                                nonlocal full_response
                                tts_stream = self.tts.stream()

                                llm_stream = self.llm.chat(chat_ctx=chat_context)
                                async for chunk in llm_stream:
                                    if chunk.delta and chunk.delta.content:
                                        content = chunk.delta.content
                                        tts_stream.push_text(content)
                                        full_response += content

                                tts_stream.flush()
                                chat_context.add_message(role="assistant", content=full_response)
                                logging.info(f"🤖 AI 回答: '{full_response}'")

                                # 播放 TTS 音频
                                logging.info("🔊 开始播放 TTS 音频")
                                frame_count = 0
                                async for audio_chunk in tts_stream:
                                    try:
                                        if hasattr(audio_chunk, 'frame'):
                                            await self.audio_source.capture_frame(audio_chunk.frame)
                                            frame_count += 1
                                        elif audio_chunk:
                                            await self.audio_source.capture_frame(audio_chunk)
                                            frame_count += 1
                                    except Exception as e:
                                        logging.error(f"播放音频帧失败: {e}")

                                logging.info(f"✅ TTS 音频播放完成，共播放 {frame_count} 帧")

                                # 🔧 关键：确保 TTS 流正确关闭
                                await tts_stream.aclose()

                            # 创建独立任务，避免阻塞 STT 事件循环
                            asyncio.create_task(process_llm_and_tts())

                        except Exception as e:
                            logging.error(f"LLM/TTS 处理错误: {e}", exc_info=True)

            except Exception as e:
                logging.error(f"STT 处理错误: {e}", exc_info=True)

        # 并行处理音频流和STT
        await asyncio.gather(
            feed_stt(audio_stream, stt_stream),
            handle_stt(),
            return_exceptions=True
        )

    async def start(self):
        """启动AI助手"""
        try:
            await self.initialize()
            await self.connect_to_room()

            # 监听轨道订阅事件（这是关键！）
            @self.room.on("track_subscribed")
            def on_track_subscribed(
                    track: rtc.Track,
                    publication: rtc.RemoteTrackPublication,
                    participant: rtc.RemoteParticipant
            ):
                logging.info(
                    f"🔔 订阅轨道: {participant.identity} - Source:{publication.source} Kind:{publication.kind}")

                # 只在这里处理麦克风音频
                if (publication.kind == rtc.TrackKind.KIND_AUDIO and
                        publication.source == rtc.TrackSource.SOURCE_MICROPHONE):
                    logging.info(f"🎤 检测到麦克风轨道，开始处理用户: {participant.identity}")
                    asyncio.create_task(self.process_participant_audio(participant))

            # 监听新参与者（仅用于日志）
            @self.room.on("participant_connected")
            def on_participant_connected(participant: rtc.RemoteParticipant):
                logging.info(f"👤 新用户加入: {participant.identity}")

            for participant in self.room.remote_participants.values():
                for pub in participant.track_publications.values():
                    if (pub.kind == rtc.TrackKind.KIND_AUDIO and
                            pub.source == rtc.TrackSource.SOURCE_MICROPHONE):
                                pub.set_subscribed(True)  # ← 改成 12 个空格（3层缩进 × 4空格）

            logging.info("✨ AI Agent 准备就绪")
            await asyncio.Event().wait()

        except Exception as e:
            logging.error(f"AI助手运行错误: {e}")
        finally:
            await self.cleanup()

    async def cleanup(self):
        """清理资源"""
        if self.http_session:
            await self.http_session.close()
        if self.room:
            await self.room.disconnect()
        logging.info("🚪 AI 助手已关闭")


async def ai_assistant_task():
    """启动AI助手任务"""
    assistant = AIAssistant()
    await assistant.start()


# --- FastAPI Web 服务器 ---
app = FastAPI(title="语音助手API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.get("/")
async def root():
    return {"message": "语音助手API服务运行中"}


@app.get("/token")  # ← 改这里：post → get，路径改为 /token
async def create_token_endpoint():
    """为用户生成加入房间的token"""
    identity = f"user-{int(asyncio.get_event_loop().time())}"
    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(
            room_join=True,
            room=ROOM_NAME,
            can_publish=True,
            can_subscribe=True
        ))
    ).to_jwt()
    return {"token": token, "identity": identity}


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "voice-assistant"}


# --- 主程序入口 ---
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'agent':
        logging.info("启动模式: AI Agent")
        try:
            asyncio.run(ai_assistant_task())
        except KeyboardInterrupt:
            logging.info("AI Agent 被手动停止")
    else:
        logging.info("启动模式: FastAPI Server")
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )