from __future__ import annotations
import os
import json
import asyncio
import aiohttp
from typing import Optional
from livekit import rtc
from livekit.agents import stt, utils, APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS


class AliyunSTT(stt.STT):
    """阿里云 DashScope 实时语音识别"""

    def __init__(
            self,
            *,
            api_key: str,
            model: str = "paraformer-realtime-v2",
            language: str = "zh-CN",
    ):
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=True, interim_results=True)
        )
        self._running = False
        self._api_key = api_key
        self._model = model
        self._language = language
        self._session: Optional[aiohttp.ClientSession] = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        """确保 HTTP 会话存在"""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _recognize_impl(
            self,
            buffer: utils.AudioBuffer,
            *,
            language: str | None = None,
    ) -> stt.SpeechEvent:
        """实现非流式识别（必需方法）"""
        raise NotImplementedError("请使用 stream() 方法进行流式识别")

    def stream(
            self,
            *,
            language: str | None = None,
            conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> "AliyunSTTStream":
        print("📞 STT stream 方法被调用")
        """创建流式识别会话"""
        stream = AliyunSTTStream(
            stt=self,
            conn_options=conn_options,
            api_key=self._api_key,
            model=self._model,
            language=language or self._language,
        )
        print("✅ STT 流对象已创建，准备启动...")
        return stream

    async def aclose(self) -> None:
        """关闭资源"""
        if self._session:
            await self._session.close()


class AliyunSTTStream(stt.SpeechStream):
    """阿里云语音识别流"""

    def __init__(
            self,
            *,
            stt: AliyunSTT,
            conn_options: APIConnectOptions,
            api_key: str,
            model: str,
            language: str,
    ):
        super().__init__(stt=stt, conn_options=conn_options)
        print("🔧 初始化 AliyunSTTStream")
        self._running = False
        self._api_key = api_key
        self._model = model
        self._language = language
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._task_id = f"task-{utils.shortuuid()}"
        self._session = stt._ensure_session()
        self._task_started_event = asyncio.Event()  # 用于同步任务启动
        self._closed = False
        print("▶️ 准备启动 _run 协程")
        self._main_task = asyncio.create_task(self._run())
        print("✅ _run 协程已启动")

    async def _run(self) -> None:
        """运行识别流程"""
        if self._running:
            print("⚠️ _run 已在运行中，跳过重复启动")
            return

        self._running = True
        print("🚀 _run 方法被执行，开始连接阿里云 WebSocket...")

        # 修正 URL
        url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"

        # 添加查询参数
        import urllib.parse
        params = {
            "model": self._model,
            "api_key": self._api_key,
        }
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"

        print(f"🔗 连接URL: {full_url}")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }

        try:
            print("⏳ 正在建立 WebSocket 连接...")
            self._ws = await self._session.ws_connect(full_url, headers=headers)
            print("✅ WebSocket 连接成功！")
            print(f"📊 WebSocket 状态: closed={self._ws.closed}")

            # 并发处理:音频发送 + 结果接收
            await asyncio.gather(
                self._send_audio_task(),
                self._receive_task(),
                return_exceptions=True
            )

        except Exception as e:
            print(f"❌ STT 错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._running = False
            if self._ws and not self._ws.closed:
                await self._ws.close()
            self._ws = None
            print("🔚 _run 方法结束")

    async def _send_audio_task(self) -> None:
        """发送音频数据"""
        try:
            # 生成任务ID
            import uuid
            task_id = str(uuid.uuid4())
            print(f"🆔 生成任务ID: {task_id}")

            # 发送 run-task 指令
            run_task_msg = {
                "header": {
                    "action": "run-task",
                    "task_id": task_id,
                    "streaming": "duplex"
                },
                "payload": {
                    "task_group": "audio",
                    "task": "asr",
                    "function": "recognition",
                    "model": "paraformer-realtime-v2",
                    "parameters": {
                        "format": "pcm",
                        "sample_rate": 16000,
                        "disfluency_removal_enabled": False,
                        "language_hints": ["zh"],
                        "semantic_punctuation_enabled": False,
                        "max_sentence_silence": 800,
                        "punctuation_prediction_enabled": True,
                        "inverse_text_normalization_enabled": True
                    },
                    "input": {}
                }
            }

            print(f"📤 发送 run-task 指令")
            await self._ws.send_str(json.dumps(run_task_msg))

            # 等待 task-started 事件 (由 _receive_task 设置)
            print("⏳ 等待任务启动...")
            try:
                await asyncio.wait_for(self._task_started_event.wait(), timeout=10.0)
                print("✅ 任务已启动，开始发送音频数据")
            except asyncio.TimeoutError:
                print("❌ 等待任务启动超时")
                return

            # 从父类的输入队列读取音频帧
            print("🎤 开始发送音频数据...")
            async for frame in self._input_ch:
                if self._closed:
                    print("🛑 流已关闭，停止发送音频")
                    break

                if frame is None:  # 结束信号
                    print("🛑 收到结束信号")
                    break

                # 发送二进制音频数据
                if not self._ws.closed:
                    # 转换音频帧为字节
                    audio_bytes = frame.data.tobytes()
                    await self._ws.send_bytes(audio_bytes)
                    #if len(audio_bytes) > 0:
                        #print(f"📤 发送音频帧: {len(audio_bytes)} 字节")
                else:
                    print("⚠️ WebSocket 已关闭，无法发送音频")
                    break

            # 发送 finish-task 指令
            if not self._ws.closed:
                finish_task_msg = {
                    "header": {
                        "action": "finish-task",
                        "task_id": task_id,
                        "streaming": "duplex"
                    },
                    "payload": {
                        "input": {}
                    }
                }
                print(f"📤 发送 finish-task 指令")
                await self._ws.send_str(json.dumps(finish_task_msg))

        except asyncio.CancelledError:
            print("⚠️ 音频发送任务被取消")
            raise
        except Exception as e:
            print(f"❌ 音频发送任务错误: {e}")
            import traceback
            traceback.print_exc()

    async def _receive_task(self) -> None:
        """接收识别结果"""
        print("👂 开始结果接收任务...")
        try:
            if not self._ws:
                print("⚠️ WebSocket 未初始化")
                return

            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    print(f"📥 收到识别结果: {json.dumps(data, ensure_ascii=False, indent=2)}")

                    # 处理不同的事件类型
                    header = data.get("header", {})
                    event = header.get("event")

                    if event == "task-started":
                        print("✅ 任务已开始")
                        self._task_started_event.set()  # 通知发送任务可以开始

                    elif event == "result-generated":
                        payload = data.get("payload", {})
                        output = payload.get("output", {})

                        # 处理识别结果
                        if "sentence" in output:
                            sentence = output["sentence"]
                            text = sentence.get("text", "").strip()
                            sentence_end = sentence.get("sentence_end", False)

                            if text and not sentence.get("heartbeat", False):
                                print(f"🎯 识别到文本: '{text}' (句子结束: {sentence_end})")

                                # 发送识别事件
                                speech_event = stt.SpeechEvent(
                                    type=stt.SpeechEventType.FINAL_TRANSCRIPT if sentence_end else stt.SpeechEventType.INTERIM_TRANSCRIPT,
                                    alternatives=[
                                        stt.SpeechData(
                                            language=self._language,
                                            text=text,
                                            confidence=0.9,
                                        )
                                    ],
                                )
                                self._event_ch.send_nowait(speech_event)

                    elif event == "task-finished":
                        print("✅ 任务已完成")
                        break

                    elif event == "task-failed":
                        error_code = header.get("error_code")
                        error_message = header.get("error_message")
                        print(f"❌ 任务失败: {error_code} - {error_message}")
                        break

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"❌ WebSocket 错误: {msg.data}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    print("🔌 WebSocket 连接已关闭")
                    break

        except asyncio.CancelledError:
            print("⚠️ 结果接收任务被取消")
            raise
        except Exception as e:
            print(f"❌ 结果接收错误: {e}")
            import traceback
            traceback.print_exc()

    async def aclose(self) -> None:
        """关闭流"""
        print("🛑 调用 aclose，准备关闭连接...")
        self._closed = True

        # 发送结束信号到输入队列
        try:
            await self._input_ch.send(None)
        except Exception as e:
            print(f"⚠️ 发送结束信号失败: {e}")

        # 取消主任务
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                print("✅ 主任务已取消")

        if self._ws and not self._ws.closed:
            await self._ws.close()
            print("✅ WebSocket 已关闭")

        self._event_ch.close()
        print("✅ AliyunSTTStream 已完全关闭")
